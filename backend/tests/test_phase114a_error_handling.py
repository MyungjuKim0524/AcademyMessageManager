# ruff: noqa: E501  -- SQL kept on one line (as in the other integration suites)
"""Phase 11-4-A: database failures the client can act on, bounded connect time, linear upload
buffering. Unit tests need no database; the one PostgreSQL test only connects (no data)."""

import asyncio
import logging
import os
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError
from sqlalchemy.exc import TimeoutError as PoolTimeout

from app.config import get_settings
from app.db.session import (
    DB_CONNECT_TIMEOUT_SECONDS,
    create_db_engine,
    create_session_factory,
    get_db,
)
from app.main import app
from app.middleware import CompatibilityMiddleware, classify_database_error

SECRET = "guardian-err@example.invalid"


def _orig(sqlstate):
    class Orig(Exception):
        pass

    error = Orig(f"DETAIL: Key (parent_email)=({SECRET})")
    error.sqlstate = sqlstate
    return error


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (OperationalError("SELECT 1", {}, _orig(None)), (503, "DATABASE_UNAVAILABLE")),
        (OperationalError("SELECT 1", {}, _orig("08006")), (503, "DATABASE_UNAVAILABLE")),
        (OperationalError("SELECT 1", {}, _orig("28P01")), (503, "DATABASE_UNAVAILABLE")),
        (OperationalError("SELECT 1", {}, _orig("53300")), (503, "DATABASE_UNAVAILABLE")),
        (OperationalError("SELECT 1", {}, _orig("57P01")), (503, "DATABASE_UNAVAILABLE")),
        (PoolTimeout("QueuePool limit reached"), (503, "DATABASE_UNAVAILABLE")),
        (OperationalError("SELECT 1", {}, _orig("40P01")), (409, "TRANSACTION_CONFLICT")),
        (OperationalError("SELECT 1", {}, _orig("55P03")), (409, "TRANSACTION_CONFLICT")),
        (OperationalError("SELECT 1", {}, _orig("40001")), (409, "TRANSACTION_CONFLICT")),
        # Programming / data errors stay a 500: they are bugs, not something to retry.
        (ProgrammingError("SELECT x", {}, _orig("42P01")), None),
        (IntegrityError("INSERT", {}, _orig("23505")), None),
        (OperationalError("SELECT 1", {}, _orig("22012")), None),
        (ValueError("plain bug"), None),
    ],
)
def test_database_errors_are_classified(exc, expected) -> None:
    result = classify_database_error(exc)
    assert (result[:2] if result else None) == expected


@pytest.mark.parametrize(
    ("sqlstate", "status", "code"),
    [
        (None, 503, "DATABASE_UNAVAILABLE"),
        ("40P01", 409, "TRANSACTION_CONFLICT"),
        ("42P01", 500, "INTERNAL_ERROR"),
    ],
)
def test_api_answers_and_never_leaks_the_error_text(
    monkeypatch, caplog, sqlstate, status, code
) -> None:
    error_type = ProgrammingError if sqlstate == "42P01" else OperationalError

    def broken_db():
        class Session:
            def _fail(self, *_a, **_k):
                raise error_type(
                    "SELECT secret FROM staff_user", {"email": SECRET}, _orig(sqlstate)
                )

            scalar = scalars = execute = get = _fail

            def rollback(self):
                pass

        yield Session()

    monkeypatch.setenv("ACADEMY_ENABLE_DB_APIS", "1")
    monkeypatch.setenv("ACADEMY_DB_MODE", "test")
    monkeypatch.setenv("ACADEMY_API_HOST", "127.0.0.1")
    app.dependency_overrides[get_db] = broken_db
    caplog.set_level(logging.INFO)
    try:
        response = TestClient(app).post(  # raise_server_exceptions=True: nothing escapes
            "/api/auth/login", json={"email": "nobody@example.invalid", "password": "x" * 12}
        )
    finally:
        app.dependency_overrides.clear()
    assert (response.status_code, response.json()["code"]) == (status, code)
    logged = "\n".join(record.getMessage() for record in caplog.records)
    for leaked in (SECRET, "SELECT secret"):
        assert leaked not in response.text and leaked not in logged
    assert f"status={status}" in logged  # the request log line carries the real status


@pytest.mark.postgres
def test_engine_connections_use_the_connect_timeout() -> None:
    """The timeout libpq actually used for a real connection to the isolated test DB."""
    if os.getenv("ACADEMY_RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("ACADEMY_RUN_POSTGRES_INTEGRATION=1 is required")
    engine = create_db_engine()
    try:
        with engine.connect() as connection:
            parameters = connection.connection.dbapi_connection.info.get_parameters()
        assert parameters["connect_timeout"] == str(DB_CONNECT_TIMEOUT_SECONDS)
        assert 1 <= DB_CONNECT_TIMEOUT_SECONDS <= 10
    finally:
        engine.dispose()


def test_upload_body_is_buffered_in_linear_time() -> None:
    """10MB in 64KB chunks (as uvicorn delivers it). Before: ~0.5s of event-loop CPU because
    bytes += copied the whole body per chunk; after: a small fraction of that."""
    chunk, size = 64 * 1024, 10 * 1024 * 1024
    delivered = {}

    async def inner(scope, receive, send):
        message = await receive()
        delivered["bytes"] = len(message["body"])
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})

    async def run() -> float:
        parts = iter([b"x" * chunk] * (size // chunk))

        async def receive():
            try:
                return {"type": "http.request", "body": next(parts), "more_body": True}
            except StopIteration:
                return {"type": "http.request", "body": b"", "more_body": False}

        async def send(_message):
            pass

        scope = {
            "type": "http",
            "method": "POST",
            "path": "/api/lesson-uploads/preview",
            "headers": [(b"content-type", b"multipart/form-data")],
        }
        started = time.perf_counter()
        await CompatibilityMiddleware(inner, get_settings())(scope, receive, send)
        return time.perf_counter() - started

    elapsed = min(asyncio.run(run()) for _ in range(3))
    assert delivered["bytes"] == size  # the body reaches the app unchanged
    assert elapsed < 0.25, elapsed


@pytest.mark.postgres
def test_progress_eligibility_single_query_matches_the_per_day_rule(monkeypatch) -> None:
    """Phase 11-4-A P2: eligibility_by_day now runs one query for all days. Same answer as the
    previous per-day loop, for every kind of enrolment period, and the same progress response.
    Non-destructive: own fictional rows (P114E prefix), no TRUNCATE."""
    import uuid
    from datetime import date, timedelta

    from sqlalchemy import select, text

    from app.db.models.tables import Enrollment
    from app.modules.academics.repository import AcademicsRepository, eligible_on
    from app.modules.auth.service import hash_password, login_rate_limiter

    if os.getenv("ACADEMY_RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("ACADEMY_RUN_POSTGRES_INTEGRATION=1 is required")
    for key, value in {"ACADEMY_ENABLE_DB_APIS": "1", "ACADEMY_COOKIE_SECURE": "0"}.items():
        monkeypatch.setenv(key, value)
    login_rate_limiter.clear()
    engine = create_db_engine()
    sfx = uuid.uuid4().hex[:8]
    start = date(2026, 9, 1)
    days = {start + timedelta(days=4 * i) for i in range(20)}  # 2026-09-01 .. 2026-11-16

    def sql(statement, **params):
        with engine.begin() as connection:
            return connection.execute(text(statement), params)

    teacher = sql(
        "INSERT INTO staff_user(email,display_name,password_hash,role,status) "
        "VALUES(:e,'P114E','"
        + hash_password("correct horse battery staple")
        + "','TEACHER','ACTIVE') RETURNING id",
        e=f"p114e-{sfx}@example.invalid",
    ).scalar_one()
    room = sql(
        "INSERT INTO classroom(name,class_type) VALUES(:n,'REGULAR') RETURNING id", n=f"중3 E{sfx}"
    ).scalar_one()
    sql(
        "INSERT INTO classroom_staff_assignment(classroom_id,staff_user_id,assignment_role,valid_from) "
        "VALUES(:c,:s,'TEACHER','2026-01-01')",
        c=room,
        s=teacher,
    )
    cases = [  # (status, enrolled_at, ended_at, pause_from, resumed_on)
        ("ACTIVE", "2026-01-01", None, None, None),
        ("ACTIVE", "2026-10-10", None, None, None),  # joined in the middle
        ("ACTIVE", "2026-01-01", "2026-10-01", None, None),  # left in the middle
        ("WITHDRAWN", "2026-01-01", None, None, None),  # period unknown: never eligible
        ("ACTIVE", "2026-01-01", None, "2026-09-20", "2026-10-15"),  # closed pause
        ("ACTIVE", "2026-01-01", None, "2026-11-01", None),  # open pause (status set below)
    ]
    for i, (status, enrolled, ended, paused, resumed) in enumerate(cases):
        sid = sql(
            "INSERT INTO student(name) VALUES(:n) RETURNING id", n=f"P114E{sfx}-{i}"
        ).scalar_one()
        eid = sql(
            "INSERT INTO enrollment(student_id,classroom_id,status,enrolled_at,ended_at) "
            "VALUES(:s,:c,:st,:en,:ed) RETURNING id",
            s=sid,
            c=room,
            st=status,
            en=enrolled,
            ed=ended,
        ).scalar_one()
        if paused:
            sql(
                "INSERT INTO enrollment_pause(enrollment_id,paused_from,resumed_on,source) "
                "VALUES(:e,:p,:r,'MANUAL')",
                e=eid,
                p=paused,
                r=resumed,
            )
            if resumed is None:
                sql("UPDATE enrollment SET status='PAUSED' WHERE id=:e", e=eid)
    for day in sorted(days):
        sql(
            "INSERT INTO lesson(classroom_id,lesson_date,session_no,status) VALUES(:c,:d,1,'COMPLETED')",
            c=room,
            d=day,
        )
    session = create_session_factory(engine)()
    try:
        repo = AcademicsRepository(session)
        new = repo.eligibility_by_day(room, days)
        old = {
            (enrollment_id, day)
            for day in days
            for enrollment_id in session.scalars(
                select(Enrollment.id).where(Enrollment.classroom_id == room, eligible_on(day))
            )
        }
    finally:
        session.close()
    assert new == old and len(new) > 0
    assert repo.eligibility_by_day(room, set()) == set()

    client = TestClient(app, raise_server_exceptions=False)
    assert (
        client.post(
            "/api/auth/login",
            json={
                "email": f"p114e-{sfx}@example.invalid",
                "password": "correct horse battery staple",
            },
        ).status_code
        == 200
    )
    path = f"/api/classrooms/{room}/progress?date_from=2026-09-01&date_to=2026-11-20"
    current = client.get(path)

    def per_day(self, classroom_id, wanted):  # the previous implementation, for comparison
        return {
            (enrollment_id, day)
            for day in wanted
            for enrollment_id in self.db.scalars(
                select(Enrollment.id).where(
                    Enrollment.classroom_id == classroom_id, eligible_on(day)
                )
            )
        }

    monkeypatch.setattr(AcademicsRepository, "eligibility_by_day", per_day)
    previous = client.get(path)
    assert current.status_code == previous.status_code == 200
    assert current.json() == previous.json()
    engine.dispose()


@pytest.mark.postgres
def test_unreachable_database_answers_503(monkeypatch) -> None:
    """A real failed connection (same allow-listed test DB, wrong secret): 503, no data used."""
    if os.getenv("ACADEMY_RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("ACADEMY_RUN_POSTGRES_INTEGRATION=1 is required")
    monkeypatch.setenv("ACADEMY_ENABLE_DB_APIS", "1")
    monkeypatch.setenv("ACADEMY_COOKIE_SECURE", "0")
    url = os.environ["ACADEMY_DATABASE_URL"].replace("academy_test:", "academy_test:wrong-", 1)
    bad = create_db_engine(url)
    factory = create_session_factory(bad)

    def unreachable():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = unreachable
    try:
        response = TestClient(app, raise_server_exceptions=False).post(
            "/api/auth/login", json={"email": "nobody@example.invalid", "password": "x" * 12}
        )
    finally:
        app.dependency_overrides.clear()
        bad.dispose()
    assert (response.status_code, response.json()["code"]) == (503, "DATABASE_UNAVAILABLE")
