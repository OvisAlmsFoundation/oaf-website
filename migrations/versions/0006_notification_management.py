"""Audited editable preferences and management recovery in the existing outbox."""

from alembic import op
from oaf_website.notification_management_schema import upgrade_notification_management

revision = "0006_notification_management"
down_revision = "0005_confirmation_outbox"
branch_labels = None
depends_on = None


def upgrade():
    upgrade_notification_management(op.get_bind())


def downgrade():
    raise RuntimeError("Ordinary migration downgrade is prohibited.")
