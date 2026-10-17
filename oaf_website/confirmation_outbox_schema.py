"""Additive confirmation intent/attempt source; no startup DDL."""

from sqlalchemy import (CheckConstraint, Column, ForeignKeyConstraint, Index,
                        MetaData, PrimaryKeyConstraint, String, Table, UniqueConstraint, text)
from .notification_schema import notifications
from .notification_delivery_schema import deliveries, attempts

OUTBOX = "0005_confirmation_outbox"
metadata = MetaData(schema="oaf_website")
# Resolve FKs without modifying the historical 0003 metadata/helper.
notifications.to_metadata(metadata)


def table(name, columns, checks, *constraints):
    return Table(name, metadata, *columns,
                 *(CheckConstraint(value, name=name + "_" + key) for key, value in checks.items()),
                 *constraints)


# Reuse the reviewed delivery state/check vocabulary without altering 0004 tables.

def checks(item):
    return {c.name.removeprefix(item.name + "_"): str(c.sqltext)
            for c in item.constraints if isinstance(c, CheckConstraint)}


def columns(item, excluded):
    return [Column(c.name, c.type, nullable=c.nullable) for c in item.columns if c.name not in excluded]


intents = table("notification_confirmation_intents", [
    Column("intent", String(64), nullable=False),
    Column("token_digest", String(64), nullable=False),
    *columns(deliveries, {"event_id"}),
], dict(checks(deliveries), context_check="intent ~ '^[0-9a-f]{64}$' AND token_digest ~ '^[0-9a-f]{64}$'"),
    PrimaryKeyConstraint("intent", name="notification_confirmation_intents_pk"),
    ForeignKeyConstraint(["subscription"], ["oaf_website.notifications.unsubscribe_digest"],
                         name="notification_confirmation_intents_subscription_fk"))
confirmation_attempts = table("notification_confirmation_attempts", [
    Column("intent", String(64), nullable=False),
    *columns(attempts, {"event_id", "subscription"}),
], checks(attempts),
    PrimaryKeyConstraint("intent", "attempt", name="notification_confirmation_attempts_pk"),
    ForeignKeyConstraint(["intent"], ["oaf_website.notification_confirmation_intents.intent"],
                         name="notification_confirmation_attempts_intent_fk"))
TABLES = (intents, confirmation_attempts)
Index("notification_confirmation_intents_retry", intents.c.status, intents.c.next_attempt_at)
Index("notification_confirmation_intents_lease", intents.c.status, intents.c.lease_until)
Index("notification_confirmation_intents_subscription", intents.c.subscription)
MUTABLE = {
    intents.name: ("status", "attempts", "claim_digest", "lease_until", "next_attempt_at", "outcome",
                   "provider_message_id", "updated_at", "accepted_at"),
    confirmation_attempts.name: ("submitting_at", "finished_at", "outcome", "provider_message_id"),
}
GRANTS = []
OBJECTS = []
for item in TABLES:
    GRANTS.append(dict(object="oaf_website." + item.name, role="matching_runtime",
                       privileges=["SELECT", "INSERT"], grant_option=False))
    GRANTS.extend(dict(object="oaf_website." + item.name + "." + column, role="matching_runtime",
                       privileges=["UPDATE"], grant_option=False) for column in MUTABLE[item.name])
    OBJECTS.extend([dict(kind="table", name=item.name), dict(kind="row_type", name=item.name),
                    dict(kind="array_type", name="_" + item.name)])
    for constraint in sorted(item.constraints, key=lambda c: c.name):
        kind = {PrimaryKeyConstraint: "primary_key", UniqueConstraint: "unique",
                ForeignKeyConstraint: "foreign_key", CheckConstraint: "check"}[type(constraint)]
        OBJECTS.append(dict(kind=kind, name=constraint.name))
        if kind in {"primary_key", "unique"}:
            OBJECTS.append(dict(kind="index", name=constraint.name))
    OBJECTS.extend(dict(kind="index", name=index.name) for index in sorted(item.indexes, key=lambda i: i.name))


def upgrade_confirmation_outbox(connection):
    from sqlalchemy.schema import CreateIndex, CreateTable
    from .migration_config import IDENTITIES, Failure, MigrationError
    owner = connection.execute(text("SELECT current_user")).scalar_one()
    identity = next((i for i in IDENTITIES.values() if i.owner == owner), None)
    if identity is None:
        raise MigrationError(Failure.WRONG_IDENTITY)
    for item in TABLES:
        connection.execute(CreateTable(item))
        for index in sorted(item.indexes, key=lambda i: i.name):
            connection.execute(CreateIndex(index))
        connection.execute(text(f"REVOKE ALL ON TYPE oaf_website.{item.name} FROM PUBLIC"))
        connection.execute(text(f'GRANT SELECT, INSERT ON TABLE oaf_website.{item.name} TO "{identity.runtime}"'))
        columns = ", ".join(MUTABLE[item.name])
        connection.execute(text(f'GRANT UPDATE ({columns}) ON TABLE oaf_website.{item.name} TO "{identity.runtime}"'))

# Exact pg_depend graph, including generated RI triggers. Numeric trigger names
# are never trusted; catalog labels bind the FK, relation, event and function.
EDGES = []
FK_TRIGGERS = []
for item in TABLES:
    tbl = "delivery_table_" + item.name
    EDGES += [[tbl, 0, "schema", 0, "n"],
              ["delivery_type_" + item.name, 0, tbl, 0, "i"],
              ["delivery_type__" + item.name, 0, "delivery_type_" + item.name, 0, "i"]]
    positions = {column.name: n for n, column in enumerate(item.columns, 1)}
    for constraint in sorted(item.constraints, key=lambda c: c.name):
        label = "delivery_constraint_" + constraint.name
        if isinstance(constraint, CheckConstraint):
            import re
            names = set(re.findall(r"[a-z_]+", str(constraint.sqltext))) & set(positions)
            EDGES += [[label, 0, tbl, positions[name], kind] for name in sorted(names) for kind in ("a", "n")]
        else:
            EDGES += [[label, 0, tbl, positions[column.name], "a"] for column in constraint.columns]
            if isinstance(constraint, ForeignKeyConstraint):
                parent = constraint.elements[0].column.table
                parent_table = "notification_table" if parent.name == "notifications" else "delivery_table_" + parent.name
                parent_index = "notification_index" if parent.name == "notifications" else "delivery_index_" + parent.primary_key.name
                EDGES.append([label, 0, parent_index, 0, "n"])
                for element in constraint.elements:
                    EDGES.append([label, 0, parent_table, list(parent.columns).index(element.column) + 1, "n"])
                for relation, types in ((parent.name, (9, 17)), (item.name, (5, 17))):
                    for trigger_type in types:
                        trigger = "delivery_trigger_" + constraint.name + "_" + relation + "_" + str(trigger_type)
                        EDGES.append([trigger, 0, label, 0, "i"])
                        function = {9: "RI_FKey_noaction_del", 5: "RI_FKey_check_ins"}.get(trigger_type,
                            "RI_FKey_noaction_upd" if relation == parent.name else "RI_FKey_check_upd")
                        FK_TRIGGERS.append(dict(label=trigger, relation=relation, kind=trigger_type, function=function,
                            internal=True, enabled="O", deferrable=False, deferred=False, function_schema="pg_catalog",
                            arguments="", argument_count=0, attributes="", condition=None, old_table=None, new_table=None,
                            other_relation=item.name if relation == parent.name else parent.name))
            else:
                EDGES.append(["delivery_index_" + constraint.name, 0, label, 0, "i"])
    for index in sorted(item.indexes, key=lambda i: i.name):
        EDGES += [["delivery_index_" + index.name, 0, tbl, positions[column.name], "a"] for column in index.columns]
