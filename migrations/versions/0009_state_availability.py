"""State-specific availability in the existing authenticated release inventory."""

from alembic import op
from oaf_website.state_availability_schema import upgrade_state_availability

revision = "0009_state_availability"
down_revision = "0008_web_launch"
branch_labels = None
depends_on = None


def upgrade():
    upgrade_state_availability(op.get_bind())


def downgrade():
    raise RuntimeError("Ordinary migration downgrade is prohibited.")
