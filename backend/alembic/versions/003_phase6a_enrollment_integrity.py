"""Prevent duplicate student/classroom enrollments."""

from alembic import op

revision = "003_phase6a_enrollment_integrity"
down_revision = "002_staff_auth_rbac"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_enrollment_student_classroom", "enrollment", ["student_id", "classroom_id"], unique=True
    )


def downgrade() -> None:
    op.drop_index("uq_enrollment_student_classroom", table_name="enrollment")
