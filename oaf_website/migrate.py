"""Guarded standalone migration runner; no live work occurs at import.

CLI plan is repository-only. Verify/upgrade require an existing, independently
approved artifact set and a separate owner-issued single-use authorization.
"""

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import sys
import time
from typing import Protocol
import uuid

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from .migration_config import (
    Failure, MigrationError, database_failure, load_migration_config, select_identity,
)
from .migration_authority import FileOperationalAuthority, record_denial
from .migration_validation import (
    ROOT, VerifiedArtifacts, _runner_execution, catalog_state, scalar,
    validate_artifacts, verify_authority, verify_identity, verify_session_lock,
)


# Registered two-int PostgreSQL SESSION lock, scoped to the selected database.
# Namespace 0x4F414657 = OAFW; resource 4 = Checkpoint 4 migration framework.
# This is independent of application locks and survives commit for verification.
LOCK_ID = (0x4F414657, 4)
LOCK_SECONDS = 5.0
STATEMENT_TIMEOUT_MS = 60_000


@dataclass(frozen=True)
class Request:
    action: str
    environment: str
    expected_start: str
    target: str
    manifest_hash: str
    revision_hash: str


@dataclass(frozen=True)
class AuditEvent:
    """Only framework-generated, sanitized fields; never exception/SQL text."""

    run_id: str
    utc: str
    environment: str
    action: str
    expected_database: str
    expected_authenticated: str
    expected_effective: str
    verified_identity: bool
    verified_database: str | None
    verified_authenticated: str | None
    verified_effective: str | None
    expected_start: str
    observed_start: str | None
    target: str
    manifest_hash: str
    revision_hash: str
    phase: str
    failed_phase: str | None
    lock_outcome: str
    validation_outcome: str
    commit_certainty: str
    outcome: str
    failure: str | None
    operational_authority_verified: bool
    audit_write_outcome: str
    transaction_outcome: str
    database_commit_confirmed: bool
    mutation_started: bool
    interruption_phase: str | None
    cleanup: dict
    cleanup_attempts: dict
    secondary_failures: tuple


class AuditSink(Protocol):
    """Persistence contract implemented by the local operational adapter.

    write/finalize must acknowledge persistence or raise. The implementation
    must keep raw logs outside Git and implement the approved
    destination, retention, failed-write handling, and evidence review procedure.
    Same-Windows-account storage is not tamper-proof.
    """

    def write(self, event: AuditEvent) -> None: ...
    def finalize(self, event: AuditEvent) -> None: ...


class OperationalAuthority(Protocol):
    """Trusted adapter, absent by default; never inferred from digests.

    authorize must validate the local owner record for this exact run/action,
    environment, start/target, manifest and all hashes. It must verify dependency
    acceptance, bootstrap, lock/timeouts, recovery procedure and all four audit
    policies have been separately approved and are available. Return a working
    audit sink only on success. No actual authorization records are created here.
    """

    def authorize(self, request: Request, run_id: str,
                  artifacts: VerifiedArtifacts) -> AuditSink: ...


# Exact concrete class only. Registration does not confer artifact approval or
# execution permission; an independently supplied owner record is still needed.
_OPERATIONAL_ADAPTER_TYPES = (FileOperationalAuthority,)


def _require_operational_adapter(authority, *, request=None, run_id=None, sink=None):
    if type(authority) not in _OPERATIONAL_ADAPTER_TYPES:
        raise MigrationError(Failure.OPERATIONAL_GATE)
    if request is not None:
        authority.require_binding(request, run_id, sink)


_CLEANUP_COMPONENTS = ('rollback', 'advisory_unlock', 'connection_close',
                       'engine_dispose', 'audit_finalize')


@dataclass
class _Evidence:
    request: Request
    identity: object
    run_id: str
    authorized: bool = False
    audit_acknowledged: bool = False
    audit_write: str = 'not_attempted'
    verified: bool = False
    session_lock_verified: bool = False
    observed_start: str | None = None
    phase: str = 'authorization'
    failed_phase: str | None = None
    lock: str = 'not_acquired'
    validation: str = 'not_checked'
    commit: str = 'not_invoked'
    transaction: str = 'not_started'
    mutation_started: bool = False
    interruption_phase: str | None = None
    cleanup_attempts: dict = field(default_factory=lambda: {k: [] for k in _CLEANUP_COMPONENTS})
    secondary_failures: list = field(default_factory=list)
    verified_connection: object = field(default=None, repr=False)
    verified_transaction: object = field(default=None, repr=False)
    audit_sink: object = field(default=None, repr=False)
    operational_authority: object = field(default=None, repr=False)
    session_lock_backend: int | None = None

    @property
    def commit_confirmed(self):
        # Derive from one atomic certainty transition, avoiding disagreement
        # between flags if the operator interrupts after commit returns.
        return self.commit in {'confirmed', 'postcommit_verification_failed'}

    def cleanup(self):
        # Retain every attempt; later success never erases an earlier failure.
        result = {}
        for component, attempts in self.cleanup_attempts.items():
            result[component] = ('failed' if 'failed' in attempts else
                                 'unconfirmed' if 'unconfirmed' in attempts else
                                 'confirmed_successful' if attempts else 'not_attempted')
        return result

    def event(self, outcome='pending', failure=None):
        i = self.identity
        return AuditEvent(
            self.run_id, datetime.now(timezone.utc).isoformat(),
            self.request.environment, self.request.action, i.database,
            i.migrator, i.owner, self.verified,
            i.database if self.verified else None,
            i.migrator if self.verified else None,
            i.owner if self.verified else None, self.request.expected_start,
            self.observed_start, self.request.target, self.request.manifest_hash,
            self.request.revision_hash, self.phase, self.failed_phase,
            self.lock, self.validation, self.commit, outcome, failure,
            self.authorized, self.audit_write, self.transaction,
            self.commit_confirmed, self.mutation_started, self.interruption_phase,
            self.cleanup(), {k: tuple(v) for k, v in self.cleanup_attempts.items()},
            tuple(dict(v) for v in self.secondary_failures),
        )

    def result(self, outcome, failure):
        return {
            'run_id': self.run_id, 'outcome': 'failed' if failure else outcome,
            'classification': failure, 'failed_phase': self.failed_phase,
            'commit_certainty': self.commit,
            'database_commit_confirmed': self.commit_confirmed,
            'transaction_outcome': self.transaction,
            'mutation_started': self.mutation_started,
            'interruption_phase': self.interruption_phase,
            'lock_outcome': self.lock, 'validation_outcome': self.validation,
            'audit_write_outcome': self.audit_write,
            'cleanup': self.cleanup(),
            'cleanup_attempts': {k: list(v) for k, v in self.cleanup_attempts.items()},
            'secondary_failures': list(self.secondary_failures),
        }


def _audit(sink, evidence):
    evidence.audit_acknowledged = False
    evidence.audit_write = 'unconfirmed'
    try:
        sink.write(evidence.event())
    except Exception:
        evidence.audit_write = 'failed'
        raise MigrationError(Failure.AUDIT_WRITE) from None
    evidence.audit_write = 'confirmed_successful'
    evidence.audit_acknowledged = True


def _set_limits(connection, *, readonly=False):
    if readonly:
        connection.execute(text("SET TRANSACTION READ ONLY"))
    connection.execute(text("SET LOCAL lock_timeout = '5s'"))
    connection.execute(text("SET LOCAL statement_timeout = '60s'"))
    connection.execute(text("SET LOCAL search_path = pg_catalog, oaf_website, pg_temp"))
    if scalar(connection, "SELECT pg_catalog.current_setting('search_path')") != "pg_catalog, oaf_website, pg_temp":
        raise MigrationError(Failure.INVALID_CONFIGURATION)
    if (scalar(connection, "SELECT setting::int FROM pg_catalog.pg_settings WHERE name='lock_timeout'") != 5_000
            or scalar(connection, "SELECT setting::int FROM pg_catalog.pg_settings WHERE name='statement_timeout'") != STATEMENT_TIMEOUT_MS):
        # Both settings use milliseconds; Stage 5 must confirm enforcement.
        raise MigrationError(Failure.INVALID_CONFIGURATION)


def _assume_owner(connection, identity):
    # Identifier is from the immutable registry, never caller text or a URL.
    connection.execute(text(f'SET LOCAL ROLE "{identity.owner}"'))
    verify_identity(connection, identity, assumed=True)


def _lock(connection):
    # Advisory try-lock never waits in the server; the bounded poll defines
    # contention handling. Cap each acquisition query too (Stage 5 must verify).
    connection.execute(text("SET LOCAL statement_timeout = '5s'"))
    deadline = time.monotonic() + LOCK_SECONDS
    while True:
        acquired = scalar(connection,
            "SELECT pg_catalog.pg_try_advisory_lock(:namespace, :resource)",
            namespace=LOCK_ID[0], resource=LOCK_ID[1])
        if acquired is True:
            return
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise MigrationError(Failure.LOCK_BUSY)
        time.sleep(min(0.05, remaining))


def _execute_revision(connection, identity, artifacts, transaction, evidence,
                      sink, authority, session_lock_backend):
    from alembic import command
    from alembic.config import Config

    verified = validate_artifacts(
        expected_start=artifacts.expected_start, target=artifacts.target,
        manifest_hash=artifacts.manifest_hash, revision_hash=artifacts.revision_hash,
    )
    config = Config(str(ROOT / 'alembic.ini'))
    previous = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        with _runner_execution(connection, identity, verified, transaction,
                               evidence, sink, authority, session_lock_backend) as runner:
            config.attributes['oaf_runner'] = runner
            command.upgrade(config, verified.target)
    finally:
        config.attributes.pop('oaf_runner', None)
        sys.dont_write_bytecode = previous


def _interruption(evidence):
    evidence.interruption_phase = (
        'during_commit' if evidence.commit == 'invocation_begun' else
        'after_confirmed_commit' if evidence.commit_confirmed else
        'before_commit_invocation' if evidence.phase in {'precommit', 'commit_ready', 'commit'} else
        'during_transaction_execution' if evidence.mutation_started else
        'before_transaction_mutation')
    if evidence.commit == 'invocation_begun':
        evidence.commit = 'uncertain'
        evidence.transaction = 'unknown'
        return Failure.UNCERTAIN_COMMIT
    return Failure.INTERRUPTED


def run(request: Request, *, authority: OperationalAuthority | None = None):
    """Also retain sanitized denials from validation before runner setup."""
    try:
        if type(request) is not Request or any(type(value) is not str for value in vars(request).values()):
            raise MigrationError(Failure.INVALID_CONFIGURATION)
        return _run(request, authority=authority)
    except MigrationError as error:
        if error.operational_result is None:
            error.run_id = str(uuid.uuid4())
            error.denial_persisted = record_denial(request, error.run_id, error.classification)
        raise
    except Exception:
        error = MigrationError(Failure.INVALID_CONFIGURATION)
        error.run_id = str(uuid.uuid4())
        error.denial_persisted = record_denial(request, error.run_id, error.classification)
        raise error from None


def _run(request: Request, *, authority: OperationalAuthority | None = None):
    """Controlled runner boundary; CLI and arbitrary callers remain gated.

    One revision transaction plus read-only setup/postcommit transactions. A
    session lock must survive setup rollback and commit. No retry or repair.
    Operator interruption is a sanitized failure (CLI exit 130), with cleanup
    and finalization attempts, rather than a raw KeyboardInterrupt traceback.
    """
    if request.action not in {'plan', 'verify', 'upgrade'}:
        raise MigrationError(Failure.INVALID_CONFIGURATION)
    identity = select_identity(request.environment)
    artifacts = validate_artifacts(
        expected_start=request.expected_start, target=request.target,
        manifest_hash=request.manifest_hash, revision_hash=request.revision_hash,
    )
    if request.action == 'plan':
        return {
            'outcome': 'planned', 'environment': identity.environment,
            'starting_revision': request.expected_start, 'target_revision': request.target,
            'manifest_hash': artifacts.manifest_hash, 'revision_hash': artifacts.revision_hash,
            'live_execution': 'blocked_pending_independent_artifact_approval_and_owner_authorization',
        }
    evidence = _Evidence(request, identity, str(uuid.uuid4()))
    connection = engine = transaction = sink = None
    original_proxy = original_dbapi = original_driver = original_pgconn = None
    backend = None
    lock_attempted = False
    failure = None
    outcome = 'failed'

    def require_original_session():
        # Strong references bind evidence to the physical session, not merely
        # the reusable SQLAlchemy Connection or a potentially reused PID.
        # Check lifecycle state BEFORE Connection.connection: that property can
        # reconnect an invalidated connection. These checks issue no SQL.
        if (connection is None or connection.closed or connection.invalidated
                or original_proxy is None or not original_proxy.is_valid
                or original_dbapi is None or original_driver is None
                or original_pgconn is None):
            raise MigrationError(Failure.CONNECTION)
        current_proxy = connection.connection
        if (current_proxy is not original_proxy
                or current_proxy.dbapi_connection is not original_dbapi
                or current_proxy.driver_connection is not original_driver
                or original_driver.closed or original_driver.broken
                or original_driver.pgconn is not original_pgconn
                or type(backend) is not int
                or original_driver.info.backend_pid != backend):
            raise MigrationError(Failure.CONNECTION)

    try:
        _require_operational_adapter(authority)  # Before credentials or engines.
        try:
            sink = authority.authorize(request, evidence.run_id, artifacts)
        except MigrationError as error:
            if hasattr(error, 'denial_persisted'):
                evidence.audit_write = 'confirmed_successful' if error.denial_persisted else 'failed'
            raise
        except Exception:
            raise MigrationError(Failure.OPERATIONAL_GATE) from None
        if sink is None or not callable(getattr(sink, 'write', None)) or not callable(getattr(sink, 'finalize', None)):
            raise MigrationError(Failure.OPERATIONAL_GATE)
        _require_operational_adapter(authority, request=request, run_id=evidence.run_id, sink=sink)
        evidence.authorized = True
        evidence.audit_sink = sink
        evidence.operational_authority = authority
        _audit(sink, evidence)
        evidence.phase = 'credential'
        config = load_migration_config(environment=request.environment)
        engine = create_engine(
            config.url, poolclass=NullPool, echo=False, hide_parameters=True,
            connect_args={'connect_timeout': 5, 'application_name': 'oaf_website_migrations',
                          'require_auth': 'scram-sha-256'},
        )
        evidence.phase = 'connection'
        connection = engine.connect()
        transaction = connection.begin()
        evidence.transaction = 'setup_readonly_active'
        _set_limits(connection, readonly=True)
        verify_identity(connection, identity)
        original_proxy = connection.connection
        original_dbapi = original_proxy.dbapi_connection
        original_driver = original_proxy.driver_connection
        original_pgconn = original_driver.pgconn
        backend = scalar(connection, 'SELECT pg_catalog.pg_backend_pid()')
        require_original_session()
        evidence.phase = 'lock'
        # A new physical session must not already hold this resource. Reject a
        # reentrant acquisition, so one successful unlock can be verified later.
        if scalar(connection, """
            SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_locks
                WHERE locktype='advisory' AND pid=pg_catalog.pg_backend_pid()
                  AND classid=:namespace AND objid=:resource AND objsubid=2)
        """, namespace=LOCK_ID[0], resource=LOCK_ID[1]):
            raise MigrationError(Failure.LOCK_BUSY)
        lock_attempted = True
        evidence.lock = 'acquisition_unconfirmed'
        require_original_session()
        _lock(connection)  # The SESSION API, never pg_try_advisory_xact_lock.
        require_original_session()
        evidence.lock = 'acquired'
        try:
            if (connection.closed or connection.invalidated
                    or connection.get_transaction() is not transaction
                    or not transaction.is_active):
                raise MigrationError(Failure.CONNECTION)
            transaction.rollback()
            require_original_session()
            if connection.closed or connection.invalidated or connection.in_transaction():
                raise MigrationError(Failure.CONNECTION)
        except KeyboardInterrupt:
            evidence.cleanup_attempts['rollback'].append('unconfirmed')
            raise
        except Exception:
            evidence.cleanup_attempts['rollback'].append('failed')
            raise
        else:
            evidence.cleanup_attempts['rollback'].append('confirmed_successful')
        evidence.transaction = 'setup_rollback_confirmed'
        transaction = connection.begin()
        _set_limits(connection, readonly=request.action == 'verify')
        verify_identity(connection, identity)
        require_original_session()
        verify_session_lock(connection, backend, LOCK_ID)
        evidence.session_lock_verified = True  # Proof survived transaction end.
        evidence.session_lock_backend = backend
        evidence.transaction = 'active_before_mutation'
        _audit(sink, evidence)
        evidence.phase = 'preflight'
        verify_authority(connection, identity)
        _assume_owner(connection, identity)
        evidence.verified = True
        evidence.verified_connection = connection
        evidence.verified_transaction = transaction
        current = catalog_state(connection, identity)
        evidence.observed_start = current
        if current != request.expected_start:
            raise MigrationError(Failure.STARTING_REVISION)
        evidence.validation = 'preflight_passed'
        _audit(sink, evidence)
        if request.action == 'verify' or current == request.target:
            _require_operational_adapter(authority, request=request, run_id=evidence.run_id, sink=sink)
            outcome = ('verified_target' if current == request.target else 'verified_start') if request.action == 'verify' else 'verified_noop'
            # Final cleanup must confirm read-only/noop rollback before success.
        else:
            evidence.phase = 'revision'
            _audit(sink, evidence)  # Acknowledged audit bound into env context.
            _require_operational_adapter(authority, request=request, run_id=evidence.run_id, sink=sink)
            _execute_revision(connection, identity, artifacts, transaction,
                              evidence, sink, authority, backend)
            if connection.get_transaction() is not transaction or not transaction.is_active:
                raise MigrationError(Failure.TRANSACTION)
            evidence.phase = 'precommit'
            require_original_session()
            verify_session_lock(connection, backend, LOCK_ID)
            verify_authority(connection, identity)
            verify_identity(connection, identity, assumed=True)
            if catalog_state(connection, identity) != request.target:
                raise MigrationError(Failure.DRIFT)
            evidence.validation = 'precommit_passed'
            _audit(sink, evidence)
            evidence.phase = 'commit_ready'
            # Audit intent BEFORE marking invocation begun. Failure here proves
            # commit was not invoked, and retains rollback eligibility.
            _audit(sink, evidence)
            _require_operational_adapter(authority, request=request, run_id=evidence.run_id, sink=sink)
            evidence.phase = 'commit'
            evidence.commit = 'invocation_begun'
            try:
                transaction.commit()
            except Exception as error:
                classification = database_failure(error, committing=True)
                if classification == Failure.UNCERTAIN_COMMIT:
                    evidence.secondary_failures.append({
                        'component': 'commit', 'classification': database_failure(error),
                    })
                evidence.commit = 'uncertain' if classification == Failure.UNCERTAIN_COMMIT else 'rejected'
                evidence.transaction = 'unknown' if evidence.commit == 'uncertain' else 'commit_rejected'
                raise MigrationError(classification) from None
            evidence.commit = 'confirmed'
            evidence.transaction = 'committed_confirmed'
            evidence.phase = 'postcommit'
            _audit(sink, evidence)
            transaction = connection.begin()
            _set_limits(connection, readonly=True)
            verify_identity(connection, identity)
            require_original_session()
            verify_session_lock(connection, backend, LOCK_ID)
            verify_authority(connection, identity)
            _assume_owner(connection, identity)
            if catalog_state(connection, identity) != request.target:
                raise MigrationError(Failure.POSTCOMMIT)
            evidence.validation = 'postcommit_passed'
            outcome = 'applied_and_verified'
    except KeyboardInterrupt:
        failure = _interruption(evidence)
    except MigrationError as error:
        failure = error.classification
    except Exception as error:
        failure = database_failure(error)
    finally:
        if evidence.commit_confirmed:
            evidence.transaction = 'committed_confirmed'
        if failure:
            evidence.failed_phase = evidence.phase
        if failure and evidence.commit_confirmed and evidence.phase == 'postcommit':
            evidence.commit = 'postcommit_verification_failed'
            evidence.validation = 'postcommit_failed'

        def cleanup(component, operation):
            nonlocal failure
            try:
                attempted = operation()
            except KeyboardInterrupt:
                evidence.cleanup_attempts[component].append('unconfirmed')
                classification = Failure.INTERRUPTED
                if evidence.interruption_phase is None:
                    evidence.interruption_phase = 'cleanup_' + component
            except Exception as error:
                evidence.cleanup_attempts[component].append('failed')
                classification = database_failure(error)
            else:
                if attempted is not False:
                    evidence.cleanup_attempts[component].append('confirmed_successful')
                return True
            evidence.secondary_failures.append({'component': component, 'classification': classification})
            if failure is None:
                failure = classification
                evidence.failed_phase = 'cleanup_' + component
            return False

        def rollback():
            # Do not infer rollback from attempted closure or inactive local
            # transaction state. A successful rollback call is required evidence.
            if lock_attempted:
                try:
                    require_original_session()
                except (Exception, KeyboardInterrupt):
                    if evidence.commit == 'not_invoked':
                        evidence.transaction = 'rollback_unconfirmed'
                    raise
            if connection.closed or connection.invalidated:
                if evidence.commit == 'not_invoked':
                    evidence.transaction = 'rollback_unconfirmed'
                raise MigrationError(Failure.CONNECTION)
            if connection.in_transaction():
                if evidence.commit == 'not_invoked':
                    evidence.transaction = 'rollback_unconfirmed'
                connection.rollback()
                if lock_attempted:
                    require_original_session()
                if connection.closed or connection.invalidated or connection.in_transaction():
                    raise MigrationError(Failure.CONNECTION)
                if evidence.commit == 'not_invoked':
                    evidence.transaction = 'rollback_confirmed'
            elif evidence.transaction in {'active_before_mutation', 'mutation_possible', 'setup_readonly_active', 'rollback_unconfirmed'}:
                raise MigrationError(Failure.TRANSACTION)
            else:
                return False  # No rollback invoked; never report it as success.

        if connection is not None:
            if evidence.commit != 'uncertain':
                # Skip when there is no active transaction (e.g. just committed).
                # State inspection itself can fail, so keep it in the boundary.
                cleanup('rollback', rollback)
            else:
                evidence.transaction = 'unknown'  # Rollback intentionally skipped.
            if lock_attempted and evidence.commit != 'uncertain':
                def unlock():
                    require_original_session()
                    released = scalar(connection,
                        'SELECT pg_catalog.pg_advisory_unlock(:namespace, :resource)',
                        namespace=LOCK_ID[0], resource=LOCK_ID[1])
                    require_original_session()
                    if released is not True and released is not False:
                        raise MigrationError(Failure.TRANSACTION)
                    if released is not True and evidence.lock == 'acquired':
                        raise MigrationError(Failure.TRANSACTION)
                    present = scalar(connection, """
                        SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_locks
                            WHERE locktype='advisory' AND pid=pg_catalog.pg_backend_pid()
                              AND classid=:namespace AND objid=:resource AND objsubid=2
                              AND mode='ExclusiveLock' AND granted)
                    """, namespace=LOCK_ID[0], resource=LOCK_ID[1])
                    require_original_session()
                    if present is not False:
                        raise MigrationError(Failure.TRANSACTION)
                    # False unlock with unconfirmed acquisition proves absence
                    # on this original session, not that a lock was released.
                    evidence.lock = 'release_confirmed' if released is True else 'absence_confirmed'
                if not cleanup('advisory_unlock', unlock):
                    evidence.lock = 'release_unconfirmed'
                cleanup('rollback', rollback)  # Unlock's implicit read transaction.
            elif lock_attempted:
                evidence.lock = 'release_unconfirmed'
            cleanup('connection_close', connection.close)
            # Even successful close is not explicit proof of advisory release on
            # the server after a transport loss or uncertain commit.
        if engine is not None:
            cleanup('engine_dispose', engine.dispose)
        if failure in {Failure.DRIFT, Failure.SCHEMA_OWNERSHIP, Failure.STARTING_REVISION,
                       Failure.WRONG_IDENTITY, Failure.UNAUTHORIZED_MEMBERSHIP}:
            evidence.validation = 'failed' if not evidence.commit_confirmed else 'postcommit_failed'
        if failure == Failure.LOCK_BUSY and evidence.lock == 'not_acquired':
            evidence.lock = 'busy'
        evidence.phase = 'finalization'
        if sink is None and evidence.audit_write == 'not_attempted':
            persisted = record_denial(request, evidence.run_id, failure or Failure.OPERATIONAL_GATE)
            evidence.audit_write = 'confirmed_successful' if persisted else 'failed'
        if sink is not None:
            # The terminal event describes an unconfirmed finalization attempt.
            # The structured returned/raised result records its acknowledged
            # outcome. The file sink publishes completion only after both the
            # terminal payload and its completion evidence have synchronized.
            evidence.cleanup_attempts['audit_finalize'].append('unconfirmed')
            try:
                sink.finalize(evidence.event('failed' if failure else outcome, failure))
            except (Exception, KeyboardInterrupt) as error:
                interrupted = isinstance(error, KeyboardInterrupt)
                evidence.cleanup_attempts['audit_finalize'][-1] = 'unconfirmed' if interrupted else 'failed'
                classification = Failure.INTERRUPTED if interrupted else Failure.AUDIT
                evidence.secondary_failures.append({'component': 'audit_finalize', 'classification': classification})
                if interrupted and evidence.interruption_phase is None:
                    evidence.interruption_phase = 'audit_finalization'
                if failure is None:
                    failure = classification
                    evidence.failed_phase = 'audit_finalization'
            else:
                evidence.cleanup_attempts['audit_finalize'][-1] = 'confirmed_successful'
    result = evidence.result(outcome, failure)
    if failure:
        error = MigrationError(failure)
        error.run_id = evidence.run_id
        error.commit_certainty = evidence.commit
        error.secondary_failure = evidence.secondary_failures[0]['classification'] if evidence.secondary_failures else None
        error.operational_result = result
        raise error from None
    return result


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        # argparse normally echoes unexpected caller text, potentially a secret.
        raise MigrationError(Failure.INVALID_CONFIGURATION)


def main(argv=None):
    parser = _Parser(description="Guarded OAF Website migrations", allow_abbrev=False)
    parser.add_argument("action", choices=("plan", "verify", "upgrade"))
    parser.add_argument("--environment", required=True, choices=("development", "testing"))
    parser.add_argument("--expected-start", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--revision-sha256", required=True)
    parser.add_argument("--authorization-id")
    try:
        args = parser.parse_args(argv)
        result = run(Request(
            args.action, args.environment, args.expected_start, args.target,
            args.manifest_sha256, args.revision_sha256,
        ), authority=FileOperationalAuthority(args.authorization_id) if args.authorization_id else None)
    except MigrationError as error:
        if error.operational_result is None and not hasattr(error, 'denial_persisted'):
            error.run_id = str(uuid.uuid4())
            record_denial(None, error.run_id, error.classification)
        print(json.dumps(error.operational_result or {
            "outcome": "failed", "classification": error.classification,
            "run_id": error.run_id, "commit_certainty": error.commit_certainty,
            "secondary_failure": error.secondary_failure,
        }, sort_keys=True))
        return 130 if error.operational_result and error.operational_result['interruption_phase'] else 1
    except KeyboardInterrupt:
        print(json.dumps({"outcome": "failed", "classification": Failure.INTERRUPTED,
                          "commit_certainty": "unconfirmed"}))
        return 130
    except Exception:
        print(json.dumps({"outcome": "failed", "classification": Failure.TRANSACTION}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
