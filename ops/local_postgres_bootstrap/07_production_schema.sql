-- PROPOSED PRODUCTION COMPATIBILITY SOURCE ONLY. DO NOT EXECUTE.
-- Separate owner bootstrap authorization and approved TLS/endpoint required.
-- Existing psql bootstrap pattern; exact preprovisioned LOGIN roles, no secrets.
\set ON_ERROR_STOP on
\set ON_ERROR_ROLLBACK off

BEGIN;
SET LOCAL search_path = pg_catalog, pg_temp;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';

DO $$
DECLARE
    provider_owner oid;
BEGIN
    SELECT datdba INTO provider_owner FROM pg_catalog.pg_database
        WHERE datname = pg_catalog.current_database();
    IF pg_catalog.current_database() <> 'oaf_website_prod'
       OR current_user <> session_user
       OR current_user <> pg_catalog.pg_get_userbyid(provider_owner)
       OR current_user IN ('oaf_website_prod_app', 'oaf_website_prod_migrator')
       OR pg_catalog.current_setting('server_version_num')::int / 10000 <> 17
       OR EXISTS (SELECT 1 FROM pg_catalog.pg_namespace WHERE nspname = 'oaf_website')
       OR NOT EXISTS (SELECT 1 FROM pg_catalog.pg_namespace WHERE nspname = 'public')
    THEN RAISE EXCEPTION 'Production bootstrap identity or starting state rejected'; END IF;

    IF (SELECT count(*) FROM pg_catalog.pg_roles
        WHERE rolname IN ('oaf_website_prod_app', 'oaf_website_prod_migrator')
          AND rolcanlogin AND NOT rolinherit AND NOT rolsuper AND NOT rolcreatedb
          AND NOT rolcreaterole AND NOT rolreplication AND NOT rolbypassrls) <> 2
       OR EXISTS (
          SELECT 1 FROM pg_catalog.pg_auth_members m
          JOIN pg_catalog.pg_roles member ON member.oid=m.member
          JOIN pg_catalog.pg_roles parent ON parent.oid=m.roleid
          WHERE member.rolname IN ('oaf_website_prod_app', 'oaf_website_prod_migrator')
             OR (parent.rolname IN ('oaf_website_prod_app', 'oaf_website_prod_migrator')
                 AND NOT (member.rolsuper OR pg_catalog.pg_has_role(member.oid, provider_owner, 'SET'))))
       OR EXISTS (
          SELECT 1 FROM pg_catalog.pg_shdepend d
          JOIN pg_catalog.pg_roles r ON r.oid=d.refobjid
          WHERE d.refclassid='pg_catalog.pg_authid'::pg_catalog.regclass
            AND d.deptype='o' AND r.rolname IN ('oaf_website_prod_app', 'oaf_website_prod_migrator'))
    THEN RAISE EXCEPTION 'Production bootstrap role authority rejected'; END IF;

    -- Direct/PUBLIC parameter grants do not appear in role attributes or memberships.
    -- In particular, session_replication_role SET can bypass foreign-key triggers.
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles r CROSS JOIN pg_catalog.pg_parameter_acl p
        WHERE r.rolname IN ('oaf_website_prod_app', 'oaf_website_prod_migrator')
          AND pg_catalog.has_parameter_privilege(r.oid, p.parname, 'ALTER SYSTEM'))
       OR EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles r CROSS JOIN pg_catalog.pg_settings p
        WHERE r.rolname IN ('oaf_website_prod_app', 'oaf_website_prod_migrator')
          AND p.context IN ('superuser', 'superuser-backend')
          AND pg_catalog.has_parameter_privilege(r.oid, p.name, 'SET'))
    THEN RAISE EXCEPTION 'Production bootstrap server-parameter authority rejected'; END IF;
END $$;

SELECT datdba::text AS saved_database_owner FROM pg_catalog.pg_database
    WHERE datname = pg_catalog.current_database() \gset
SELECT nspowner::text AS saved_public_owner, COALESCE(nspacl::text, '<NULL>') AS saved_public_acl
    FROM pg_catalog.pg_namespace WHERE nspname = 'public' \gset

REVOKE ALL PRIVILEGES ON DATABASE oaf_website_prod FROM PUBLIC;
REVOKE ALL PRIVILEGES ON DATABASE oaf_website_prod FROM oaf_website_prod_app, oaf_website_prod_migrator;
GRANT CONNECT ON DATABASE oaf_website_prod TO oaf_website_prod_app, oaf_website_prod_migrator;

-- CREATE exists only inside this separately authorized bootstrap transaction.
GRANT CREATE ON DATABASE oaf_website_prod TO oaf_website_prod_migrator;
SET LOCAL ROLE oaf_website_prod_migrator;
CREATE SCHEMA oaf_website AUTHORIZATION oaf_website_prod_migrator;
REVOKE ALL PRIVILEGES ON SCHEMA oaf_website FROM PUBLIC;
GRANT USAGE ON SCHEMA oaf_website TO oaf_website_prod_app;
ALTER DEFAULT PRIVILEGES FOR ROLE oaf_website_prod_migrator REVOKE ALL PRIVILEGES ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE oaf_website_prod_migrator REVOKE ALL PRIVILEGES ON SEQUENCES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE oaf_website_prod_migrator REVOKE EXECUTE ON ROUTINES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE oaf_website_prod_migrator REVOKE USAGE ON TYPES FROM PUBLIC;
SET LOCAL ROLE NONE;
REVOKE CREATE ON DATABASE oaf_website_prod FROM oaf_website_prod_migrator;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles r CROSS JOIN pg_catalog.pg_namespace n
        WHERE r.rolname IN ('oaf_website_prod_app', 'oaf_website_prod_migrator')
          AND n.nspname !~ '^pg_(temp|toast_temp)_[0-9]+$'
          AND pg_catalog.has_schema_privilege(r.oid,n.oid,'CREATE')
          AND NOT (r.rolname='oaf_website_prod_migrator' AND n.nspname='oaf_website'))
       OR EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles r CROSS JOIN pg_catalog.pg_database d
        WHERE r.rolname IN ('oaf_website_prod_app', 'oaf_website_prod_migrator')
          AND d.datname='oaf_website_prod'
          AND (pg_catalog.has_database_privilege(r.oid,d.oid,'CREATE')
            OR pg_catalog.has_database_privilege(r.oid,d.oid,'TEMPORARY')
            OR (d.datname='oaf_website_prod' AND (
                NOT pg_catalog.has_database_privilege(r.oid,d.oid,'CONNECT')
                OR pg_catalog.has_database_privilege(r.oid,d.oid,'CONNECT WITH GRANT OPTION')))))
    THEN RAISE EXCEPTION 'Production bootstrap effective authority rejected'; END IF;
END $$;

SELECT datdba::text = :'saved_database_owner' AS database_owner_preserved
    FROM pg_catalog.pg_database WHERE datname = pg_catalog.current_database() \gset
SELECT nspowner::text = :'saved_public_owner'
    AND COALESCE(nspacl::text, '<NULL>') = :'saved_public_acl' AS public_preserved
    FROM pg_catalog.pg_namespace WHERE nspname = 'public' \gset
\if :database_owner_preserved
\else
DO $$ BEGIN RAISE EXCEPTION 'Provider database owner changed'; END $$;
\endif
\if :public_preserved
\else
DO $$ BEGIN RAISE EXCEPTION 'Existing public schema changed'; END $$;
\endif
COMMIT;
\echo BOOTSTRAP_PRODUCTION_SCHEMA_COMMIT_ACKNOWLEDGED
