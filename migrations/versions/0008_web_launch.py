"""Typed web launch in the existing event contract; no new tables or grants."""

from alembic import op
from oaf_website.web_launch_schema import upgrade_web_launch

revision = "0008_web_launch"
down_revision = "0007_release_approvals"
branch_labels = None
depends_on = None


def upgrade():
    upgrade_web_launch(op.get_bind())


def downgrade():
    raise RuntimeError("Ordinary migration downgrade is prohibited.")
