"""Offline-only 0010 artifacts, SQL compilation and synthetic catalog/ACL checks."""
import migration_offline as isolation
isolation.require_early_registration()

from copy import deepcopy
import json
import runpy
from types import SimpleNamespace

import pytest
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, PrimaryKeyConstraint
from sqlalchemy.dialects import postgresql

from oaf_website import reoptin_schema as s, migration_validation as v
from oaf_website import notification_delivery_validation as validator
from oaf_website.migration_config import IDENTITIES, Failure, MigrationError
from test_notification_management_migration import StateCatalog
from migration_offline import Result
from test_migration_operational import operational, records


class ReoptinCatalog(StateCatalog):
    def __init__(self, environment="testing"):
        super().__init__(environment)
        self.marker = [dict(version_num=v.REOPTIN)]
        snapshot = self.snapshots["oaf_website." + s.intents.name]
        snapshot["columns"] = validator.column_contract(s.intents)
        snapshot["constraints"] = [dict(name=c.name,
            kind="c" if isinstance(c, CheckConstraint) else "f" if isinstance(c, ForeignKeyConstraint)
            else "p" if isinstance(c, PrimaryKeyConstraint) else "u",
            validated=True, deferrable=False, deferred=False, local=True, inherited=0,
            definition=validator.constraint_definition(c)) for c in sorted(s.intents.constraints, key=lambda c: c.name)]
        snapshot["column_acl"].append(dict(column="revoked_at", grantee=self.i.runtime,
            grantor=self.i.owner, privilege="UPDATE", grantable=False))
        block = self.snapshots["oaf_website.notification_suppressions"]
        block["columns"] = validator.column_contract(s.suppressions)
        block["constraints"] = [dict(name=c.name, kind="c" if isinstance(c, CheckConstraint) else "p",
            validated=True, deferrable=False, deferred=False, local=True, inherited=0,
            definition=validator.constraint_definition(c)) for c in sorted(s.suppressions.constraints, key=lambda c:c.name)]
        block["column_acl"].append(dict(column="reoptin_blocked_at", grantee=self.i.runtime,
            grantor=self.i.owner, privilege="UPDATE", grantable=False))
        self.objects += [dict(label=label, classid=59000+n, objid=60000+n)
                         for n, label in enumerate(sorted({edge[0] for edge in s.ADDED_EDGES}))]
        addresses = {o["label"]: (o["classid"], o["objid"]) for o in self.objects}
        self.dependencies += [dict(classid=addresses[a][0], objid=addresses[a][1], objsubid=b,
            refclassid=addresses[c][0], refobjid=addresses[c][1], refobjsubid=d, deptype=e)
            for a, b, c, d, e in s.ADDED_EDGES]

    def execute(self, sql, parameters=None):
        p = parameters or {}
        if ("has_column_privilege" in str(sql) and p.get("table") == "oaf_website." + s.intents.name
                and p.get("column") == "revoked_at"):
            return Result(p["role"] == self.i.owner or p["role"] == self.i.runtime
                          and p["privilege"] in {"SELECT", "INSERT", "UPDATE"})
        if ("has_column_privilege" in str(sql) and p.get("table") == "oaf_website.notification_suppressions"
                and p.get("column") == "reoptin_blocked_at"):
            return Result(p["role"] == self.i.owner or p["role"] == self.i.runtime
                          and p["privilege"] in {"SELECT", "INSERT", "UPDATE"})
        return super().execute(sql, parameters)


@pytest.mark.parametrize("environment", ["testing", "development", "production"])
def test_exact_successor_catalog_and_runtime_column_privilege(environment):
    catalog = ReoptinCatalog(environment)
    assert v.catalog_state(catalog, catalog.i) == v.REOPTIN


@pytest.mark.parametrize("mutation", ["column", "purpose", "check", "grant", "dependency", "marker",
                                    "block_column", "block_check", "block_grant"])
def test_successor_drift_is_rejected(mutation):
    catalog = ReoptinCatalog()
    snapshot = catalog.snapshots["oaf_website." + s.intents.name]
    if mutation == "column": snapshot["columns"].pop()
    if mutation == "purpose":
        next(c for c in snapshot["constraints"] if c["name"] == s.PURPOSE_CHECK)["definition"] = "CHECK (true)"
    if mutation == "check": snapshot["constraints"] = [c for c in snapshot["constraints"] if "revocation" not in c["name"]]
    if mutation == "grant": snapshot["column_acl"].pop()
    if mutation == "dependency": catalog.dependencies.pop()
    if mutation == "marker": catalog.marker = [dict(version_num=v.STATE_AVAILABILITY)]
    block = catalog.snapshots["oaf_website.notification_suppressions"]
    if mutation == "block_column": block["columns"].pop()
    if mutation == "block_check": block["constraints"] = [c for c in block["constraints"] if "reoptin_block" not in c["name"]]
    if mutation == "block_grant": block["column_acl"].pop()
    with pytest.raises(MigrationError, match=Failure.DRIFT):
        v.catalog_state(catalog, catalog.i)


@pytest.mark.parametrize("start", [v.STATE_AVAILABILITY, v.REOPTIN])
def test_exact_offline_artifacts_and_single_revision_transition(start):
    payload = (v.ROOT / "migrations/manifest.json").read_bytes()
    document = json.loads(payload)
    assert document["approval_status"] == "pending_independent_review"
    assert v.validate_artifacts(expected_start=start, target=v.REOPTIN,
        manifest_hash=v.digest(payload), revision_hash=document["revisions"][9]["sha256"]).target == v.REOPTIN
    # Previously deployed source hashes remain exact.
    for revision in document["revisions"][:9]:
        assert v.digest((v.ROOT / revision["file"]).read_bytes()) == revision["sha256"]


@pytest.mark.parametrize("start,target", [(v.MANAGEMENT, v.REOPTIN), (v.REOPTIN, v.STATE_AVAILABILITY)])
def test_skipped_revision_or_downgrade_denied(start, target):
    with pytest.raises(MigrationError, match=Failure.STARTING_REVISION):
        v.validate_artifacts(expected_start=start, target=target, manifest_hash="0"*64, revision_hash="1"*64)


@pytest.mark.parametrize("environment", ["testing", "development", "production"])
def test_migration_sql_only_adds_required_persistence_and_grant(environment):
    statements = []
    def execute(statement):
        statements.append(str(statement.compile(dialect=postgresql.dialect())))
        return Result(IDENTITIES[environment].owner)
    s.upgrade_voluntary_reoptin(SimpleNamespace(execute=execute))
    assert len(statements) == 9
    assert "ADD COLUMN revoked_at timestamp with time zone" in statements[1]
    assert "DROP CONSTRAINT notification_confirmation_intents_purpose_check" in statements[2]
    assert "GRANT UPDATE (revoked_at)" in statements[5]
    assert "ADD COLUMN reoptin_blocked_at timestamp with time zone" in statements[6]
    assert "GRANT UPDATE (reoptin_blocked_at)" in statements[-1]
    assert not any("CREATE TABLE" in q or "DELETE FROM" in q for q in statements)
    with pytest.raises(MigrationError, match=Failure.WRONG_IDENTITY):
        s.upgrade_voluntary_reoptin(SimpleNamespace(execute=lambda q: Result(IDENTITIES[environment].runtime)))


def test_revision_wrapper_and_prohibited_downgrade(monkeypatch):
    from alembic import op
    revision = runpy.run_path(str(v.ROOT / v.REOPTIN_REVISION_FILE))
    calls, sentinel = [], object()
    monkeypatch.setattr(op, "get_bind", lambda: sentinel)
    revision["upgrade"].__globals__["upgrade_voluntary_reoptin"] = calls.append
    revision["upgrade"]()
    assert calls == [sentinel] and revision["down_revision"] == v.STATE_AVAILABILITY
    with pytest.raises(RuntimeError): revision["downgrade"]()


def test_synthetic_authorized_successor_is_single_use_and_noop_is_separate(operational, monkeypatch):
    from dataclasses import replace
    from datetime import timedelta
    from oaf_website import migrate as runner
    op = operational
    document = json.loads((v.ROOT / "migrations/manifest.json").read_bytes())
    request = replace(op.request, expected_start=v.STATE_AVAILABILITY, target=v.REOPTIN,
                      revision_hash=document["revisions"][9]["sha256"])
    monkeypatch.setattr(runner, "catalog_state", lambda *args: v.REOPTIN
                        if op.runner.connection.target else v.STATE_AVAILABILITY)
    authorization = op.issue(op.approvals(request))
    assert op.run(authorization, request)["outcome"] == "applied_and_verified"
    with pytest.raises(MigrationError, match=Failure.OPERATIONAL_GATE): op.run(authorization, request)
    op.clock.now += timedelta(seconds=1)
    op.runner.connection.closed = False
    noop = replace(request, expected_start=v.REOPTIN)
    assert op.run(op.issue(op.approvals(noop)), noop)["outcome"] == "verified_noop"
    assert len(records(op, "claim-*.json")) == 2
