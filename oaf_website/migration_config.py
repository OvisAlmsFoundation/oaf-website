"""Separate fixed migration identities. Importing this module accesses no secrets.

There is no local migration settings file or URL override. The registry is the
entire nonsecret configuration authority. The existing runtime loader is intact.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
import os
from types import MappingProxyType

from sqlalchemy.engine import URL

from .database_config import _windows_password, WINDOWS_BACKEND


@dataclass(frozen=True)
class MigrationIdentity:
    environment: str
    database: str
    migrator: str
    owner: str
    runtime: str
    credential_service: str
    schema: str = "oaf_website"
    host: str = "127.0.0.1"
    port: int = 5432
    postgres_major: int = 17


IDENTITIES = MappingProxyType({
    "development": MigrationIdentity(
        "development", "oaf_website_dev", "oaf_website_dev_migrator",
        "oaf_website_dev_schema_owner", "oaf_website_app",
        "OAF Website/development/PostgreSQL/Migrations",
    ),
    "testing": MigrationIdentity(
        "testing", "oaf_website_test", "oaf_website_test_migrator",
        "oaf_website_test_schema_owner", "oaf_website_test_app",
        "OAF Website/testing/PostgreSQL/Migrations",
    ),
})


class Failure:
    INVALID_CONFIGURATION = "invalid_configuration"
    CREDENTIAL_UNAVAILABLE = "credential_unavailable"
    WRONG_IDENTITY = "wrong_database_or_identity"
    UNAUTHORIZED_MEMBERSHIP = "unauthorized_role_membership"
    SCHEMA_OWNERSHIP = "unexpected_schema_ownership"
    STARTING_REVISION = "incorrect_starting_revision"
    ARTIFACT_HASH = "invalid_artifact_hash"
    DRIFT = "drift_detected"
    LOCK_BUSY = "lock_busy"
    TRANSACTION = "transaction_failure"
    STATEMENT_TIMEOUT = "statement_timeout"
    DEADLOCK = "deadlock"
    UNCERTAIN_COMMIT = "uncertain_commit_outcome"
    POSTCOMMIT = "postcommit_verification_failure"
    AUDIT = "audit_finalization_failure"
    AUDIT_WRITE = "audit_write_failure"
    OPERATIONAL_GATE = "operational_prerequisites_unresolved"
    INTERRUPTED = "operator_interruption"
    SERIALIZATION = "serialization_failure"
    CONNECTION = "connection_failure"
    DATABASE = "migration_database_failure"


_FAILURES = frozenset(v for k, v in vars(Failure).items() if k.isupper())


class MigrationError(RuntimeError):
    """Only a registered classification, never provider/SQL text or input values."""

    def __init__(self, classification: str):
        self.classification = (
            classification if classification in _FAILURES else Failure.TRANSACTION
        )
        self.run_id = None
        self.commit_certainty = "not_invoked"
        self.secondary_failure = None
        self.operational_result = None
        super().__init__(self.classification)


def database_failure(error, *, committing=False):
    """Fixed SQLSTATE categories shared by env and runner; never render errors.

    Only the listed server transaction-rejection responses establish certainty
    during commit. Transport loss, cancellation by the operator, and unknown
    errors during invocation require reconciliation, never automatic retry.
    """
    if isinstance(error, MigrationError):
        return Failure.UNCERTAIN_COMMIT if committing else error.classification
    original = getattr(error, "orig", error)
    code = getattr(original, "sqlstate", None)
    rejected = {
        "40001": Failure.SERIALIZATION, "40P01": Failure.DEADLOCK,
        "57014": Failure.STATEMENT_TIMEOUT, "55P03": Failure.LOCK_BUSY,
    }
    if committing:
        # Only these transaction-rollback responses are treated as confirmed
        # rejection. Other responses retain their category in runner evidence
        # but require conservative commit reconciliation.
        return rejected[code] if code in {"40001", "40P01"} else Failure.UNCERTAIN_COMMIT
    if code in rejected:
        return rejected[code]
    if isinstance(code, str) and (code.startswith("08") or code in {"57P01", "57P02", "57P03"}):
        return Failure.CONNECTION
    return Failure.DATABASE if isinstance(code, str) and len(code) == 5 else Failure.TRANSACTION


def select_identity(
    environment: str, *, environ: Mapping[str, str] | None = None,
    settings: Mapping[str, object] | None = None,
) -> MigrationIdentity:
    """Pure validation; production and every unknown key fail before credentials."""
    source = os.environ if environ is None else environ
    if environment not in IDENTITIES or source.get("OAF_ENV") != environment:
        raise MigrationError(Failure.INVALID_CONFIGURATION)
    if settings is not None and (not isinstance(settings, Mapping) or settings):
        raise MigrationError(Failure.INVALID_CONFIGURATION)
    for key in source:
        name = key.upper()
        if (
            (name.startswith("OAF_") and name != "OAF_ENV")
            or name.startswith(("PG", "DB_", "DATABASE_"))
            or name in {"DATABASE_URL", "SQLALCHEMY_DATABASE_URI", "SQLALCHEMY_URL"}
            or "KEYRING_PROPERTY_" in name
        ):
            raise MigrationError(Failure.INVALID_CONFIGURATION)
    if source.get("PYTHON_KEYRING_BACKEND", WINDOWS_BACKEND) != WINDOWS_BACKEND:
        raise MigrationError(Failure.INVALID_CONFIGURATION)
    return IDENTITIES[environment]


@dataclass(frozen=True)
class MigrationConfig:
    identity: MigrationIdentity
    url: URL = field(repr=False)

    def __post_init__(self):
        i = self.identity
        if i != IDENTITIES.get(i.environment) or (
            not isinstance(self.url, URL)
            or self.url.drivername != "postgresql+psycopg"
            or self.url.host != i.host or self.url.port != i.port
            or type(self.url.port) is not int
            or self.url.database != i.database or self.url.username != i.migrator
            or self.url.query or not isinstance(self.url.password, str)
            or not self.url.password
        ):
            raise MigrationError(Failure.INVALID_CONFIGURATION)


def load_migration_config(
    *, environment: str, environ: Mapping[str, str] | None = None,
    settings: Mapping[str, object] | None = None,
) -> MigrationConfig:
    """Explicit later execution only. Retrieve exactly the selected credential.

    _windows_password binds WinVaultKeyring directly and requires the exact
    Stage 4C service target/account, generic type and machine-local persistence.
    It does not discover backends, write secrets, or open a connection.
    Offline tests can patch that adapter; production has no alternate provider.
    """
    source = dict(os.environ if environ is None else environ)
    identity = select_identity(environment, environ=source, settings=settings)
    try:
        password = _windows_password(
            identity.credential_service, identity.migrator, source, exact_target=True,
        )
    except Exception:
        raise MigrationError(Failure.CREDENTIAL_UNAVAILABLE) from None
    if not isinstance(password, str) or not password:
        raise MigrationError(Failure.CREDENTIAL_UNAVAILABLE)
    return MigrationConfig(identity, URL.create(
        "postgresql+psycopg", username=identity.migrator, password=password,
        host=identity.host, port=identity.port, database=identity.database,
    ))
