# ruff: noqa: E501  -- raw SQL statements are kept on one line for readability
"""Phase 7 Stage 2: database-level integrity of lessons, attendance and grades (real PostgreSQL)."""

import os
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import IntegrityError

from alembic import command
from app.db.session import create_db_engine

pytestmark = pytest.mark.postgres
HEAD = "011_staff_deleted_status"


@pytest.fixture(scope="module")
def engine() -> Engine:
    if os.getenv("ACADEMY_RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("ACADEMY_RUN_POSTGRES_INTEGRATION=1 is required")
    db_engine = create_db_engine()
    command.upgrade(Config(str(Path(__file__).parents[1] / "alembic.ini")), "head")
    yield db_engine
    db_engine.dispose()


@pytest.fixture()
def ids(engine: Engine) -> dict[str, int]:
    with engine.begin() as c:
        assert c.execute(text("SELECT current_database(), current_user")).one() == (
            "academy_learningops_test",
            "academy_test",
        )
        c.execute(
            text(
                "TRUNCATE TABLE assessment_result, assessment, makeup_request, message_draft, "
                "lesson_result, lesson, enrollment, student, classroom "
                "RESTART IDENTITY CASCADE"
            )
        )
        one = lambda sql, **p: c.execute(text(sql), p).scalar_one()  # noqa: E731
        a = one("INSERT INTO classroom(name,class_type) VALUES('A','REGULAR') RETURNING id")
        b = one("INSERT INTO classroom(name,class_type) VALUES('B','REGULAR') RETURNING id")
        s1 = one("INSERT INTO student(name) VALUES('s1') RETURNING id")
        s2 = one("INSERT INTO student(name) VALUES('s2') RETURNING id")
        enrol = "INSERT INTO enrollment(student_id,classroom_id,status,enrolled_at) VALUES(:s,:c,'ACTIVE','2026-01-01') RETURNING id"
        ea = one(enrol, s=s1, c=a)
        eb = one(enrol, s=s2, c=b)
        # Java import inserts only these three columns.
        la = one(
            "INSERT INTO lesson(classroom_id,lesson_date,exam_round) VALUES(:c,'2026-11-01',NULL) RETURNING id",
            c=a,
        )
        lb = one(
            "INSERT INTO lesson(classroom_id,lesson_date,exam_round) VALUES(:c,'2026-11-01',NULL) RETURNING id",
            c=b,
        )
        asm = one(
            "INSERT INTO assessment(classroom_id,lesson_id,title,assessment_date,max_score) "
            "VALUES(:c,:l,'quiz','2026-11-01',10) RETURNING id",
            c=a,
            l=la,
        )
    return {"a": a, "b": b, "ea": ea, "eb": eb, "la": la, "lb": lb, "asm": asm}


def _fails(engine: Engine, sql: str, **params) -> None:
    with pytest.raises(IntegrityError):
        with engine.begin() as c:
            c.execute(text(sql), params)


def _result(c: Connection, asm: int, enrollment: int, classroom: int, score, status="SCORED"):
    return c.execute(
        text(
            "INSERT INTO assessment_result(assessment_id,classroom_id,max_score,enrollment_id,result_status,score) "
            "SELECT id,classroom_id,max_score,:e,:st,:sc FROM assessment WHERE id=:a RETURNING id"
        ),
        {"a": asm, "e": enrollment, "st": status, "sc": score},
    ).scalar_one()


def test_legacy_lesson_insert_defaults_and_version_trigger(engine: Engine, ids) -> None:
    with engine.begin() as c:
        status, version = c.execute(
            text("SELECT status, version FROM lesson WHERE id=:id"), {"id": ids["la"]}
        ).one()
        assert (status, version) == ("COMPLETED", 1)
        c.execute(text("UPDATE lesson SET topic='t' WHERE id=:id"), {"id": ids["la"]})
        c.execute(text("UPDATE lesson SET topic='u' WHERE id=:id"), {"id": ids["la"]})
        assert (
            c.execute(text("SELECT version FROM lesson WHERE id=:id"), {"id": ids["la"]}).scalar()
            == 3
        )
    _fails(engine, "UPDATE lesson SET status='DONE' WHERE id=:id", id=ids["la"])


def test_attendance_classroom_guard_and_uniqueness(engine: Engine, ids) -> None:
    insert = "INSERT INTO lesson_result(lesson_id,enrollment_id,attendance_status) VALUES(:l,:e,:s)"
    _fails(engine, insert, l=ids["la"], e=ids["eb"], s="PRESENT")  # other classroom's student
    _fails(engine, insert, l=ids["la"], e=ids["ea"], s="SICK")  # unsupported status (EXCUSED is valid since 7.1)
    with engine.begin() as c:
        c.execute(text(insert), {"l": ids["la"], "e": ids["ea"], "s": "PRESENT"})
        # Legacy Java-style UPDATE bumps the version too.
        c.execute(
            text("UPDATE lesson_result SET attendance_status='LATE' WHERE lesson_id=:l"),
            {"l": ids["la"]},
        )
        assert c.execute(text("SELECT version FROM lesson_result")).scalar() == 2
    _fails(engine, insert, l=ids["la"], e=ids["ea"], s="ABSENT")  # duplicate
    _fails(engine, "UPDATE lesson_result SET lesson_id=:l", l=ids["lb"])  # move across classrooms


def test_assessment_result_score_rules(engine: Engine, ids) -> None:
    a, asm, ea, eb = ids["a"], ids["asm"], ids["ea"], ids["eb"]
    for score, status in (
        (Decimal("10.01"), "SCORED"),
        (Decimal("-1"), "SCORED"),
        (None, "SCORED"),
        (Decimal("0"), "NOT_TAKEN"),
    ):
        with pytest.raises(IntegrityError):
            with engine.begin() as c:
                _result(c, asm, ea, a, score, status)
    with pytest.raises(IntegrityError):  # student of another classroom
        with engine.begin() as c:
            c.execute(
                text(
                    "INSERT INTO assessment_result(assessment_id,classroom_id,max_score,enrollment_id,result_status,score) "
                    "VALUES(:a,:c,10,:e,'SCORED',1)"
                ),
                {"a": asm, "c": ids["a"], "e": eb},
            )
    with pytest.raises(IntegrityError):  # forged max_score
        with engine.begin() as c:
            c.execute(
                text(
                    "INSERT INTO assessment_result(assessment_id,classroom_id,max_score,enrollment_id,result_status,score) "
                    "VALUES(:a,:c,100,:e,'SCORED',50)"
                ),
                {"a": asm, "c": a, "e": ea},
            )
    with engine.begin() as c:
        _result(c, asm, ea, a, Decimal("0"))  # zero is a real score, distinct from missing
    with pytest.raises(IntegrityError):  # one result per assessment and student
        with engine.begin() as c:
            _result(c, asm, ea, a, Decimal("5"))
    with engine.begin() as c:
        c.execute(text("UPDATE assessment_result SET score=9.5"))
    _fails(engine, "UPDATE assessment SET max_score=9 WHERE id=:a", a=asm)  # would exceed new max
    with engine.begin() as c:
        c.execute(text("UPDATE assessment SET max_score=20 WHERE id=:a"), {"a": asm})
        assert c.execute(text("SELECT max_score FROM assessment_result")).scalar() == Decimal(
            "20.00"
        )


def test_assessment_cannot_link_other_classroom_lesson(engine: Engine, ids) -> None:
    _fails(
        engine,
        "INSERT INTO assessment(classroom_id,lesson_id,title,assessment_date,max_score) "
        "VALUES(:c,:l,'x',:d,10)",
        c=ids["a"],
        l=ids["lb"],
        d=date(2026, 11, 1),
    )
    _fails(
        engine,
        "INSERT INTO assessment(classroom_id,title,assessment_date,max_score) VALUES(:c,'  ',:d,10)",
        c=ids["a"],
        d=date(2026, 11, 1),
    )
    _fails(
        engine,
        "INSERT INTO assessment(classroom_id,title,assessment_date,max_score) VALUES(:c,'x',:d,0)",
        c=ids["a"],
        d=date(2026, 11, 1),
    )
    _fails(engine, "DELETE FROM lesson WHERE id=:l", l=ids["la"])  # linked assessment keeps lesson


def test_migration_downgrade_and_reupgrade(engine: Engine) -> None:
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    with engine.begin() as c:
        c.execute(text("TRUNCATE TABLE assessment_result, assessment RESTART IDENTITY CASCADE"))
    command.downgrade(config, "005_staff_display_name")
    with engine.connect() as c:
        assert c.scalar(text("SELECT to_regclass('assessment')")) is None
        assert c.scalar(text("SELECT count(*) FROM pg_proc WHERE proname='bump_row_version'")) == 0
    command.upgrade(config, "head")
    with engine.connect() as c:
        assert c.scalar(text("SELECT version_num FROM alembic_version")) == HEAD
