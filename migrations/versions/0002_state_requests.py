"""Anonymous counted requests; the runner owns the transaction and approval gates."""

from alembic import op
from oaf_website.state_request_schema import upgrade_state_requests

revision = "0002_state_requests"
down_revision = "0001_migration_baseline"
branch_labels = None
depends_on = None


def upgrade():
    upgrade_state_requests(op.get_bind())


def downgrade():
    raise RuntimeError("Ordinary migration downgrade is prohibited.")
