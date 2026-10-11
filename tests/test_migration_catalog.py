"""Synthetic PostgreSQL catalog results; these do not prove SQL/server semantics."""

import migration_offline as isolation
isolation.require_early_registration()

from copy import deepcopy

import pytest

from migration_offline import Result
from oaf_website import migration_config as c, migration_validation as v


class Catalog:
    """Explicit approved records. Unknown query shapes fail the fixture closed."""
    def __init__(self, environment="testing", target=True):
        self.i = i = c.IDENTITIES[environment]
        self.target = target
        self.calls = []
        self.scalar_changes = {}
        owners = {j.owner for j in c.IDENTITIES.values()}
        self.roles = [dict(oid=n, rolname=name, rolsuper=False, rolcreatedb=False,
            rolcreaterole=False, rolreplication=False, rolbypassrls=False,
            rolinherit=False, rolcanlogin=name not in owners, exceptional=False)
            for n, name in enumerate(sorted({name for j in c.IDENTITIES.values()
                         for name in (j.runtime, j.migrator, j.owner)}), 1)]
        self.memberships = [dict(member=j.migrator, parent=j.owner, inherit_option=False,
                                  set_option=True, admin_option=False) for j in c.IDENTITIES.values()]
        self.schema_owner = [{"owner": i.owner}]
        self.schema_acl = [dict(grantee=i.owner, grantor=i.owner, privilege=p, grantable=False)
                           for p in ("USAGE", "CREATE")]
        self.schema_acl.append(dict(grantee=i.runtime, grantor=i.owner, privilege="USAGE", grantable=False))
        self.defaults = [dict(kind=k, namespace=0, schema=None, acl="synthetic-owner-only") for k in ("f", "T")]
        self.defaults += [dict(kind=k, namespace=42, schema="oaf_website", acl="synthetic-owner-only")
                          for k in ("r", "S", "f", "T")]
        self.relations = [dict(name=name, kind=kind, owner=i.owner, persistence="p", rls=False,
                              force_rls=False, rules=False, triggers=False, options=None)
                          for name, kind in (("alembic_version", "r"), ("alembic_version_pkc", "i"))] if target else []
        self.types = [dict(name="_alembic_version", kind="b", owner=i.owner, relation=0, element=102),
                      dict(name="alembic_version", kind="c", owner=i.owner, relation=101, element=0)] if target else []
        self.type_acl = [dict(name=name, grantee=grantee, grantor=i.owner, privilege="USAGE", grantable=False)
                         for name in ("alembic_version", "_alembic_version") for grantee in (i.owner, "PUBLIC")]
        labels = ["schema"] + (["table", "index", "row_type", "array_type", "primary_key"] if target else [])
        labels += [f'default_{d["namespace"]}_{d["kind"]}' for d in self.defaults]
        self.objects = [dict(label=label, classid=1000+n, objid=2000+n) for n, label in enumerate(labels)]
        edges = list(v.SECURITY_CONTRACT["dependencies"]["baseline_edges"]) if target else []
        edges += [[label, 0, "schema", 0, "a"] for label in labels if label.startswith("default_42_")]
        address = {o["label"]: (o["classid"], o["objid"]) for o in self.objects}
        self.dependencies = [dict(classid=address[s][0], objid=address[s][1], objsubid=sn,
                                  refclassid=address[t][0], refobjid=address[t][1], refobjsubid=tn, deptype=kind)
                             for s, sn, t, tn, kind in edges]
        self.columns = [dict(name="version_num", type="character varying(32)", required=True,
            has_default=False, identity="", generated="", dropped=False, position=1,
            dimensions=0, default_collation=True)]
        self.constraints = [dict(name="alembic_version_pkc", kind="p", validated=True,
            deferrable=False, deferred=False, definition="PRIMARY KEY (version_num)")]
        self.marker = [{"version_num": v.BASELINE}]
        self.identity = [dict(database=i.database, authenticated=i.migrator, effective=i.migrator,
                              host=i.host, port=i.port, major=17)]

    def execute(self, sql, parameters=None):
        q, p = str(sql), parameters or {}
        self.calls.append((q, p))
        for needle, value in self.scalar_changes.items():
            if needle in q:
                return Result(value(p) if callable(value) else value)
        for needle, value in (
            ("current_database() AS database", self.identity),
            ("SELECT oid, rolname", self.roles), ("member.rolname AS member", self.memberships),
            ("AS owner\n        FROM pg_catalog.pg_namespace", self.schema_owner),
            ("n.nspacl", self.schema_acl), ("d.defaclobjtype AS kind", self.defaults),
            ("c.relname AS name", self.relations), ("t.typtype AS kind", self.types),
            ("COALESCE(t.typacl", self.type_acl), ("'schema' AS label", self.objects),
            ("SELECT classid::bigint", self.dependencies), ("a.attname AS name", self.columns),
            ("c.conname AS name", self.constraints), ("SELECT version_num", self.marker)):
            if needle in q:
                return Result(deepcopy(value))
        if "has_database_privilege" in q:
            if "privilege" in p:
                return Result(False)
            permitted = any(p["db"] == j.database and p["name"] in (j.runtime, j.migrator)
                            for j in c.IDENTITIES.values())
            return Result(permitted)
        if "n.nspname !~" in q or "pg_shdepend" in q or "datdba" in q:
            return Result(False)
        if "has_schema_privilege" in q:
            return Result("'USAGE'" in q)
        if "pg_default_acl d" in q:
            return Result(False)
        if "t.typrelid='oaf_website.alembic_version'" in q or "i.indisunique" in q:
            return Result(True)
        if "has_type_privilege" in q:
            return Result("WITH GRANT OPTION" not in q)
        if "SELECT EXISTS" in q and ("pg_constraint" in q or "aclexplode" in q):
            return Result(False)
        if "has_table_privilege" in q:
            return Result(p["name"] == self.i.owner)
        if "has_any_column_privilege" in q:
            return Result(False)
        raise AssertionError("Unknown synthetic catalog query: " + q)


@pytest.mark.parametrize("environment", c.IDENTITIES)
@pytest.mark.parametrize("target", [False, True])
def test_approved_catalog_state_and_six_role_isolation(environment, target):
    catalog = Catalog(environment, target)
    v.verify_identity(catalog, catalog.i)
    catalog.identity[0]["effective"] = catalog.i.owner
    v.verify_identity(catalog, catalog.i, assumed=True)
    v.verify_authority(catalog, catalog.i)
    assert v.catalog_state(catalog, catalog.i) == (v.BASELINE if target else v.BASE)
    names = {p["name"] for q, p in catalog.calls if "has_database_privilege" in q}
    assert names == {name for j in c.IDENTITIES.values() for name in (j.owner, j.runtime, j.migrator)}


@pytest.mark.parametrize("field,value", [("database", "wrong"), ("authenticated", "postgres"),
    ("effective", "wrong"), ("host", "localhost"), ("port", 5433), ("major", 16)])
def test_connection_identity_mismatch(field, value):
    catalog = Catalog()
    catalog.identity[0][field] = value
    with pytest.raises(c.MigrationError, match=c.Failure.WRONG_IDENTITY):
        v.verify_identity(catalog, catalog.i)


@pytest.mark.parametrize("name", sorted({name for i in c.IDENTITIES.values() for name in (i.owner, i.runtime, i.migrator)}))
@pytest.mark.parametrize("attribute", ["rolsuper", "rolcreatedb", "rolcreaterole", "rolreplication", "rolbypassrls", "exceptional", "rolcanlogin"])
def test_all_six_roles_reject_elevation_or_wrong_login(name, attribute):
    catalog = Catalog()
    role = next(r for r in catalog.roles if r["rolname"] == name)
    role[attribute] = not role[attribute]
    with pytest.raises(c.MigrationError, match=c.Failure.UNAUTHORIZED_MEMBERSHIP):
        v.verify_authority(catalog, catalog.i)


@pytest.mark.parametrize("attribute", ["inherit_option", "set_option", "admin_option"])
@pytest.mark.parametrize("environment", c.IDENTITIES)
def test_exact_membership_options(environment, attribute):
    catalog = Catalog()
    member = next(m for m in catalog.memberships if m["member"] == c.IDENTITIES[environment].migrator)
    member[attribute] = not member[attribute]
    with pytest.raises(c.MigrationError, match=c.Failure.UNAUTHORIZED_MEMBERSHIP):
        v.verify_authority(catalog, catalog.i)


@pytest.mark.parametrize("case", ["missing", "duplicate", "cross_outgoing", "cross_incoming", "runtime_owner",
    "shared_inherit", "shared_set", "shared_admin", "indirect", "incoming_indirect", "role_missing", "inherit"])
def test_membership_paths_fail_closed(case):
    catalog = Catalog()
    dev, test = c.IDENTITIES.values()
    def edge(member, parent, inherit=False, set_role=True, admin=False):
        return dict(member=member, parent=parent, inherit_option=inherit, set_option=set_role, admin_option=admin)
    external = dict(catalog.roles[0], rolname="external", oid=999, rolcanlogin=True)
    catalog.roles.append(external)
    if case == "missing":
        catalog.memberships.pop()
    elif case == "duplicate":
        catalog.memberships.append(dict(catalog.memberships[0]))
    elif case in {"cross_outgoing", "cross_incoming"}:
        catalog.memberships.append(edge(dev.migrator if case == "cross_outgoing" else test.runtime, test.owner if case == "cross_outgoing" else dev.owner))
    elif case == "runtime_owner":
        catalog.memberships.append(edge(test.runtime, test.owner))
    elif case.startswith("shared_"):
        catalog.memberships.append(edge(test.owner, "oaf_website_owner", case == "shared_inherit", case == "shared_set", case == "shared_admin"))
    elif case == "indirect":
        catalog.memberships += [edge(test.owner, "external"), edge("external", "oaf_website_owner")]
    elif case == "incoming_indirect":
        catalog.memberships += [edge("external", test.migrator)]
    elif case == "role_missing":
        catalog.roles = catalog.roles[1:]
    else:
        next(r for r in catalog.roles if r["rolname"] == test.owner)["rolinherit"] = True
    with pytest.raises(c.MigrationError, match=c.Failure.UNAUTHORIZED_MEMBERSHIP):
        v.verify_authority(catalog, catalog.i)


@pytest.mark.parametrize("exceptional", [False, True])
def test_exceptional_administrator_distinct_from_ordinary_authority(exceptional):
    catalog = Catalog()
    catalog.roles.append(dict(catalog.roles[0], rolname="existing_admin", oid=900,
                              rolcreaterole=True, exceptional=exceptional))
    catalog.memberships.append(dict(member="existing_admin", parent=catalog.i.owner,
                                    inherit_option=False, set_option=True, admin_option=True))
    if exceptional:
        v.verify_authority(catalog, catalog.i)
    else:
        with pytest.raises(c.MigrationError, match=c.Failure.UNAUTHORIZED_MEMBERSHIP):
            v.verify_authority(catalog, catalog.i)


@pytest.mark.parametrize("needle", ["has_database_privilege(:name, :db, 'CONNECT')", "has_database_privilege(:name, :db, :privilege)",
    "n.nspname !~", "datdba", "pg_shdepend"])
def test_database_schema_and_material_ownership_authority(needle):
    catalog = Catalog()
    catalog.scalar_changes[needle] = False if "'CONNECT'" in needle else True
    with pytest.raises(c.MigrationError, match=c.Failure.UNAUTHORIZED_MEMBERSHIP):
        v.verify_authority(catalog, catalog.i)


@pytest.mark.parametrize("privilege", ["CREATE", "TEMPORARY", "CONNECT WITH GRANT OPTION",
    "CREATE WITH GRANT OPTION", "TEMPORARY WITH GRANT OPTION"])
def test_unapproved_database_privileges(privilege):
    catalog = Catalog()
    catalog.scalar_changes["has_database_privilege(:name, :db, :privilege)"] = lambda p: p["privilege"] == privilege
    with pytest.raises(c.MigrationError, match=c.Failure.UNAUTHORIZED_MEMBERSHIP):
        v.verify_authority(catalog, catalog.i)


@pytest.mark.parametrize("case", ["owner", "public", "runtime_create", "grant_option", "missing_usage", "effective_create", "effective_no_usage"])
def test_schema_ownership_and_privileges(case):
    catalog = Catalog()
    if case == "owner":
        catalog.schema_owner = [{"owner": "wrong"}]
    elif case == "public":
        catalog.schema_acl.append(dict(catalog.schema_acl[0], grantee="PUBLIC"))
    elif case == "runtime_create":
        catalog.schema_acl[-1]["privilege"] = "CREATE"
    elif case == "grant_option":
        catalog.schema_acl[-1]["grantable"] = True
    elif case == "missing_usage":
        catalog.schema_acl.pop()
    elif case == "effective_create":
        catalog.scalar_changes["has_schema_privilege(:name, 'oaf_website', 'CREATE')"] = True
    else:
        catalog.scalar_changes["has_schema_privilege(:name, 'oaf_website', 'USAGE')"] = False
    with pytest.raises(c.MigrationError, match=c.Failure.SCHEMA_OWNERSHIP if case == "owner" else c.Failure.DRIFT):
        v.catalog_state(catalog, catalog.i)


@pytest.mark.parametrize("case", ["missing_global_routine", "missing_global_type", "unknown_kind", "foreign_schema", "schema_n", "foreign_acl"])
def test_default_acl_records(case):
    catalog = Catalog()
    if case.startswith("missing_global"):
        catalog.defaults.pop(0 if case.endswith("routine") else 1)
    elif case == "unknown_kind":
        catalog.defaults[0]["kind"] = "x"
    elif case == "foreign_schema":
        catalog.defaults[-1]["schema"] = "other"
    elif case == "schema_n":
        catalog.defaults[-1]["kind"] = "n"
    else:
        catalog.scalar_changes["CROSS JOIN LATERAL pg_catalog.aclexplode(d.defaclacl)"] = True
    with pytest.raises(c.MigrationError, match=c.Failure.DRIFT):
        v.catalog_state(catalog, catalog.i)


@pytest.mark.parametrize("field,value", [("owner", "wrong"), ("persistence", "u"), ("rls", True),
    ("force_rls", True), ("rules", True), ("triggers", True), ("options", ["fillfactor=50"]), ("kind", "v"), ("name", "other")])
def test_metadata_relation_drift(field, value):
    catalog = Catalog()
    catalog.relations[0][field] = value
    with pytest.raises(c.MigrationError, match=c.Failure.DRIFT):
        v.catalog_state(catalog, catalog.i)


@pytest.mark.parametrize("case", ["ordinary_type", "wrong_owner", "no_relation", "no_element", "explicit_acl", "public_grant", "duplicate_acl", "effective_no_usage", "grant_option"])
def test_generated_type_exception_is_exact(case):
    catalog = Catalog()
    if case == "ordinary_type":
        catalog.types.append(dict(catalog.types[0], name="independent_type"))
    elif case == "wrong_owner":
        catalog.types[0]["owner"] = "wrong"
    elif case == "no_relation":
        catalog.types[1]["relation"] = 0
    elif case == "no_element":
        catalog.types[0]["element"] = 0
    elif case == "explicit_acl":
        catalog.scalar_changes["t.typrelid='oaf_website.alembic_version'"] = False
    elif case == "public_grant":
        catalog.type_acl.append(dict(catalog.type_acl[0], name="ordinary_type", grantee="PUBLIC"))
    elif case == "duplicate_acl":
        catalog.type_acl.append(dict(catalog.type_acl[0]))
    elif case == "effective_no_usage":
        catalog.scalar_changes["has_type_privilege(:role, :name, 'USAGE')"] = False
    else:
        catalog.scalar_changes["has_type_privilege(:role, :name, 'USAGE WITH GRANT OPTION')"] = True
    with pytest.raises(c.MigrationError, match=c.Failure.DRIFT):
        v.catalog_state(catalog, catalog.i)


@pytest.mark.parametrize("case", ["external", "extension", "missing", "duplicate", "wrong_kind", "wrong_subobject", "default_missing", "extra_object"])
def test_exact_internal_and_default_acl_dependencies(case):
    catalog = Catalog()
    if case in {"external", "extension"}:
        catalog.dependencies.append(dict(catalog.dependencies[0], classid=9999,
                                         deptype="e" if case == "extension" else "n"))
    elif case == "missing":
        catalog.dependencies.pop(0)
    elif case == "duplicate":
        catalog.dependencies.append(dict(catalog.dependencies[0]))
    elif case == "wrong_kind":
        catalog.dependencies[0]["deptype"] = "a"
    elif case == "wrong_subobject":
        catalog.dependencies[0]["objsubid"] = 1
    elif case == "default_missing":
        catalog.dependencies.pop()
    else:
        catalog.objects.append(dict(label="unexpected", classid=9000, objid=9000))
    with pytest.raises(c.MigrationError, match=c.Failure.DRIFT):
        v.catalog_state(catalog, catalog.i)


@pytest.mark.parametrize("field,value", [("name", "wrong"), ("type", "text"), ("required", False),
    ("has_default", True), ("identity", "a"), ("generated", "s"), ("dropped", True),
    ("position", 2), ("dimensions", 1), ("default_collation", False)])
def test_version_column_definition(field, value):
    catalog = Catalog()
    catalog.columns[0][field] = value
    with pytest.raises(c.MigrationError, match=c.Failure.DRIFT):
        v.catalog_state(catalog, catalog.i)


@pytest.mark.parametrize("field,value", [("name", "wrong"), ("kind", "u"), ("validated", False),
    ("deferrable", True), ("deferred", True), ("definition", "UNIQUE (version_num)")])
def test_primary_key_definition(field, value):
    catalog = Catalog()
    catalog.constraints[0][field] = value
    with pytest.raises(c.MigrationError, match=c.Failure.DRIFT):
        v.catalog_state(catalog, catalog.i)


@pytest.mark.parametrize("case", ["index", "acl", "owner_privilege", "runtime_table", "runtime_column", "marker_missing", "marker_extra", "marker_wrong", "sequence", "table", "routine_dependency", "base_type", "base_constraint"])
def test_metadata_grants_objects_and_revision_marker(case):
    catalog = Catalog(target=not case.startswith("base_"))
    if case == "index":
        catalog.scalar_changes["i.indisunique"] = False
    elif case == "acl":
        catalog.scalar_changes["COALESCE(c.relacl"] = True
    elif case == "owner_privilege":
        catalog.scalar_changes["has_table_privilege"] = False
    elif case == "runtime_table":
        catalog.scalar_changes["has_table_privilege"] = True
    elif case == "runtime_column":
        catalog.scalar_changes["has_any_column_privilege"] = True
    elif case == "marker_missing":
        catalog.marker = []
    elif case == "marker_extra":
        catalog.marker *= 2
    elif case == "marker_wrong":
        catalog.marker[0]["version_num"] = "0002"
    elif case in {"sequence", "table"}:
        catalog.relations.append(dict(catalog.relations[0], name="unexpected", kind="S" if case == "sequence" else "r"))
    elif case == "routine_dependency":
        catalog.dependencies.append(dict(catalog.dependencies[0], classid=1255, objid=9999))
    elif case == "base_type":
        catalog.types = [{"name": "ordinary"}]
    else:
        catalog.scalar_changes["SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_constraint"] = True
    with pytest.raises(c.MigrationError, match=c.Failure.DRIFT):
        v.catalog_state(catalog, catalog.i)


@pytest.mark.parametrize("name", sorted({name for i in c.IDENTITIES.values() for name in (i.owner, i.migrator)}))
def test_each_owner_and_migrator_must_be_noinherit(name):
    catalog = Catalog()
    next(role for role in catalog.roles if role["rolname"] == name)["rolinherit"] = True
    with pytest.raises(c.MigrationError, match=c.Failure.UNAUTHORIZED_MEMBERSHIP):
        v.verify_authority(catalog, catalog.i)


@pytest.mark.parametrize("name", sorted({name for i in c.IDENTITIES.values() for name in (i.owner, i.runtime, i.migrator)}))
def test_cross_database_material_ownership_rejected_for_every_identity(name):
    catalog = Catalog()
    catalog.scalar_changes["AND d.dbid<>0"] = lambda p: p["name"] == name
    with pytest.raises(c.MigrationError, match=c.Failure.UNAUTHORIZED_MEMBERSHIP):
        v.verify_authority(catalog, catalog.i)


@pytest.mark.parametrize("name", sorted({name for i in c.IDENTITIES.values() for name in (i.owner, i.runtime, i.migrator)} - {c.IDENTITIES["testing"].owner}))
@pytest.mark.parametrize("privilege", ["SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER", "MAINTAIN"])
def test_each_nonowner_metadata_privilege_rejected(name, privilege):
    catalog = Catalog()
    catalog.scalar_changes["has_table_privilege"] = lambda p: p["name"] == catalog.i.owner or (p["name"] == name and p["privilege"] == privilege)
    with pytest.raises(c.MigrationError, match=c.Failure.DRIFT):
        v.catalog_state(catalog, catalog.i)


@pytest.mark.parametrize("name", sorted({name for i in c.IDENTITIES.values() for name in (i.owner, i.runtime, i.migrator)} - {c.IDENTITIES["testing"].owner}))
def test_each_nonowner_column_privilege_rejected(name):
    catalog = Catalog()
    catalog.scalar_changes["has_any_column_privilege"] = lambda p: p["name"] == name
    with pytest.raises(c.MigrationError, match=c.Failure.DRIFT):
        v.catalog_state(catalog, catalog.i)


@pytest.mark.parametrize("role", sorted({name for i in c.IDENTITIES.values() for name in (i.owner, i.runtime, i.migrator)} - {c.IDENTITIES["testing"].owner}))
@pytest.mark.parametrize("type_name", ["oaf_website.alembic_version", "oaf_website._alembic_version"])
def test_generated_type_nonowner_grant_options_rejected(role, type_name):
    catalog = Catalog()
    catalog.scalar_changes["has_type_privilege(:role, :name, 'USAGE WITH GRANT OPTION')"] = lambda p: p["role"] == role and p["name"] == type_name
    with pytest.raises(c.MigrationError, match=c.Failure.DRIFT):
        v.catalog_state(catalog, catalog.i)
