"""0008 extends only existing release-event checks; historical schemas stay exact."""

from sqlalchemy import CheckConstraint, MetaData, text
from sqlalchemy.schema import AddConstraint, DropConstraint

from .notification_delivery_schema import events as original_events, TABLES as ORIGINAL_TABLES, EDGES as ORIGINAL_EDGES

WEB_LAUNCH = "0008_web_launch"
metadata = MetaData(schema="oaf_website")
events = original_events.to_metadata(metadata)
CHECKS = {
    "notification_release_events_platform_check": "platform IN ('android','ios','web')",
    "notification_release_events_content_check": "(platform IN ('android','ios') AND content_version = 'mobile-launch-v1') OR (platform = 'web' AND content_version = 'web-launch-v1' AND release_id = 'gramanna-web')",
}
for constraint in tuple(events.constraints):
    if constraint.name in CHECKS:
        events.constraints.remove(constraint)
for name, expression in CHECKS.items():
    events.append_constraint(CheckConstraint(expression, name=name))
TABLES = tuple(events if item is original_events else item for item in ORIGINAL_TABLES)
# The typed content check now also depends on platform and release_id.
ADDED_EDGES = [
    ["delivery_constraint_notification_release_events_content_check", 0,
     "delivery_table_notification_release_events", position, kind]
    for position in (4, 5) for kind in ("a", "n")
]
EDGES = ORIGINAL_EDGES + ADDED_EDGES


def upgrade_web_launch(connection):
    from .migration_config import IDENTITIES, Failure, MigrationError
    owner = connection.execute(text("SELECT current_user")).scalar_one()
    if owner not in {identity.owner for identity in IDENTITIES.values()}:
        raise MigrationError(Failure.WRONG_IDENTITY)
    for constraint in sorted(original_events.constraints, key=lambda c: c.name):
        if constraint.name in CHECKS:
            connection.execute(DropConstraint(constraint))
    for constraint in sorted(events.constraints, key=lambda c: c.name):
        if constraint.name in CHECKS:
            connection.execute(AddConstraint(constraint))
