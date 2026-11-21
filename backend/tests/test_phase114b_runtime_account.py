# ruff: noqa: E501  -- SQL and long assertions kept on one line
"""Phase 11-4-B: deployed runtime mode (SEC-04), server-side idle session expiry (SEC-05),
password change and administrator-issued one-time reset codes (SEC-10).

Unit tests need no database. PostgreSQL tests are non-destructive: own fictional rows under a
random "P114B" prefix, no TRUNCATE. Time is moved by replacing ``auth.service.utc_now``."""

import json
import logging
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config import get_settings, production_problems
from app.db.safety import UnsafeDatabaseError, require_database_url
from app.modules.auth import service as auth_service
from app.modules.auth.service import PasswordResetCodes, password_problem

BACKEND = Path(__file__).resolve().parents[1]
PROD_URL = "postgresql+psycopg://app_user:not-a-real-secret@db.example.invalid:5432/academy_prod?sslmode=require"
PROD_ENV = {
    "ACADEMY_DB_MODE": "production",
    "ACADEMY_ENABLE_DB_APIS": "1",
    "ACADEMY_DATABASE_URL": PROD_URL,
    "ACADEMY_COOKIE_SECURE": "1",
    "ACADEMY_CORS_ORIGINS": "https://academy-demo.example.invalid",
    "ACADEMY_API_HOST": "0.0.0.0",
}


# =============================================================================== SEC-04 (unit)
def _prod(monkeypatch, **changes) -> None:
    for name in ("ACADEMY_DB_TEST_MODE", "ACADEMY_RUN_POSTGRES_INTEGRATION", "ACADEMY_TRUSTED_PROXIES"):
        monkeypatch.delenv(name, raising=False)
    for key, value in {**PROD_ENV, **changes}.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)


def test_a_safe_production_configuration_has_no_problems(monkeypatch) -> None:
    _prod(monkeypatch)
    assert production_problems(get_settings()) == []
    assert require_database_url(PROD_URL).host == "db.example.invalid"


@pytest.mark.parametrize(
    ("changes", "fragment"),
    [
        ({"ACADEMY_ENABLE_DB_APIS": "0"}, "ACADEMY_ENABLE_DB_APIS"),
        ({"ACADEMY_COOKIE_SECURE": "0"}, "ACADEMY_COOKIE_SECURE"),
        ({"ACADEMY_CORS_ORIGINS": "http://academy-demo.example.invalid"}, "https://"),
        ({"ACADEMY_CORS_ORIGINS": "https://*.example.invalid"}, "https://"),
        ({"ACADEMY_CORS_ORIGINS": "https://localhost:5173"}, "local development"),
        ({"ACADEMY_TRUSTED_PROXIES": "0.0.0.0/0"}, "/0"),
        ({"ACADEMY_DB_TEST_MODE": "1"}, "test switches"),
        ({"ACADEMY_DATABASE_URL": None}, "ACADEMY_DATABASE_URL"),
        ({"ACADEMY_DATABASE_URL": PROD_URL.replace("?sslmode=require", "")}, "ACADEMY_DATABASE_URL"),
        ({"ACADEMY_DATABASE_URL": PROD_URL.replace("sslmode=require", "sslmode=prefer")}, "ACADEMY_DATABASE_URL"),
        ({"ACADEMY_DATABASE_URL": "postgresql+psycopg://academy_test:x@127.0.0.1:55432/academy_learningops_test?sslmode=require"}, "ACADEMY_DATABASE_URL"),
        ({"ACADEMY_DATABASE_URL": "sqlite:///x.db"}, "ACADEMY_DATABASE_URL"),
    ],
)
def test_unsafe_production_settings_are_reported_by_name_only(monkeypatch, changes, fragment) -> None:
    _prod(monkeypatch, **changes)
    problems = production_problems(get_settings())
    assert any(fragment in p for p in problems), problems
    assert "not-a-real-secret" not in " ".join(problems)  # never the values


def test_local_modes_keep_their_fixed_targets(monkeypatch) -> None:
    monkeypatch.setenv("ACADEMY_DB_MODE", "development")
    with pytest.raises(UnsafeDatabaseError):
        require_database_url(PROD_URL)  # a cloud URL is not a development database
    monkeypatch.setenv("ACADEMY_DB_MODE", "staging")  # unknown mode: refused
    with pytest.raises(UnsafeDatabaseError):
        require_database_url(PROD_URL)


def test_api_gate_opens_in_production_and_stays_closed_otherwise(monkeypatch) -> None:
    from app.errors import CompatibilityError
    from app.security import require_local_db_api

    _prod(monkeypatch)
    require_local_db_api()  # production, platform bind address: open
    monkeypatch.setenv("ACADEMY_ENABLE_DB_APIS", "0")
    with pytest.raises(CompatibilityError):
        require_local_db_api()  # still needs the explicit switch
    monkeypatch.setenv("ACADEMY_ENABLE_DB_APIS", "1")
    monkeypatch.setenv("ACADEMY_DB_MODE", "development")
    with pytest.raises(CompatibilityError):
        require_local_db_api()  # development keeps the loopback rule (0.0.0.0 here)


def _start(env: dict) -> subprocess.CompletedProcess:
    """Import the app in a fresh interpreter, as uvicorn would, and call two endpoints."""
    script = (
        "from fastapi.testclient import TestClient\n"
        "from app.main import app\n"
        "c = TestClient(app, base_url='https://testserver')\n"
        "print('HEALTH', c.get('/api/health').status_code)\n"
        "print('ME', c.get('/api/auth/me').status_code, c.get('/api/auth/me').json()['code'])\n"
        "print('DOCS', c.get('/openapi.json').status_code)\n"
    )
    clean = {k: v for k, v in os.environ.items() if not k.startswith("ACADEMY_")}
    return subprocess.run([sys.executable, "-c", script], cwd=BACKEND, env={**clean, **env}, capture_output=True, text=True, timeout=120)


def test_production_process_starts_and_serves_health_without_touching_a_database() -> None:
    result = _start(PROD_ENV)
    assert result.returncode == 0, result.stderr[-2000:]
    assert "HEALTH 200" in result.stdout
    assert "ME 401 AUTHENTICATION_REQUIRED" in result.stdout  # DB API gate open (not 404)
    assert "DOCS 404" in result.stdout


def test_production_process_refuses_unsafe_settings_without_printing_secrets() -> None:
    result = _start({**PROD_ENV, "ACADEMY_COOKIE_SECURE": "0", "ACADEMY_CORS_ORIGINS": "http://localhost:5173"})
    assert result.returncode != 0
    assert "Unsafe production configuration" in result.stderr
    assert "ACADEMY_COOKIE_SECURE" in result.stderr and "ACADEMY_CORS_ORIGINS" in result.stderr
    assert "not-a-real-secret" not in result.stderr + result.stdout


def test_development_start_is_unchanged() -> None:
    result = _start({"ACADEMY_DB_MODE": "development", "ACADEMY_ENABLE_DB_APIS": "1", "ACADEMY_API_HOST": "127.0.0.1"})
    assert result.returncode == 0, result.stderr[-2000:]
    assert "HEALTH 200" in result.stdout and "ME 401" in result.stdout


# =========================================================================== SEC-05/10 (unit)
@pytest.mark.parametrize("value", ["0", "-5", "481"])
def test_idle_timeout_must_be_bounded(monkeypatch, value) -> None:
    monkeypatch.setenv("ACADEMY_SESSION_IDLE_MINUTES", value)
    with pytest.raises(ValueError):
        get_settings()


def test_idle_timeout_defaults_to_60_minutes(monkeypatch) -> None:
    monkeypatch.delenv("ACADEMY_SESSION_IDLE_MINUTES", raising=False)
    assert get_settings().session_idle_minutes == 60


def test_reset_codes_are_one_time_expiring_and_bounded() -> None:
    store = PasswordResetCodes()
    now = datetime(2026, 11, 21, 12, 0)
    code, expires = store.issue(7, now, 15)
    assert len(code) == 11 and code[5] == "-" and expires == now + timedelta(minutes=15)
    assert not store.consume(8, code, now)  # bound to the account
    assert store.consume(7, code.lower().replace("-", " "), now)  # forgiving input format
    assert not store.consume(7, code, now)  # one use only
    code, _ = store.issue(7, now, 15)
    assert not store.consume(7, code, now + timedelta(minutes=15))  # expired
    old, _ = store.issue(7, now, 15)
    new, _ = store.issue(7, now, 15)
    assert not store.consume(7, old, now) and store.consume(7, new, now)  # new code replaces old
    code, _ = store.issue(7, now, 15)
    for _ in range(PasswordResetCodes.MAX_WRONG):
        assert not store.consume(7, "AAAAA-AAAAA", now)
    assert not store.consume(7, code, now)  # too many wrong tries: void


def test_password_rule() -> None:
    assert password_problem("short", email="a@example.invalid")
    assert password_problem("a@example.invalid", email="A@example.invalid")
    assert password_problem("same password 1", email="a@example.invalid", current="same password 1")
    assert password_problem("            ", email="a@example.invalid")
    assert password_problem("long enough password", email="a@example.invalid") is None


# ================================================================ PostgreSQL (non-destructive)
PASSWORD = "correct horse battery staple"
NEW_PASSWORD = "a brand new passphrase"


@pytest.fixture(scope="module")
def engine():
    if os.getenv("ACADEMY_RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("ACADEMY_RUN_POSTGRES_INTEGRATION=1 is required")
    from app.db.session import create_db_engine, get_engine, get_session_factory

    get_engine.cache_clear()
    get_session_factory.cache_clear()
    db = create_db_engine()
    with db.connect() as c:
        assert c.execute(text("SELECT current_database(), current_user")).one() == ("academy_learningops_test", "academy_test")
    yield db
    db.dispose()


class Clock:
    def __init__(self) -> None:
        self.offset = timedelta(0)

    def __call__(self) -> datetime:
        return datetime.now(auth_service.UTC) + self.offset


@pytest.fixture()
def world(engine, monkeypatch):
    import uuid

    for key, value in {"ACADEMY_ENABLE_DB_APIS": "1", "ACADEMY_COOKIE_SECURE": "0", "ACADEMY_API_HOST": "127.0.0.1"}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("ACADEMY_SESSION_IDLE_MINUTES", raising=False)
    auth_service.login_rate_limiter.clear()
    auth_service.password_reset_codes.clear()
    clock = Clock()
    monkeypatch.setattr(auth_service, "utc_now", clock)
    sfx = uuid.uuid4().hex[:8]
    ids = {"sfx": sfx, "clock": clock}
    pw = auth_service.hash_password(PASSWORD)
    with engine.begin() as c:
        for role in ("admin", "admin2", "teacher", "assistant"):
            ids[role] = c.execute(
                text("INSERT INTO staff_user(email,display_name,password_hash,role,status) VALUES(:e,:d,:p,:r,'ACTIVE') RETURNING id"),
                {"e": f"p114b-{sfx}-{role}@example.invalid", "d": f"P114B {role}", "p": pw, "r": "ADMIN" if role.startswith("admin") else role.upper()},
            ).scalar_one()
    return ids


def email(ids, role):
    return f"p114b-{ids['sfx']}-{role}@example.invalid"


def login(ids, role, password=PASSWORD):
    from app.main import app

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post("/api/auth/login", json={"email": email(ids, role), "password": password})
    return client, response


def signed_in(ids, role):
    client, response = login(ids, role)
    assert response.status_code == 200, response.text
    return client


def call(client, method, path, payload=None, csrf=True, headers=None):
    merged = {**({"X-CSRF-Token": client.cookies.get("academy_csrf")} if csrf else {}), **(headers or {})}
    return client.request(method, path, json=payload, headers=merged)


def last_seen(engine, ids, role):
    with engine.connect() as c:
        return c.execute(text("SELECT last_seen_at FROM auth_session WHERE staff_user_id=:u AND revoked_at IS NULL ORDER BY created_at DESC LIMIT 1"), {"u": ids[role]}).scalar()


# --------------------------------------------------------------------------------- SEC-05
@pytest.mark.postgres
def test_active_use_keeps_the_session_and_idle_time_ends_it(engine, world) -> None:
    clock = world["clock"]
    client = signed_in(world, "teacher")
    for step in range(4):  # 4 x 50 min of real use: well past one idle period
        clock.offset = timedelta(minutes=50 * (step + 1))
        assert client.get("/api/auth/me").status_code == 200
    clock.offset += timedelta(minutes=59, seconds=59)
    assert client.get("/api/auth/me").status_code == 200  # just inside the limit
    clock.offset += timedelta(minutes=60, seconds=1)
    expired = client.get("/api/auth/me")
    assert (expired.status_code, expired.json()["code"]) == (401, "SESSION_IDLE_EXPIRED")
    again = client.get("/api/auth/me")  # revoked on the server: no way back
    assert (again.status_code, again.json()["code"]) == (401, "SESSION_EXPIRED")
    fresh = signed_in(world, "teacher")  # signing in again works
    assert fresh.get("/api/auth/me").status_code == 200


@pytest.mark.postgres
def test_exact_idle_boundary_and_absolute_expiry(engine, world) -> None:
    clock = world["clock"]
    client = signed_in(world, "teacher")
    clock.offset = timedelta(minutes=60)  # exactly the idle limit: expired (>=)
    assert client.get("/api/auth/me").json()["code"] == "SESSION_IDLE_EXPIRED"
    clock.offset = timedelta(0)
    client = signed_in(world, "teacher")  # new session starts at offset 0
    for minutes in range(55, 8 * 60, 55):  # continuous use for 8 hours
        clock.offset = timedelta(minutes=minutes)
        assert client.get("/api/auth/me").status_code == 200, minutes
    clock.offset = timedelta(minutes=8 * 60 + 1)  # the absolute 8-hour limit still applies
    assert client.get("/api/auth/me").json()["code"] == "SESSION_EXPIRED"


@pytest.mark.postgres
def test_activity_is_written_at_most_once_a_minute_and_background_requests_do_not_count(engine, world) -> None:
    clock = world["clock"]
    client = signed_in(world, "teacher")
    first = last_seen(engine, world, "teacher")
    clock.offset = timedelta(seconds=30)
    client.get("/api/auth/me")
    assert last_seen(engine, world, "teacher") == first  # within a minute: no write
    clock.offset = timedelta(seconds=90)
    client.get("/api/auth/me")
    assert last_seen(engine, world, "teacher") > first  # counted
    moved = last_seen(engine, world, "teacher")
    for minutes in (20, 40, 59):  # automatic refreshes for an hour
        clock.offset = timedelta(seconds=90) + timedelta(minutes=minutes)
        assert client.get("/api/auth/me", headers={"X-Academy-Background": "1"}).status_code == 200
    assert last_seen(engine, world, "teacher") == moved  # never extended the session
    clock.offset = timedelta(seconds=90) + timedelta(minutes=60)
    assert client.get("/api/auth/me", headers={"X-Academy-Background": "1"}).json()["code"] == "SESSION_IDLE_EXPIRED"


@pytest.mark.postgres
def test_concurrent_requests_record_activity_consistently(engine, world) -> None:
    clock = world["clock"]
    client = signed_in(world, "teacher")
    cookies = dict(client.cookies)
    from app.main import app

    clock.offset = timedelta(minutes=30)

    def hit(_):
        return TestClient(app, raise_server_exceptions=False, cookies=cookies).get("/api/auth/me").status_code

    with ThreadPoolExecutor(max_workers=10) as pool:
        assert list(pool.map(hit, range(20))) == [200] * 20
    seen = last_seen(engine, world, "teacher")
    clock.offset = timedelta(minutes=30, seconds=30)
    with ThreadPoolExecutor(max_workers=10) as pool:
        list(pool.map(hit, range(10)))
    assert last_seen(engine, world, "teacher") == seen  # never moved backwards or re-written
    clock.offset = timedelta(minutes=89)  # 59 minutes after the recorded activity: still valid
    assert hit(0) == 200


@pytest.mark.postgres
def test_logout_and_deactivation_still_end_sessions(engine, world) -> None:
    client = signed_in(world, "teacher")
    assert call(client, "POST", "/api/auth/logout").status_code == 200
    assert client.get("/api/auth/me").status_code == 401
    other = signed_in(world, "assistant")
    admin = signed_in(world, "admin")
    assert call(admin, "PATCH", f"/api/staff/{world['assistant']}/status", {"status": "INACTIVE"}).status_code == 200
    assert other.get("/api/auth/me").status_code == 401


# --------------------------------------------------------------------------------- SEC-10-A
@pytest.mark.postgres
def test_password_change(engine, world, caplog) -> None:
    caplog.set_level(logging.INFO)
    phone = signed_in(world, "teacher")  # a second session of the same member
    laptop = signed_in(world, "teacher")
    assert call(laptop, "POST", "/api/auth/password", {"current_password": PASSWORD, "new_password": NEW_PASSWORD}, csrf=False).status_code == 403
    from app.main import app

    assert TestClient(app).post("/api/auth/password", json={"current_password": PASSWORD, "new_password": NEW_PASSWORD}).status_code == 401
    weak = call(laptop, "POST", "/api/auth/password", {"current_password": PASSWORD, "new_password": "short"})
    assert (weak.status_code, weak.json()["code"]) == (400, "WEAK_PASSWORD")
    same = call(laptop, "POST", "/api/auth/password", {"current_password": PASSWORD, "new_password": PASSWORD})
    assert same.json()["code"] == "WEAK_PASSWORD"
    wrong = call(laptop, "POST", "/api/auth/password", {"current_password": "not my password", "new_password": NEW_PASSWORD})
    assert (wrong.status_code, wrong.json()["code"]) == (400, "INVALID_CURRENT_PASSWORD")
    assert laptop.get("/api/auth/me").status_code == 200  # a wrong current password is not a log-out
    done = call(laptop, "POST", "/api/auth/password", {"current_password": PASSWORD, "new_password": NEW_PASSWORD})
    assert done.status_code == 200 and done.json() == {"changed": True, "other_sessions_revoked": 1}
    assert laptop.get("/api/auth/me").status_code == 200  # this session stays
    assert phone.get("/api/auth/me").status_code == 401  # the other one is signed out
    assert login(world, "teacher")[1].status_code == 401  # old password refused
    assert login(world, "teacher", NEW_PASSWORD)[1].status_code == 200
    with engine.connect() as c:
        details = c.execute(text("SELECT details::text FROM audit_log WHERE event_type='STAFF_PASSWORD_CHANGED' AND target_id=:t"), {"t": str(world["teacher"])}).scalar_one()
    logged = "\n".join(r.getMessage() for r in caplog.records)
    for secret in (PASSWORD, NEW_PASSWORD):
        assert secret not in details and secret not in logged


@pytest.mark.postgres
def test_wrong_current_passwords_are_limited(engine, world) -> None:
    client = signed_in(world, "teacher")
    codes = [call(client, "POST", "/api/auth/password", {"current_password": "guess number x", "new_password": NEW_PASSWORD}).status_code for _ in range(6)]
    assert codes == [400] * 5 + [429]


# --------------------------------------------------------------------------------- SEC-10-B
def issue(admin, staff_id):
    return call(admin, "POST", f"/api/staff/{staff_id}/password-reset-code")


def reset(email_value, code, new=NEW_PASSWORD):
    from app.main import app

    return TestClient(app, raise_server_exceptions=False).post("/api/auth/password-reset", json={"email": email_value, "code": code, "new_password": new})


@pytest.mark.postgres
def test_admin_reset_code_flow(engine, world, caplog) -> None:
    caplog.set_level(logging.INFO)
    admin, teacher = signed_in(world, "admin"), signed_in(world, "teacher")
    victim_session = signed_in(world, "assistant")
    assert issue(teacher, world["assistant"]).status_code == 403  # administrators only
    assert call(admin, "POST", f"/api/staff/{world['assistant']}/password-reset-code", csrf=False).status_code == 403
    assert issue(admin, world["admin"]).json()["code"] == "SELF_RESET_FORBIDDEN"
    assert issue(admin, 999_999_999).status_code == 404
    issued = issue(admin, world["assistant"])
    assert issued.status_code == 200, issued.text
    code = issued.json()["code"]
    weak = reset(email(world, "assistant"), code, "short")
    assert weak.json()["code"] == "WEAK_PASSWORD"  # checked before the code is used
    done = reset(email(world, "assistant"), code)
    assert done.status_code == 200 and done.json() == {"reset": True}
    assert victim_session.get("/api/auth/me").status_code == 401  # every session ended
    assert login(world, "assistant")[1].status_code == 401
    assert login(world, "assistant", NEW_PASSWORD)[1].status_code == 200
    assert reset(email(world, "assistant"), code, "yet another passphrase").json()["code"] == "RESET_FAILED"  # one use
    with engine.connect() as c:
        events = dict(c.execute(text("SELECT event_type, details::text FROM audit_log WHERE target_id=:t AND event_type LIKE 'STAFF_PASSWORD_RESET%'"), {"t": str(world["assistant"])}).all())
    assert set(events) == {"STAFF_PASSWORD_RESET_ISSUED", "STAFF_PASSWORD_RESET_COMPLETED"}
    logged = "\n".join(r.getMessage() for r in caplog.records)
    for secret in (code, code.replace("-", ""), NEW_PASSWORD):
        assert secret not in " ".join(events.values()) and secret not in logged


@pytest.mark.postgres
def test_reset_failures_look_identical_and_codes_expire(engine, world) -> None:
    clock = world["clock"]
    admin = signed_in(world, "admin")
    code = issue(admin, world["teacher"]).json()["code"]
    unknown = reset(f"nobody-{world['sfx']}@example.invalid", code)
    wrong = reset(email(world, "teacher"), "ABCDE-FGHJK")
    assert unknown.status_code == wrong.status_code == 400
    assert unknown.json() == wrong.json()  # nothing tells whether the account exists
    clock.offset = timedelta(minutes=16)
    assert reset(email(world, "teacher"), code).json()["code"] == "RESET_FAILED"  # expired
    assert login(world, "teacher")[1].status_code == 200  # password unchanged


@pytest.mark.postgres
def test_reset_code_refused_for_inactive_accounts_and_form_posts(engine, world) -> None:
    admin = signed_in(world, "admin")
    assert call(admin, "PATCH", f"/api/staff/{world['assistant']}/status", {"status": "INACTIVE"}).status_code == 200
    assert issue(admin, world["assistant"]).json()["code"] == "STAFF_NOT_ACTIVE"
    from app.main import app

    form = TestClient(app, raise_server_exceptions=False).post(
        "/api/auth/password-reset", data={"email": email(world, "teacher"), "code": "x", "new_password": NEW_PASSWORD}
    )
    assert form.status_code == 415  # JSON only, like log-in
    other_admin = issue(admin, world["admin2"])  # another administrator: allowed, audited
    assert other_admin.status_code == 200 and json.dumps(other_admin.json())
