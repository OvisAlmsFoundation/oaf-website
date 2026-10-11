"""Exact feature definitions and least-privilege checks for revision 0002."""

import re

from .migration_config import IDENTITIES, Failure, MigrationError
from .state_request_schema import STATE_CODES


def verify_state_requests(connection, identity):
    from .migration_validation import rows, scalar

    columns = rows(connection, """
        SELECT a.attname AS name, pg_catalog.format_type(a.atttypid,a.atttypmod) AS type,
               a.attnotnull AS required, a.attidentity AS identity,
               a.attgenerated AS generated, a.attisdropped AS dropped,
               a.attnum AS position, a.attndims AS dimensions,
               a.attcollation AS collation, a.atthasdef AS has_default,
               pg_catalog.pg_get_expr(d.adbin,d.adrelid) AS default_expression,
               a.atttypid IN ('pg_catalog.varchar'::pg_catalog.regtype,
                             'pg_catalog.uuid'::pg_catalog.regtype,
                             'pg_catalog.timestamptz'::pg_catalog.regtype) AS builtin
        FROM pg_catalog.pg_attribute a
        LEFT JOIN pg_catalog.pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum
        WHERE a.attrelid='oaf_website.state_requests'::pg_catalog.regclass AND a.attnum>0
        ORDER BY a.attnum
    """)
    default_collation = scalar(connection, "SELECT 'pg_catalog.\"default\"'::pg_catalog.regcollation::oid")
    expected_columns = [
        dict(name=name, type=kind, required=True, identity="", generated="", dropped=False,
             position=n, dimensions=0, collation=default_collation if n == 1 else 0,
             has_default=n == 3, default_expression="CURRENT_TIMESTAMP" if n == 3 else None,
             builtin=True)
        for n, (name, kind) in enumerate([
            ("state", "character varying(2)"), ("browser_key", "uuid"),
            ("created_at", "timestamp with time zone")], 1)
    ]
    if columns != expected_columns:
        raise MigrationError(Failure.DRIFT)
    constraints = rows(connection, """
        SELECT c.conname AS name, c.contype AS kind, c.convalidated AS validated,
               c.condeferrable AS deferrable, c.condeferred AS deferred,
               c.conkey AS keys, c.connoinherit AS no_inherit,
               c.conislocal AS local, c.coninhcount AS inherited,
               pg_catalog.pg_get_constraintdef(c.oid) AS definition
        FROM pg_catalog.pg_constraint c
        WHERE c.conrelid='oaf_website.state_requests'::pg_catalog.regclass
        ORDER BY c.conname
    """)
    if len(constraints) != 2:
        raise MigrationError(Failure.DRIFT)
    pk, check = constraints
    expected_common = dict(validated=True, deferrable=False, deferred=False,
                           no_inherit=False, local=True, inherited=0)
    if pk != dict(expected_common, no_inherit=True, name="state_requests_pk", kind="p", keys=[1, 2],
                  definition="PRIMARY KEY (state, browser_key)"):
        raise MigrationError(Failure.DRIFT)
    definition = check.get("definition", "")
    normalized = re.sub(r"::(?:text\[\]|character varying|text)", "", definition)
    normalized = re.sub(r"[\s()]", "", normalized)
    if (check != dict(expected_common, name="state_requests_state_check", kind="c", keys=[1],
                      definition=definition)
            or normalized != "CHECKstate=ANYARRAY[" + ",".join(repr(code) for code in STATE_CODES) + "]"):
        raise MigrationError(Failure.DRIFT)
    if not scalar(connection, """
        SELECT i.indisunique AND i.indisprimary AND i.indisvalid AND i.indisready
               AND i.indislive AND NOT i.indnullsnotdistinct
               AND i.indexprs IS NULL AND i.indpred IS NULL
               AND i.indnatts=2 AND i.indnkeyatts=2 AND am.amname='btree'
               AND i.indkey[0]=1 AND i.indkey[1]=2
               AND i.indoption[0]=0 AND i.indoption[1]=0
               AND i.indcollation[0]='pg_catalog."default"'::pg_catalog.regcollation
               AND i.indcollation[1]=0
               AND op1.opcname='text_ops' AND ns1.nspname='pg_catalog'
               AND op2.opcname='uuid_ops' AND ns2.nspname='pg_catalog'
        FROM pg_catalog.pg_index i JOIN pg_catalog.pg_class c ON c.oid=i.indexrelid
        JOIN pg_catalog.pg_am am ON am.oid=c.relam
        JOIN pg_catalog.pg_opclass op1 ON op1.oid=i.indclass[0]
        JOIN pg_catalog.pg_namespace ns1 ON ns1.oid=op1.opcnamespace
        JOIN pg_catalog.pg_opclass op2 ON op2.oid=i.indclass[1]
        JOIN pg_catalog.pg_namespace ns2 ON ns2.oid=op2.opcnamespace
        WHERE i.indexrelid='oaf_website.state_requests_pk'::pg_catalog.regclass
          AND i.indrelid='oaf_website.state_requests'::pg_catalog.regclass
    """):
        raise MigrationError(Failure.DRIFT)
    acl = rows(connection, """
        SELECT CASE WHEN a.grantee=0 THEN 'PUBLIC'
                    ELSE pg_catalog.pg_get_userbyid(a.grantee) END AS grantee,
               pg_catalog.pg_get_userbyid(a.grantor) AS grantor,
               a.privilege_type AS privilege, a.is_grantable AS grantable
        FROM pg_catalog.pg_class c CROSS JOIN LATERAL
             pg_catalog.aclexplode(COALESCE(c.relacl, pg_catalog.acldefault('r',c.relowner))) a
        WHERE c.oid='oaf_website.state_requests'::pg_catalog.regclass
    """)
    privileges = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER", "MAINTAIN")
    expected_acl = {(identity.owner, identity.owner, p, False) for p in privileges}
    expected_acl |= {(identity.runtime, identity.owner, p, False) for p in ("SELECT", "INSERT")}
    if ({(a['grantee'], a['grantor'], a['privilege'], a['grantable']) for a in acl} != expected_acl
            or len(acl) != len(expected_acl)):
        raise MigrationError(Failure.DRIFT)
    if scalar(connection, """
        SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_attribute
            WHERE attrelid='oaf_website.state_requests'::pg_catalog.regclass AND attacl IS NOT NULL)
           OR EXISTS (SELECT 1 FROM pg_catalog.pg_inherits
            WHERE inhrelid='oaf_website.state_requests'::pg_catalog.regclass
               OR inhparent='oaf_website.state_requests'::pg_catalog.regclass)
    """):
        raise MigrationError(Failure.DRIFT)
    for i in IDENTITIES.values():
        for role in (i.owner, i.runtime, i.migrator):
            for privilege in privileges:
                expected = role == identity.owner or (role == identity.runtime and privilege in {"SELECT", "INSERT"})
                if scalar(connection,
                        "SELECT pg_catalog.has_table_privilege(:role, 'oaf_website.state_requests', :privilege)",
                        role=role, privilege=privilege) is not expected:
                    raise MigrationError(Failure.DRIFT)
                if role != identity.owner and scalar(connection,
                        "SELECT pg_catalog.has_table_privilege(:role, 'oaf_website.state_requests', :privilege)",
                        role=role, privilege=privilege + " WITH GRANT OPTION"):
                    raise MigrationError(Failure.DRIFT)
            for privilege in ("SELECT", "INSERT", "UPDATE", "REFERENCES"):
                expected = role == identity.owner or (role == identity.runtime and privilege in {"SELECT", "INSERT"})
                if scalar(connection,
                        "SELECT pg_catalog.has_any_column_privilege(:role, 'oaf_website.state_requests', :privilege)",
                        role=role, privilege=privilege) is not expected:
                    raise MigrationError(Failure.DRIFT)
    # The generated array has no independent ACL; its effective privileges
    # must follow the explicitly private table row type.
    if not scalar(connection, """
        SELECT t.typrelid='oaf_website.state_requests'::pg_catalog.regclass
               AND a.typelem=t.oid AND t.typarray=a.oid
               AND t.typisdefined AND a.typisdefined AND a.typrelid=0
               AND t.typelem=0 AND a.typarray=0
               AND t.typcategory='C' AND a.typcategory='A'
               AND a.typsubscript='pg_catalog.array_subscript_handler'::pg_catalog.regproc
               AND t.typacl IS NOT NULL AND a.typacl IS NULL
        FROM pg_catalog.pg_type t JOIN pg_catalog.pg_type a ON a.oid=t.typarray
        WHERE t.oid=(SELECT reltype FROM pg_catalog.pg_class
                     WHERE oid='oaf_website.state_requests'::pg_catalog.regclass)
    """):
        raise MigrationError(Failure.DRIFT)
    type_acl = rows(connection, """
        SELECT pg_catalog.pg_get_userbyid(a.grantee) AS grantee,
               pg_catalog.pg_get_userbyid(a.grantor) AS grantor,
               a.privilege_type AS privilege, a.is_grantable AS grantable
        FROM pg_catalog.pg_type t CROSS JOIN LATERAL pg_catalog.aclexplode(t.typacl) a
        WHERE t.oid='oaf_website.state_requests'::pg_catalog.regtype
    """)
    if type_acl != [dict(grantee=identity.owner, grantor=identity.owner, privilege="USAGE", grantable=False)]:
        raise MigrationError(Failure.DRIFT)
    for name in ("oaf_website.state_requests", "oaf_website._state_requests"):
        for i in IDENTITIES.values():
            for role in (i.owner, i.runtime, i.migrator):
                if scalar(connection, "SELECT pg_catalog.has_type_privilege(:role, :name, 'USAGE')",
                          role=role, name=name) is not (role == identity.owner):
                    raise MigrationError(Failure.DRIFT)
                if role != identity.owner and scalar(connection,
                        "SELECT pg_catalog.has_type_privilege(:role, :name, 'USAGE WITH GRANT OPTION')",
                        role=role, name=name):
                    raise MigrationError(Failure.DRIFT)
