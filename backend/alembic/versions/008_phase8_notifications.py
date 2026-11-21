"""Phase 8: parent notification templates, drafts/approval workflow and mock send attempts.

New tables only. The Java message tables (message_template, message_draft, delivery_job,
delivery_attempt) record real e-mail sends and are intentionally left untouched.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "008_phase8_notifications"
down_revision = "007_phase71_sessions_pauses"
branch_labels = None
depends_on = None

NOW = sa.text("CURRENT_TIMESTAMP")
STATUSES = "('DRAFT','READY_FOR_REVIEW','APPROVED','MOCK_SENT','MOCK_FAILED','CANCELLED')"

DEFAULT_TEMPLATE = (
    "안녕하세요. {학생명} 학생의 {수업일자} {분반명} 수업 안내입니다.\n"
    "\n"
    "수업 내용: {수업주제}\n"
    "출결: {출결}\n"
    "{보강메시지}\n"
    "{성적요약}\n"
    "\n"
    "감사합니다."
)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    ]


def _staff(name: str) -> sa.Column:
    return sa.Column(name, sa.BigInteger(), sa.ForeignKey("staff_user.id", ondelete="SET NULL"))


def _triggers(table: str) -> None:
    op.execute(
        f"CREATE TRIGGER trg_{table}_updated_at BEFORE UPDATE ON {table} "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.execute(
        f"CREATE TRIGGER trg_{table}_version BEFORE UPDATE ON {table} "
        "FOR EACH ROW EXECUTE FUNCTION bump_row_version()"
    )


def upgrade() -> None:
    template = op.create_table(
        "notification_template",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        _staff("created_by_staff_user_id"),
        *_timestamps(),
        sa.CheckConstraint("btrim(name) <> ''", name="chk_notification_template_name"),
        sa.CheckConstraint(
            "btrim(body) <> '' AND char_length(body) <= 2000", name="chk_notification_template_body"
        ),
        sa.UniqueConstraint("name", name="uq_notification_template_name"),
    )
    _triggers("notification_template")

    op.create_table(
        "parent_notification",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("classroom_id", sa.BigInteger(), nullable=False),
        sa.Column("lesson_id", sa.BigInteger(), nullable=False),
        sa.Column("enrollment_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "template_id",
            sa.BigInteger(),
            sa.ForeignKey("notification_template.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("template_version", sa.Integer(), nullable=False),
        # Template text as used at generation: lets approval re-check the source data exactly.
        sa.Column("template_body", sa.Text(), nullable=False),
        sa.Column("recipient_email", sa.String(255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("source_hash", sa.CHAR(64), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default=sa.text("'DRAFT'")),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        _staff("created_by_staff_user_id"),
        _staff("updated_by_staff_user_id"),
        _staff("approved_by_staff_user_id"),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        *_timestamps(),
        sa.CheckConstraint(f"status IN {STATUSES}", name="chk_parent_notification_status"),
        sa.CheckConstraint(
            "btrim(body) <> '' AND char_length(body) <= 2000", name="chk_parent_notification_body"
        ),
        sa.CheckConstraint(
            "status NOT IN ('APPROVED','MOCK_SENT','MOCK_FAILED') OR approved_at IS NOT NULL",
            name="chk_parent_notification_approved",
        ),
        sa.ForeignKeyConstraint(
            ["lesson_id", "classroom_id"],
            ["lesson.id", "lesson.classroom_id"],
            name="fk_parent_notification_lesson",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["enrollment_id", "classroom_id"],
            ["enrollment.id", "enrollment.classroom_id"],
            name="fk_parent_notification_enrollment",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "uq_parent_notification_active",
        "parent_notification",
        ["lesson_id", "enrollment_id", "template_id"],
        unique=True,
        postgresql_where=sa.text("status <> 'CANCELLED'"),
    )
    op.create_index(
        "idx_parent_notification_classroom_status",
        "parent_notification",
        ["classroom_id", "status"],
    )
    op.create_index("idx_parent_notification_lesson", "parent_notification", ["lesson_id"])
    _triggers("parent_notification")

    op.create_table(
        "notification_send_attempt",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "notification_id",
            sa.BigInteger(),
            sa.ForeignKey("parent_notification.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("idempotency_key", postgresql.UUID(), nullable=False),
        sa.Column("channel", sa.String(10), nullable=False, server_default=sa.text("'MOCK'")),
        sa.Column("result", sa.String(20), nullable=False),
        sa.Column("error_code", sa.String(50)),
        sa.Column("error_message", sa.String(255)),
        _staff("requested_by_staff_user_id"),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.CheckConstraint("channel = 'MOCK'", name="chk_notification_send_attempt_channel"),
        sa.CheckConstraint(
            "(result = 'MOCK_SUCCESS' AND error_code IS NULL) OR "
            "(result = 'MOCK_FAILURE' AND error_code IS NOT NULL)",
            name="chk_notification_send_attempt_result",
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_notification_send_attempt_key"),
    )
    op.create_index(
        "uq_notification_send_attempt_success",
        "notification_send_attempt",
        ["notification_id"],
        unique=True,
        postgresql_where=sa.text("result = 'MOCK_SUCCESS'"),
    )
    op.create_index(
        "idx_notification_send_attempt_notification",
        "notification_send_attempt",
        ["notification_id"],
    )

    op.bulk_insert(template, [{"name": "수업 안내 (기본)", "body": DEFAULT_TEMPLATE}])


def downgrade() -> None:
    op.drop_table("notification_send_attempt")
    op.drop_table("parent_notification")
    op.drop_table("notification_template")
