"""Metadata-only root. The administrative bootstrap must already exist."""

revision = "0001_migration_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Alembic creates/advances its version table inside the runner transaction.
    # No schema, feature objects, or runtime grants belong to this baseline.
    pass


def downgrade():
    raise RuntimeError("Ordinary migration downgrade is prohibited.")
