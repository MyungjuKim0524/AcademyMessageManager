"""Prevent duplicate open classroom staff assignments."""

import sqlalchemy as sa

from alembic import op

revision = "004_phase6b_assignment_integrity"
down_revision = "003_phase6a_enrollment_integrity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_assignment_open_staff_classroom",
        "classroom_staff_assignment",
        ["classroom_id", "staff_user_id"],
        unique=True,
        postgresql_where=sa.text("valid_to IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_assignment_open_staff_classroom",
        table_name="classroom_staff_assignment",
    )
