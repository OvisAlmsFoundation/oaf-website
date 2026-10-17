"""Additive 0004 source. No import/startup DDL; 0001--0003 stay immutable."""

from sqlalchemy import (CheckConstraint, Column, DateTime, ForeignKeyConstraint, Index,
                        Integer, MetaData, PrimaryKeyConstraint, String, Table, UniqueConstraint, text)
from .notification_schema import notifications

DELIVERY = "0004_notification_delivery"
metadata = MetaData(schema="oaf_website")
# Resolve FKs without modifying the historical 0003 metadata/helper.
notifications.to_metadata(metadata)


def table(name, columns, checks, *constraints):
    return Table(name, metadata, *columns,
                 *(CheckConstraint(value, name=name + "_" + key) for key, value in checks.items()),
                 *constraints)


def stamp(name, nullable=False):
    return Column(name, DateTime(timezone=True), nullable=nullable)


verification = table("notification_verification", [
    Column("subscription", String(64), nullable=False),
    Column("token_digest", String(64), nullable=False),
    stamp("issued_at"), stamp("expires_at"), stamp("verified_at", True),
], {"token_check": "token_digest ~ '^[0-9a-f]{64}$'",
    "time_check": "expires_at > issued_at AND (verified_at IS NULL OR verified_at >= issued_at AND verified_at < expires_at)"},
    PrimaryKeyConstraint("subscription", name="notification_verification_pk"),
    UniqueConstraint("token_digest", name="notification_verification_token"),
    ForeignKeyConstraint(["subscription"], ["oaf_website.notifications.unsubscribe_digest"],
                         name="notification_verification_subscription_fk"))
limits = table("notification_confirmation_limits", [
    Column("bucket", String(64), nullable=False), stamp("window_start"), stamp("last_requested_at"),
    Column("requests", Integer, nullable=False),
], {"count_check": "requests BETWEEN 1 AND 1000",
    "time_check": "last_requested_at >= window_start",
    "bucket_check": "bucket ~ '^[0-9a-f]{64}$'"},
    PrimaryKeyConstraint("bucket", name="notification_confirmation_limits_pk"))
events = table("notification_release_events", [
    Column("event_id", String(36), nullable=False), Column("source_approval_id", String(36), nullable=False),
    Column("environment", String(11), nullable=False), Column("platform", String(7), nullable=False),
    Column("release_id", String(150), nullable=False), Column("release_url", String(300), nullable=False),
    stamp("approved_at"), stamp("audience_cutoff"), Column("content_version", String(40), nullable=False),
    Column("payload_digest", String(64), nullable=False), Column("status", String(12), nullable=False),
    stamp("created_at"), stamp("updated_at"),
], {"environment_check": "environment IN ('development','testing','production')",
    "platform_check": "platform IN ('android','ios')",
    "content_check": "content_version = 'mobile-launch-v1'",
    "status_check": "status IN ('received','ready','completed','attention')",
    "time_check": "audience_cutoff <= approved_at AND approved_at <= created_at AND updated_at >= created_at",
    "digest_check": "payload_digest ~ '^[0-9a-f]{64}$'"},
    PrimaryKeyConstraint("event_id", name="notification_release_events_pk"),
    UniqueConstraint("environment", "platform", name="notification_release_events_launch"))
deliveries = table("notification_deliveries", [
    Column("event_id", String(36), nullable=False), Column("subscription", String(64), nullable=False),
    Column("status", String(12), nullable=False), Column("attempts", Integer, nullable=False),
    Column("claim_digest", String(64), nullable=True), stamp("lease_until", True), stamp("next_attempt_at", True),
    Column("outcome", String(24), nullable=True), Column("provider_message_id", String(200), nullable=True),
    stamp("created_at"), stamp("updated_at"), stamp("accepted_at", True),
], {"status_check": "status IN ('pending','claimed','submitting','accepted','rejected','failed','suppressed','uncertain')",
    "attempts_check": "attempts BETWEEN 0 AND 3",
    "claim_check": "(status IN ('claimed','submitting') AND claim_digest IS NOT NULL AND lease_until IS NOT NULL) OR (status NOT IN ('claimed','submitting') AND claim_digest IS NULL AND lease_until IS NULL)",
    "digest_check": "claim_digest IS NULL OR claim_digest ~ '^[0-9a-f]{64}$'",
    "retry_check": "next_attempt_at IS NULL OR status IN ('pending','failed') AND attempts < 3",
    "accepted_check": "(status = 'accepted') = (accepted_at IS NOT NULL)",
    "outcome_check": "outcome IS NULL OR outcome IN ('provider_accepted','provider_rejected','not_submitted','retryable_rejection','submission_unknown','claim_expired','suppressed','ineligible')",
    "time_check": "updated_at >= created_at AND (accepted_at IS NULL OR accepted_at >= created_at)"},
    PrimaryKeyConstraint("event_id", "subscription", name="notification_deliveries_pk"),
    ForeignKeyConstraint(["event_id"], ["oaf_website.notification_release_events.event_id"], name="notification_deliveries_event_fk"),
    ForeignKeyConstraint(["subscription"], ["oaf_website.notifications.unsubscribe_digest"], name="notification_deliveries_subscription_fk"))
attempts = table("notification_delivery_attempts", [
    Column("event_id", String(36), nullable=False), Column("subscription", String(64), nullable=False),
    Column("attempt", Integer, nullable=False), stamp("claimed_at"), stamp("submitting_at", True),
    stamp("finished_at", True), Column("outcome", String(24), nullable=True),
    Column("provider_message_id", String(200), nullable=True),
], {"attempt_check": "attempt BETWEEN 1 AND 3",
    "outcome_check": "outcome IS NULL OR outcome IN ('provider_accepted','provider_rejected','not_submitted','retryable_rejection','submission_unknown','claim_expired','suppressed','ineligible')",
    "time_check": "(submitting_at IS NULL OR submitting_at >= claimed_at) AND (finished_at IS NULL OR finished_at >= claimed_at)"},
    PrimaryKeyConstraint("event_id", "subscription", "attempt", name="notification_delivery_attempts_pk"),
    ForeignKeyConstraint(["event_id", "subscription"],
                         ["oaf_website.notification_deliveries.event_id", "oaf_website.notification_deliveries.subscription"],
                         name="notification_delivery_attempts_delivery_fk"))
suppressions = table("notification_suppressions", [
    Column("mailbox_digest", String(64), nullable=False), Column("reason", String(20), nullable=False),
    stamp("created_at"),
], {"digest_check": "mailbox_digest ~ '^[0-9a-f]{64}$'",
    "reason_check": "reason IN ('hard_bounce','complaint','provider_block','owner_policy')"},
    PrimaryKeyConstraint("mailbox_digest", name="notification_suppressions_pk"))
TABLES = (verification, limits, events, deliveries, attempts, suppressions)
Index("notification_deliveries_retry", deliveries.c.status, deliveries.c.next_attempt_at)
Index("notification_deliveries_lease", deliveries.c.status, deliveries.c.lease_until)
# Immutable identities/content and append-only suppression; no DELETE privilege.
MUTABLE = {
    verification.name: ("token_digest", "issued_at", "expires_at", "verified_at"),
    limits.name: ("window_start", "last_requested_at", "requests"),
    events.name: ("status", "updated_at"),
    deliveries.name: ("status", "attempts", "claim_digest", "lease_until", "next_attempt_at", "outcome",
                      "provider_message_id", "updated_at", "accepted_at"),
    attempts.name: ("submitting_at", "finished_at", "outcome", "provider_message_id"),
    suppressions.name: (),
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


def upgrade_notification_delivery(connection):
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
        if MUTABLE[item.name]:
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
