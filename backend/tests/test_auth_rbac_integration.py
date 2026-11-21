import os
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select, text

from app.db.models.tables import (
    AuthSession,
    Classroom,
    ClassroomStaffAssignment,
    StaffUser,
)
from app.db.session import create_db_engine, create_session_factory, get_engine, get_session_factory
from app.main import app
from app.modules.auth.service import hash_password, login_rate_limiter

pytestmark = pytest.mark.postgres


@pytest.fixture(scope="module")
def engine() -> Engine:
    if os.getenv("ACADEMY_RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("ACADEMY_RUN_POSTGRES_INTEGRATION=1이 필요합니다.")
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    db_engine = create_db_engine()
    yield db_engine
    db_engine.dispose()
    get_engine.cache_clear()
    get_session_factory.cache_clear()


@pytest.fixture(autouse=True)
def clean_auth_data(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ACADEMY_ENABLE_DB_APIS", "1")
    monkeypatch.setenv("ACADEMY_API_HOST", "127.0.0.1")
    monkeypatch.setenv("ACADEMY_DB_MODE", "test")
    monkeypatch.setenv("ACADEMY_DB_TEST_MODE", "1")
    monkeypatch.setenv("ACADEMY_COOKIE_SECURE", "0")
    monkeypatch.setenv("ACADEMY_LOGIN_ATTEMPT_LIMIT", "5")
    login_rate_limiter.clear()
    with engine.begin() as connection:
        assert connection.execute(text("SELECT current_database(),current_user")).one() == (
            "academy_learningops_test",
            "academy_test",
        )
        connection.execute(
            text(
                "TRUNCATE TABLE audit_log,auth_session,classroom_staff_assignment,staff_user,"
                "lesson_result,lesson,enrollment,student,"
                "classroom RESTART IDENTITY CASCADE"
            )
        )


def _seed(engine: Engine) -> None:
    factory = create_session_factory(engine)
    with factory.begin() as session:
        session.add_all(
            [
                StaffUser(
                    email="admin@example.invalid",
                    password_hash=hash_password("correct horse battery staple"),
                    role="ADMIN",
                    status="ACTIVE",
                ),
                StaffUser(
                    email="teacher@example.invalid",
                    password_hash=hash_password("correct horse battery staple"),
                    role="TEACHER",
                    status="ACTIVE",
                ),
                StaffUser(
                    email="inactive@example.invalid",
                    password_hash=hash_password("correct horse battery staple"),
                    role="ASSISTANT",
                    status="INACTIVE",
                ),
                StaffUser(
                    email="assistant@example.invalid",
                    password_hash=hash_password("correct horse battery staple"),
                    role="ASSISTANT",
                    status="ACTIVE",
                ),
            ]
        )
    with factory.begin() as session:
        teacher = session.scalar(select(StaffUser).where(StaffUser.role == "TEACHER"))
        assistant = session.scalar(
            select(StaffUser).where(StaffUser.email == "assistant@example.invalid")
        )
        assigned = Classroom(name="A반", class_type="REGULAR")
        other = Classroom(name="B반", class_type="REGULAR")
        session.add_all([assigned, other])
        session.flush()
        session.add_all(
            [
                ClassroomStaffAssignment(
                classroom_id=assigned.id,
                staff_user_id=teacher.id,  # type: ignore[union-attr]
                assignment_role="TEACHER",
                valid_from=date.today(),
                ),
                ClassroomStaffAssignment(
                    classroom_id=assigned.id,
                    staff_user_id=assistant.id,  # type: ignore[union-attr]
                    assignment_role="ASSISTANT",
                    valid_from=date.today(),
                ),
            ]
        )


def _login(client: TestClient, email: str, password: str = "correct horse battery staple"):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def test_login_me_logout_and_session_reuse_is_blocked(engine: Engine) -> None:
    _seed(engine)
    client = TestClient(app, raise_server_exceptions=False)
    client.cookies.set(
        "academy_session", "attacker-fixed-session", domain="testserver.local", path="/"
    )
    login = _login(client, "admin@example.invalid")
    assert login.status_code == 200
    assert login.json()["user"]["role"] == "ADMIN"
    assert "password" not in login.text.lower()
    session_cookie = client.cookies.get("academy_session")
    csrf = client.cookies.get("academy_csrf")
    assert session_cookie and csrf
    assert session_cookie != "attacker-fixed-session"
    assert "HttpOnly" in login.headers.get("set-cookie", "")
    assert client.get("/api/auth/me").status_code == 200
    logout = client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})
    assert logout.status_code == 200
    replay = TestClient(app, raise_server_exceptions=False)
    replay.cookies.set("academy_session", session_cookie)
    assert replay.get("/api/auth/me").status_code == 401


def test_invalid_inactive_rate_limit_and_no_enumeration(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The address-wide limit defaults to 20 since Phase 11-2-B-2; set to 5 here so this test
    # keeps checking that counter (defaults: test_phase112b2_login_and_upload_hardening.py).
    monkeypatch.setenv("ACADEMY_LOGIN_IP_ATTEMPT_LIMIT", "5")
    _seed(engine)
    client = TestClient(app, raise_server_exceptions=False)
    missing = _login(client, "missing@example.invalid", "wrong")
    wrong = _login(client, "admin@example.invalid", "wrong")
    inactive = _login(client, "inactive@example.invalid")
    assert {missing.status_code, wrong.status_code, inactive.status_code} == {401}
    assert missing.json() == wrong.json() == inactive.json()
    injection = _login(client, "admin@example.invalid' OR '1'='1", "wrong")
    assert injection.status_code in {400, 401}
    assert _login(client, "one@example.invalid", "wrong").status_code == 401
    assert _login(client, "two@example.invalid", "wrong").status_code == 401
    limited = _login(client, "three@example.invalid", "wrong")
    assert limited.status_code == 429


def test_expired_and_malformed_session_are_rejected(engine: Engine) -> None:
    _seed(engine)
    client = TestClient(app, raise_server_exceptions=False)
    assert _login(client, "admin@example.invalid").status_code == 200
    factory = create_session_factory(engine)
    with factory.begin() as session:
        auth_session = session.scalar(select(AuthSession))
        auth_session.created_at = datetime.now(UTC) - timedelta(hours=2)  # type: ignore[union-attr]
        auth_session.expires_at = datetime.now(UTC) - timedelta(hours=1)  # type: ignore[union-attr]
    assert client.get("/api/auth/me").status_code == 401
    client.cookies.set("academy_session", "malformed")
    assert client.get("/api/auth/me").status_code == 401


def test_secure_cookie_flag_is_enabled_when_configured(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(engine)
    monkeypatch.setenv("ACADEMY_COOKIE_SECURE", "1")
    client = TestClient(app, base_url="https://testserver", raise_server_exceptions=False)
    response = _login(client, "admin@example.invalid")
    assert response.status_code == 200
    set_cookie = response.headers.get("set-cookie", "")
    assert "HttpOnly" in set_cookie
    assert "Secure" in set_cookie
    assert "SameSite=lax" in set_cookie


def test_roles_csrf_and_classroom_scope_are_enforced(engine: Engine) -> None:
    _seed(engine)
    teacher = TestClient(app, raise_server_exceptions=False)
    assert _login(teacher, "teacher@example.invalid").status_code == 200
    # Administrator-only API (the legacy /api/imports endpoints were removed on 2026-11-20).
    assert teacher.get("/api/staff", headers={"X-Role": "ADMIN"}).status_code == 403
    teacher_csrf = teacher.cookies.get("academy_csrf")
    create = teacher.post("/api/staff", json={}, headers={"X-CSRF-Token": teacher_csrf})
    assert create.status_code == 403

    assigned = {
        "studentName": "가상학생",
        "className": "A반",
        "classType": "REGULAR",
        "lessonDate": "2026-11-10",
        "testRound": "1회차",
        "attendance": "PRESENT",
    }
    assert teacher.post("/api/messages/preview", json=assigned).status_code == 200
    assert teacher.post(
        "/api/messages/preview", json={**assigned, "className": "B반"}
    ).status_code == 403

    assistant = TestClient(app, raise_server_exceptions=False)
    assert _login(assistant, "assistant@example.invalid").status_code == 200
    assert assistant.get("/api/staff").status_code == 403
    assert assistant.post("/api/messages/preview", json=assigned).status_code == 200
    assert assistant.post(
        "/api/messages/preview", json={**assigned, "className": "B반"}
    ).status_code == 403

    admin = TestClient(app, raise_server_exceptions=False)
    assert _login(admin, "admin@example.invalid").status_code == 200
    assert admin.get("/api/staff").status_code == 200
    csrf = admin.cookies.get("academy_csrf")
    no_csrf = admin.post("/api/auth/logout")
    assert no_csrf.status_code == 403
    assert admin.post("/api/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 200
