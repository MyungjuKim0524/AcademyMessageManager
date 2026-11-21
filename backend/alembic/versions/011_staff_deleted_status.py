"""Allow staff_user.status = 'DELETED' (user decision 2026-11-20, staff deletion option B).

An account with work history (log-ins, confirmed / sent messages, changes) is deleted by marking
it DELETED: it cannot log in and disappears from staff lists, but every history row keeps
pointing at it, so "who did this" is never lost. An account without any history is removed for
real. Downgrade refuses while a DELETED account exists, so no account is silently revived.
"""

from alembic import op

revision = "011_staff_deleted_status"
down_revision = "010_drop_legacy_import_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE staff_user DROP CONSTRAINT chk_staff_user_status")
    op.execute(
        "ALTER TABLE staff_user ADD CONSTRAINT chk_staff_user_status "
        "CHECK (status IN ('ACTIVE','INACTIVE','DELETED'))"
    )


def downgrade() -> None:
    deleted = (
        op.get_bind()
        .exec_driver_sql("SELECT count(*) FROM staff_user WHERE status = 'DELETED'")
        .scalar_one()
    )
    if deleted:
        raise RuntimeError(
            f"삭제 처리된 직원 계정 {deleted}개가 있어 되돌리지 않습니다. "
            "상태를 정한 뒤 다시 실행하세요."
        )
    op.execute("ALTER TABLE staff_user DROP CONSTRAINT chk_staff_user_status")
    op.execute(
        "ALTER TABLE staff_user ADD CONSTRAINT chk_staff_user_status "
        "CHECK (status IN ('ACTIVE','INACTIVE'))"
    )
