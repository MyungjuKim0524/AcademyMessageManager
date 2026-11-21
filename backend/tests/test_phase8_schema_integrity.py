# ruff: noqa: E501  -- raw SQL statements are kept on one line for readability
"""Phase 8 Stage 2: database-level integrity of notifications (real PostgreSQL)."""

import os
import uuid
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from alembic import command
from app.db.session import create_db_engine

pytestmark = pytest.mark.postgres
HASH = "0" * 64


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
        assert c.execute(text("SELECT current_database()")).scalar() == "academy_learningops_test"
        c.execute(
            text(
                "TRUNCATE TABLE notification_send_attempt, parent_notification, notification_template, "
                "lesson_result, lesson, enrollment, student, classroom RESTART IDENTITY CASCADE"
            )
        )
        one = lambda sql, **p: c.execute(text(sql), p).scalar_one()  # noqa: E731
        a = one("INSERT INTO classroom(name,class_type) VALUES('A','REGULAR') RETURNING id")
        b = one("INSERT INTO classroom(name,class_type) VALUES('B','REGULAR') RETURNING id")
        s = one("INSERT INTO student(name) VALUES('s') RETURNING id")
        ea = one("INSERT INTO enrollment(student_id,classroom_id,status,enrolled_at) VALUES(:s,:c,'ACTIVE','2026-01-01') RETURNING id", s=s, c=a)
        sb = one("INSERT INTO student(name) VALUES('t') RETURNING id")
        eb = one("INSERT INTO enrollment(student_id,classroom_id,status,enrolled_at) VALUES(:s,:c,'ACTIVE','2026-01-01') RETURNING id", s=sb, c=b)
        la = one("INSERT INTO lesson(classroom_id,lesson_date) VALUES(:c,'2026-11-03') RETURNING id", c=a)
        tpl = one("INSERT INTO notification_template(name,body) VALUES('t','{학생명}') RETURNING id")
    return {"a": a, "b": b, "ea": ea, "eb": eb, "la": la, "tpl": tpl}


def _notification(c, ids, *, enrollment=None, classroom=None, status="DRAFT", approved=False, body="본문"):
    return c.execute(
        text(
            "INSERT INTO parent_notification(classroom_id,lesson_id,enrollment_id,template_id,template_version,template_body,"
            "recipient_email,body,source_hash,status,approved_at) VALUES(:c,:l,:e,:t,1,'{학생명}','p@example.invalid',:b,:h,:s,"
            "CASE WHEN :ap THEN CURRENT_TIMESTAMP END) RETURNING id"
        ),
        {"c": classroom or ids["a"], "l": ids["la"], "e": enrollment or ids["ea"], "t": ids["tpl"], "b": body, "h": HASH, "s": status, "ap": approved},
    ).scalar_one()


def _fails(engine: Engine, fn) -> None:
    with pytest.raises(IntegrityError):
        with engine.begin() as c:
            fn(c)


def test_notification_scope_uniqueness_and_status_rules(engine: Engine, ids) -> None:
    _fails(engine, lambda c: _notification(c, ids, enrollment=ids["eb"]))  # other classroom's student
    _fails(engine, lambda c: _notification(c, ids, classroom=ids["b"], enrollment=ids["eb"]))  # lesson of A
    _fails(engine, lambda c: _notification(c, ids, status="SENT"))  # unknown / misleading status
    _fails(engine, lambda c: _notification(c, ids, status="APPROVED"))  # approval needs approved_at
    _fails(engine, lambda c: _notification(c, ids, body="   "))
    _fails(engine, lambda c: _notification(c, ids, body="가" * 2001))
    with engine.begin() as c:
        first = _notification(c, ids)
    _fails(engine, lambda c: _notification(c, ids))  # one active message per lesson/student/template
    with engine.begin() as c:
        c.execute(text("UPDATE parent_notification SET status='CANCELLED' WHERE id=:i"), {"i": first})
        assert c.execute(text("SELECT version FROM parent_notification WHERE id=:i"), {"i": first}).scalar() == 2
        _notification(c, ids)  # cancelled one no longer blocks a new draft
    _fails(engine, lambda c: c.execute(text("DELETE FROM lesson WHERE id=:l"), {"l": ids["la"]}))


def test_send_attempt_ledger_rules(engine: Engine, ids) -> None:
    with engine.begin() as c:
        nid = _notification(c, ids, status="APPROVED", approved=True)

    def attempt(c, result, code=None, key=None):
        c.execute(
            text(
                "INSERT INTO notification_send_attempt(notification_id,idempotency_key,result,error_code) "
                "VALUES(:n,:k,:r,:e)"
            ),
            {"n": nid, "k": str(key or uuid.uuid4()), "r": result, "e": code},
        )

    _fails(engine, lambda c: attempt(c, "MOCK_FAILURE"))  # failure needs an error code
    _fails(engine, lambda c: attempt(c, "MOCK_SUCCESS", "X"))
    _fails(engine, lambda c: attempt(c, "SENT"))
    _fails(
        engine,
        lambda c: c.execute(
            text("INSERT INTO notification_send_attempt(notification_id,idempotency_key,channel,result) VALUES(:n,:k,'SMS','MOCK_SUCCESS')"),
            {"n": nid, "k": str(uuid.uuid4())},
        ),
    )
    key = uuid.uuid4()
    with engine.begin() as c:
        attempt(c, "MOCK_FAILURE", "MOCK_RECIPIENT_REJECTED", key)
        attempt(c, "MOCK_SUCCESS")
    _fails(engine, lambda c: attempt(c, "MOCK_FAILURE", "X", key))  # idempotency key is unique
    _fails(engine, lambda c: attempt(c, "MOCK_SUCCESS"))  # at most one success per message
    _fails(engine, lambda c: c.execute(text("DELETE FROM parent_notification WHERE id=:n"), {"n": nid}))


def test_template_rules_and_downgrade_roundtrip(engine: Engine, ids) -> None:
    _fails(engine, lambda c: c.execute(text("INSERT INTO notification_template(name,body) VALUES('t','x')")))
    _fails(engine, lambda c: c.execute(text("INSERT INTO notification_template(name,body) VALUES('u','  ')")))
    with engine.begin() as c:
        c.execute(text("UPDATE notification_template SET body='{분반명}' WHERE id=:t"), {"t": ids["tpl"]})
        assert c.execute(text("SELECT version FROM notification_template WHERE id=:t"), {"t": ids["tpl"]}).scalar() == 2
        c.execute(text("TRUNCATE TABLE notification_send_attempt, parent_notification, notification_template RESTART IDENTITY CASCADE"))
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    command.downgrade(config, "007_phase71_sessions_pauses")
    with engine.connect() as c:
        assert c.scalar(text("SELECT to_regclass('parent_notification')")) is None
    command.upgrade(config, "head")
    with engine.connect() as c:
        assert c.scalar(text("SELECT name FROM notification_template")) == "수업 안내 (기본)"
