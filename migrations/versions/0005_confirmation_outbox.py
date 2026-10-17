"""Atomic, recoverable lifecycle/version-bound confirmation delivery intents."""

from alembic import op
from oaf_website.confirmation_outbox_schema import upgrade_confirmation_outbox

revision = "0005_confirmation_outbox"
down_revision = "0004_notification_delivery"
branch_labels = None
depends_on = None


def upgrade():
    upgrade_confirmation_outbox(op.get_bind())


def downgrade():
    raise RuntimeError("Ordinary migration downgrade is prohibited.")
