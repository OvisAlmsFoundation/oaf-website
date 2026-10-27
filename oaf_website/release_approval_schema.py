"""Additive 0007 approval history; original events and attempts stay immutable."""

from sqlalchemy import (CheckConstraint, Column, DateTime, ForeignKeyConstraint,
                        MetaData, PrimaryKeyConstraint, String, Table, UniqueConstraint, text)
from .notification_delivery_schema import events

RELEASE_APPROVALS = "0007_release_approvals"
metadata = MetaData(schema="oaf_website")
events.to_metadata(metadata)
revisions = Table("notification_release_approvals", metadata,
    Column("source_approval_id", String(36), nullable=False),
    Column("event_id", String(36), nullable=False),
    Column("previous_approval_id", String(36), nullable=False),
    Column("action", String(8), nullable=False),
    Column("release_id", String(150), nullable=False),
    Column("release_url", String(300), nullable=False),
    Column("approved_at", DateTime(timezone=True), nullable=False),
    Column("payload_digest", String(64), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    PrimaryKeyConstraint("source_approval_id", name="notification_release_approvals_pk"),
    UniqueConstraint("event_id", "previous_approval_id", name="notification_release_approvals_parent"),
    ForeignKeyConstraint(["event_id"], ["oaf_website.notification_release_events.event_id"],
                         name="notification_release_approvals_event_fk"),
    CheckConstraint("action IN ('correct','withdraw')", name="notification_release_approvals_action"),
    CheckConstraint("approved_at <= created_at", name="notification_release_approvals_time"),
    CheckConstraint("payload_digest ~ '^[0-9a-f]{64}$'", name="notification_release_approvals_digest"))
TABLES = (revisions,)
GRANTS = [dict(object="oaf_website." + revisions.name, role="matching_runtime",
               privileges=["SELECT", "INSERT"], grant_option=False)]
OBJECTS = [dict(kind=k, name=n) for k, n in (
    ("table", revisions.name), ("row_type", revisions.name), ("array_type", "_" + revisions.name))]
EDGES = []
FK_TRIGGERS = []
for item in TABLES:
    tbl = "delivery_table_" + item.name
    EDGES += [[tbl, 0, "schema", 0, "n"], ["delivery_type_" + item.name, 0, tbl, 0, "i"],
              ["delivery_type__" + item.name, 0, "delivery_type_" + item.name, 0, "i"]]
    positions = {c.name: n for n, c in enumerate(item.columns, 1)}
    for constraint in sorted(item.constraints, key=lambda c: c.name):
        kind = {PrimaryKeyConstraint: "primary_key", UniqueConstraint: "unique",
                ForeignKeyConstraint: "foreign_key", CheckConstraint: "check"}[type(constraint)]
        OBJECTS.append(dict(kind=kind, name=constraint.name))
        label = "delivery_constraint_" + constraint.name
        if isinstance(constraint, CheckConstraint):
            import re
            names = set(re.findall(r"[a-z_]+", str(constraint.sqltext))) & set(positions)
            EDGES += [[label, 0, tbl, positions[n], k] for n in sorted(names) for k in ("a", "n")]
        else:
            EDGES += [[label, 0, tbl, positions[c.name], "a"] for c in constraint.columns]
            if isinstance(constraint, ForeignKeyConstraint):
                parent = events.name
                EDGES += [[label, 0, "delivery_index_" + events.primary_key.name, 0, "n"],
                          [label, 0, "delivery_table_" + parent, 1, "n"]]
                for relation, types in ((parent, (9, 17)), (item.name, (5, 17))):
                    for trigger_type in types:
                        trigger = "delivery_trigger_" + constraint.name + "_" + relation + "_" + str(trigger_type)
                        EDGES.append([trigger, 0, label, 0, "i"])
                        function = {9: "RI_FKey_noaction_del", 5: "RI_FKey_check_ins"}.get(trigger_type,
                            "RI_FKey_noaction_upd" if relation == parent else "RI_FKey_check_upd")
                        FK_TRIGGERS.append(dict(label=trigger, relation=relation, kind=trigger_type, function=function,
                            internal=True, enabled="O", deferrable=False, deferred=False, function_schema="pg_catalog",
                            arguments="", argument_count=0, attributes="", condition=None, old_table=None, new_table=None,
                            other_relation=item.name if relation == parent else parent))
            else:
                OBJECTS.append(dict(kind="index", name=constraint.name))
                EDGES.append(["delivery_index_" + constraint.name, 0, label, 0, "i"])


def upgrade_release_approvals(connection):
    from sqlalchemy.schema import CreateTable
    from .migration_config import IDENTITIES, Failure, MigrationError
    owner = connection.execute(text("SELECT current_user")).scalar_one()
    identity = next((i for i in IDENTITIES.values() if i.owner == owner), None)
    if identity is None:
        raise MigrationError(Failure.WRONG_IDENTITY)
    connection.execute(CreateTable(revisions))
    connection.execute(text("REVOKE ALL ON TYPE oaf_website.notification_release_approvals FROM PUBLIC"))
    connection.execute(text(f'GRANT SELECT, INSERT ON TABLE oaf_website.notification_release_approvals TO "{identity.runtime}"'))
