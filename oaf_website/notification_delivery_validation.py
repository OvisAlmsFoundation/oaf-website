"""Fail-closed catalog/ACL verification for the additive delivery inventory.

Synthetic snapshots prove validator decisions only. PostgreSQL 17 rendering,
FK-trigger/dependency and effective ACL semantics require separate live approval.
"""

import re
from sqlalchemy import Boolean, CheckConstraint, ForeignKeyConstraint, PrimaryKeyConstraint, String, Integer
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import AddConstraint, CreateIndex
from .migration_config import IDENTITIES, Failure, MigrationError
from .notification_delivery_schema import TABLES, MUTABLE, FK_TRIGGERS


def require(condition):
    if not condition:
        raise MigrationError(Failure.DRIFT)


def check_tree(definition, columns=()):
    """Canonicalize only the CHECK grammar used by the 0004/0005 contract.

    No SQL is executed or translated to Python. IN/NOT IN and = ANY/<> ALL
    share a tree only for nonempty text lists without NULL elements. Erase
    only binary-compatible, unbounded text/varchar casts on text operands.
    """
    require(isinstance(definition, str) and len(definition) <= 16384)
    tokens = []
    end = 0
    for match in re.finditer(r"\s+|'(?:[^']|'')*'|[a-zA-Z_][a-zA-Z_0-9]*|[0-9]+|::|<>|<=|>=|[()[\],=<>~]", definition):
        require(match.start() == end)
        token = match.group()
        if not token.isspace():
            tokens.append(token)
        end = match.end()
    require(end == len(definition))
    text_columns = {c.name for c in columns if isinstance(c.type, String)}
    position = 0

    def peek():
        return tokens[position].upper() if position < len(tokens) else ""

    def take(value):
        nonlocal position
        if peek() == value:
            position += 1
            return True
        return False

    def expect(value):
        require(take(value))

    def combine(operator, left, right):
        # Associativity only: never commute operands or discard grouping.
        children = []
        for node in (left, right):
            children.extend(node[1] if node[0] == operator else (node,))
        return (operator, tuple(children))

    def atom():
        nonlocal position
        if take("("):
            node = disjunction()
            expect(")")
        elif take("ARRAY"):
            expect("[")
            values = [atom()]
            while take(","):
                values.append(atom())
            expect("]")
            require(all(value[0] == "text" for value in values))
            node = ("array", tuple(values))
        else:
            require(position < len(tokens))
            value = tokens[position]
            position += 1
            if value.startswith("'"):
                node = ("text", value[1:-1].replace("''", "'"))
            elif value.isdigit():
                require(len(value) <= 10)
                node = ("integer", int(value))
            else:
                require(re.fullmatch(r"[a-zA-Z_][a-zA-Z_0-9]*", value) is not None)
                node = ("column", value.lower())
        while take("::"):
            if not take("TEXT"):
                expect("CHARACTER")
                expect("VARYING")
            if take("["):
                expect("]")
                require(node[0] == "array")
            else:
                require(node[0] == "text" or node[0] == "column" and node[1] in text_columns)
        return node

    def comparison():
        left = atom()
        if take("IS"):
            negative = take("NOT")
            expect("NULL")
            return ("is_not_null" if negative else "is_null", left)
        if take("BETWEEN"):
            lower = atom()
            expect("AND")
            return combine("and", (">=", left, lower), ("<=", left, atom()))
        negative = take("NOT")
        if take("IN"):
            expect("(")
            values = [atom()]
            while take(","):
                values.append(atom())
            expect(")")
            require(all(value[0] == "text" for value in values))
            return ("not_in" if negative else "in", left, tuple(values))
        require(not negative)
        operator = peek()
        if operator in {"=", "<>", "<", "<=", ">", ">=", "~"}:
            expect(operator)
            quantifier = peek()
            if quantifier in {"ANY", "ALL"}:
                expect(quantifier)
                require((operator, quantifier) in {("=", "ANY"), ("<>", "ALL")})
                expect("(")
                values = atom()
                expect(")")
                require(values[0] == "array")
                return ("in" if operator == "=" else "not_in", left, values[1])
            return (operator, left, atom())
        return left

    def conjunction():
        node = comparison()
        while take("AND"):
            node = combine("and", node, comparison())
        return node

    def disjunction():
        node = conjunction()
        while take("OR"):
            node = combine("or", node, conjunction())
        return node

    expect("CHECK")
    try:
        tree = disjunction()
    except RecursionError:
        raise MigrationError(Failure.DRIFT) from None
    require(position == len(tokens))
    return tree


def verify_foreign_key(connection, table, constraint):
    """Compare catalog identity and behavior, independent of deparser spelling."""
    from .migration_validation import rows
    actual = rows(connection, """
        SELECT n.nspname AS referenced_schema, r.relname AS referenced_table,
               ARRAY(SELECT a.attname::text FROM pg_catalog.unnest(c.conkey) WITH ORDINALITY AS k(num, pos)
                     JOIN pg_catalog.pg_attribute a ON a.attrelid=c.conrelid AND a.attnum=k.num
                     ORDER BY k.pos) AS columns,
               ARRAY(SELECT a.attname::text FROM pg_catalog.unnest(c.confkey) WITH ORDINALITY AS k(num, pos)
                     JOIN pg_catalog.pg_attribute a ON a.attrelid=c.confrelid AND a.attnum=k.num
                     ORDER BY k.pos) AS referenced_columns,
               c.confupdtype::text AS on_update, c.confdeltype::text AS on_delete,
               c.confmatchtype::text AS match
        FROM pg_catalog.pg_constraint c JOIN pg_catalog.pg_class r ON r.oid=c.confrelid
        JOIN pg_catalog.pg_namespace n ON n.oid=r.relnamespace
        WHERE c.conrelid=CAST(:table AS pg_catalog.regclass) AND c.conname=:constraint AND c.contype='f'
    """, table=table, constraint=constraint.name)
    target = constraint.elements[0].column.table
    actions = {None: "a", "NO ACTION": "a", "RESTRICT": "r", "CASCADE": "c", "SET NULL": "n", "SET DEFAULT": "d"}
    require(actual == [dict(referenced_schema=target.schema, referenced_table=target.name,
        columns=[c.parent.name for c in constraint.elements],
        referenced_columns=[c.column.name for c in constraint.elements],
        on_update=actions[constraint.onupdate], on_delete=actions[constraint.ondelete],
        match={None: "s", "SIMPLE": "s", "FULL": "f", "PARTIAL": "p"}[constraint.match])])


def column_contract(item):
    return [dict(name=c.name, type="character varying(" + str(c.type.length) + ")" if isinstance(c.type, String)
                 else "integer" if isinstance(c.type, Integer) else "boolean" if isinstance(c.type, Boolean) else "timestamp with time zone",
                 required=not c.nullable, identity="", generated="", dropped=False, position=n,
                 dimensions=0, default_collation=isinstance(c.type, String), has_default=c.server_default is not None)
            for n, c in enumerate(item.columns, 1)]


def constraint_definition(constraint):
    sql = str(AddConstraint(constraint, isolate_from_table=False).compile(dialect=postgresql.dialect()))
    return sql.split(" ADD CONSTRAINT " + constraint.name + " ", 1)[1]


def index_contract(item):
    result = []
    for c in item.constraints:
        if isinstance(c, PrimaryKeyConstraint) or type(c).__name__ == "UniqueConstraint":
            result.append(dict(name=c.name, definition="CREATE UNIQUE INDEX " + c.name + " ON oaf_website."
                + item.name + " USING btree (" + ", ".join(col.name for col in c.columns) + ")"))
    for index in item.indexes:
        definition = str(CreateIndex(index).compile(dialect=postgresql.dialect()))
        definition = definition.replace(" ON oaf_website." + item.name + " (", " ON oaf_website." + item.name + " USING btree (")
        result.append(dict(name=index.name, definition=definition))
    return sorted(result, key=lambda r: r["name"])


def verify_delivery(connection, identity, *, tables=TABLES, mutable=MUTABLE, expected_triggers=FK_TRIGGERS):
    from .migration_validation import rows, scalar
    for item in tables:
        name = "oaf_website." + item.name
        columns = rows(connection, """
            SELECT a.attname AS name, pg_catalog.format_type(a.atttypid,a.atttypmod) AS type,
                   a.attnotnull AS required, a.attidentity AS identity, a.attgenerated AS generated,
                   a.attisdropped AS dropped, a.attnum AS position, a.attndims AS dimensions,
                   a.attcollation='pg_catalog."default"'::pg_catalog.regcollation AS default_collation,
                   a.atthasdef AS has_default
            FROM pg_catalog.pg_attribute a WHERE a.attrelid=CAST(:table AS pg_catalog.regclass) AND a.attnum>0 ORDER BY a.attnum
        """, table=name)
        require(columns == column_contract(item))
        if any(c.server_default is not None for c in item.columns):
            defaults = rows(connection, """
                SELECT a.attname AS default_column, pg_catalog.pg_get_expr(d.adbin,d.adrelid) AS expression
                FROM pg_catalog.pg_attribute a JOIN pg_catalog.pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum
                WHERE a.attrelid=CAST(:table AS pg_catalog.regclass) ORDER BY a.attnum
            """, table=name)
            expected_defaults = {c.name: str(c.server_default.arg) for c in item.columns if c.server_default is not None}
            require(len(defaults) == len(expected_defaults) and {d["default_column"] for d in defaults} == set(expected_defaults))
            for default in defaults:
                expected = expected_defaults[default["default_column"]]
                require(check_tree("CHECK (" + default["expression"] + " = " + expected + ")", item.columns)
                        == check_tree("CHECK (" + expected + " = " + expected + ")", item.columns))
        actual = rows(connection, """
            SELECT c.conname AS name, c.contype AS kind, c.convalidated AS validated,
                   c.condeferrable AS deferrable, c.condeferred AS deferred, c.conislocal AS local,
                   c.coninhcount AS inherited, pg_catalog.pg_get_constraintdef(c.oid) AS definition
            FROM pg_catalog.pg_constraint c WHERE c.conrelid=CAST(:table AS pg_catalog.regclass) ORDER BY c.conname
        """, table=name)
        expected = {c.name: c for c in item.constraints}
        require(len(actual) == len(expected) and {c["name"] for c in actual} == set(expected))
        for record in actual:
            c = expected[record["name"]]
            kind = "c" if isinstance(c, CheckConstraint) else "f" if isinstance(c, ForeignKeyConstraint) else "p" if isinstance(c, PrimaryKeyConstraint) else "u"
            require(record == dict(name=c.name, kind=kind, validated=True, deferrable=False,
                                   deferred=False, local=True, inherited=0, definition=record["definition"]))
            definition = constraint_definition(c)
            if kind == "c":
                require(check_tree(record["definition"], item.columns) == check_tree(definition, item.columns))
            elif kind == "f":
                verify_foreign_key(connection, name, c)
            else:
                require(" ".join(record["definition"].split()) == " ".join(definition.split()))
        indexes = rows(connection, """
            SELECT c.relname AS name, pg_catalog.pg_get_indexdef(i.indexrelid) AS definition
            FROM pg_catalog.pg_index i JOIN pg_catalog.pg_class c ON c.oid=i.indexrelid
            WHERE i.indrelid=CAST(:table AS pg_catalog.regclass) AND i.indisvalid AND i.indisready AND i.indislive
              AND NOT i.indnullsnotdistinct ORDER BY c.relname
        """, table=name)
        expected_indexes = index_contract(item)
        require(len(indexes) == len(expected_indexes))
        for actual_index, expected_index in zip(indexes, expected_indexes):
            require(actual_index["name"] == expected_index["name"])
            expected_base, separator, expected_where = expected_index["definition"].partition(" WHERE ")
            if separator:
                actual_base, actual_separator, actual_where = actual_index["definition"].partition(" WHERE ")
                require(actual_base == expected_base and actual_separator == separator)
                require(check_tree("CHECK (" + actual_where + ")", item.columns) ==
                        check_tree("CHECK (" + expected_where + ")", item.columns))
            else:
                require(actual_index == expected_index)
        require(not scalar(connection, """
            SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_inherits WHERE inhrelid=CAST(:table AS pg_catalog.regclass) OR inhparent=CAST(:table AS pg_catalog.regclass))
              OR EXISTS (SELECT 1 FROM pg_catalog.pg_policy WHERE polrelid=CAST(:table AS pg_catalog.regclass))
        """, table=name))
        privileges = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER", "MAINTAIN")
        acl = rows(connection, """
            SELECT CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE pg_catalog.pg_get_userbyid(a.grantee) END AS grantee,
                   pg_catalog.pg_get_userbyid(a.grantor) AS grantor, a.privilege_type AS privilege, a.is_grantable AS grantable
            FROM pg_catalog.pg_class c CROSS JOIN LATERAL pg_catalog.aclexplode(COALESCE(c.relacl,pg_catalog.acldefault('r',c.relowner))) a
            WHERE c.oid=CAST(:table AS pg_catalog.regclass)
        """, table=name)
        expected_acl = {(identity.owner, identity.owner, p, False) for p in privileges} | {
            (identity.runtime, identity.owner, p, False) for p in ("SELECT", "INSERT")}
        require(len(acl) == len(expected_acl) and {tuple(a[k] for k in ("grantee", "grantor", "privilege", "grantable")) for a in acl} == expected_acl)
        column_acl = rows(connection, """
            SELECT c.attname AS column, pg_catalog.pg_get_userbyid(a.grantee) AS grantee,
                   pg_catalog.pg_get_userbyid(a.grantor) AS grantor, a.privilege_type AS privilege, a.is_grantable AS grantable
            FROM pg_catalog.pg_attribute c CROSS JOIN LATERAL pg_catalog.aclexplode(c.attacl) a
            WHERE c.attrelid=CAST(:table AS pg_catalog.regclass)
        """, table=name)
        expected_columns = {(c, identity.runtime, identity.owner, "UPDATE", False) for c in mutable[item.name]}
        require(len(column_acl) == len(expected_columns) and {tuple(a[k] for k in ("column", "grantee", "grantor", "privilege", "grantable")) for a in column_acl} == expected_columns)
        type_acl = rows(connection, """
            SELECT pg_catalog.pg_get_userbyid(a.grantee) AS grantee, pg_catalog.pg_get_userbyid(a.grantor) AS grantor,
                   a.privilege_type AS privilege, a.is_grantable AS grantable
            FROM pg_catalog.pg_type t CROSS JOIN LATERAL pg_catalog.aclexplode(t.typacl) a WHERE t.oid=CAST(:table AS pg_catalog.regtype)
        """, table=name)
        require(type_acl == [dict(grantee=identity.owner, grantor=identity.owner, privilege="USAGE", grantable=False)])
        # One psycopg parameter must stay text before the two distinct OID lookups.
        require(scalar(connection, """
            SELECT t.typrelid=CAST(CAST(:table AS pg_catalog.text) AS pg_catalog.regclass) AND a.typelem=t.oid AND t.typarray=a.oid
               AND t.typisdefined AND a.typisdefined AND a.typrelid=0 AND t.typelem=0 AND a.typarray=0
               AND t.typcategory='C' AND a.typcategory='A' AND a.typsubscript='pg_catalog.array_subscript_handler'::pg_catalog.regproc
               AND t.typacl IS NOT NULL AND a.typacl IS NULL
            FROM pg_catalog.pg_type t JOIN pg_catalog.pg_type a ON a.oid=t.typarray WHERE t.oid=CAST(CAST(:table AS pg_catalog.text) AS pg_catalog.regtype)
        """, table=name) is True)
        for registered in IDENTITIES.values():
            for role in (registered.owner, registered.runtime, registered.migrator):
                for privilege in privileges:
                    permitted = role == identity.owner or role == identity.runtime and privilege in {"SELECT", "INSERT"}
                    require(scalar(connection, "SELECT pg_catalog.has_table_privilege(:role,:table,:privilege)", role=role, table=name, privilege=privilege) is permitted)
                    if role != identity.owner:
                        require(not scalar(connection, "SELECT pg_catalog.has_table_privilege(:role,:table,:privilege)", role=role, table=name, privilege=privilege + " WITH GRANT OPTION"))
                for c in item.columns:
                    for privilege in ("SELECT", "INSERT", "UPDATE", "REFERENCES"):
                        permitted = role == identity.owner or role == identity.runtime and (privilege in {"SELECT", "INSERT"} or privilege == "UPDATE" and c.name in mutable[item.name])
                        require(scalar(connection, "SELECT pg_catalog.has_column_privilege(:role,:table,:column,:privilege)", role=role, table=name, column=c.name, privilege=privilege) is permitted)
                        if role != identity.owner:
                            require(not scalar(connection, "SELECT pg_catalog.has_column_privilege(:role,:table,:column,:privilege)", role=role, table=name, column=c.name, privilege=privilege + " WITH GRANT OPTION"))
                for type_name in (name, "oaf_website._" + item.name):
                    require(scalar(connection, "SELECT pg_catalog.has_type_privilege(:role,:name,'USAGE')", role=role, name=type_name) is (role == identity.owner))
                    if role != identity.owner:
                        require(not scalar(connection, "SELECT pg_catalog.has_type_privilege(:role,:name,'USAGE WITH GRANT OPTION')", role=role, name=type_name))
    triggers = rows(connection, """
        SELECT 'delivery_trigger_' || c.conname || '_' || r.relname || '_' || t.tgtype::text AS label,
               r.relname AS relation, t.tgtype AS kind, p.proname AS function,
               t.tgisinternal AS internal, t.tgenabled AS enabled, t.tgdeferrable AS deferrable,
               t.tginitdeferred AS deferred, pn.nspname AS function_schema,
               pg_catalog.encode(t.tgargs,'hex') AS arguments, t.tgnargs AS argument_count,
               t.tgattr::text AS attributes, pg_catalog.pg_get_expr(t.tgqual,t.tgrelid) AS condition,
               t.tgoldtable AS old_table, t.tgnewtable AS new_table, other.relname AS other_relation
        FROM pg_catalog.pg_trigger t LEFT JOIN pg_catalog.pg_constraint c ON c.oid=t.tgconstraint
        JOIN pg_catalog.pg_class r ON r.oid=t.tgrelid JOIN pg_catalog.pg_namespace n ON n.oid=r.relnamespace
        JOIN pg_catalog.pg_proc p ON p.oid=t.tgfoid JOIN pg_catalog.pg_namespace pn ON pn.oid=p.pronamespace
        LEFT JOIN pg_catalog.pg_class other ON other.oid=t.tgconstrrelid
        WHERE n.nspname='oaf_website'
        ORDER BY label
    """)
    require(triggers == sorted(expected_triggers, key=lambda r: r["label"]))
