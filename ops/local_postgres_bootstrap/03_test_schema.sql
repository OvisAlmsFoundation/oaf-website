-- PROPOSED - DO NOT EXECUTE. SEPARATE OWNER APPROVAL REQUIRED.
\set ON_ERROR_STOP on
\set ON_ERROR_ROLLBACK off
\set expected_database oaf_website_test

BEGIN;
\set bootstrap_preflight true
\ir 04_verify.sql

-- Preserve the existing public schema exactly; do not assume its owner/ACL.
SELECT nspowner::text AS saved_public_owner,
       COALESCE(nspacl::text, '<NULL>') AS saved_public_acl
FROM pg_catalog.pg_namespace WHERE nspname = 'public' \gset

CREATE SCHEMA oaf_website AUTHORIZATION oaf_website_test_schema_owner;
GRANT CONNECT ON DATABASE oaf_website_test TO oaf_website_test_migrator;

SET LOCAL ROLE oaf_website_test_schema_owner;
REVOKE ALL PRIVILEGES ON SCHEMA oaf_website FROM PUBLIC;
GRANT USAGE ON SCHEMA oaf_website TO oaf_website_test_app;
-- Database-wide, role-specific defaults: no IN SCHEMA revocation shortcut.
ALTER DEFAULT PRIVILEGES FOR ROLE oaf_website_test_schema_owner
    REVOKE ALL PRIVILEGES ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE oaf_website_test_schema_owner
    REVOKE ALL PRIVILEGES ON SEQUENCES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE oaf_website_test_schema_owner
    REVOKE EXECUTE ON ROUTINES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE oaf_website_test_schema_owner
    REVOKE USAGE ON TYPES FROM PUBLIC;
SET LOCAL ROLE NONE;

SELECT nspowner::text = :'saved_public_owner'
       AND COALESCE(nspacl::text, '<NULL>') = :'saved_public_acl' AS public_preserved
FROM pg_catalog.pg_namespace WHERE nspname = 'public' \gset
\if :public_preserved
\else
DO $$ BEGIN RAISE EXCEPTION 'Existing public schema changed'; END $$;
\endif

\set bootstrap_preflight false
\ir 04_verify.sql
COMMIT;
\echo BOOTSTRAP_TEST_SCHEMA_COMMIT_ACKNOWLEDGED
