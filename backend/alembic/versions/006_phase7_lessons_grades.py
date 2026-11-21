"""Phase 7: lesson management, attendance integrity, assessments and grades.

Additive only. Existing rows, keys and CHECK values used by the Java import stay unchanged.
"""

import sqlalchemy as sa

from alembic import op

revision = "006_phase7_lessons_grades"
down_revision = "005_staff_display_name"
branch_labels = None
depends_on = None

TIMESTAMP_DEFAULT = sa.text("CURRENT_TIMESTAMP")


def _version_trigger(table: str) -> None:
    op.execute(
        f"CREATE TRIGGER trg_{table}_version BEFORE UPDATE ON {table} "
        "FOR EACH ROW EXECUTE FUNCTION bump_row_version()"
    )


def upgrade() -> None:
    # Every UPDATE (including legacy Java updates) advances the optimistic-lock version.
    op.execute(
        """
        CREATE FUNCTION bump_row_version() RETURNS TRIGGER AS $$
        BEGIN
            NEW.version := OLD.version + 1;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )

    # lesson: topic, memo, status and version. Legacy/imported lessons are past lessons.
    op.add_column("lesson", sa.Column("topic", sa.String(200)))
    op.add_column("lesson", sa.Column("memo", sa.String(2000)))
    op.add_column(
        "lesson",
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'COMPLETED'")),
    )
    op.add_column(
        "lesson", sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1"))
    )
    op.create_check_constraint(
        "chk_lesson_status", "lesson", "status IN ('SCHEDULED','COMPLETED','CANCELLED')"
    )
    op.create_unique_constraint("uq_lesson_id_classroom", "lesson", ["id", "classroom_id"])
    _version_trigger("lesson")

    # lesson_result is the attendance record: memo, version and a classroom consistency guard.
    op.add_column("lesson_result", sa.Column("memo", sa.String(500)))
    op.add_column(
        "lesson_result",
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )
    _version_trigger("lesson_result")
    op.execute(
        """
        CREATE FUNCTION check_lesson_result_classroom() RETURNS TRIGGER AS $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM lesson l
                JOIN enrollment e ON e.classroom_id = l.classroom_id
                WHERE l.id = NEW.lesson_id AND e.id = NEW.enrollment_id
            ) THEN
                RAISE EXCEPTION 'lesson_result lesson and enrollment belong to different classrooms'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER trg_lesson_result_classroom "
        "BEFORE INSERT OR UPDATE OF lesson_id, enrollment_id ON lesson_result "
        "FOR EACH ROW EXECUTE FUNCTION check_lesson_result_classroom()"
    )

    op.create_unique_constraint(
        "uq_enrollment_id_classroom", "enrollment", ["id", "classroom_id"]
    )

    op.create_table(
        "assessment",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "classroom_id",
            sa.BigInteger(),
            sa.ForeignKey("classroom.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("lesson_id", sa.BigInteger()),
        sa.Column("title", sa.String(100), nullable=False),
        sa.Column("assessment_date", sa.Date(), nullable=False),
        sa.Column("max_score", sa.Numeric(6, 2), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
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
        sa.CheckConstraint("max_score > 0", name="chk_assessment_max_score"),
        sa.CheckConstraint("btrim(title) <> ''", name="chk_assessment_title"),
        sa.ForeignKeyConstraint(
            ["lesson_id", "classroom_id"],
            ["lesson.id", "lesson.classroom_id"],
            name="fk_assessment_lesson_classroom",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("id", "classroom_id", "max_score", name="uq_assessment_scope"),
    )
    op.create_index(
        "idx_assessment_classroom_date", "assessment", ["classroom_id", "assessment_date"]
    )
    op.execute(
        "CREATE TRIGGER trg_assessment_updated_at BEFORE UPDATE ON assessment "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    _version_trigger("assessment")

    op.create_table(
        "assessment_result",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("assessment_id", sa.BigInteger(), nullable=False),
        sa.Column("classroom_id", sa.BigInteger(), nullable=False),
        sa.Column("max_score", sa.Numeric(6, 2), nullable=False),
        sa.Column("enrollment_id", sa.BigInteger(), nullable=False),
        sa.Column("result_status", sa.String(20), nullable=False),
        sa.Column("score", sa.Numeric(6, 2)),
        sa.Column("memo", sa.String(500)),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
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
            "result_status IN ('SCORED','NOT_TAKEN')", name="chk_assessment_result_status"
        ),
        sa.CheckConstraint(
            "(result_status = 'SCORED' AND score IS NOT NULL AND score >= 0 "
            "AND score <= max_score) OR (result_status = 'NOT_TAKEN' AND score IS NULL)",
            name="chk_assessment_result_score",
        ),
        sa.ForeignKeyConstraint(
            ["assessment_id", "classroom_id", "max_score"],
            ["assessment.id", "assessment.classroom_id", "assessment.max_score"],
            name="fk_assessment_result_assessment",
            onupdate="CASCADE",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["enrollment_id", "classroom_id"],
            ["enrollment.id", "enrollment.classroom_id"],
            name="fk_assessment_result_enrollment",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("assessment_id", "enrollment_id", name="uq_assessment_result"),
    )
    op.create_index("idx_assessment_result_enrollment", "assessment_result", ["enrollment_id"])
    op.execute(
        "CREATE TRIGGER trg_assessment_result_updated_at BEFORE UPDATE ON assessment_result "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    _version_trigger("assessment_result")


def downgrade() -> None:
    op.drop_table("assessment_result")
    op.drop_table("assessment")
    op.drop_constraint("uq_enrollment_id_classroom", "enrollment", type_="unique")
    op.execute("DROP TRIGGER trg_lesson_result_classroom ON lesson_result")
    op.execute("DROP FUNCTION check_lesson_result_classroom()")
    op.execute("DROP TRIGGER trg_lesson_result_version ON lesson_result")
    op.drop_column("lesson_result", "version")
    op.drop_column("lesson_result", "memo")
    op.execute("DROP TRIGGER trg_lesson_version ON lesson")
    op.drop_constraint("uq_lesson_id_classroom", "lesson", type_="unique")
    op.drop_constraint("chk_lesson_status", "lesson", type_="check")
    op.drop_column("lesson", "version")
    op.drop_column("lesson", "status")
    op.drop_column("lesson", "memo")
    op.drop_column("lesson", "topic")
    op.execute("DROP FUNCTION bump_row_version()")
