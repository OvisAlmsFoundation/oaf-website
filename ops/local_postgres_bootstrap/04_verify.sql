-- Read-only catalog checks, also included inside bootstrap transactions.
-- Standalone: use the README's read-only transaction and expected_database.
-- bootstrap_preflight=true is ONLY for the documented pre-schema checks;
-- it reports PREFLIGHT_PASS, never completed bootstrap verification.
\set ON_ERROR_STOP on
\set ON_ERROR_ROLLBACK off
\set VERBOSITY terse
\set SHOW_CONTEXT never
\if :{?expected_database}
\else
DO $$ BEGIN RAISE EXCEPTION 'expected_database is required'; END $$;
\endif
\if :{?bootstrap_preflight}
\else
\set bootstrap_preflight false
\endif

SELECT pg_catalog.current_database() = :'expected_database'
       AND :'expected_database' IN ('oaf_website_dev', 'oaf_website_test')
       AND :'bootstrap_preflight' IN ('true', 'false') AS invocation_matches \gset
\if :invocation_matches
\else
DO $$ BEGIN RAISE EXCEPTION 'Unexpected verification database or mode'; END $$;
\endif

SET LOCAL search_path = pg_catalog, pg_temp;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';

DO $authority$
DECLARE
    ordinary_roles text[] := ARRAY[
        'oaf_website_app', 'oaf_website_test_app',
        'oaf_website_dev_migrator', 'oaf_website_test_migrator',
        'oaf_website_dev_schema_owner', 'oaf_website_test_schema_owner'];
    identity record;
    role_name text;
    role_id oid;
    database_name text;
    schema_id oid;
    local_owner oid;
    expected_connect boolean;
BEGIN
    IF session_user <> 'postgres' OR current_user <> 'postgres'
       OR NOT EXISTS (SELECT FROM pg_catalog.pg_roles
                      WHERE oid = 10 AND rolname = 'postgres' AND rolsuper AND rolcanlogin)
       OR pg_catalog.current_setting('server_version_num') <> '170011'
       OR pg_catalog.inet_server_addr() IS DISTINCT FROM '127.0.0.1'::inet
       OR pg_catalog.inet_server_port() IS DISTINCT FROM 5432 THEN
        RAISE EXCEPTION 'Bootstrap administrator, version or endpoint mismatch';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles
                   WHERE rolname = 'oaf_website_owner' AND NOT rolcanlogin)
       OR (SELECT count(*) FROM pg_catalog.pg_roles
           WHERE rolname = ANY(ordinary_roles)) <> 6 THEN
        RAISE EXCEPTION 'Required existing owner or ordinary roles missing';
    END IF;
    SELECT oid INTO schema_id FROM pg_catalog.pg_namespace WHERE nspname = 'oaf_website';
    SELECT oid INTO local_owner FROM pg_catalog.pg_roles WHERE rolname =
        CASE pg_catalog.current_database() WHEN 'oaf_website_dev'
            THEN 'oaf_website_dev_schema_owner' ELSE 'oaf_website_test_schema_owner' END;

    FOR role_name IN SELECT unnest(ordinary_roles) LOOP
        SELECT oid INTO STRICT role_id FROM pg_catalog.pg_roles WHERE rolname = role_name;
        IF EXISTS (SELECT FROM pg_catalog.pg_roles WHERE oid = role_id AND
            (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls
             OR (rolname NOT IN ('oaf_website_app', 'oaf_website_test_app') AND
                 (rolcanlogin OR rolinherit OR rolconfig IS NOT NULL
                  OR rolconnlimit <> -1 OR rolvaliduntil IS NOT NULL))
             OR (rolname IN ('oaf_website_app', 'oaf_website_test_app') AND NOT rolcanlogin)))
           OR pg_catalog.pg_has_role(role_id, 'oaf_website_owner', 'MEMBER') THEN
            RAISE EXCEPTION 'Ordinary role attributes or shared-owner authority mismatch';
        END IF;
        -- Inspect only NULL-ness, never select or emit a password/verifier value.
        IF role_name NOT IN ('oaf_website_app', 'oaf_website_test_app') AND EXISTS (
            SELECT FROM pg_catalog.pg_authid WHERE oid = role_id AND rolpassword IS NOT NULL) THEN
            RAISE EXCEPTION 'Premature bootstrap credential activation';
        END IF;
    END LOOP;
    IF EXISTS (SELECT FROM pg_catalog.pg_db_role_setting s
               JOIN pg_catalog.pg_roles r ON r.oid = s.setrole
               WHERE r.rolname = ANY(ordinary_roles[3:6])) THEN
        RAISE EXCEPTION 'Unexpected bootstrap role settings';
    END IF;
    IF EXISTS (SELECT FROM pg_catalog.pg_roles r CROSS JOIN pg_catalog.pg_parameter_acl p
               WHERE r.rolname = ANY(ordinary_roles)
                 AND pg_catalog.has_parameter_privilege(r.oid, p.parname, 'ALTER SYSTEM'))
       OR EXISTS (SELECT FROM pg_catalog.pg_roles r CROSS JOIN pg_catalog.pg_settings p
                  WHERE r.rolname = ANY(ordinary_roles)
                    AND p.context IN ('superuser', 'superuser-backend')
                    AND pg_catalog.has_parameter_privilege(r.oid, p.name, 'SET')) THEN
        RAISE EXCEPTION 'Unexpected ordinary-role server-parameter authority';
    END IF;

    -- Exact edges close indirect paths: no ordinary role has another parent,
    -- and no extra member can enter an ordinary role. No new administrator edge.
    IF (SELECT count(*) FROM pg_catalog.pg_auth_members m
        JOIN pg_catalog.pg_roles member ON member.oid = m.member
        JOIN pg_catalog.pg_roles parent ON parent.oid = m.roleid
        WHERE member.rolname = ANY(ordinary_roles) OR parent.rolname = ANY(ordinary_roles)) <> 2
       OR (SELECT count(*) FROM pg_catalog.pg_auth_members m
           JOIN pg_catalog.pg_roles member ON member.oid = m.member
           JOIN pg_catalog.pg_roles parent ON parent.oid = m.roleid
           WHERE (member.rolname, parent.rolname) IN (
                ('oaf_website_dev_migrator', 'oaf_website_dev_schema_owner'),
                ('oaf_website_test_migrator', 'oaf_website_test_schema_owner'))
             AND NOT m.inherit_option AND m.set_option AND NOT m.admin_option
             AND m.grantor = 10) <> 2 THEN
        RAISE EXCEPTION 'Expected exactly two matching restricted memberships granted by postgres';
    END IF;

    FOR identity IN SELECT * FROM (VALUES
        ('oaf_website_dev', 'oaf_website_app', 'oaf_website_dev_migrator', 'oaf_website_dev_schema_owner'),
        ('oaf_website_test', 'oaf_website_test_app', 'oaf_website_test_migrator', 'oaf_website_test_schema_owner')
    ) AS registry(database_name, runtime_name, migrator_name, owner_name) LOOP
        IF NOT EXISTS (SELECT FROM pg_catalog.pg_database d
                       JOIN pg_catalog.pg_roles r ON r.oid = d.datdba
                       WHERE d.datname = identity.database_name
                         AND r.rolname = 'oaf_website_owner' AND d.datallowconn AND NOT d.datistemplate)
           OR EXISTS (SELECT FROM pg_catalog.pg_database d CROSS JOIN LATERAL
                      pg_catalog.aclexplode(COALESCE(d.datacl, pg_catalog.acldefault('d', d.datdba))) a
                      WHERE d.datname = identity.database_name AND a.grantee = 0) THEN
            RAISE EXCEPTION 'Database ownership, availability or PUBLIC restrictions mismatch';
        END IF;
        FOREACH role_name IN ARRAY ARRAY[identity.runtime_name, identity.migrator_name, identity.owner_name] LOOP
            FOREACH database_name IN ARRAY ARRAY['oaf_website_dev', 'oaf_website_test'] LOOP
                expected_connect := database_name = identity.database_name
                    AND (role_name = identity.runtime_name OR
                         (role_name = identity.migrator_name AND schema_id IS NOT NULL));
                -- The other database's matching migrator CONNECT may be pending
                -- or complete. Its local schema/defaults are NOT inspected here.
                IF NOT (role_name = identity.migrator_name AND database_name = identity.database_name
                        AND database_name <> pg_catalog.current_database()) AND
                   pg_catalog.has_database_privilege(role_name, database_name, 'CONNECT')
                       IS DISTINCT FROM expected_connect THEN
                    RAISE EXCEPTION 'Effective database CONNECT isolation mismatch';
                END IF;
                IF pg_catalog.has_database_privilege(role_name, database_name,
                    'CREATE, TEMPORARY, CONNECT WITH GRANT OPTION, CREATE WITH GRANT OPTION, TEMPORARY WITH GRANT OPTION') THEN
                    RAISE EXCEPTION 'Unexpected database DDL, TEMP or grant authority';
                END IF;
            END LOOP;
        END LOOP;
    END LOOP;

    IF NOT EXISTS (SELECT FROM pg_catalog.pg_namespace WHERE nspname = 'public')
       OR EXISTS (SELECT FROM pg_catalog.pg_namespace n CROSS JOIN LATERAL
                  pg_catalog.aclexplode(COALESCE(n.nspacl, pg_catalog.acldefault('n', n.nspowner))) a
                  WHERE n.nspname = 'public' AND a.grantee = 0 AND a.privilege_type = 'CREATE')
       OR EXISTS (SELECT FROM pg_catalog.pg_namespace n CROSS JOIN
                  pg_catalog.pg_roles r WHERE r.rolname = ANY(ordinary_roles)
                    AND n.nspname !~ '^pg_(temp|toast_temp)_[0-9]+$'
                    AND pg_catalog.has_schema_privilege(r.oid, n.oid, 'CREATE')
                    AND NOT (n.oid IS NOT DISTINCT FROM schema_id AND r.oid = local_owner)) THEN
        RAISE EXCEPTION 'Unexpected PUBLIC or ordinary-role schema CREATE authority';
    END IF;

    -- Shared ownership dependencies cover every catalog, not just tables.
    -- Runtime/migrator ownership anywhere is forbidden. Remote schema owners
    -- may own objects only in their registered DB; remote object ACLs are unknown.
    IF EXISTS (SELECT FROM pg_catalog.pg_shdepend d
        JOIN pg_catalog.pg_roles r ON r.oid = d.refobjid
        WHERE d.refclassid = 'pg_catalog.pg_authid'::regclass AND d.deptype = 'o'
          AND r.rolname = ANY(ordinary_roles) AND NOT (
            r.rolname IN ('oaf_website_dev_schema_owner', 'oaf_website_test_schema_owner')
            AND d.dbid = (SELECT oid FROM pg_catalog.pg_database WHERE datname =
                CASE r.rolname WHEN 'oaf_website_dev_schema_owner'
                    THEN 'oaf_website_dev' ELSE 'oaf_website_test' END)
            AND (d.dbid <> (SELECT oid FROM pg_catalog.pg_database WHERE datname = pg_catalog.current_database())
                 OR (d.classid = 'pg_catalog.pg_namespace'::regclass AND d.objid IS NOT DISTINCT FROM schema_id)
                 OR (d.classid = 'pg_catalog.pg_default_acl'::regclass AND d.objid IN (
                    SELECT oid FROM pg_catalog.pg_default_acl WHERE defaclrole = local_owner
                      AND defaclnamespace = 0 AND defaclobjtype IN ('r', 'S', 'f', 'T')))))) THEN
        RAISE EXCEPTION 'Unexpected ordinary-role object ownership';
    END IF;
END
$authority$;

\if :bootstrap_preflight
DO $schema_absent$
BEGIN
    IF EXISTS (SELECT FROM pg_catalog.pg_namespace WHERE nspname = 'oaf_website') THEN
        RAISE EXCEPTION 'Application schema collision; existing schema must not be adopted';
    END IF;
    IF EXISTS (SELECT FROM pg_catalog.pg_default_acl d JOIN pg_catalog.pg_roles r ON r.oid = d.defaclrole
               WHERE r.rolname IN ('oaf_website_dev_schema_owner', 'oaf_website_test_schema_owner')) THEN
        RAISE EXCEPTION 'Unexpected pre-bootstrap schema-owner defaults';
    END IF;
END
$schema_absent$;
\echo BOOTSTRAP_PREFLIGHT_PASS :expected_database
\else
DO $schema_present$
DECLARE
    schema_row record;
    runtime_id oid;
    kind "char";
    effective_acl aclitem[];
BEGIN
    SELECT * INTO STRICT schema_row FROM pg_catalog.pg_namespace WHERE nspname = 'oaf_website';
    IF schema_row.nspowner IS DISTINCT FROM (SELECT oid FROM pg_catalog.pg_roles WHERE rolname =
        CASE pg_catalog.current_database() WHEN 'oaf_website_dev'
            THEN 'oaf_website_dev_schema_owner' ELSE 'oaf_website_test_schema_owner' END) THEN
        RAISE EXCEPTION 'Application schema ownership mismatch';
    END IF;
    SELECT oid INTO STRICT runtime_id FROM pg_catalog.pg_roles WHERE rolname =
        CASE pg_catalog.current_database() WHEN 'oaf_website_dev'
            THEN 'oaf_website_app' ELSE 'oaf_website_test_app' END;

    -- Exact ACL: owner USAGE/CREATE and matching runtime USAGE, no grant options.
    IF EXISTS (
        WITH actual AS (SELECT grantor, grantee, privilege_type, is_grantable FROM
            pg_catalog.aclexplode(COALESCE(schema_row.nspacl, pg_catalog.acldefault('n', schema_row.nspowner)))),
        expected AS (SELECT schema_row.nspowner, schema_row.nspowner, 'USAGE'::text, false
            UNION ALL SELECT schema_row.nspowner, schema_row.nspowner, 'CREATE', false
            UNION ALL SELECT schema_row.nspowner, runtime_id, 'USAGE', false)
        (SELECT * FROM actual EXCEPT ALL SELECT * FROM expected)
        UNION ALL (SELECT * FROM expected EXCEPT ALL SELECT * FROM actual))
       OR NOT pg_catalog.has_schema_privilege(runtime_id, schema_row.oid, 'USAGE')
       OR pg_catalog.has_schema_privilege(runtime_id, schema_row.oid, 'CREATE') THEN
        RAISE EXCEPTION 'Application schema permissions mismatch';
    END IF;

    -- No inbound/outbound local schema dependency is approved at empty base.
    -- This catches tables, types, routines, operators, collations, extensions,
    -- other schema-bound objects and schema-specific additive default grants.
    IF EXISTS (SELECT FROM pg_catalog.pg_depend WHERE
        (classid = 'pg_catalog.pg_namespace'::regclass AND objid = schema_row.oid) OR
        (refclassid = 'pg_catalog.pg_namespace'::regclass AND refobjid = schema_row.oid)) THEN
        RAISE EXCEPTION 'Unexpected application objects or schema dependencies';
    END IF;
    IF EXISTS (SELECT FROM pg_catalog.pg_default_acl WHERE defaclrole = schema_row.nspowner
               AND (defaclnamespace <> 0 OR defaclobjtype NOT IN ('r', 'S', 'f', 'T'))) THEN
        RAISE EXCEPTION 'Unexpected schema-owner default privilege scope';
    END IF;
    FOREACH kind IN ARRAY ARRAY['r', 'S', 'f', 'T']::"char"[] LOOP
        SELECT COALESCE((SELECT defaclacl FROM pg_catalog.pg_default_acl
                        WHERE defaclrole = schema_row.nspowner AND defaclnamespace = 0 AND defaclobjtype = kind),
                       pg_catalog.acldefault(
    CASE WHEN kind = 'S' THEN 's'::"char" ELSE kind END,
    schema_row.nspowner
)) INTO effective_acl;
        IF EXISTS (
            WITH actual AS (SELECT grantor, grantee, privilege_type, is_grantable
                            FROM pg_catalog.aclexplode(effective_acl)),
            expected AS (SELECT grantor, grantee, privilege_type, is_grantable
                         FROM pg_catalog.aclexplode(pg_catalog.acldefault(
    CASE WHEN kind = 'S' THEN 's'::"char" ELSE kind END,
    schema_row.nspowner
))
                         WHERE grantee = schema_row.nspowner)
            (SELECT * FROM actual EXCEPT ALL SELECT * FROM expected)
            UNION ALL (SELECT * FROM expected EXCEPT ALL SELECT * FROM actual)) THEN
            RAISE EXCEPTION 'Global defaults must be exactly owner-only for tables, sequences, routines and types';
        END IF;
    END LOOP;
END
$schema_present$;
\echo BOOTSTRAP_VERIFY_PASS :expected_database
\endif
