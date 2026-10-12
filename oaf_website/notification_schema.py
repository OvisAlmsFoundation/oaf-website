"""Notification consent lifecycles; imports never create database objects."""

from sqlalchemy import (
    Boolean, CheckConstraint, Column, DateTime, Index, MetaData,
    PrimaryKeyConstraint, String, Table, text,
)

from .state_request_schema import STATE_CODES

NOTIFICATIONS = "0003_notifications"
CONSENT_VERSION = "gramanna-announcements-v1"
metadata = MetaData(schema="oaf_website")
CHECKS = {
    "notifications_token_check": "unsubscribe_digest ~ '^[0-9a-f]{64}$'",
    "notifications_email_check": "email = lower(email) AND email = btrim(email) AND length(email) >= 3",
    "notifications_preferences_check": "web_launch OR android_launch OR ios_launch OR state IS NOT NULL",
    "notifications_state_check": "state IS NULL OR state IN (" + ", ".join(repr(c) for c in STATE_CODES) + ")",
    "notifications_consent_check": f"consent_version = '{CONSENT_VERSION}'",
    "notifications_lifecycle_check": "unsubscribed_at IS NULL OR unsubscribed_at >= created_at",
}
notifications = Table(
    "notifications", metadata,
    Column("unsubscribe_digest", String(64), nullable=False),
    Column("email", String(254), nullable=False),
    Column("web_launch", Boolean, nullable=False),
    Column("android_launch", Boolean, nullable=False),
    Column("ios_launch", Boolean, nullable=False),
    Column("state", String(2), nullable=True),
    Column("consent_version", String(40), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")),
    Column("unsubscribed_at", DateTime(timezone=True), nullable=True),
    PrimaryKeyConstraint("unsubscribe_digest", name="notifications_pk"),
    *(CheckConstraint(expression, name=name) for name, expression in CHECKS.items()),
)
active_email = Index("notifications_active_email", notifications.c.email, unique=True,
                     postgresql_where=notifications.c.unsubscribed_at.is_(None))
NOTIFICATION_GRANTS = [
    {"object": "oaf_website.notifications", "role": "matching_runtime",
     "privileges": ["SELECT", "INSERT"], "grant_option": False},
    {"object": "oaf_website.notifications.unsubscribed_at", "role": "matching_runtime",
     "privileges": ["UPDATE"], "grant_option": False},
]
NOTIFICATION_OBJECTS = [
    {"kind": "table", "name": "notifications"},
    {"kind": "index", "name": "notifications_pk"},
    {"kind": "index", "name": "notifications_active_email"},
    {"kind": "row_type", "name": "notifications"},
    {"kind": "array_type", "name": "_notifications"},
    {"kind": "primary_key", "name": "notifications_pk"},
    *({"kind": "check", "name": name} for name in CHECKS),
    {"kind": "default", "name": "notifications.created_at"},
]
NOTIFICATION_EDGES = [
    ["notification_table", 0, "schema", 0, "n"],
    ["notification_row_type", 0, "notification_table", 0, "i"],
    ["notification_array_type", 0, "notification_row_type", 0, "i"],
    ["notification_primary_key", 0, "notification_table", 1, "a"],
    ["notification_index", 0, "notification_primary_key", 0, "i"],
    ["notification_active_index", 0, "notification_table", 2, "a"],
    ["notification_active_index", 0, "notification_table", 9, "a"],
    ["notification_default", 0, "notification_table", 8, "a"],
]
CHECK_COLUMNS = {
    "notifications_token_check": [1], "notifications_email_check": [2],
    "notifications_preferences_check": [3, 4, 5, 6], "notifications_state_check": [6],
    "notifications_consent_check": [7], "notifications_lifecycle_check": [9, 8],
}
for name, columns in CHECK_COLUMNS.items():
    for column in columns:
        for kind in ("a", "n"):
            NOTIFICATION_EDGES.append(["notification_" + name, 0, "notification_table", column, kind])


def upgrade_notifications(connection):
    from sqlalchemy.schema import CreateIndex, CreateTable
    from .migration_config import IDENTITIES, Failure, MigrationError

    owner = connection.execute(text("SELECT current_user")).scalar_one()
    identity = next((i for i in IDENTITIES.values() if i.owner == owner), None)
    if identity is None:
        raise MigrationError(Failure.WRONG_IDENTITY)
    connection.execute(CreateTable(notifications))
    connection.execute(CreateIndex(active_email))
    connection.execute(text("REVOKE ALL ON TYPE oaf_website.notifications FROM PUBLIC"))
    connection.execute(text(f'GRANT SELECT, INSERT ON TABLE oaf_website.notifications TO "{identity.runtime}"'))
    connection.execute(text(f'GRANT UPDATE (unsubscribed_at) ON TABLE oaf_website.notifications TO "{identity.runtime}"'))
