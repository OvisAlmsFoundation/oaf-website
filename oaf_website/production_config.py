"""Fixed production metadata and protected file injection; no I/O on import.

Render secret files are provisioned separately for each service. No URL, path,
account, credential backend or development fallback can be selected by environment.
"""

from dataclasses import dataclass
import os
from pathlib import Path
import re
import stat
import tomllib

from .database_config import DatabaseConfigurationError, _validate_environment
from .notification_dispatch import diagnostic_error

PUBLIC_ORIGIN = "https://ovisalmsfoundation.org"
DATABASE = "oaf_website_prod"
RUNTIME_ROLE = "oaf_website_prod_app"
MIGRATOR_ROLE = "oaf_website_prod_migrator"
SCHEMA_OWNER = MIGRATOR_ROLE
SECRETS_DIR = Path("/etc/secrets")
POSIX = os.name == "posix"
# Render internal certificates are self-signed. Require encryption on both paths;
# require mode does not independently authenticate the server's identity.
TLS_QUERY = {"sslmode": "require", "ssl_min_protocol_version": "TLSv1.2", "sslsni": "1"}
SECRET_FILES = frozenset({"recognition-key", "runtime-db-password", "smtp-password",
                         "brevo-api-key", "webhook-token", "integration-submission",
                         "integration-reporting", "integration-release"})
FLAGS = frozenset({"confirmation_enabled", "management_enabled", "integrations_enabled",
                   "releases_enabled", "webhook_enabled", "processing_enabled"})


def reject(predicate):
    return diagnostic_error(DatabaseConfigurationError("Production configuration unavailable."),
                            "configuration", predicate, stage="startup")


def valid_database_host(value, *, internal=False):
    # Fixed owner-provisioned metadata selects the exact endpoint. Web/Cron use
    # Render's private single-label hostname; Windows needs full DNS for SNI.
    if internal:
        return (type(value) is str and len(value) <= 63
                and re.fullmatch(r"dpg-[a-z0-9]+(?:-[a-z0-9]+)*", value) is not None)
    return (type(value) is str and len(value) <= 253 and "." in value
            and not value.endswith((".localhost", ".local"))
            and all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                    for label in value.split("."))
            and not all(label.isdecimal() for label in value.split(".")))


def _read_file(name, *, secret=False):
    """Bounded regular-file read, no redirects, protected against other users.

    Linux production files must belong to root or the service UID; secrets must
    have no group/other permissions. Provisioning must verify these properties.
    Tests supply only synthetic files and file metadata.
    """
    path = SECRETS_DIR / name
    try:
        for parent in (*path.parents, path):
            if parent.is_symlink():
                raise ValueError
        with path.open("rb") as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_mode & (0o077 if secret else 0o022)
                    or not POSIX or info.st_uid not in {0, os.geteuid()}):
                raise ValueError
            value = stream.read(8193)
        if not value or len(value) > 8192:
            raise ValueError
        return value
    except Exception:
        pass
    raise reject("production_protected_file") from None


def read_secret(name):
    if name not in SECRET_FILES:
        raise reject("production_secret_scope")
    try:
        value = _read_file(name, secret=True).decode("utf-8").removesuffix("\n")
        if not 1 <= len(value) <= 4096 or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError
        return value
    except DatabaseConfigurationError:
        raise
    except Exception:
        pass
    raise reject("production_secret_read") from None


def recognition_secret():
    value = read_secret("recognition-key")
    if re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise reject("production_key_format")
    return bytes.fromhex(value)


@dataclass(frozen=True)
class ProductionSettings:
    database_host: str
    confirmation_enabled: bool = False
    management_enabled: bool = False
    integrations_enabled: bool = False
    releases_enabled: bool = False
    webhook_enabled: bool = False
    processing_enabled: bool = False
    smtp: dict | None = None


def load_production_settings(*, environ=None):
    environment = dict(os.environ if environ is None else environ)
    _validate_environment(environment, "production")
    try:
        document = tomllib.loads(_read_file("oaf-production.toml").decode("utf-8"))
    except Exception as exc:
        if isinstance(exc, DatabaseConfigurationError):
            raise
    else:
        if (set(document) <= {"public_origin", "database_host", "smtp"} | FLAGS
                and document.get("public_origin") == PUBLIC_ORIGIN
                and valid_database_host(document.get("database_host"), internal=True)
                and all(type(document.get(flag, False)) is bool for flag in FLAGS)):
            settings = ProductionSettings(**{k: v for k, v in document.items() if k != "public_origin"})
            if ((settings.management_enabled and not settings.confirmation_enabled)
                    or (settings.webhook_enabled and not settings.management_enabled)
                    or (settings.processing_enabled and not (settings.confirmation_enabled
                        and settings.management_enabled and settings.webhook_enabled))
                    or (settings.releases_enabled and not (settings.management_enabled
                        and settings.integrations_enabled and settings.webhook_enabled))):
                raise reject("production_activation_dependencies")
            if settings.smtp is not None:
                from .contact_mail import SMTPConfig
                if (type(settings.smtp) is not dict or set(settings.smtp) != {
                        "host", "port", "tls_mode", "username", "from_email"}
                        or (settings.smtp.get("tls_mode"), settings.smtp.get("port"))
                        not in (("ssl", 465), ("starttls", 587))):
                    raise reject("production_smtp_metadata")
                SMTPConfig(**settings.smtp, password="validation-only")
            return settings
    raise reject("production_metadata") from None


def load_runtime_database(*, environ=None):
    from sqlalchemy.engine import URL
    from .database_config import DatabaseConfig
    settings = load_production_settings(environ=environ)
    return DatabaseConfig("production", URL.create("postgresql+psycopg",
        host=settings.database_host, port=5432, database=DATABASE,
        username=RUNTIME_ROLE, password=read_secret("runtime-db-password"), query=TLS_QUERY))


def load_contact(*, environ=None):
    from .contact_mail import SMTPConfig
    settings = load_production_settings(environ=environ)
    if settings.smtp is None:
        raise reject("production_smtp_metadata")
    return SMTPConfig(**settings.smtp, password=read_secret("smtp-password"))


def load_integrations(secret):
    from .integrations import IntegrationConfig, validate_configuration
    settings = load_production_settings()
    config = IntegrationConfig("production", "gramanna", read_secret("integration-submission"),
        read_secret("integration-reporting"),
        read_secret("integration-release") if settings.releases_enabled else None)
    validate_configuration(config, "production", secret)
    return config
