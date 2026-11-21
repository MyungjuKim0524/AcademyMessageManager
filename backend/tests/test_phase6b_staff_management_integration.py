import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select, text

from app.db.models.tables import ClassroomStaffAssignment, StaffUser
from app.db.session import create_db_engine, create_session_factory, get_engine, get_session_factory
from app.main import app
from app.modules.auth.service import hash_password, login_rate_limiter

pytestmark = pytest.mark.postgres
PASSWORD = "correct horse battery staple"


@pytest.fixture(scope="module")
def engine() -> Engine:
    if os.getenv("ACADEMY_RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("ACADEMY_RUN_POSTGRES_INTEGRATION=1 is required")
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    db_engine = create_db_engine()
    yield db_engine
    db_engine.dispose()
    get_engine.cache_clear()
    get_session_factory.cache_clear()


@pytest.fixture(autouse=True)
def isolated_data(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ACADEMY_ENABLE_DB_APIS", "1")
    monkeypatch.setenv("ACADEMY_DB_MODE", "test")
    monkeypatch.setenv("ACADEMY_DB_TEST_MODE", "1")
    monkeypatch.setenv("ACADEMY_COOKIE_SECURE", "0")
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
    factory = create_session_factory(engine)
    with factory.begin() as session:
        session.add_all(
            [
                StaffUser(
                    email="admin@example.invalid",
                    password_hash=hash_password(PASSWORD),
                    role="ADMIN",
                    status="ACTIVE",
                ),
                StaffUser(
                    email="second-admin@example.invalid",
                    password_hash=hash_password(PASSWORD),
                    role="ADMIN",
                    status="ACTIVE",
                ),
                StaffUser(
                    email="teacher@example.invalid",
                    password_hash=hash_password(PASSWORD),
                    role="TEACHER",
                    status="ACTIVE",
                ),
            ]
        )


def _login(email: str) -> TestClient:
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200
    return client


def _change(client: TestClient, method: str, path: str, payload: dict | None = None):
    return client.request(
        method,
        path,
        json=payload,
        headers={"X-CSRF-Token": client.cookies.get("academy_csrf")},
    )


def test_admin_staff_lifecycle_security_and_session_revocation(engine: Engine) -> None:
    admin = _login("admin@example.invalid")
    teacher = _login("teacher@example.invalid")

    assert TestClient(app).get("/api/staff").status_code == 401
    assert teacher.get("/api/staff").status_code == 403
    assert (
        admin.post(
            "/api/staff",
            json={"email": "no-csrf@example.invalid", "password": PASSWORD, "role": "TEACHER"},
        ).status_code
        == 403
    )

    payload = {
        "email": "new-teacher@example.invalid",
        "display_name": "  김   선생  ",
        "password": PASSWORD,
        "role": "TEACHER",
    }
    created = _change(admin, "POST", "/api/staff", payload)
    assert created.status_code == 201
    staff_id = created.json()["id"]
    assert created.json()["display_name"] == "김 선생"
    for bad_name in (None, "", "   ", "x" * 101, "bad\u0000name"):
        assert (
            _change(
                admin,
                "POST",
                "/api/staff",
                {**payload, "email": "bad-name@example.invalid", "display_name": bad_name},
            ).status_code
            == 400
        )
    no_name = {key: value for key, value in payload.items() if key != "display_name"}
    assert (
        _change(
            admin, "POST", "/api/staff", {**no_name, "email": "no-name@example.invalid"}
        ).status_code
        == 400
    )

    renamed = _change(admin, "PATCH", f"/api/staff/{staff_id}", {"display_name": "이 선생"})
    assert renamed.status_code == 200
    assert renamed.json()["display_name"] == "이 선생"
    assert (
        _change(
            admin, "PATCH", f"/api/staff/{staff_id}", {"display_name": "x", "role": "ADMIN"}
        ).status_code
        == 400
    )
    assert admin.patch(f"/api/staff/{staff_id}", json={"display_name": "x"}).status_code == 403
    assert (
        _change(teacher, "PATCH", f"/api/staff/{staff_id}", {"display_name": "x"}).status_code
        == 403
    )
    assert _change(admin, "PATCH", "/api/staff/999999", {"display_name": "x"}).status_code == 404
    with create_session_factory(engine)() as session:
        stored = session.get(StaffUser, staff_id)
        assert (stored.display_name, stored.role) == ("이 선생", "TEACHER")
    assert "password" not in created.text.lower()
    assert "hash" not in created.text.lower()
    assert "session" not in created.text.lower()
    assert _change(admin, "POST", "/api/staff", payload).status_code == 409
    assert (
        _change(
            admin,
            "POST",
            "/api/staff",
            {**payload, "email": "admin-role@example.invalid", "role": "ADMIN"},
        ).status_code
        == 400
    )
    assert _change(admin, "POST", "/api/staff", {**payload, "status": "ACTIVE"}).status_code == 400
    assert (
        _change(
            admin,
            "POST",
            "/api/staff",
            {**payload, "email": "x' OR 1=1 --"},
        ).status_code
        == 400
    )

    page = admin.get("/api/staff")
    detail = admin.get(f"/api/staff/{staff_id}")
    assert page.status_code == detail.status_code == 200
    assert all("password" not in item for item in page.json()["items"])

    new_teacher = _login("new-teacher@example.invalid")
    assert new_teacher.get("/api/auth/me").json()["user"]["display_name"] == "이 선생"
    disabled = _change(admin, "PATCH", f"/api/staff/{staff_id}/status", {"status": "INACTIVE"})
    assert disabled.status_code == 200
    assert disabled.json()["status"] == "INACTIVE"
    assert new_teacher.get("/api/auth/me").status_code == 401
    assert (
        TestClient(app)
        .post("/api/auth/login", json={"email": payload["email"], "password": PASSWORD})
        .status_code
        == 401
    )

    reenabled = _change(admin, "PATCH", f"/api/staff/{staff_id}/status", {"status": "ACTIVE"})
    assert reenabled.status_code == 200
    assert _login("new-teacher@example.invalid").get("/api/auth/me").status_code == 200

    admin_id = admin.get("/api/auth/me").json()["user"]["id"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(
            pool.map(
                lambda _: (
                    _change(
                        TestClient(app, cookies=dict(admin.cookies)),
                        "PATCH",
                        f"/api/staff/{admin_id}/status",
                        {"status": "INACTIVE"},
                    ).status_code
                ),
                range(2),
            )
        )
    assert statuses == [409, 409]
    with create_session_factory(engine)() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(StaffUser)
                .where(StaffUser.role == "ADMIN", StaffUser.status == "ACTIVE")
            )
            == 2
        )


def test_assignment_concurrency_listing_revocation_and_bola(engine: Engine) -> None:
    admin = _login("admin@example.invalid")
    teacher = _login("teacher@example.invalid")
    factory = create_session_factory(engine)
    with factory() as session:
        teacher_id = session.scalar(
            select(StaffUser.id).where(StaffUser.email == "teacher@example.invalid")
        )
    classroom = _change(
        admin, "POST", "/api/classrooms", {"name": "Phase 6B", "class_type": "REGULAR"}
    )
    assert classroom.status_code == 201
    classroom_id = classroom.json()["id"]
    payload = {
        "staff_user_id": teacher_id,
        "assignment_role": "TEACHER",
        "valid_from": date.today().isoformat(),
    }

    def assign() -> int:
        client = TestClient(app, raise_server_exceptions=False, cookies=dict(admin.cookies))
        return _change(
            client, "POST", f"/api/classrooms/{classroom_id}/assignments", payload
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: assign(), range(2))) == [201, 409]
    with factory() as session:
        assignment = session.scalar(select(ClassroomStaffAssignment))
        assert assignment is not None
        assignment_id = assignment.id
        assert session.scalar(select(func.count()).select_from(ClassroomStaffAssignment)) == 1

    classroom_staff = admin.get(f"/api/classrooms/{classroom_id}/staff")
    assert classroom_staff.status_code == 200
    assert classroom_staff.json()["items"][0]["staff_user_id"] == teacher_id
    assert "display_name" in classroom_staff.json()["items"][0]
    assert teacher.get(f"/api/classrooms/{classroom_id}/staff").status_code == 403
    assert admin.get(f"/api/staff/{teacher_id}/assignments").status_code == 200
    assert teacher.get(f"/api/staff/{teacher_id}/assignments").status_code == 200
    assert teacher.get("/api/staff/1/assignments").status_code == 403
    assert teacher.get("/api/classrooms").json()["items"][0]["id"] == classroom_id
    assert teacher.get(f"/api/classrooms/{classroom_id}/students").status_code == 200

    removed = _change(
        admin, "DELETE", f"/api/classrooms/{classroom_id}/assignments/{assignment_id}"
    )
    assert removed.status_code == 204
    assert teacher.get(f"/api/classrooms/{classroom_id}/students").status_code == 403
    assert teacher.get("/api/classrooms").json()["items"] == []
    assert (
        _change(
            admin, "DELETE", f"/api/classrooms/{classroom_id}/assignments/{assignment_id}"
        ).status_code
        == 404
    )
    assert (
        _change(
            admin,
            "POST",
            f"/api/classrooms/{classroom_id}/assignments",
            {**payload, "staff_user_id": 999999},
        ).status_code
        == 400
    )


def test_staff_deletion_keeps_history_and_removes_unused_accounts(engine: Engine) -> None:
    """Staff deletion option B (2026-11-20): an account without history is removed; one with
    history (a log-in is enough) is marked deleted — it cannot log in and leaves the lists, but
    records keep naming it."""
    from app.modules.notifications.repository import NotificationRepository

    admin = _login("admin@example.invalid")
    teacher = _login("teacher@example.invalid")  # logging in leaves an AUTH_LOGIN record
    unused = _change(
        admin,
        "POST",
        "/api/staff",
        {
            "email": "unused@example.invalid",
            "display_name": "미사용",
            "password": PASSWORD,
            "role": "ASSISTANT",
        },
    ).json()
    staff = {row["email"]: row for row in admin.get("/api/staff").json()["items"]}
    teacher_id = staff["teacher@example.invalid"]["id"]
    room = _change(admin, "POST", "/api/classrooms", {"name": "A반", "class_type": "REGULAR"})
    assignment = _change(
        admin,
        "POST",
        f"/api/classrooms/{room.json()['id']}/assignments",
        {"staff_user_id": teacher_id, "assignment_role": "TEACHER", "valid_from": "2026-01-01"},
    )
    assert assignment.status_code == 201

    # Teachers cannot delete; CSRF is required; the signed-in account cannot delete itself.
    assert _change(teacher, "DELETE", f"/api/staff/{unused['id']}").status_code == 403
    assert admin.delete(f"/api/staff/{unused['id']}").status_code == 403
    me = staff["admin@example.invalid"]["id"]
    assert _change(admin, "DELETE", f"/api/staff/{me}").json()["code"] == "SELF_DELETION_FORBIDDEN"

    removed = _change(admin, "DELETE", f"/api/staff/{unused['id']}")
    assert removed.status_code == 200 and removed.json() == {
        "staff_id": unused["id"],
        "mode": "HARD",
    }
    with engine.connect() as connection:
        assert (
            connection.scalar(
                text("SELECT count(*) FROM staff_user WHERE id = :i"), {"i": unused["id"]}
            )
            == 0
        )

    kept = _change(admin, "DELETE", f"/api/staff/{teacher_id}")
    assert kept.json() == {"staff_id": teacher_id, "mode": "SOFT"}
    assert teacher.get("/api/auth/me").status_code == 401  # session revoked at once
    relogin = TestClient(app, raise_server_exceptions=False).post(
        "/api/auth/login", json={"email": "teacher@example.invalid", "password": PASSWORD}
    )
    assert relogin.status_code == 401
    emails = {row["email"] for row in admin.get("/api/staff").json()["items"]}
    assert "teacher@example.invalid" not in emails
    roster = admin.get(f"/api/classrooms/{room.json()['id']}/staff").json()["items"]
    assert roster == []  # no longer shown as the class's teacher
    assert admin.get(f"/api/staff/{teacher_id}").status_code == 404
    assert (
        _change(admin, "PATCH", f"/api/staff/{teacher_id}/status", {"status": "ACTIVE"}).status_code
        == 404
    )  # never revived
    again = _change(
        admin,
        "POST",
        "/api/staff",
        {
            "email": "teacher@example.invalid",
            "display_name": "재입사",
            "password": PASSWORD,
            "role": "TEACHER",
        },
    )
    assert again.status_code == 409 and "삭제된 직원" in again.json()["message"]
    assert _change(admin, "DELETE", f"/api/staff/{teacher_id}").status_code == 404

    with engine.connect() as connection:
        logins = connection.scalar(
            text("SELECT count(*) FROM audit_log WHERE actor_staff_user_id = :i"), {"i": teacher_id}
        )
        events = (
            connection.execute(
                text("SELECT details FROM audit_log WHERE event_type = 'STAFF_DELETED' ORDER BY id")
            )
            .scalars()
            .all()
        )
    assert logins >= 1  # the teacher's own records still point at the account
    assert [e["mode"] for e in events] == ["HARD", "SOFT"]
    with create_session_factory(engine)() as session:
        names = NotificationRepository(session).staff_names([teacher_id])
    assert names[teacher_id] == "teacher@example.invalid (삭제된 직원)"
