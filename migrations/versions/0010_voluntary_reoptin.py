"""Lifecycle-specific voluntary re-opt-in through the existing confirmation outbox."""

from alembic import op
from oaf_website.reoptin_schema import upgrade_voluntary_reoptin

revision = "0010_voluntary_reoptin"
down_revision = "0009_state_availability"
branch_labels = None
depends_on = None


def upgrade():
    upgrade_voluntary_reoptin(op.get_bind())


def downgrade():
    raise RuntimeError("Ordinary migration downgrade is prohibited.")
