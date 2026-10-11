"""${message}

Draft only: adding an artifact requires independent contract/manifest approval.
"""

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = None
depends_on = None


def upgrade():
    raise RuntimeError("Unapproved migration draft.")


def downgrade():
    raise RuntimeError("Ordinary migration downgrade is prohibited.")
