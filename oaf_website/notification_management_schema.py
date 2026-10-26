"""0006 additive contract. Historical metadata and revisions remain unchanged."""

from sqlalchemy import (Boolean, CheckConstraint, Column, DateTime, ForeignKeyConstraint,
                        Integer, MetaData, PrimaryKeyConstraint, String, Table,
                        UniqueConstraint, text)
from .notification_schema import notifications as original_notifications
from .confirmation_outbox_schema import intents as original_intents
from .state_request_schema import STATE_CODES

MANAGEMENT = "0006_notification_management"
CONSENT_VERSION = "gramanna-preferences-v2"
metadata = MetaData(schema="oaf_website")
notifications = original_notifications.to_metadata(metadata)
notifications.append_column(Column("preferences_revision", Integer, nullable=False, server_default=text("0")))
notifications.append_constraint(CheckConstraint("preferences_revision >= 0", name="notifications_revision_check"))
intents = original_intents.to_metadata(metadata)
intents.append_column(Column("purpose", String(20), nullable=False, server_default=text("'confirmation'")))
intents.append_column(Column("management_revision", Integer, nullable=True))
intents.append_constraint(CheckConstraint(
    "(purpose = 'confirmation' AND management_revision IS NULL) OR "
    "(purpose = 'management' AND management_revision >= 0 AND management_revision IS NOT NULL)",
    name="notification_confirmation_intents_purpose_check"))

changes = Table("notification_preference_changes", metadata,
    Column("action_digest", String(64), nullable=False),
    Column("subscription", String(64), nullable=False),
    Column("payload_digest", String(64), nullable=False),
    Column("source", String(20), nullable=False),
    Column("previous_revision", Integer, nullable=False),
    Column("revision", Integer, nullable=False),
    *(Column(prefix + name, Boolean if name != "state" else String(2), nullable=name == "state")
      for prefix in ("before_", "after_") for name in ("web_launch", "android_launch", "ios_launch", "state")),
    *(Column(name + "_granted_at", DateTime(timezone=True), nullable=True)
      for name in ("web_launch", "android_launch", "ios_launch", "state")),
    Column("consent_version", String(40), nullable=True),
    Column("outcome", String(20), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("provider_message_id", String(200), nullable=True),
    Column("provider_event_at", DateTime(timezone=True), nullable=True),
    PrimaryKeyConstraint("action_digest", name="notification_preference_changes_pk"),
    UniqueConstraint("subscription", "revision", name="notification_preference_changes_revision_key"),
    ForeignKeyConstraint(["subscription"], ["oaf_website.notifications.unsubscribe_digest"],
                         name="notification_preference_changes_subscription_fk"),
    CheckConstraint("action_digest ~ '^[0-9a-f]{64}$' AND payload_digest ~ '^[0-9a-f]{64}$'",
                    name="notification_preference_changes_digest_check"),
    CheckConstraint("previous_revision >= 0 AND revision > previous_revision",
                    name="notification_preference_changes_revision_check"),
    CheckConstraint("source IN ('management', 'legacy', 'brevo') AND outcome IN ('saved', 'unsubscribed')",
                    name="notification_preference_changes_outcome_check"),
    CheckConstraint("(outcome = 'saved' AND consent_version = 'gramanna-preferences-v2' AND consent_version IS NOT NULL) "
                    "OR (outcome = 'unsubscribed' AND consent_version IS NULL)",
                    name="notification_preference_changes_consent_check"),
    CheckConstraint("(source = 'brevo' AND provider_message_id IS NOT NULL AND provider_event_at IS NOT NULL "
                    "AND outcome = 'unsubscribed') OR (source IN ('management', 'legacy') "
                    "AND provider_message_id IS NULL AND provider_event_at IS NULL)",
                    name="notification_preference_changes_provider_check"),
    *(CheckConstraint(prefix + "state IS NULL OR " + prefix + "state IN (" +
                      ", ".join(repr(s) for s in STATE_CODES) + ")",
                      name="notification_preference_changes_" + prefix + "state_check")
      for prefix in ("before_", "after_")),
    *(CheckConstraint(name + "_granted_at IS NULL OR " + name + "_granted_at <= created_at",
                      name="notification_preference_changes_" + name + "_time_check")
      for name in ("web_launch", "android_launch", "ios_launch", "state")),
)
TABLES = (changes,)
MUTABLE = {changes.name: ()}
PREFERENCE_COLUMNS = ("web_launch", "android_launch", "ios_launch", "state")
NOTIFICATION_MUTABLE = ("unsubscribed_at", *PREFERENCE_COLUMNS, "preferences_revision")
GRANTS = [dict(object="oaf_website.notifications." + c, role="matching_runtime",
               privileges=["UPDATE"], grant_option=False) for c in (*PREFERENCE_COLUMNS, "preferences_revision")]
GRANTS.append(dict(object="oaf_website." + changes.name, role="matching_runtime",
                   privileges=["SELECT", "INSERT"], grant_option=False))

# Generate only this successor's new table inventory and exact dependency edges
# with the same conventions as the historical schema helpers.
OBJECTS = [dict(kind=k, name=n) for k, n in (
    ("table", changes.name), ("row_type", changes.name), ("array_type", "_" + changes.name))]
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
                EDGES += [[label, 0, "notification_index", 0, "n"], [label, 0, "notification_table", 1, "n"]]
                for relation, types in (("notifications", (9, 17)), (item.name, (5, 17))):
                    for trigger_type in types:
                        trigger = "delivery_trigger_" + constraint.name + "_" + relation + "_" + str(trigger_type)
                        EDGES.append([trigger, 0, label, 0, "i"])
                        function = {9: "RI_FKey_noaction_del", 5: "RI_FKey_check_ins"}.get(trigger_type,
                            "RI_FKey_noaction_upd" if relation == "notifications" else "RI_FKey_check_upd")
                        FK_TRIGGERS.append(dict(label=trigger, relation=relation, kind=trigger_type, function=function,
                            internal=True, enabled="O", deferrable=False, deferred=False, function_schema="pg_catalog",
                            arguments="", argument_count=0, attributes="", condition=None, old_table=None, new_table=None,
                            other_relation=item.name if relation == "notifications" else "notifications"))
            else:
                OBJECTS.append(dict(kind="index", name=constraint.name))
                EDGES.append(["delivery_index_" + constraint.name, 0, label, 0, "i"])

ADDED_OBJECTS = OBJECTS + [
    dict(kind="check", name="notifications_revision_check"),
    dict(kind="default", name="notifications.preferences_revision"),
    dict(kind="check", name="notification_confirmation_intents_purpose_check"),
    dict(kind="default", name="notification_confirmation_intents.purpose"),
]
EDGES += [["notification_notifications_revision_check", 0, "notification_table", 10, k] for k in ("a", "n")]
EDGES += [["management_default_notifications_preferences_revision", 0, "notification_table", 10, "a"],
          ["management_default_notification_confirmation_intents_purpose", 0,
           "delivery_table_notification_confirmation_intents", len(original_intents.columns) + 1, "a"]]
EDGES += [["delivery_constraint_notification_confirmation_intents_purpose_check", 0,
           "delivery_table_notification_confirmation_intents", len(original_intents.columns) + n, k]
          for n in (1, 2) for k in ("a", "n")]


def upgrade_notification_management(connection):
    from sqlalchemy.schema import CreateTable
    from .migration_config import IDENTITIES, Failure, MigrationError
    owner = connection.execute(text("SELECT current_user")).scalar_one()
    identity = next((i for i in IDENTITIES.values() if i.owner == owner), None)
    if identity is None:
        raise MigrationError(Failure.WRONG_IDENTITY)
    for sql in (
        "ALTER TABLE oaf_website.notifications ADD COLUMN preferences_revision integer NOT NULL DEFAULT 0",
        "ALTER TABLE oaf_website.notifications ADD CONSTRAINT notifications_revision_check CHECK (preferences_revision >= 0)",
        "ALTER TABLE oaf_website.notification_confirmation_intents ADD COLUMN purpose varchar(20) NOT NULL DEFAULT 'confirmation'",
        "ALTER TABLE oaf_website.notification_confirmation_intents ADD COLUMN management_revision integer",
        "ALTER TABLE oaf_website.notification_confirmation_intents ADD CONSTRAINT notification_confirmation_intents_purpose_check CHECK "
        "((purpose = 'confirmation' AND management_revision IS NULL) OR (purpose = 'management' AND management_revision >= 0 AND management_revision IS NOT NULL))",
    ):
        connection.execute(text(sql))
    connection.execute(CreateTable(changes))
    connection.execute(text("REVOKE ALL ON TYPE oaf_website.notification_preference_changes FROM PUBLIC"))
    connection.execute(text(f'GRANT SELECT, INSERT ON TABLE oaf_website.notification_preference_changes TO "{identity.runtime}"'))
    connection.execute(text(f'GRANT UPDATE (web_launch, android_launch, ios_launch, state, preferences_revision) ON TABLE oaf_website.notifications TO "{identity.runtime}"'))
