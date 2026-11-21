"""Add a human-readable display name to staff accounts."""

import sqlalchemy as sa

from alembic import op

revision = "005_staff_display_name"
down_revision = "004_phase6b_assignment_integrity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable so existing accounts stay valid; the API requires it for new accounts.
    op.add_column("staff_user", sa.Column("display_name", sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column("staff_user", "display_name")
