"""Append-only official mobile release corrections and withdrawals."""

from alembic import op
from oaf_website.release_approval_schema import upgrade_release_approvals

revision = "0007_release_approvals"
down_revision = "0006_notification_management"
branch_labels = None
depends_on = None


def upgrade():
    upgrade_release_approvals(op.get_bind())


def downgrade():
    raise RuntimeError("Ordinary migration downgrade is prohibited.")
