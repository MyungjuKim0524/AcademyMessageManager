"""Phase 7.1: same-day lesson sessions, dated enrollment pauses, EXCUSED attendance.

Additive for data: no rows are deleted or rewritten. Two unique indexes are replaced by wider
ones (adding session_no); every existing lesson becomes session 1, so uniqueness is preserved.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ExcludeConstraint

from alembic import op

revision = "007_phase71_sessions_pauses"
down_revision = "006_phase7_lessons_grades"
branch_labels = None
depends_on = None

TIMESTAMP_DEFAULT = sa.text("CURRENT_TIMESTAMP")
# The container runs in UTC; the academy's business day is Korean time (as in the Python API).
BUSINESS_TODAY = "(CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Seoul')::date"


def upgrade() -> None:
    # 1. Same-day sessions. Java inserts omit session_no and therefore always create session 1.
    op.add_column(
        "lesson",
        sa.Column("session_no", sa.SmallInteger(), nullable=False, server_default=sa.text("1")),
    )
    op.create_check_constraint("chk_lesson_session_no", "lesson", "session_no BETWEEN 1 AND 9")
    op.create_index(
        "uq_lesson_session_with_exam_round",
        "lesson",
        ["classroom_id", "lesson_date", "exam_round", "session_no"],
        unique=True,
        postgresql_where=sa.text("exam_round IS NOT NULL"),
    )
    op.create_index(
        "uq_lesson_session_without_exam_round",
        "lesson",
        ["classroom_id", "lesson_date", "session_no"],
        unique=True,
        postgresql_where=sa.text("exam_round IS NULL"),
    )
    op.drop_index("uq_lesson_with_exam_round", table_name="lesson")
    op.drop_index("uq_lesson_without_exam_round", table_name="lesson")

    # 2. EXCUSED (인정결석). Widening only; every existing value stays valid.
    op.drop_constraint("chk_lesson_result_attendance", "lesson_result", type_="check")
    op.create_check_constraint(
        "chk_lesson_result_attendance",
        "lesson_result",
        "attendance_status IN ('PRESENT','ABSENT','LATE','EXCUSED')",
    )

    # 3. Dated pause history. btree_gist lets one EXCLUDE constraint forbid overlapping pauses.
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.create_table(
        "enrollment_pause",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "enrollment_id",
            sa.BigInteger(),
            sa.ForeignKey("enrollment.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("paused_from", sa.Date(), nullable=False),
        sa.Column("resumed_on", sa.Date()),
        sa.Column("source", sa.String(20), nullable=False, server_default=sa.text("'MANUAL'")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=TIMESTAMP_DEFAULT,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=TIMESTAMP_DEFAULT,
        ),
        sa.CheckConstraint(
            "resumed_on IS NULL OR resumed_on > paused_from", name="chk_enrollment_pause_dates"
        ),
        sa.CheckConstraint(
            "source IN ('MANUAL','STATUS_CHANGE')", name="chk_enrollment_pause_source"
        ),
        ExcludeConstraint(
            ("enrollment_id", "="),
            (sa.text("daterange(paused_from, resumed_on, '[)')"), "&&"),
            name="ex_enrollment_pause_overlap",
            using="gist",
        ),
    )
    op.execute(
        "CREATE TRIGGER trg_enrollment_pause_updated_at BEFORE UPDATE ON enrollment_pause "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    # Status changes made outside the pause API (e.g. the Java import) still leave a dated record,
    # using the day the change was observed. The pause API writes the record first, so it is
    # never duplicated here.
    op.execute(
        f"""
        CREATE FUNCTION sync_enrollment_pause() RETURNS TRIGGER AS $$
        BEGIN
            IF NEW.status = 'PAUSED' AND (TG_OP = 'INSERT' OR OLD.status <> 'PAUSED') THEN
                IF NOT EXISTS (
                    SELECT 1 FROM enrollment_pause
                    WHERE enrollment_id = NEW.id AND resumed_on IS NULL
                ) THEN
                    -- Paused again before the last pause has ended (e.g. resumed and re-paused
                    -- on the same day by repeated imports): continue that pause instead of
                    -- inserting an overlapping one.
                    UPDATE enrollment_pause SET resumed_on = NULL
                    WHERE enrollment_id = NEW.id AND resumed_on > {BUSINESS_TODAY};
                    IF NOT FOUND THEN
                        INSERT INTO enrollment_pause(enrollment_id, paused_from, source)
                        VALUES (
                            NEW.id, GREATEST({BUSINESS_TODAY}, NEW.enrolled_at), 'STATUS_CHANGE'
                        );
                    END IF;
                END IF;
            ELSIF TG_OP = 'UPDATE' AND OLD.status = 'PAUSED' AND NEW.status <> 'PAUSED' THEN
                UPDATE enrollment_pause
                SET resumed_on = GREATEST({BUSINESS_TODAY}, paused_from + 1)
                WHERE enrollment_id = NEW.id AND resumed_on IS NULL;
            END IF;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER trg_enrollment_pause_sync AFTER INSERT OR UPDATE OF status ON enrollment "
        "FOR EACH ROW EXECUTE FUNCTION sync_enrollment_pause()"
    )


def downgrade() -> None:
    # Fails on purpose if EXCUSED rows or same-day session 2+ lessons exist (no silent data loss).
    op.execute("DROP TRIGGER trg_enrollment_pause_sync ON enrollment")
    op.execute("DROP FUNCTION sync_enrollment_pause()")
    op.drop_table("enrollment_pause")
    op.drop_constraint("chk_lesson_result_attendance", "lesson_result", type_="check")
    op.create_check_constraint(
        "chk_lesson_result_attendance",
        "lesson_result",
        "attendance_status IN ('PRESENT','ABSENT','LATE')",
    )
    op.create_index(
        "uq_lesson_without_exam_round",
        "lesson",
        ["classroom_id", "lesson_date"],
        unique=True,
        postgresql_where=sa.text("exam_round IS NULL"),
    )
    op.create_index(
        "uq_lesson_with_exam_round",
        "lesson",
        ["classroom_id", "lesson_date", "exam_round"],
        unique=True,
        postgresql_where=sa.text("exam_round IS NOT NULL"),
    )
    op.drop_index("uq_lesson_session_without_exam_round", table_name="lesson")
    op.drop_index("uq_lesson_session_with_exam_round", table_name="lesson")
    op.drop_constraint("chk_lesson_session_no", "lesson", type_="check")
    op.drop_column("lesson", "session_no")
