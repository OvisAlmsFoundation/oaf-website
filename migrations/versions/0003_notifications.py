"""GraManna announcement subscriptions and private unsubscribe capabilities."""

from alembic import op
from oaf_website.notification_schema import upgrade_notifications

revision = "0003_notifications"
down_revision = "0002_state_requests"
branch_labels = None
depends_on = None


def upgrade():
    upgrade_notifications(op.get_bind())


def downgrade():
    raise RuntimeError("Ordinary migration downgrade is prohibited.")
