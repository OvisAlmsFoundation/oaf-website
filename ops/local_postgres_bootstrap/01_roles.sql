-- PROPOSED - DO NOT EXECUTE. SEPARATE OWNER APPROVAL REQUIRED.
-- Run in a fresh psql -X session connected to oaf_website_dev as postgres.
\set ON_ERROR_STOP on
\set ON_ERROR_ROLLBACK off
\set VERBOSITY terse
\set SHOW_CONTEXT never

BEGIN;
SET LOCAL search_path = pg_catalog, pg_temp;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';

DO $roles_preflight$
DECLARE
    identity record;
    role_id oid;
    database_name text;
BEGIN
    IF session_user <> 'postgres' OR current_user <> 'postgres'
       OR NOT EXISTS (SELECT FROM pg_catalog.pg_roles
                      WHERE oid = 10 AND rolname = 'postgres' AND rolsuper AND rolcanlogin)
       OR pg_catalog.current_database() <> 'oaf_website_dev'
       OR pg_catalog.current_setting('server_version_num') <> '170011'
       OR pg_catalog.inet_server_addr() IS DISTINCT FROM '127.0.0.1'::inet
       OR pg_catalog.inet_server_port() IS DISTINCT FROM 5432 THEN
        RAISE EXCEPTION 'Bootstrap administrator, database, version or endpoint mismatch';
    END IF;
    IF EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname IN (
        'oaf_website_dev_migrator', 'oaf_website_dev_schema_owner',
        'oaf_website_test_migrator', 'oaf_website_test_schema_owner')) THEN
        RAISE EXCEPTION 'Bootstrap role collision; existing roles must not be adopted';
    END IF;
    -- Inspect the preserved foundation before any role creation, then verify
    -- the complete new authority with the shared guard before COMMIT.
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles
                   WHERE rolname = 'oaf_website_owner' AND NOT rolcanlogin)
       OR EXISTS (SELECT FROM pg_catalog.pg_namespace WHERE nspname = 'oaf_website') THEN
        RAISE EXCEPTION 'Existing owner mismatch or development schema collision';
    END IF;
    FOR identity IN SELECT * FROM (VALUES
        ('oaf_website_dev', 'oaf_website_app'),
        ('oaf_website_test', 'oaf_website_test_app')
    ) AS registry(database_name, runtime_name) LOOP
        SELECT oid INTO STRICT role_id FROM pg_catalog.pg_roles WHERE rolname = identity.runtime_name
            AND rolcanlogin AND NOT (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls);
        IF NOT EXISTS (SELECT FROM pg_catalog.pg_database d
                       JOIN pg_catalog.pg_roles r ON r.oid = d.datdba
                       WHERE d.datname = identity.database_name AND r.rolname = 'oaf_website_owner'
                         AND d.datallowconn AND NOT d.datistemplate)
           OR EXISTS (SELECT FROM pg_catalog.pg_database d CROSS JOIN LATERAL
                      pg_catalog.aclexplode(COALESCE(d.datacl, pg_catalog.acldefault('d', d.datdba))) a
                      WHERE d.datname = identity.database_name AND a.grantee = 0)
           OR EXISTS (SELECT FROM pg_catalog.pg_auth_members WHERE member = role_id OR roleid = role_id)
           OR pg_catalog.pg_has_role(role_id, 'oaf_website_owner', 'MEMBER')
           OR EXISTS (SELECT FROM pg_catalog.pg_namespace n
                      WHERE pg_catalog.has_schema_privilege(role_id, n.oid, 'CREATE'))
           OR EXISTS (SELECT FROM pg_catalog.pg_shdepend WHERE
                      refclassid = 'pg_catalog.pg_authid'::regclass AND refobjid = role_id AND deptype = 'o') THEN
            RAISE EXCEPTION 'Preserved database or runtime authority mismatch';
        END IF;
        FOREACH database_name IN ARRAY ARRAY['oaf_website_dev', 'oaf_website_test'] LOOP
            IF pg_catalog.has_database_privilege(role_id, database_name, 'CONNECT')
                   IS DISTINCT FROM (database_name = identity.database_name)
               OR pg_catalog.has_database_privilege(role_id, database_name,
                   'CREATE, TEMPORARY, CONNECT WITH GRANT OPTION, CREATE WITH GRANT OPTION, TEMPORARY WITH GRANT OPTION') THEN
                RAISE EXCEPTION 'Preserved runtime database privileges mismatch';
            END IF;
        END LOOP;
    END LOOP;
END
$roles_preflight$;

CREATE ROLE oaf_website_dev_schema_owner WITH NOLOGIN NOSUPERUSER NOCREATEDB
    NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT PASSWORD NULL;
CREATE ROLE oaf_website_test_schema_owner WITH NOLOGIN NOSUPERUSER NOCREATEDB
    NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT PASSWORD NULL;
CREATE ROLE oaf_website_dev_migrator WITH NOLOGIN NOSUPERUSER NOCREATEDB
    NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT PASSWORD NULL;
CREATE ROLE oaf_website_test_migrator WITH NOLOGIN NOSUPERUSER NOCREATEDB
    NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT PASSWORD NULL;

-- The verified bootstrap superuser is the explicit, stable membership grantor.
GRANT oaf_website_dev_schema_owner TO oaf_website_dev_migrator
    WITH INHERIT FALSE, SET TRUE, ADMIN FALSE GRANTED BY postgres;
GRANT oaf_website_test_schema_owner TO oaf_website_test_migrator
    WITH INHERIT FALSE, SET TRUE, ADMIN FALSE GRANTED BY postgres;

-- Checks all six ordinary roles, both shared database ACLs and the local
-- pre-schema state. Any failure rolls back roles AND memberships together.
\set expected_database oaf_website_dev
\set bootstrap_preflight true
\ir 04_verify.sql
COMMIT;
\echo BOOTSTRAP_ROLES_COMMIT_ACKNOWLEDGED
