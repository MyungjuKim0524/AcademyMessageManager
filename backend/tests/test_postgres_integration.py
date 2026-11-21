import os
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import Engine, inspect, select, text
from sqlalchemy.exc import IntegrityError, OperationalError

from alembic import command
from app.db.models.tables import Classroom, Enrollment, Student
from app.db.schema import (
    ACADEMIC_TABLES,
    AUTH_TABLES,
    EXPECTED_TABLES,
    LEGACY_IMPORT_TABLES,
    LEGACY_TABLES,
    assert_expected_schema,
    server_identity,
)
from app.db.session import create_db_engine, create_session_factory

pytestmark = pytest.mark.postgres


def _enabled() -> bool:
    return os.getenv("ACADEMY_RUN_POSTGRES_INTEGRATION") == "1"


@pytest.fixture(scope="module")
def engine() -> Engine:
    if not _enabled():
        pytest.skip("ACADEMY_RUN_POSTGRES_INTEGRATION=1이 필요합니다.")
    db_engine = create_db_engine()
    with db_engine.connect() as connection:
        identity = server_identity(connection)
        assert identity["database"] == "academy_learningops_test"
        assert identity["user"] == "academy_test"
        existing = set(inspect(connection).get_table_names()) - {"alembic_version"}
        # Allowed states: empty, Java baseline, Phase 5-6B (+auth), Phase 7 (006), 7.1 (007),
        # 008-009 (legacy import tables still present), head (010 dropped them).
        assert not existing or existing in {
            LEGACY_TABLES,
            LEGACY_TABLES | AUTH_TABLES,
            LEGACY_TABLES | AUTH_TABLES | {"assessment", "assessment_result"},
            LEGACY_TABLES | AUTH_TABLES | ACADEMIC_TABLES,
            EXPECTED_TABLES | LEGACY_IMPORT_TABLES,
            EXPECTED_TABLES,
        }

    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    command.upgrade(config, "head")
    with db_engine.connect() as connection:
        assert_expected_schema(connection)
    yield db_engine
    db_engine.dispose()


@pytest.fixture(autouse=True)
def clean_rows(engine: Engine) -> None:
    with engine.begin() as connection:
        assert_expected_schema(connection)
        connection.execute(
            text(
                "TRUNCATE TABLE audit_log, auth_session, classroom_staff_assignment, staff_user, "
                "delivery_attempt, delivery_job, message_draft, "
                "message_template, makeup_request, assessment_result, "
                "assessment, enrollment_pause, lesson_result, lesson, "
                "enrollment, student, classroom RESTART IDENTITY CASCADE"
            )
        )


def test_connection_identity_and_bad_credentials(engine: Engine) -> None:
    with engine.connect() as connection:
        identity = server_identity(connection)
        assert identity["database"] == "academy_learningops_test"
        assert identity["user"] == "academy_test"
        assert "PostgreSQL 17.6" in str(identity["version"])

    wrong = create_db_engine(
        "postgresql+psycopg://academy_test:wrong@127.0.0.1:55432/academy_learningops_test"
    )
    try:
        with pytest.raises(OperationalError):
            wrong.connect()
    finally:
        wrong.dispose()


def test_student_crud_and_transaction_rollback(engine: Engine) -> None:
    factory = create_session_factory(engine)
    with factory.begin() as session:
        student = Student(name="합성학생", school_name="가상학교")
        session.add(student)
    with factory.begin() as session:
        stored = session.scalar(select(Student).where(Student.name == "합성학생"))
        assert stored is not None
        stored.parent_email = "parent@example.invalid"
    with factory() as session:
        assert (
            session.scalar(select(Student).where(Student.name == "합성학생")).parent_email
            == "parent@example.invalid"
        )  # type: ignore[union-attr]

    try:
        with factory.begin() as session:
            session.add(Student(name="롤백학생", school_name="가상학교"))
            session.flush()
            raise RuntimeError("force rollback")
    except RuntimeError:
        pass
    with factory() as session:
        assert session.scalar(select(Student).where(Student.name == "롤백학생")) is None

    with factory.begin() as session:
        session.delete(session.scalar(select(Student).where(Student.name == "합성학생")))  # type: ignore[arg-type]


def test_constraints_and_partial_unique_indexes(engine: Engine) -> None:
    factory = create_session_factory(engine)
    with factory.begin() as session:
        session.add(Student(name="중복학생", school_name=None))
    with pytest.raises(IntegrityError):
        with factory.begin() as session:
            session.add(Student(name="중복학생", school_name=None))

    with pytest.raises(IntegrityError):
        with factory.begin() as session:
            session.add(Classroom(name="오류반", class_type="INVALID"))

    with pytest.raises(IntegrityError):
        with factory.begin() as session:
            session.add(
                Enrollment(
                    student_id=999999,
                    classroom_id=999999,
                    status="ACTIVE",
                    enrolled_at="2026-11-06",
                )
            )  # type: ignore[arg-type]

    with engine.begin() as connection:
        classroom_id = connection.execute(
            text(
                "INSERT INTO classroom(name,class_type) "
                "VALUES('부분인덱스반','REGULAR') RETURNING id"
            )
        ).scalar_one()
        connection.execute(
            text("INSERT INTO lesson(classroom_id,lesson_date) VALUES(:id,'2026-11-06')"),
            {"id": classroom_id},
        )
        with pytest.raises(IntegrityError):
            connection.execute(
                text("INSERT INTO lesson(classroom_id,lesson_date) VALUES(:id,'2026-11-06')"),
                {"id": classroom_id},
            )


def test_sessions_are_distinct_and_recover_after_failure(engine: Engine) -> None:
    factory = create_session_factory(engine)
    first, second = factory(), factory()
    try:
        assert first is not second
        first.add(Classroom(name="실패반", class_type="INVALID"))
        with pytest.raises(IntegrityError):
            first.commit()
        first.rollback()
        second.add(Classroom(name="정상반", class_type="REGULAR"))
        second.commit()
        assert second.scalar(select(Classroom).where(Classroom.name == "정상반")) is not None
    finally:
        first.close()
        second.close()


def test_legacy_import_table_drop_refuses_to_delete_existing_records(engine: Engine) -> None:
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    command.downgrade(config, "009_phase81_lesson_upload")
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO import_job(source_type, source_file_name) VALUES ('CSV', 'x.csv')"
                )
            )
        with pytest.raises(RuntimeError, match="import_job=1"):
            command.upgrade(config, "head")
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM import_job")) == 1  # kept
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM import_job"))
    finally:
        command.upgrade(config, "head")
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT to_regclass('import_job')")) is None


def test_alembic_version_and_schema_reproducibility(engine: Engine) -> None:
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    command.upgrade(config, "head")
    with engine.connect() as connection:
        assert (
            connection.scalar(text("SELECT version_num FROM alembic_version"))
            == "011_staff_deleted_status"
        )
        staff_status = connection.scalar(
            text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conname = 'chk_staff_user_status'"
            )
        )
        assert "DELETED" in staff_status  # staff deletion option B (migration 011)
        for table in LEGACY_IMPORT_TABLES:
            assert connection.scalar(text("SELECT to_regclass(:t)"), {"t": table}) is None
        assert_expected_schema(connection)
        display_name = {
            column["name"]: column for column in inspect(connection).get_columns("staff_user")
        }["display_name"]
        assert display_name["nullable"] is True
        assert display_name["type"].length == 100
        assert set(inspect(connection).get_table_names()) == EXPECTED_TABLES | {"alembic_version"}
        triggers = set(
            connection.execute(
                text(
                    "SELECT trigger_name FROM information_schema.triggers "
                    "WHERE trigger_schema='public'"
                )
            ).scalars()
        )
        assert triggers == {
            "trg_student_updated_at",
            "trg_classroom_updated_at",
            "trg_enrollment_updated_at",
            "trg_lesson_updated_at",
            "trg_lesson_result_updated_at",
            "trg_makeup_request_updated_at",
            "trg_message_template_updated_at",
            "trg_message_draft_updated_at",
            "trg_delivery_job_updated_at",
            "trg_lesson_version",
            "trg_lesson_result_version",
            "trg_lesson_result_classroom",
            "trg_assessment_updated_at",
            "trg_assessment_version",
            "trg_assessment_result_updated_at",
            "trg_assessment_result_version",
            "trg_enrollment_pause_updated_at",
            "trg_enrollment_pause_sync",
            "trg_notification_template_updated_at",
            "trg_notification_template_version",
            "trg_parent_notification_updated_at",
            "trg_parent_notification_version",
        }
        partial_indexes = " ".join(
            connection.execute(
                text(
                    "SELECT indexdef FROM pg_indexes WHERE schemaname='public' "
                    "AND indexname LIKE 'uq_lesson_%'"
                )
            ).scalars()
        )
        assert "WHERE (exam_round IS NOT NULL)" in partial_indexes
        assert "WHERE (exam_round IS NULL)" in partial_indexes
