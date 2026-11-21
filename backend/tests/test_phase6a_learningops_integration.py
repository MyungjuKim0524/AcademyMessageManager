import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select, text

from app.db.models.tables import Enrollment, StaffUser
from app.db.session import create_db_engine, create_session_factory, get_engine, get_session_factory
from app.main import app
from app.modules.auth.service import hash_password, login_rate_limiter

pytestmark = pytest.mark.postgres
PASSWORD = "correct horse battery staple"


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
                    email="teacher@example.invalid",
                    password_hash=hash_password(PASSWORD),
                    role="TEACHER",
                    status="ACTIVE",
                ),
                StaffUser(
                    email="other@example.invalid",
                    password_hash=hash_password(PASSWORD),
                    role="TEACHER",
                    status="ACTIVE",
                ),
                StaffUser(
                    email="inactive@example.invalid",
                    password_hash=hash_password(PASSWORD),
                    role="TEACHER",
                    status="INACTIVE",
                ),
            ]
        )


def _login(email: str) -> TestClient:
    client = TestClient(app, raise_server_exceptions=False)
    assert (
        client.post("/api/auth/login", json={"email": email, "password": PASSWORD}).status_code
        == 200
    )
    return client


def _post(client: TestClient, path: str, payload: dict):
    return client.post(
        path, json=payload, headers={"X-CSRF-Token": client.cookies.get("academy_csrf")}
    )


def test_admin_flow_scope_privacy_csrf_and_concurrent_duplicate(engine: Engine) -> None:
    admin = _login("admin@example.invalid")
    assert (
        admin.post("/api/classrooms", json={"name": "no-csrf", "class_type": "REGULAR"}).status_code
        == 403
    )
    classroom = _post(admin, "/api/classrooms", {"name": "A반", "class_type": "REGULAR"})
    other_class = _post(admin, "/api/classrooms", {"name": "B반", "class_type": "REGULAR"})
    student = _post(
        admin,
        "/api/students",
        {
            "name": "가상학생",
            "school_name": "가상학교",
            "parent_name": "비공개",
            "parent_email": "parent@example.invalid",
        },
    )
    assert {classroom.status_code, other_class.status_code, student.status_code} == {201}
    classroom_id, other_id, student_id = (
        classroom.json()["id"],
        other_class.json()["id"],
        student.json()["id"],
    )

    factory = create_session_factory(engine)
    with factory() as session:
        teacher_id = session.scalar(
            select(StaffUser.id).where(StaffUser.email == "teacher@example.invalid")
        )
        inactive_id = session.scalar(
            select(StaffUser.id).where(StaffUser.email == "inactive@example.invalid")
        )
    assignment = _post(
        admin,
        f"/api/classrooms/{classroom_id}/assignments",
        {
            "staff_user_id": teacher_id,
            "assignment_role": "TEACHER",
            "valid_from": date.today().isoformat(),
        },
    )
    assert assignment.status_code == 201
    assert (
        _post(
            admin,
            f"/api/classrooms/{classroom_id}/assignments",
            {
                "staff_user_id": inactive_id,
                "assignment_role": "TEACHER",
                "valid_from": date.today().isoformat(),
            },
        ).status_code
        == 400
    )

    path = f"/api/classrooms/{classroom_id}/enrollments"
    payload = {"student_id": student_id, "enrolled_at": date.today().isoformat()}
    csrf = admin.cookies.get("academy_csrf")
    cookies = dict(admin.cookies)

    def submit():
        client = TestClient(app, raise_server_exceptions=False, cookies=cookies)
        return client.post(path, json=payload, headers={"X-CSRF-Token": csrf}).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = sorted(pool.map(lambda _: submit(), range(2)))
    assert statuses == [201, 409]
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Enrollment)) == 1

    teacher = _login("teacher@example.invalid")
    visible = teacher.get(f"/api/classrooms/{classroom_id}/students")
    assert visible.status_code == 200
    assert visible.json()["items"][0]["name"] == "가상학생"
    assert "parent" not in visible.text.lower()
    assert teacher.get(f"/api/classrooms/{other_id}/students").status_code == 403
    assert (
        _login("other@example.invalid").get(f"/api/classrooms/{classroom_id}/students").status_code
        == 403
    )


def test_class_student_pages_cover_large_classes_without_gaps_or_overlap(engine: Engine) -> None:
    """Phase 10.5 M3: the client now reads limit=100 pages until a short one. The contract it
    relies on: pages ordered by student id are disjoint and complete, still scoped to the class
    and the staff member's assignment, with the default page size unchanged."""
    with engine.begin() as c:

        def sql(statement: str, **params):
            return c.execute(text(statement), params)

        room = "INSERT INTO classroom(name, class_type) VALUES (:n, 'REGULAR') RETURNING id"
        a, b = sql(room, n="대형반").scalar(), sql(room, n="다른반").scalar()
        sql(
            "INSERT INTO student(name, school_name) "
            "SELECT '가상학생' || n, '가상학교' FROM generate_series(1, 154) n"
        )
        sql(
            "INSERT INTO enrollment(student_id, classroom_id, status, enrolled_at) "
            "SELECT id, CASE WHEN id <= 151 THEN :a ELSE :b END, 'ACTIVE', DATE '2026-01-01' "
            "FROM student",
            a=a,
            b=b,
        )
        teacher = sql("SELECT id FROM staff_user WHERE email = 'teacher@example.invalid'").scalar()
        sql(
            "INSERT INTO classroom_staff_assignment"
            "(classroom_id, staff_user_id, assignment_role, valid_from) "
            "VALUES (:a, :t, 'TEACHER', DATE '2026-01-01')",
            a=a,
            t=teacher,
        )
    client = _login("teacher@example.invalid")

    def page(offset: int, limit: int | None = 100):
        params = {"offset": offset} if limit is None else {"limit": limit, "offset": offset}
        response = client.get(f"/api/classrooms/{a}/students", params=params)
        assert response.status_code == 200, response.text
        return response.json()["items"]

    pages = [page(0), page(100), page(200)]
    assert [len(p) for p in pages] == [100, 51, 0]
    ids = [row["enrollment_id"] for p in pages for row in p]
    assert len(ids) == len(set(ids)) == 151  # no overlap at the boundary, nothing missing
    student_ids = [row["id"] for p in pages for row in p]
    assert student_ids == sorted(student_ids)  # stable order the client relies on
    assert all("parent_email" not in row for p in pages for row in p)  # privacy unchanged
    assert len(page(0, limit=None)) == 50  # default page size (API contract) unchanged
    assert client.get(f"/api/classrooms/{a}/students", params={"limit": 101}).status_code == 400
    assert client.get(f"/api/classrooms/{b}/students", params={"limit": 100}).status_code == 403


def test_admin_lists_all_students_with_classes_and_search(engine: Engine) -> None:
    admin = _login("admin@example.invalid")
    room_a = _post(admin, "/api/classrooms", {"name": "A반", "class_type": "REGULAR"}).json()["id"]
    room_b = _post(admin, "/api/classrooms", {"name": "B반", "class_type": "EXAM_PREP"}).json()[
        "id"
    ]
    ids = {}
    for name, email in (
        ("가상하나", "p1@example.invalid"),
        ("가상둘", None),
        ("가상_100%", None),
    ):
        created = _post(admin, "/api/students", {"name": name, "parent_email": email})
        assert created.status_code == 201
        ids[name] = created.json()["id"]
    today = date.today().isoformat()
    for room in (room_a, room_b):
        assert (
            _post(
                admin,
                f"/api/classrooms/{room}/enrollments",
                {"student_id": ids["가상하나"], "enrolled_at": today},
            ).status_code
            == 201
        )

    page = admin.get("/api/students")
    assert page.status_code == 200
    body = page.json()
    assert body["total"] == 3 and len(body["items"]) == 3
    by_name = {item["name"]: item for item in body["items"]}
    assert [(e["classroom_name"], e["status"]) for e in by_name["가상하나"]["enrollments"]] == [
        ("A반", "ACTIVE"),
        ("B반", "ACTIVE"),
    ]
    assert by_name["가상하나"]["parent_email"] == "p1@example.invalid"
    assert by_name["가상둘"]["enrollments"] == []  # not enrolled anywhere yet: still listed

    found = admin.get("/api/students", params={"q": " 하나 "}).json()
    assert [item["id"] for item in found["items"]] == [ids["가상하나"]] and found["total"] == 1
    # LIKE wildcards are matched literally.
    assert [i["name"] for i in admin.get("/api/students", params={"q": "_"}).json()["items"]] == [
        "가상_100%"
    ]
    assert admin.get("/api/students", params={"q": "%"}).json()["total"] == 1
    paged = admin.get("/api/students", params={"limit": 1, "offset": 1}).json()
    assert paged["total"] == 3 and len(paged["items"]) == 1
    assert admin.get("/api/students", params={"limit": 101}).status_code == 400

    # Guardian contact is personal data: administrators only.
    assert _login("teacher@example.invalid").get("/api/students").status_code == 403
    assert TestClient(app, raise_server_exceptions=False).get("/api/students").status_code == 401


def _send(client: TestClient, method: str, path: str, payload: dict | None = None):
    return client.request(
        method, path, json=payload, headers={"X-CSRF-Token": client.cookies.get("academy_csrf")}
    )


def test_admin_manages_classes_and_registers_a_student_with_a_class(engine: Engine) -> None:
    """2026-11-20: 반 관리 (rename, end / resume operation, delete only an empty class) and
    student registration that enrols in the same transaction."""
    admin, teacher = _login("admin@example.invalid"), _login("teacher@example.invalid")
    used = _post(admin, "/api/classrooms", {"name": "중3 토10", "class_type": "REGULAR"}).json()
    typo = _post(admin, "/api/classrooms", {"name": "002 토2", "class_type": "EXAM_PREP"}).json()
    today = date.today().isoformat()

    # Register + enrol at once; a failing enrolment saves nothing.
    created = _post(
        admin,
        "/api/students",
        {"name": "가상신입", "classroom_id": used["id"], "enrolled_at": today},
    )
    assert created.status_code == 201, created.text
    roster = admin.get(f"/api/classrooms/{used['id']}/students").json()["items"]
    assert [(r["name"], r["enrollment_status"]) for r in roster] == [("가상신입", "ACTIVE")]
    missing = _post(
        admin, "/api/students", {"name": "가상둘", "classroom_id": 999999, "enrolled_at": today}
    )
    assert (missing.status_code, missing.json()["code"]) == (404, "CLASSROOM_NOT_FOUND")
    half = _post(admin, "/api/students", {"name": "가상셋", "classroom_id": used["id"]})
    assert half.status_code in (400, 422)  # class and date go together
    duplicate = _post(
        admin,
        "/api/students",
        {"name": "가상신입", "classroom_id": used["id"], "enrolled_at": today},
    )
    assert duplicate.json()["code"] == "STUDENT_BUSINESS_KEY_CONFLICT"
    with engine.connect() as connection:
        names = connection.execute(text("SELECT name FROM student ORDER BY id")).scalars().all()
    assert names == ["가상신입"]

    # Rename a typo; teachers cannot manage classes.
    renamed = _send(admin, "PATCH", f"/api/classrooms/{typo['id']}", {"name": "00고2 토2"})
    assert renamed.status_code == 200 and renamed.json()["name"] == "00고2 토2"
    assert (
        _send(teacher, "PATCH", f"/api/classrooms/{typo['id']}", {"name": "x"}).status_code == 403
    )
    assert (
        admin.patch(f"/api/classrooms/{typo['id']}", json={"name": "y"}).status_code == 403
    )  # CSRF

    # A class with records cannot be deleted; it can end operation and come back.
    refused = _send(admin, "DELETE", f"/api/classrooms/{used['id']}")
    assert (refused.status_code, refused.json()["code"]) == (409, "CLASSROOM_HAS_RECORDS")
    ended = _send(admin, "PATCH", f"/api/classrooms/{used['id']}", {"is_active": False})
    assert ended.json()["is_active"] is False
    active_names = [c["name"] for c in admin.get("/api/classrooms").json()["items"]]
    assert active_names == ["00고2 토2"]  # hidden from daily screens
    everything = admin.get("/api/classrooms", params={"include_inactive": "true"}).json()["items"]
    assert [(c["name"], c["is_active"]) for c in everything] == [
        ("00고2 토2", True),
        ("중3 토10", False),
    ]
    assert admin.get(f"/api/classrooms/{used['id']}/students").status_code == 404
    listing = admin.get("/api/students").json()["items"][0]["enrollments"][0]
    assert listing["classroom_active"] is False  # history kept, shown as ended
    again = _post(admin, "/api/classrooms", {"name": "중3 토10", "class_type": "REGULAR"})
    assert again.status_code == 409 and "다시 운영" in again.json()["message"]
    assert teacher.get("/api/classrooms", params={"include_inactive": "true"}).json()["items"] == []
    resumed = _send(admin, "PATCH", f"/api/classrooms/{used['id']}", {"is_active": True})
    assert resumed.json()["is_active"] is True
    assert len(admin.get(f"/api/classrooms/{used['id']}/students").json()["items"]) == 1

    # An empty class (registered by mistake) is deleted.
    assert _send(admin, "DELETE", f"/api/classrooms/{typo['id']}").status_code == 204
    assert _send(admin, "DELETE", f"/api/classrooms/{typo['id']}").status_code == 404
    with engine.connect() as connection:
        events = connection.execute(
            text(
                # CLASSROOM_CREATED (Phase 11-2-B-1) is covered by the security suite.
                "SELECT event_type, details FROM audit_log "
                "WHERE target_type='CLASSROOM' AND event_type <> 'CLASSROOM_CREATED' ORDER BY id"
            )
        ).all()
    assert [e for e, _ in events] == [
        "CLASSROOM_UPDATED",
        "CLASSROOM_UPDATED",
        "CLASSROOM_UPDATED",
        "CLASSROOM_DELETED",
    ]
    assert events[0][1]["changed"]["name"] == {"before": "002 토2", "after": "00고2 토2"}
