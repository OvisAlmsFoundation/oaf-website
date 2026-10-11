"""Only the verified OAF runner may supply a connection and exact revision."""

from alembic import context
from uuid import uuid4

from oaf_website.migrate import LOCK_ID, _require_operational_adapter
from oaf_website.migration_authority import record_denial
from oaf_website.migration_config import IDENTITIES, Failure, MigrationError, database_failure
from oaf_website.migration_validation import (
    BASE, catalog_state, consume_runner_context, scalar, validate_artifacts,
    verify_authority, verify_identity, verify_session_lock,
)


def run_migrations():
    if context.is_offline_mode():
        raise MigrationError(Failure.INVALID_CONFIGURATION)
    config = context.config
    runner = consume_runner_context(config.attributes.get("oaf_runner"))
    _require_operational_adapter(runner.authority, request=runner.evidence.request,
                                 run_id=runner.evidence.run_id, sink=runner.sink)
    i, connection = runner.identity, runner.connection
    if i != IDENTITIES.get(i.environment) or i.schema != "oaf_website":
        raise MigrationError(Failure.INVALID_CONFIGURATION)
    if (connection.get_transaction() is not runner.transaction
            or not runner.transaction.is_active
            or connection.in_nested_transaction()
            or config.get_main_option("sqlalchemy.url")
            or config.cmd_opts is not None):
        raise MigrationError(Failure.INVALID_CONFIGURATION)
    a = runner.artifacts
    validate_artifacts(expected_start=a.expected_start, target=a.target,
                       manifest_hash=a.manifest_hash, revision_hash=a.revision_hash)
    if context.get_x_argument() or context.get_tag_argument():
        raise MigrationError(Failure.INVALID_CONFIGURATION)
    if context.get_revision_argument() != a.target:
        raise MigrationError(Failure.STARTING_REVISION)
    verify_identity(connection, i, assumed=True)
    verify_authority(connection, i)
    if scalar(connection, "SELECT pg_catalog.current_setting('search_path')") != "pg_catalog, oaf_website, pg_temp":
        raise MigrationError(Failure.INVALID_CONFIGURATION)
    # Session provenance requires survival across the runner's setup rollback;
    # a transaction advisory lock cannot satisfy that lifecycle binding.
    verify_session_lock(connection, runner.session_lock_backend, LOCK_ID)
    if (scalar(connection, "SELECT setting::int FROM pg_catalog.pg_settings WHERE name='lock_timeout'") != 5_000
            or scalar(connection, "SELECT setting::int FROM pg_catalog.pg_settings WHERE name='statement_timeout'") != 60_000):
        raise MigrationError(Failure.INVALID_CONFIGURATION)
    if catalog_state(connection, i) != a.expected_start or a.expected_start == a.target:
        raise MigrationError(Failure.STARTING_REVISION)
    context.configure(
        connection=connection, target_metadata=None,
        version_table="alembic_version", version_table_schema=i.schema,
        version_table_pk=True, transactional_ddl=True,
        transaction_per_migration=False, compare_type=False,
        include_schemas=True,
    )
    # Alembic recognizes the existing external transaction. It must not own or
    # commit it. Each supported revision stays inside this transaction.
    with context.begin_transaction():
        # Validation and context setup may outlive the authorization. This is
        # the final boundary before Alembic can create version metadata.
        _require_operational_adapter(runner.authority, request=runner.evidence.request,
                                     run_id=runner.evidence.run_id, sink=runner.sink)
        runner.evidence.mutation_started = True
        runner.evidence.transaction = 'mutation_possible'
        context.run_migrations()
    if connection.get_transaction() is not runner.transaction or not runner.transaction.is_active:
        raise MigrationError(Failure.TRANSACTION)


try:
    run_migrations()
except MigrationError as error:
    record_denial(None, str(uuid4()), error.classification)
    raise
except Exception as error:
    record_denial(None, str(uuid4()), database_failure(error))
    raise MigrationError(database_failure(error)) from None
