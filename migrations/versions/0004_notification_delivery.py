"""Double opt-in, mobile launch events, delivery attempts and durable suppression."""

from alembic import op
from oaf_website.notification_delivery_schema import upgrade_notification_delivery

revision = "0004_notification_delivery"
down_revision = "0003_notifications"
branch_labels = None
depends_on = None


def upgrade():
    upgrade_notification_delivery(op.get_bind())


def downgrade():
    raise RuntimeError("Ordinary migration downgrade is prohibited.")
