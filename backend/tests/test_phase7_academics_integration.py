"""Phase 7 Stages 3-5: lessons, attendance and grades over the real API and PostgreSQL."""

import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select, text

from app.db.models.tables import (
    AssessmentResult,
    AuditLog,
    Classroom,
    ClassroomStaffAssignment,
    Enrollment,
    LessonResult,
    StaffUser,
    Student,
)
from app.db.session import create_db_engine, create_session_factory, get_engine, get_session_factory
from app.main import app
from app.modules.auth.service import hash_password, login_rate_limiter

pytestmark = pytest.mark.postgres
PASSWORD = "correct horse battery staple"
PAST = "2026-11-03"
FUTURE = (date.today() + timedelta(days=7)).isoformat()


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


@pytest.fixture()
def world(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> dict:
    monkeypatch.setenv("ACADEMY_ENABLE_DB_APIS", "1")
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
                "assessment_result,assessment,makeup_request,message_draft,"
                "lesson_result,lesson,enrollment,student,classroom "
                "RESTART IDENTITY CASCADE"
            )
        )
    ids: dict = {}
    with create_session_factory(engine).begin() as session:

        def staff(key: str, role: str) -> StaffUser:
            row = StaffUser(
                email=f"{key}@example.invalid",
                display_name=key,
                password_hash=hash_password(PASSWORD),
                role=role,
                status="ACTIVE",
            )
            session.add(row)
            return row

        users = {
            "admin": staff("admin", "ADMIN"),
            "teacher": staff("teacher", "TEACHER"),
            "teacher2": staff("teacher2", "TEACHER"),
            "assistant": staff("assistant", "ASSISTANT"),
            "assistant2": staff("assistant2", "ASSISTANT"),
        }
        room_a = Classroom(name="A", class_type="REGULAR")
        room_b = Classroom(name="B", class_type="REGULAR")
        session.add_all([room_a, room_b])
        session.flush()
        for key, role in (("teacher", "TEACHER"), ("assistant", "ASSISTANT")):
            session.add(
                ClassroomStaffAssignment(
                    classroom_id=room_a.id,
                    staff_user_id=users[key].id,
                    assignment_role=role,
                    valid_from=date(2026, 1, 1),
                )
            )

        def enrol(name: str, room: Classroom, enrolled: date, status="ACTIVE", ended=None):
            student = Student(name=name)
            session.add(student)
            session.flush()
            row = Enrollment(
                student_id=student.id,
                classroom_id=room.id,
                status=status,
                enrolled_at=enrolled,
                ended_at=ended,
            )
            session.add(row)
            session.flush()
            ids[name] = row.id
            ids[f"{name}_student"] = student.id

        enrol("s1", room_a, date(2026, 1, 1))
        enrol("s2", room_a, date(2026, 1, 1))
        enrol("late_joiner", room_a, date(2026, 11, 10))
        enrol("withdrawn", room_a, date(2026, 1, 1), status="WITHDRAWN")
        enrol("other", room_b, date(2026, 1, 1))
        session.flush()
        ids.update({f"{k}_id": v.id for k, v in users.items()})
        ids["A"], ids["B"] = room_a.id, room_b.id
    return ids


def login(key: str) -> TestClient:
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/api/auth/login", json={"email": f"{key}@example.invalid", "password": PASSWORD}
    )
    assert response.status_code == 200
    return client


def send(client: TestClient, method: str, path: str, payload=None):
    return client.request(
        method, path, json=payload, headers={"X-CSRF-Token": client.cookies.get("academy_csrf")}
    )


def make_lesson(client: TestClient, room: int, day: str = PAST, **extra) -> dict:
    response = send(
        client, "POST", f"/api/classrooms/{room}/lessons", {"lesson_date": day, **extra}
    )
    assert response.status_code == 201, response.text
    return response.json()


def audit(engine: Engine, event: str) -> list[AuditLog]:
    with create_session_factory(engine)() as session:
        return list(
            session.scalars(
                select(AuditLog).where(AuditLog.event_type == event).order_by(AuditLog.id)
            )
        )


# ---------------------------------------------------------------- Scenario A
def test_lesson_management_and_permissions(engine: Engine, world: dict) -> None:
    admin, teacher, assistant = login("admin"), login("teacher"), login("assistant")
    outsider = login("teacher2")
    room_a, room_b = world["A"], world["B"]

    lesson = make_lesson(admin, room_a, topic="  이차함수 ", memo="교재 3장")
    assert (lesson["status"], lesson["version"], lesson["topic"]) == ("SCHEDULED", 1, "이차함수")
    assert TestClient(app).get(f"/api/classrooms/{room_a}/lessons").status_code == 401
    assert teacher.get(f"/api/classrooms/{room_a}/lessons").json()["items"][0]["id"] == lesson["id"]
    assert assistant.get(f"/api/lessons/{lesson['id']}").status_code == 200
    assert outsider.get(f"/api/classrooms/{room_a}/lessons").status_code == 403
    assert outsider.get(f"/api/lessons/{lesson['id']}").status_code == 403  # BOLA by lesson id
    assert login("assistant2").get(f"/api/lessons/{lesson['id']}").status_code == 403
    assert teacher.get("/api/lessons/999999").status_code == 404

    body = {"lesson_date": "2026-11-04"}
    assert send(assistant, "POST", f"/api/classrooms/{room_a}/lessons", body).status_code == 403
    assert send(teacher, "POST", f"/api/classrooms/{room_b}/lessons", body).status_code == 403
    assert teacher.post(f"/api/classrooms/{room_a}/lessons", json=body).status_code == 403  # CSRF
    assert (
        send(
            teacher, "POST", f"/api/classrooms/{room_a}/lessons", {**body, "classroom_id": room_b}
        ).status_code
        == 400
    )  # mass assignment
    duplicate = send(teacher, "POST", f"/api/classrooms/{room_a}/lessons", {"lesson_date": PAST})
    assert (duplicate.status_code, duplicate.json()["code"]) == (409, "LESSON_ALREADY_EXISTS")
    assert make_lesson(teacher, room_a, exam_round="2회차")["exam_round"] == "2회차"  # same day
    assert (
        send(
            teacher, "POST", f"/api/classrooms/{room_a}/lessons", {"lesson_date": "1999-12-31"}
        ).status_code
        == 400
    )
    future_done = {"lesson_date": FUTURE, "status": "COMPLETED"}
    assert (
        send(teacher, "POST", f"/api/classrooms/{room_a}/lessons", future_done).status_code == 400
    )

    path = f"/api/lessons/{lesson['id']}"
    updated = send(
        teacher, "PATCH", path, {"version": 1, "topic": "일차함수", "status": "COMPLETED"}
    )
    assert updated.status_code == 200
    assert (updated.json()["version"], updated.json()["topic"]) == (2, "일차함수")
    stale = send(teacher, "PATCH", path, {"version": 1, "topic": "x"})
    assert (stale.status_code, stale.json()["code"]) == (409, "VERSION_CONFLICT")
    assert send(teacher, "PATCH", path, {"version": 2, "status": None}).status_code == 400
    assert send(assistant, "PATCH", path, {"version": 2, "topic": "x"}).status_code == 403
    cleared = send(admin, "PATCH", path, {"version": 2, "memo": None})
    assert cleared.json()["memo"] is None

    events = audit(engine, "LESSON_UPDATED")
    assert [e.actor_staff_user_id for e in events] == [world["teacher_id"], world["admin_id"]]
    assert events[0].details["before"] == {"topic": "이차함수", "status": "SCHEDULED", "version": 1}
    assert events[1].details["after"] == {"memo_changed": True}
    assert "교재" not in json.dumps(events[1].details, ensure_ascii=False)


# ---------------------------------------------------- Scenarios B, C and G
def test_attendance_roster_bulk_history_and_atomicity(engine: Engine, world: dict) -> None:
    teacher, assistant = login("teacher"), login("assistant")
    lesson = make_lesson(teacher, world["A"])
    path = f"/api/lessons/{lesson['id']}/attendance"

    roster = teacher.get(path).json()
    assert [row["enrollment_id"] for row in roster["items"]] == [world["s1"], world["s2"]]
    assert all(row["record"] is None for row in roster["items"])  # unrecorded, not absent
    assert roster["summary"] == {
        "eligible": 2,
        "recorded": 0,
        "unrecorded": 2,
        "present": 0,
        "absent": 0,
        "late": 0,
        "excused": 0,  # Phase 7.1
    }

    saved = send(
        assistant,
        "PUT",
        path,
        {
            "items": [
                {"enrollment_id": world["s1"], "status": "PRESENT"},
                {"enrollment_id": world["s2"], "status": "ABSENT", "memo": "병원 진료"},
            ]
        },
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["changed"] == 2
    assert saved.json()["summary"]["absent"] == 1
    records = {row["enrollment_id"]: row["record"] for row in saved.json()["items"]}
    assert records[world["s1"]]["version"] == 1

    def rejected(items, status, code):
        response = send(teacher, "PUT", path, {"items": items})
        assert (response.status_code, response.json()["code"]) == (status, code), response.text
        return response.json()["fields"]

    # Scenario G: one invalid item rolls back the whole batch.
    fields = rejected(
        [
            {"enrollment_id": world["s1"], "status": "LATE", "version": 1},
            {"enrollment_id": world["other"], "status": "PRESENT"},
        ],
        400,
        "INVALID_ATTENDANCE_ITEMS",
    )
    assert fields == [{"field": "items.1.enrollment_id", "message": "이 반의 학생이 아닙니다."}]
    rejected(
        [{"enrollment_id": world["late_joiner"], "status": "PRESENT"}],
        400,
        "INVALID_ATTENDANCE_ITEMS",
    )
    rejected(
        [{"enrollment_id": world["withdrawn"], "status": "PRESENT"}],
        400,
        "INVALID_ATTENDANCE_ITEMS",
    )
    rejected(
        [
            {"enrollment_id": world["s1"], "status": "LATE", "version": 1},
            {"enrollment_id": world["s1"], "status": "ABSENT", "version": 1},
        ],
        400,
        "INVALID_ATTENDANCE_ITEMS",
    )
    rejected([{"enrollment_id": world["s1"], "status": "LATE"}], 409, "VERSION_CONFLICT")
    rejected(
        [{"enrollment_id": world["s1"], "status": "LATE", "version": 9}], 409, "VERSION_CONFLICT"
    )
    assert (
        send(
            # Unknown status is rejected (EXCUSED became valid in Phase 7.1).
            teacher, "PUT", path, {"items": [{"enrollment_id": world["s1"], "status": "SICK"}]}
        ).status_code
        == 400
    )
    assert teacher.get(path).json()["items"][0]["record"]["status"] == "PRESENT"

    # Scenario C: change history is consistent with the stored value.
    changed = send(
        teacher,
        "PUT",
        path,
        {
            "items": [
                {"enrollment_id": world["s1"], "status": "LATE", "version": 1},
                {
                    "enrollment_id": world["s2"],
                    "status": "ABSENT",
                    "memo": "병원 진료",
                    "version": 1,
                },
            ]
        },
    )
    assert changed.json()["changed"] == 1  # unchanged s2 is skipped
    assert changed.json()["items"][0]["record"] | {"updated_at": None} == {
        "status": "LATE",
        "memo": None,
        "version": 2,
        "updated_at": None,
    }
    [update] = audit(engine, "ATTENDANCE_UPDATED")
    assert update.actor_staff_user_id == world["teacher_id"]
    assert update.details["before"] == {"status": "PRESENT", "version": 1}
    assert update.details["after"] == {"status": "LATE", "version": 2}
    recorded = audit(engine, "ATTENDANCE_RECORDED")
    assert {e.actor_staff_user_id for e in recorded} == {world["assistant_id"]}
    assert "병원" not in json.dumps([e.details for e in recorded], ensure_ascii=False)

    lesson_path = f"/api/lessons/{lesson['id']}"
    assert (
        send(teacher, "PATCH", lesson_path, {"version": 1, "status": "CANCELLED"}).json()["code"]
        == "LESSON_HAS_RECORDS"
    )
    assert (
        send(teacher, "PATCH", lesson_path, {"version": 1, "lesson_date": "2026-11-05"}).status_code
        == 409
    )
    assert send(teacher, "PATCH", lesson_path, {"version": 1, "topic": "ok"}).status_code == 200

    cancelled = make_lesson(teacher, world["A"], "2026-11-06")
    send(teacher, "PATCH", f"/api/lessons/{cancelled['id']}", {"version": 1, "status": "CANCELLED"})
    item = {"items": [{"enrollment_id": world["s1"], "status": "PRESENT"}]}
    assert (
        send(teacher, "PUT", f"/api/lessons/{cancelled['id']}/attendance", item).json()["code"]
        == "LESSON_CANCELLED"
    )
    future = make_lesson(teacher, world["A"], FUTURE)
    assert send(teacher, "PUT", f"/api/lessons/{future['id']}/attendance", item).status_code == 400
    assert send(login("teacher2"), "PUT", path, item).status_code == 403
    assert send(login("assistant2"), "PUT", path, item).status_code == 403
    with create_session_factory(engine)() as session:
        assert session.scalar(select(func.count()).select_from(LessonResult)) == 2


# ---------------------------------------------------------- Scenarios D, E
def test_assessments_grades_validation_and_history(engine: Engine, world: dict) -> None:
    teacher, assistant, admin = login("teacher"), login("assistant"), login("admin")
    lesson = make_lesson(teacher, world["A"])
    other_lesson = make_lesson(admin, world["B"])
    create = f"/api/classrooms/{world['A']}/assessments"
    base = {"title": "단원 평가", "assessment_date": PAST, "max_score": 20}
    # 2026-11-19 (Phase 8.1, user decision): assistants may create assessments too.
    by_assistant = send(assistant, "POST", create, {**base, "title": "조교 등록 평가"})
    assert by_assistant.status_code == 201, by_assistant.text
    assert send(login("assistant2"), "POST", create, base).status_code == 403  # not assigned
    assert (
        send(teacher, "POST", create, {**base, "lesson_id": other_lesson["id"]}).json()["code"]
        == "INVALID_LESSON_LINK"
    )
    for bad in ({"max_score": 0}, {"max_score": -5}, {"max_score": 1.234}, {"title": "   "}):
        assert send(teacher, "POST", create, {**base, **bad}).status_code == 400
    assessment = send(teacher, "POST", create, {**base, "lesson_id": lesson["id"]}).json()
    assert (assessment["max_score"], assessment["version"]) == (20.0, 1)
    path = f"/api/assessments/{assessment['id']}/grades"

    def rejected(items, field_message):
        response = send(teacher, "PUT", path, {"items": items})
        assert (response.status_code, response.json()["code"]) == (400, "INVALID_GRADE_ITEMS")
        assert field_message in [f["message"] for f in response.json()["fields"]]

    s1, s2 = world["s1"], world["s2"]
    rejected(
        [{"enrollment_id": s1, "result_status": "SCORED", "score": 20.01}],
        "만점(20.00)을 넘을 수 없습니다.",
    )
    rejected(
        [{"enrollment_id": s1, "result_status": "SCORED", "score": -1}],
        "0 이상의 점수를 입력해주세요.",
    )
    rejected(
        [{"enrollment_id": s1, "result_status": "SCORED", "score": 1.234}],
        "소수점 둘째 자리까지 입력할 수 있습니다.",
    )
    rejected([{"enrollment_id": s1, "result_status": "SCORED"}], "점수를 입력해주세요.")
    rejected(
        [{"enrollment_id": s1, "result_status": "NOT_TAKEN", "score": 0}],
        "미응시는 점수를 입력하지 않습니다.",
    )
    rejected(
        [{"enrollment_id": world["other"], "result_status": "SCORED", "score": 1}],
        "이 반의 학생이 아닙니다.",
    )
    saved = send(
        teacher,
        "PUT",
        path,
        {
            "items": [
                {"enrollment_id": s1, "result_status": "SCORED", "score": 18.5},
                {"enrollment_id": s2, "result_status": "NOT_TAKEN"},
            ]
        },
    )
    assert saved.status_code == 200, saved.text
    rows = {row["enrollment_id"]: row["record"] for row in saved.json()["items"]}
    assert (rows[s1]["score"], rows[s2]["score"], rows[s2]["result_status"]) == (
        18.5,
        None,
        "NOT_TAKEN",
    )
    assert saved.json()["summary"] == {"eligible": 2, "scored": 1, "not_taken": 1, "unrecorded": 0}
    dup = send(
        teacher,
        "PUT",
        path,
        {"items": [{"enrollment_id": s1, "result_status": "SCORED", "score": 1}]},
    )
    assert dup.status_code == 409

    zero = send(
        teacher,
        "PUT",
        path,
        {"items": [{"enrollment_id": s1, "result_status": "SCORED", "score": 0, "version": 1}]},
    )
    assert zero.json()["items"][0]["record"]["score"] == 0.0
    [update] = audit(engine, "GRADE_UPDATED")
    assert update.details["before"]["score"] == "18.50" and update.details["after"]["score"] == "0"
    send(
        teacher,
        "PUT",
        path,
        {"items": [{"enrollment_id": s1, "result_status": "SCORED", "score": 18.5, "version": 2}]},
    )

    detail = f"/api/assessments/{assessment['id']}"
    low = send(teacher, "PATCH", detail, {"version": 1, "max_score": 15})
    assert (low.status_code, low.json()["code"]) == (409, "MAX_SCORE_BELOW_EXISTING")
    assert (
        send(teacher, "PATCH", detail, {"version": 1, "assessment_date": "2026-11-04"}).json()[
            "code"
        ]
        == "ASSESSMENT_HAS_RESULTS"
    )
    raised = send(teacher, "PATCH", detail, {"version": 1, "max_score": 30, "title": "단원 평가 1"})
    assert (raised.status_code, raised.json()["max_score"], raised.json()["version"]) == (
        200,
        30.0,
        2,
    )
    with create_session_factory(engine)() as session:
        assert {float(r.max_score) for r in session.scalars(select(AssessmentResult))} == {30.0}
    assert send(teacher, "PATCH", detail, {"version": 1, "title": "x"}).status_code == 409

    listed = teacher.get(f"/api/classrooms/{world['A']}/assessments").json()["items"][0]
    assert (listed["scored"], listed["not_taken"]) == (1, 1)
    records = teacher.get(
        f"/api/classrooms/{world['A']}/students/{world['s1_student']}/records"
    ).json()
    assert records["assessments"][0]["score"] == 18.5
    assert records["lessons"][0]["attendance_status"] is None  # not entered, not absent
    assert (
        teacher.get(
            f"/api/classrooms/{world['A']}/students/{world['other_student']}/records"
        ).status_code
        == 404
    )
    assert (
        login("teacher2")
        .get(f"/api/classrooms/{world['A']}/students/{world['s1_student']}/records")
        .status_code
        == 403
    )
    assert login("teacher2").get(path).status_code == 403

    # Policy change 2026-11-19 (Phase 8.1, user decision): assistants may record and correct
    # scores and edit assessments too — they already save scores through the workbook upload
    # and must be able to fix them.
    current = {r["enrollment_id"]: r["record"] for r in assistant.get(path).json()["items"]}[s1]
    item = {"enrollment_id": s1, "result_status": "SCORED", "score": 17}
    fixed = send(assistant, "PUT", path, {"items": [{**item, "version": current["version"]}]})
    assert fixed.status_code == 200, fixed.text
    assert {r["enrollment_id"]: r["record"]["score"] for r in fixed.json()["items"]}[s1] == 17.0
    renamed = send(assistant, "PATCH", detail, {"version": 2, "title": "단원 평가 (조교 수정)"})
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["title"] == "단원 평가 (조교 수정)"
    outsider = send(login("assistant2"), "PATCH", detail, {"version": 3, "title": "x"})
    assert outsider.status_code == 403  # assistants of other classes still cannot


# ---------------------------------------------------------------- Scenario F
def test_assignment_revocation_and_inactive_staff(engine: Engine, world: dict) -> None:
    admin, teacher, assistant = login("admin"), login("teacher"), login("assistant")
    lesson = make_lesson(teacher, world["A"])
    assessment = send(
        teacher,
        "POST",
        f"/api/classrooms/{world['A']}/assessments",
        {
            "title": "퀴즈",
            "assessment_date": PAST,
            "max_score": 10,
        },
    ).json()
    assert teacher.get(f"/api/lessons/{lesson['id']}/attendance").status_code == 200

    with create_session_factory(engine)() as session:
        assignment_id = session.scalar(
            select(ClassroomStaffAssignment.id).where(
                ClassroomStaffAssignment.staff_user_id == world["teacher_id"]
            )
        )
    removed = send(admin, "DELETE", f"/api/classrooms/{world['A']}/assignments/{assignment_id}")
    assert removed.status_code == 204
    item = {"items": [{"enrollment_id": world["s1"], "status": "PRESENT"}]}
    assert teacher.get(f"/api/lessons/{lesson['id']}").status_code == 403
    assert send(teacher, "PUT", f"/api/lessons/{lesson['id']}/attendance", item).status_code == 403
    assert teacher.get(f"/api/assessments/{assessment['id']}/grades").status_code == 403
    assert teacher.get(f"/api/classrooms/{world['A']}/lessons").status_code == 403

    assert (
        send(
            admin, "PATCH", f"/api/staff/{world['assistant_id']}/status", {"status": "INACTIVE"}
        ).status_code
        == 200
    )
    assert assistant.get(f"/api/lessons/{lesson['id']}").status_code == 401


# ---------------------------------------------------------------- Scenario H
def test_concurrent_attendance_and_grade_writes(engine: Engine, world: dict) -> None:
    teacher = login("teacher")
    lesson = make_lesson(teacher, world["A"])
    path = f"/api/lessons/{lesson['id']}/attendance"

    def parallel(method: str, url: str, payloads: list) -> list[int]:
        def call(payload):
            client = TestClient(app, raise_server_exceptions=False, cookies=dict(teacher.cookies))
            return send(client, method, url, payload).status_code

        with ThreadPoolExecutor(max_workers=len(payloads)) as pool:
            return sorted(pool.map(call, payloads))

    create = {"items": [{"enrollment_id": world["s1"], "status": "PRESENT"}]}
    assert parallel("PUT", path, [create, create]) == [200, 409]
    edits = [
        {"items": [{"enrollment_id": world["s1"], "status": status, "version": 1}]}
        for status in ("ABSENT", "LATE")
    ]
    assert parallel("PUT", path, edits) == [200, 409]
    with create_session_factory(engine)() as session:
        rows = list(session.scalars(select(LessonResult)))
        assert (
            len(rows) == 1
            and rows[0].version == 2
            and rows[0].attendance_status in {"ABSENT", "LATE"}
        )
        assert len(audit(engine, "ATTENDANCE_UPDATED")) == 1

    assessment = send(
        teacher,
        "POST",
        f"/api/classrooms/{world['A']}/assessments",
        {
            "title": "퀴즈",
            "assessment_date": PAST,
            "max_score": 10,
        },
    ).json()
    grades = f"/api/assessments/{assessment['id']}/grades"
    score = {"items": [{"enrollment_id": world["s2"], "result_status": "SCORED", "score": 7}]}
    assert parallel("PUT", grades, [score, score]) == [200, 409]
    with create_session_factory(engine)() as session:
        assert session.scalar(select(func.count()).select_from(AssessmentResult)) == 1
