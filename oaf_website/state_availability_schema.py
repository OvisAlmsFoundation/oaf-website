"""0009 state scope in the existing event table; historical helpers stay exact."""

from sqlalchemy import CheckConstraint, Index, MetaData, text
from sqlalchemy.schema import AddConstraint, CreateIndex, DropConstraint

from .state_request_schema import STATE_CODES
from .web_launch_schema import events as previous_events, TABLES as PREVIOUS_TABLES, EDGES as PREVIOUS_EDGES, CHECKS as WEB_CHECKS

STATE_AVAILABILITY = "0009_state_availability"
metadata = MetaData(schema="oaf_website")
events = previous_events.to_metadata(metadata)
LAUNCH = "notification_release_events_launch"
STATE_INDEX = "notification_release_events_state"
CHECKS = {
    "notification_release_events_platform_check": "platform IN ('android','ios','web','state')",
    "notification_release_events_content_check": WEB_CHECKS["notification_release_events_content_check"]
        + " OR (platform = 'state' AND content_version = 'state-availability-v1' AND release_id IN ("
        + ", ".join(repr(code) for code in STATE_CODES) + "))",
}
for constraint in tuple(events.constraints):
    if constraint.name in {*CHECKS, LAUNCH}:
        events.constraints.remove(constraint)
for name, expression in CHECKS.items():
    events.append_constraint(CheckConstraint(expression, name=name))
Index(LAUNCH, events.c.environment, events.c.platform, unique=True,
      postgresql_where=text("platform <> 'state'"))
Index(STATE_INDEX, events.c.environment, events.c.platform, events.c.release_id, unique=True,
      postgresql_where=events.c.platform == "state")
TABLES = tuple(events if item is previous_events else item for item in PREVIOUS_TABLES)
REMOVED_OBJECTS = [dict(kind="unique", name=LAUNCH)]
ADDED_OBJECTS = [dict(kind="index", name=STATE_INDEX)]
REMOVED_EDGES = [edge for edge in PREVIOUS_EDGES if edge[0] in {
    "delivery_constraint_" + LAUNCH, "delivery_index_" + LAUNCH}]
ADDED_EDGES = [["delivery_index_" + name, 0, "delivery_table_" + events.name, position, "a"]
               # PostgreSQL 17 records platform for both the key and predicate.
               for name, positions in ((LAUNCH, (3, 4, 4)), (STATE_INDEX, (3, 4, 4, 5)))
               for position in positions]
EDGES = [edge for edge in PREVIOUS_EDGES if edge not in REMOVED_EDGES] + ADDED_EDGES


def upgrade_state_availability(connection):
    from .migration_config import IDENTITIES, Failure, MigrationError
    owner = connection.execute(text("SELECT current_user")).scalar_one()
    if owner not in {identity.owner for identity in IDENTITIES.values()}:
        raise MigrationError(Failure.WRONG_IDENTITY)
    for constraint in sorted(previous_events.constraints, key=lambda c: c.name):
        if constraint.name in {*CHECKS, LAUNCH}:
            connection.execute(DropConstraint(constraint))
    for constraint in sorted(events.constraints, key=lambda c: c.name):
        if constraint.name in CHECKS:
            connection.execute(AddConstraint(constraint))
    for index in sorted(events.indexes, key=lambda i: i.name):
        connection.execute(CreateIndex(index))
