"""Exact notification catalog definitions and minimum runtime privileges."""

import re

from .migration_config import IDENTITIES, Failure, MigrationError
from .notification_schema import CHECKS, CHECK_COLUMNS
from .state_request_schema import STATE_CODES


def normalized_check(value):
    parts = re.split(r"('(?:[^']|'')*')", value)
    for index in range(0, len(parts), 2):
        parts[index] = re.sub(r"::(?:text\[\]|character varying|text)", "", parts[index])
        parts[index] = re.sub(r"[\s()]", "", parts[index])
    return ''.join(parts)


def verify_notifications(connection, identity, *, management=False):
    from .migration_validation import rows, scalar
    checks, check_columns = dict(CHECKS), dict(CHECK_COLUMNS)
    mutable = {"unsubscribed_at"}
    if management:
        from .notification_management_schema import NOTIFICATION_MUTABLE
        checks["notifications_revision_check"] = "preferences_revision >= 0"
        check_columns["notifications_revision_check"] = [10]
        mutable = set(NOTIFICATION_MUTABLE)

    def require(condition):
        if not condition:
            raise MigrationError(Failure.DRIFT)

    columns = rows(connection, """
        SELECT a.attname AS name, pg_catalog.format_type(a.atttypid,a.atttypmod) AS type,
               a.attnotnull AS required, a.attidentity AS identity,
               a.attgenerated AS generated, a.attisdropped AS dropped,
               a.attnum AS position, a.attndims AS dimensions,
               a.attcollation AS collation, a.atthasdef AS has_default,
               pg_catalog.pg_get_expr(d.adbin,d.adrelid) AS default_expression
        FROM pg_catalog.pg_attribute a
        LEFT JOIN pg_catalog.pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum
        WHERE a.attrelid='oaf_website.notifications'::pg_catalog.regclass AND a.attnum>0
        ORDER BY a.attnum
    """)
    collation = scalar(connection, "SELECT 'pg_catalog.\"default\"'::pg_catalog.regcollation::oid")
    expected = [dict(name=name, type=kind, required=n not in {6, 9}, identity="", generated="",
                     dropped=False, position=n, dimensions=0,
                     collation=collation if n in {1, 2, 6, 7} else 0,
                     has_default=n == 8, default_expression="CURRENT_TIMESTAMP" if n == 8 else None)
                for n, (name, kind) in enumerate([
                    ("unsubscribe_digest", "character varying(64)"), ("email", "character varying(254)"),
                    ("web_launch", "boolean"), ("android_launch", "boolean"), ("ios_launch", "boolean"),
                    ("state", "character varying(2)"), ("consent_version", "character varying(40)"),
                    ("created_at", "timestamp with time zone"), ("unsubscribed_at", "timestamp with time zone")], 1)]
    if management:
        expected.append(dict(name="preferences_revision", type="integer", required=True, identity="", generated="",
            dropped=False, position=10, dimensions=0, collation=0, has_default=True, default_expression="0"))
    require(columns == expected)
    constraints = rows(connection, """
        SELECT c.conname AS name, c.contype AS kind, c.convalidated AS validated,
               c.condeferrable AS deferrable, c.condeferred AS deferred,
               c.conkey AS keys, c.connoinherit AS no_inherit,
               c.conislocal AS local, c.coninhcount AS inherited,
               pg_catalog.pg_get_constraintdef(c.oid) AS definition
        FROM pg_catalog.pg_constraint c
        WHERE c.conrelid='oaf_website.notifications'::pg_catalog.regclass ORDER BY c.conname
    """)
    require(len(constraints) == len(checks) + 1)
    for constraint in constraints:
        name = constraint["name"]
        primary = name == "notifications_pk"
        require(primary or name in checks)
        definition = constraint["definition"]
        require(constraint == dict(name=name, kind="p" if primary else "c", validated=True,
                deferrable=False, deferred=False, keys=[1] if primary else check_columns[name],
                no_inherit=primary, local=True, inherited=0, definition=definition))
        if primary:
            require(definition == "PRIMARY KEY (unsubscribe_digest)")
        else:
            expected_expression = checks[name]
            if name == "notifications_state_check":
                expected_expression = "state IS NULL OR state = ANY (ARRAY[" + ",".join(repr(c) for c in STATE_CODES) + "])"
            require(normalized_check(definition) == normalized_check("CHECK (" + expected_expression + ")"))
    indexes = rows(connection, """
        SELECT c.relname AS name, i.indisunique AS unique, i.indisprimary AS primary,
               i.indisvalid AS valid, i.indisready AS ready, i.indislive AS live,
               i.indnullsnotdistinct AS nulls_not_distinct, i.indnatts AS attributes,
               i.indnkeyatts AS keys, i.indkey[0] AS column, i.indoption[0] AS option,
               i.indcollation[0] AS collation, am.amname AS method,
               op.opcname AS opclass, ns.nspname AS opnamespace,
               pg_catalog.pg_get_expr(i.indexprs,i.indrelid) AS expression,
               pg_catalog.pg_get_expr(i.indpred,i.indrelid) AS predicate
        FROM pg_catalog.pg_index i JOIN pg_catalog.pg_class c ON c.oid=i.indexrelid
        JOIN pg_catalog.pg_am am ON am.oid=c.relam
        JOIN pg_catalog.pg_opclass op ON op.oid=i.indclass[0]
        JOIN pg_catalog.pg_namespace ns ON ns.oid=op.opcnamespace
        WHERE i.indrelid='oaf_website.notifications'::pg_catalog.regclass ORDER BY c.relname
    """)
    require(indexes == [dict(name=name, unique=True, primary=primary, valid=True, ready=True,
                            live=True, nulls_not_distinct=False, attributes=1, keys=1, column=column,
                            option=0, collation=collation, method="btree", opclass="text_ops",
                            opnamespace="pg_catalog", expression=None, predicate=predicate)
                        for name, primary, column, predicate in [
                            ("notifications_active_email", False, 2, "(unsubscribed_at IS NULL)"),
                            ("notifications_pk", True, 1, None)]])
    acl = rows(connection, """
        SELECT CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE pg_catalog.pg_get_userbyid(a.grantee) END AS grantee,
               pg_catalog.pg_get_userbyid(a.grantor) AS grantor,
               a.privilege_type AS privilege, a.is_grantable AS grantable
        FROM pg_catalog.pg_class c CROSS JOIN LATERAL
             pg_catalog.aclexplode(COALESCE(c.relacl,pg_catalog.acldefault('r',c.relowner))) a
        WHERE c.oid='oaf_website.notifications'::pg_catalog.regclass
    """)
    privileges = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER", "MAINTAIN")
    expected_acl = {(identity.owner, identity.owner, p, False) for p in privileges}
    expected_acl |= {(identity.runtime, identity.owner, p, False) for p in ("SELECT", "INSERT")}
    require(len(acl) == len(expected_acl) and
            {(a['grantee'], a['grantor'], a['privilege'], a['grantable']) for a in acl} == expected_acl)
    column_acl = rows(connection, """
        SELECT c.attname AS column, pg_catalog.pg_get_userbyid(a.grantee) AS grantee,
               pg_catalog.pg_get_userbyid(a.grantor) AS grantor,
               a.privilege_type AS privilege, a.is_grantable AS grantable
        FROM pg_catalog.pg_attribute c CROSS JOIN LATERAL pg_catalog.aclexplode(c.attacl) a
        WHERE c.attrelid='oaf_website.notifications'::pg_catalog.regclass
    """)
    expected_column_acl = [dict(column=c, grantee=identity.runtime, grantor=identity.owner,
                               privilege="UPDATE", grantable=False) for c in mutable]
    require(len(column_acl) == len(expected_column_acl) and
            {tuple(sorted(r.items())) for r in column_acl} == {tuple(sorted(r.items())) for r in expected_column_acl})
    require(not scalar(connection, """
        SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_inherits
          WHERE inhrelid='oaf_website.notifications'::pg_catalog.regclass
             OR inhparent='oaf_website.notifications'::pg_catalog.regclass)
        OR EXISTS (SELECT 1 FROM pg_catalog.pg_policy WHERE polrelid='oaf_website.notifications'::pg_catalog.regclass)
    """))
    for registered in IDENTITIES.values():
        for role in (registered.owner, registered.runtime, registered.migrator):
            for privilege in privileges:
                expected_privilege = role == identity.owner or (role == identity.runtime and privilege in {"SELECT", "INSERT"})
                require(scalar(connection, "SELECT pg_catalog.has_table_privilege(:role,'oaf_website.notifications',:privilege)",
                               role=role, privilege=privilege) is expected_privilege)
                if role != identity.owner:
                    require(not scalar(connection, "SELECT pg_catalog.has_table_privilege(:role,'oaf_website.notifications',:privilege)",
                                       role=role, privilege=privilege + " WITH GRANT OPTION"))
            for column in expected:
                for privilege in ("SELECT", "INSERT", "UPDATE", "REFERENCES"):
                    allowed = role == identity.owner or (role == identity.runtime and
                              (privilege in {"SELECT", "INSERT"} or privilege == "UPDATE" and column['name'] in mutable))
                    require(scalar(connection, "SELECT pg_catalog.has_column_privilege(:role,'oaf_website.notifications',:column,:privilege)",
                                   role=role, column=column['name'], privilege=privilege) is allowed)
                    if role != identity.owner:
                        require(not scalar(connection, "SELECT pg_catalog.has_column_privilege(:role,'oaf_website.notifications',:column,:privilege)",
                                           role=role, column=column['name'], privilege=privilege + " WITH GRANT OPTION"))
    require(scalar(connection, """
        SELECT t.typrelid='oaf_website.notifications'::pg_catalog.regclass
               AND a.typelem=t.oid AND t.typarray=a.oid
               AND t.typisdefined AND a.typisdefined AND a.typrelid=0
               AND t.typelem=0 AND a.typarray=0 AND t.typcategory='C' AND a.typcategory='A'
               AND a.typsubscript='pg_catalog.array_subscript_handler'::pg_catalog.regproc
               AND t.typacl IS NOT NULL AND a.typacl IS NULL
        FROM pg_catalog.pg_type t JOIN pg_catalog.pg_type a ON a.oid=t.typarray
        WHERE t.oid=(SELECT reltype FROM pg_catalog.pg_class WHERE oid='oaf_website.notifications'::pg_catalog.regclass)
    """))
    type_acl = rows(connection, """
        SELECT pg_catalog.pg_get_userbyid(a.grantee) AS grantee,
               pg_catalog.pg_get_userbyid(a.grantor) AS grantor,
               a.privilege_type AS privilege, a.is_grantable AS grantable
        FROM pg_catalog.pg_type t CROSS JOIN LATERAL pg_catalog.aclexplode(t.typacl) a
        WHERE t.oid='oaf_website.notifications'::pg_catalog.regtype
    """)
    require(type_acl == [dict(grantee=identity.owner, grantor=identity.owner, privilege="USAGE", grantable=False)])
    for name in ("oaf_website.notifications", "oaf_website._notifications"):
        for registered in IDENTITIES.values():
            for role in (registered.owner, registered.runtime, registered.migrator):
                require(scalar(connection, "SELECT pg_catalog.has_type_privilege(:role,:name,'USAGE')",
                               role=role, name=name) is (role == identity.owner))
                if role != identity.owner:
                    require(not scalar(connection, "SELECT pg_catalog.has_type_privilege(:role,:name,'USAGE WITH GRANT OPTION')",
                                       role=role, name=name))
