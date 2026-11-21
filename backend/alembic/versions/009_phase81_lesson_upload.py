"""Phase 8.1: academy workbook upload support.

* notification_template.default_for_class_type: the template used automatically for drafts
  created from a workbook upload (one per class type).
* One test category (assessment title) per lesson, so re-uploading a workbook updates the same
  assessment instead of creating duplicates.

Additive: two default templates are inserted; no existing row is changed or removed.
"""

import sqlalchemy as sa

from alembic import op

revision = "009_phase81_lesson_upload"
down_revision = "008_phase8_notifications"
branch_labels = None
depends_on = None

REGULAR_TEMPLATE = (
    "안녕하세요, 학원입니다.\n"
    "{학생명} 학생의 {수업일자} 정규 수업 학습 현황 안내드립니다.\n"
    "\n"
    "출결: {출결}\n"
    "{예습메시지}\n"
    "{주간메시지}\n"
    "{성적요약}\n"
    "{보강메시지}\n"
    "\n"
    "오늘도 감사드립니다."
)
EXAM_PREP_TEMPLATE = (
    "안녕하세요, 학원입니다.\n"
    "{학생명} 학생의 {수업일자} 내신 대비 수업 학습 현황 안내드립니다.\n"
    "\n"
    "출결: {출결}\n"
    "{예습메시지}\n"
    "{주간메시지}\n"
    "{성적요약}\n"
    "{보강메시지}\n"
    "\n"
    "시험 대비 기간 동안 꾸준히 학습할 수 있도록 지도하겠습니다.\n"
    "감사합니다."
)


def upgrade() -> None:
    op.add_column(
        "notification_template", sa.Column("default_for_class_type", sa.String(20), nullable=True)
    )
    op.create_check_constraint(
        "chk_notification_template_default_type",
        "notification_template",
        "default_for_class_type IS NULL OR default_for_class_type IN ('REGULAR','EXAM_PREP')",
    )
    op.create_index(
        "uq_notification_template_default_type",
        "notification_template",
        ["default_for_class_type"],
        unique=True,
        postgresql_where=sa.text("default_for_class_type IS NOT NULL"),
    )
    op.create_index(
        "uq_assessment_lesson_title",
        "assessment",
        ["lesson_id", "title"],
        unique=True,
        postgresql_where=sa.text("lesson_id IS NOT NULL"),
    )
    template = sa.table(
        "notification_template",
        sa.column("name", sa.String),
        sa.column("body", sa.Text),
        sa.column("default_for_class_type", sa.String),
    )
    op.bulk_insert(
        template,
        [
            {
                "name": "정규반 기본 안내",
                "body": REGULAR_TEMPLATE,
                "default_for_class_type": "REGULAR",
            },
            {
                "name": "내신 대비 기본 안내",
                "body": EXAM_PREP_TEMPLATE,
                "default_for_class_type": "EXAM_PREP",
            },
        ],
    )


def downgrade() -> None:
    op.drop_index("uq_assessment_lesson_title", table_name="assessment")
    op.drop_index("uq_notification_template_default_type", table_name="notification_template")
    op.drop_constraint(
        "chk_notification_template_default_type", "notification_template", type_="check"
    )
    op.drop_column("notification_template", "default_for_class_type")
