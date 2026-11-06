"""0010: reuse the outbox for explicit re-opt-in and retain revocation evidence."""

from sqlalchemy import CheckConstraint, Column, DateTime, MetaData, text
from sqlalchemy.schema import AddConstraint, DropConstraint

from .notification_management_schema import intents as previous_intents, notifications
from .notification_delivery_schema import suppressions as previous_suppressions

REOPTIN = "0010_voluntary_reoptin"
metadata = MetaData(schema="oaf_website")
notifications.to_metadata(metadata)
intents = previous_intents.to_metadata(metadata)
PURPOSE_CHECK = "notification_confirmation_intents_purpose_check"
previous_check = next(c for c in previous_intents.constraints if c.name == PURPOSE_CHECK)
intents.constraints.remove(next(c for c in intents.constraints if c.name == PURPOSE_CHECK))
intents.append_column(Column("revoked_at", DateTime(timezone=True), nullable=True))
intents.append_constraint(CheckConstraint(
    "(purpose IN ('confirmation','reoptin') AND management_revision IS NULL) OR "
    "(purpose = 'management' AND management_revision >= 0 AND management_revision IS NOT NULL)",
    name=PURPOSE_CHECK))
intents.append_constraint(CheckConstraint(
    "revoked_at IS NULL OR (purpose = 'reoptin' AND revoked_at >= created_at)",
    name="notification_confirmation_intents_revocation_check"))
suppressions = previous_suppressions.to_metadata(metadata)
suppressions.append_column(Column("reoptin_blocked_at", DateTime(timezone=True), nullable=True))
suppressions.append_constraint(CheckConstraint(
    "reoptin_blocked_at IS NULL OR reoptin_blocked_at >= created_at",
    name="notification_suppressions_reoptin_block_check"))
ADDED_OBJECTS = [dict(kind="check", name="notification_confirmation_intents_revocation_check"),
                 dict(kind="check", name="notification_suppressions_reoptin_block_check")]
ADDED_EDGES = [["delivery_constraint_notification_confirmation_intents_revocation_check", 0,
                "delivery_table_notification_confirmation_intents", position, kind]
               for position in (list(intents.columns).index(intents.c.created_at) + 1,
                                list(intents.columns).index(intents.c.purpose) + 1,
                                len(intents.columns)) for kind in ("a", "n")]
ADDED_EDGES += [["delivery_constraint_notification_suppressions_reoptin_block_check", 0,
                 "delivery_table_notification_suppressions", position, kind]
                for position in (3, 4) for kind in ("a", "n")]
GRANTS = [dict(object="oaf_website.notification_confirmation_intents.revoked_at",
               role="matching_runtime", privileges=["UPDATE"], grant_option=False),
          dict(object="oaf_website.notification_suppressions.reoptin_blocked_at",
               role="matching_runtime", privileges=["UPDATE"], grant_option=False)]


def upgrade_voluntary_reoptin(connection):
    from .migration_config import IDENTITIES, Failure, MigrationError
    owner = connection.execute(text("SELECT current_user")).scalar_one()
    identity = next((i for i in IDENTITIES.values() if i.owner == owner), None)
    if identity is None:
        raise MigrationError(Failure.WRONG_IDENTITY)
    connection.execute(text("ALTER TABLE oaf_website.notification_confirmation_intents "
                            "ADD COLUMN revoked_at timestamp with time zone"))
    connection.execute(DropConstraint(previous_check))
    for constraint in sorted(intents.constraints, key=lambda c: c.name):
        if constraint.name in {PURPOSE_CHECK, ADDED_OBJECTS[0]["name"]}:
            connection.execute(AddConstraint(constraint))
    connection.execute(text('GRANT UPDATE (revoked_at) ON TABLE '
                            f'oaf_website.notification_confirmation_intents TO "{identity.runtime}"'))
    connection.execute(text("ALTER TABLE oaf_website.notification_suppressions "
                            "ADD COLUMN reoptin_blocked_at timestamp with time zone"))
    connection.execute(AddConstraint(next(c for c in suppressions.constraints
                                         if c.name == "notification_suppressions_reoptin_block_check")))
    connection.execute(text('GRANT UPDATE (reoptin_blocked_at) ON TABLE '
                            f'oaf_website.notification_suppressions TO "{identity.runtime}"'))
