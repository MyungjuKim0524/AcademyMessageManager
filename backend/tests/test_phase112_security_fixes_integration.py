# ruff: noqa: F811, E501  -- pytest fixtures imported from the Phase 7 / 8.1 suites are injected by name
"""Phase 11-2-B-1 regression tests (fictional data, isolated test DB only).

SEC-01: a workbook upload's NEW decision never links an existing student (it used to reuse a
student of another class with the same name / school, exposing that guardian's address).
SEC-02: administrators' staff / assignment / enrolment / registration changes are audited in the
same transaction, and a removed assignment stays traceable.
"""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from test_phase7_academics_integration import (  # noqa: F401
    PASSWORD,
    audit,
    engine,
    login,
    send,
    world,
)
from test_phase81_lesson_upload_integration import _post, setup  # noqa: F401
from test_phase81_workbook_parser import HEADER, workbook

from app.main import app
from app.modules.learningops.service import LearningOpsService
from app.modules.lesson_upload.service import LessonUploadService

pytestmark = pytest.mark.postgres
GUARDIAN_B = "guardian-b@example.invalid"
CLASS_B_NAME = "00고2 토10"  # what the setup fixture names class B


def _sql(engine: Engine, sql: str, **params):
    with engine.begin() as connection:
        return connection.execute(text(sql), params)


def _count(engine: Engine, sql: str, **params) -> int:
    return _sql(engine, sql, **params).scalar()


def _state(engine: Engine) -> dict:
    """Row counts an upload may touch — compared before / after a refused confirm."""
    tables = ("student", "enrollment", "lesson", "lesson_result", "assessment", "assessment_result", "parent_notification", "audit_log")
    return {t: _count(engine, f"SELECT count(*) FROM {t}") for t in tables}


def _file(*rows, name="중3 토10") -> bytes:
    return workbook(("10시", [[name, *HEADER], *rows]))


def _rows(response) -> dict:
    assert response.status_code == 200, response.text
    return {r["name"]: r for b in response.json()["blocks"] for r in b["rows"]}


def _no_other_class_data(text_: str) -> None:
    assert GUARDIAN_B not in text_
    assert CLASS_B_NAME not in text_


@pytest.fixture()
def guarded(engine: Engine, setup: dict) -> dict:
    """setup + the class-B student 'other' has a guardian address the class-A staff must not see."""
    _sql(engine, "UPDATE student SET parent_email=:m WHERE id=:s", m=GUARDIAN_B, s=setup["other_student"])
    return setup


# ------------------------------------------------------------------------------------- SEC-01
@pytest.mark.parametrize("role", ["teacher", "assistant", "admin"])
def test_new_decision_never_links_another_class_student(engine: Engine, guarded: dict, role: str) -> None:
    """Former reproduction (Phase 11-2-A): the class-A teacher put class-B student 'other' in the
    workbook and chose NEW -> 'other' was enrolled in A and the guardian e-mail became readable.
    Now the row is flagged in the preview, NEW is refused, and nothing at all is saved. The
    administrator is refused too: the upload has no 'link an existing student' option."""
    client = login(role)
    if role != "admin":  # control: no access to class B, no manual enrolment
        assert client.get(f"/api/classrooms/{guarded['B']}/students").status_code == 403
        manual = send(client, "POST", f"/api/classrooms/{guarded['A']}/enrollments", {"student_id": guarded["other_student"], "enrolled_at": "2026-11-03"})
        assert manual.status_code == 403
    content = _file(["s1", "출석", "A", "A", 12, 8], ["other", "출석", "A", "A", 12, 8])
    preview = _post(client, "preview", content)
    rows = _rows(preview)
    other = rows["other"]
    assert other["status"] == "UNREGISTERED" and other["existing_student_conflict"] is True
    assert any("신규로 등록할 수 없습니다" in w for w in other["warnings"])
    assert rows["s1"]["existing_student_conflict"] is False
    _no_other_class_data(preview.text)

    before = _state(engine)
    refused = _post(client, "confirm", content, decisions=json.dumps({other["key"]: "NEW"}))
    assert (refused.status_code, refused.json()["code"]) == (400, "EXISTING_STUDENT_ELSEWHERE")
    _no_other_class_data(refused.text)
    # No partial save: not even the s1 row, the lesson, an audit row or a message draft.
    assert _state(engine) == before
    linked = "SELECT count(*) FROM enrollment WHERE student_id=:s AND classroom_id=:a"
    assert _count(engine, linked, s=guarded["other_student"], a=guarded["A"]) == 0

    # Excluding the row saves the rest; 'other' stays out of class A, no draft for that guardian.
    saved = _post(client, "confirm", content, decisions=json.dumps({other["key"]: "EXCLUDE"}))
    assert saved.status_code == 200, saved.text
    assert (saved.json()["new_students"], saved.json()["excluded_rows"]) == (0, 1)
    _no_other_class_data(saved.text)
    assert _count(engine, linked, s=guarded["other_student"], a=guarded["A"]) == 0
    assert _count(engine, "SELECT count(*) FROM parent_notification WHERE recipient_email=:m", m=GUARDIAN_B) == 0
    assert _count(engine, "SELECT count(*) FROM student") == before["student"]
    # Follow-up message views (list, and the detail that shows the full address — M2 policy).
    listing = client.get(f"/api/notifications?classroom_id={guarded['A']}")
    assert listing.status_code == 200 and listing.json()["items"]  # s1's draft exists
    _no_other_class_data(listing.text)
    for item in listing.json()["items"]:
        _no_other_class_data(client.get(f"/api/notifications/{item['id']}").text)


def test_same_name_student_is_registered_by_admin_not_by_upload(engine: Engine, guarded: dict) -> None:
    """Two different children named 'other' (regular classes carry no school): the upload does
    not merge them, and the class can still get its own 'other' — the administrator registers
    the student with a distinguishing school (existing student key policy), then uploads match."""
    teacher, admin = login("teacher"), login("admin")
    content = _file(["other", "출석", "B", "A", 9, 7])
    assert _rows(_post(teacher, "preview", content))["other"]["existing_student_conflict"] is True

    # Existing policy (unchanged): the same key cannot be registered twice.
    duplicate = send(admin, "POST", "/api/students", {"name": "other"})
    assert (duplicate.status_code, duplicate.json()["code"]) == (409, "STUDENT_BUSINESS_KEY_CONFLICT")
    created = send(admin, "POST", "/api/students", {"name": "other", "school_name": "가나중", "classroom_id": guarded["A"], "enrolled_at": "2026-11-01"})
    assert created.status_code == 201, created.text
    new_student = created.json()["id"]
    assert new_student != guarded["other_student"]

    row = _rows(_post(teacher, "preview", content))["other"]
    assert row["status"] == "MATCHED" and row["existing_student_conflict"] is False
    confirmed = _post(teacher, "confirm", content)
    assert confirmed.status_code == 200, confirmed.text
    stored = _sql(engine, "SELECT e.student_id FROM lesson_result r JOIN enrollment e ON e.id=r.enrollment_id").scalars().all()
    assert stored == [new_student]  # written to class A's own 'other', never to class B's
    assert _count(engine, "SELECT count(*) FROM enrollment WHERE student_id=:s", s=guarded["other_student"]) == 1


def test_school_follows_exam_prep_class_and_any_taken_key_blocks_new(engine: Engine, guarded: dict) -> None:
    """Exam-prep class '00고1 토10' implies school '00고'. 'x' exists without a school (another
    child as far as the key goes) -> a new 'x'/'00고' is created, the old 'x' is untouched.
    'y'/'00고' exists in no class at all -> still not linked: NEW is refused."""
    room = _sql(engine, "INSERT INTO classroom(name, class_type) VALUES('00고1 토10','EXAM_PREP') RETURNING id").scalar_one()
    _sql(engine, "INSERT INTO classroom_staff_assignment(classroom_id, staff_user_id, assignment_role, valid_from) VALUES(:c,:s,'TEACHER','2026-01-01')", c=room, s=guarded["teacher_id"])
    old_x = _sql(engine, "INSERT INTO student(name) VALUES('x') RETURNING id").scalar_one()
    _sql(engine, "INSERT INTO enrollment(student_id,classroom_id,status,enrolled_at) VALUES(:s,:c,'ACTIVE','2026-01-01')", s=old_x, c=guarded["B"])
    _sql(engine, "INSERT INTO student(name, school_name, parent_email) VALUES('y','00고','guardian-y@example.invalid')")
    teacher = login("teacher")
    content = _file(["x", "출석", "A", "A", 10, 9], ["y", "출석", "A", "A", 10, 9], name="00고1 토10")
    rows = _rows(_post(teacher, "preview", content))
    assert rows["x"]["existing_student_conflict"] is False
    assert rows["y"]["existing_student_conflict"] is True

    before = _state(engine)
    refused = _post(teacher, "confirm", content, decisions=json.dumps({rows["x"]["key"]: "NEW", rows["y"]["key"]: "NEW"}))
    assert refused.json()["code"] == "EXISTING_STUDENT_ELSEWHERE"
    assert "guardian-y" not in refused.text
    assert _state(engine) == before

    ok = _post(teacher, "confirm", content, decisions=json.dumps({rows["x"]["key"]: "NEW", rows["y"]["key"]: "EXCLUDE"}))
    assert ok.status_code == 200, ok.text
    assert ok.json()["new_students"] == 1
    xs = dict(_sql(engine, "SELECT id, school_name FROM student WHERE name='x'").all())
    assert len(xs) == 2 and xs[old_x] is None and "00고" in xs.values()
    assert _count(engine, "SELECT count(*) FROM enrollment WHERE student_id=:s AND classroom_id=:c", s=old_x, c=room) == 0
    assert _count(engine, "SELECT count(*) FROM enrollment e JOIN student s ON s.id=e.student_id WHERE s.name='y'") == 0


def test_student_registered_between_preview_and_confirm_is_not_linked(engine: Engine, guarded: dict) -> None:
    teacher, admin = login("teacher"), login("admin")
    content = _file(["s1", "출석", "A", "A", 12, 8], ["늦은신규", "출석", "A", "A", 12, 8])
    row = _rows(_post(teacher, "preview", content))["늦은신규"]
    assert row["status"] == "UNREGISTERED" and row["existing_student_conflict"] is False
    # Meanwhile an administrator registers a '늦은신규' (no school) in class B.
    created = send(admin, "POST", "/api/students", {"name": "늦은신규", "parent_email": "guardian-late@example.invalid", "classroom_id": guarded["B"], "enrolled_at": "2026-11-01"})
    assert created.status_code == 201
    before = _state(engine)
    refused = _post(teacher, "confirm", content, decisions=json.dumps({row["key"]: "NEW"}))
    assert (refused.status_code, refused.json()["code"]) == (400, "EXISTING_STUDENT_ELSEWHERE")
    assert "guardian-late" not in refused.text
    assert _state(engine) == before


def test_concurrent_insert_of_the_same_key_rolls_back_the_whole_upload(engine: Engine, guarded: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    """If the key is taken after the check (a concurrent request), the unique index refuses the
    insert: 409, nothing saved, still no linking. Simulated by hiding the check's result."""
    monkeypatch.setattr(LessonUploadService, "_taken_student_keys", lambda self, names, school: set())
    teacher = login("teacher")
    content = _file(["s1", "출석", "A", "A", 12, 8], ["other", "출석", "A", "A", 12, 8])
    row = _rows(_post(teacher, "preview", content))["other"]
    before = _state(engine)
    refused = _post(teacher, "confirm", content, decisions=json.dumps({row["key"]: "NEW"}))
    assert (refused.status_code, refused.json()["code"]) == (409, "EXISTING_STUDENT_ELSEWHERE")
    _no_other_class_data(refused.text)
    assert _state(engine) == before


def test_genuinely_new_student_is_still_registered(engine: Engine, guarded: dict) -> None:
    assistant = login("assistant")
    content = _file(["진짜신입", "출석", "A", "A", 12, 8])
    row = _rows(_post(assistant, "preview", content))["진짜신입"]
    assert row["existing_student_conflict"] is False
    students = _count(engine, "SELECT count(*) FROM student")
    done = _post(assistant, "confirm", content, decisions=json.dumps({row["key"]: "NEW"}))
    assert done.status_code == 200 and done.json()["new_students"] == 1
    assert _count(engine, "SELECT count(*) FROM student") == students + 1
    assert _sql(engine, "SELECT school_name FROM student WHERE name='진짜신입'").scalar() is None
    [event] = audit(engine, "ENROLLMENT_CREATED_FROM_UPLOAD")
    assert event.actor_staff_user_id == guarded["assistant_id"]


def test_upload_to_a_class_not_assigned_reveals_no_student_key(engine: Engine, guarded: dict) -> None:
    """Class B is not the teacher's: blocked as before, and its rows are not checked against
    student keys (no 'this name exists' signal for classes the user does not hold)."""
    teacher = login("teacher")
    content = _file(["other", "출석", "A", "A", 12, 8], ["없는학생", "출석", "A", "A", 12, 8], name=CLASS_B_NAME)
    preview = _post(teacher, "preview", content)
    body = preview.json()
    assert body["can_confirm"] is False and any("담당 반이 아닙니다" in b for b in body["blocking"])
    assert all(r["existing_student_conflict"] is False for b in body["blocks"] for r in b["rows"])
    assert GUARDIAN_B not in preview.text


# ------------------------------------------------------------------------------------- SEC-02
def _details_text(events) -> str:
    return json.dumps([e.details for e in events], ensure_ascii=False)


def test_admin_management_changes_are_audited(engine: Engine, world: dict) -> None:
    admin = login("admin")
    admin_id = world["admin_id"]

    # Staff created / renamed / deactivated / reactivated
    staff = send(admin, "POST", "/api/staff", {"email": "audit-new@example.invalid", "display_name": "감사 대상", "password": PASSWORD, "role": "ASSISTANT"})
    assert staff.status_code == 201
    staff_id = staff.json()["id"]
    assert send(admin, "PATCH", f"/api/staff/{staff_id}", {"display_name": "새 이름"}).status_code == 200
    assert send(admin, "PATCH", f"/api/staff/{staff_id}", {"display_name": "새 이름"}).status_code == 200  # no change
    TestClient(app).post("/api/auth/login", json={"email": "audit-new@example.invalid", "password": PASSWORD})
    assert send(admin, "PATCH", f"/api/staff/{staff_id}/status", {"status": "INACTIVE"}).status_code == 200
    assert send(admin, "PATCH", f"/api/staff/{staff_id}/status", {"status": "INACTIVE"}).status_code == 200  # no change
    assert send(admin, "PATCH", f"/api/staff/{staff_id}/status", {"status": "ACTIVE"}).status_code == 200

    # Class registered, assignment given and removed
    room = send(admin, "POST", "/api/classrooms", {"name": "감사반", "class_type": "REGULAR"}).json()["id"]
    assignment = send(admin, "POST", f"/api/classrooms/{room}/assignments", {"staff_user_id": world["teacher2_id"], "assignment_role": "TEACHER", "valid_from": "2026-01-01"})
    assert assignment.status_code == 201
    assignment_id = assignment.json()["id"]
    assert send(admin, "DELETE", f"/api/classrooms/{room}/assignments/{assignment_id}").status_code == 204
    assert _count(engine, "SELECT count(*) FROM classroom_staff_assignment WHERE id=:i", i=assignment_id) == 0

    # Student registered (with enrolment) and a manual enrolment
    student = send(admin, "POST", "/api/students", {"name": "감사학생", "parent_name": "보호자", "parent_email": "guardian-audit@example.invalid", "classroom_id": room, "enrolled_at": "2026-11-01"})
    assert student.status_code == 201
    enrolled = send(admin, "POST", f"/api/classrooms/{room}/enrollments", {"student_id": world["other_student"], "enrolled_at": "2026-11-02"})
    assert enrolled.status_code == 201

    expected = {
        "STAFF_CREATED": ("STAFF_USER", staff_id, {"role": "ASSISTANT", "status": "ACTIVE"}),
        "STAFF_RENAMED": ("STAFF_USER", staff_id, {"changed": ["display_name"]}),
        "CLASSROOM_CREATED": ("CLASSROOM", room, {"name": "감사반", "class_type": "REGULAR"}),
    }
    for event, (target_type, target_id, details) in expected.items():
        [row] = audit(engine, event)  # exactly one: unchanged requests write nothing
        assert (row.actor_staff_user_id, row.target_type, row.target_id, row.details) == (admin_id, target_type, str(target_id), details)
        assert row.request_id is not None and row.created_at is not None

    status_events = audit(engine, "STAFF_STATUS_CHANGED")
    assert [(e.details["before"], e.details["after"]) for e in status_events] == [("ACTIVE", "INACTIVE"), ("INACTIVE", "ACTIVE")]
    assert status_events[0].details["sessions_revoked"] == 1 and status_events[0].target_id == str(staff_id)

    snapshot = {"assignment_id": assignment_id, "classroom_id": room, "staff_user_id": world["teacher2_id"], "assignment_role": "TEACHER", "valid_from": "2026-01-01", "valid_to": None}
    [given] = audit(engine, "ASSIGNMENT_CREATED")
    [removed] = audit(engine, "ASSIGNMENT_REMOVED")
    # The assignment row is gone, but who held which class from when is still on record.
    assert given.details == removed.details == snapshot
    assert (removed.target_type, removed.target_id, removed.actor_staff_user_id) == ("CLASSROOM_STAFF_ASSIGNMENT", str(assignment_id), admin_id)

    [registered] = audit(engine, "STUDENT_CREATED")
    assert registered.target_id == str(student.json()["id"])
    assert registered.details["parent_email_present"] is True and registered.details["school_present"] is False
    enrolments = audit(engine, "ENROLLMENT_CREATED")
    assert [(e.details["source"], e.details["classroom_id"]) for e in enrolments] == [("STUDENT_REGISTRATION", room), ("MANUAL", room)]
    assert enrolments[1].details["student_id"] == world["other_student"] and enrolments[1].target_id == str(enrolled.json()["id"])

    # No personal data or secrets in any of these audit rows.
    events = [e for name in ("STAFF_CREATED", "STAFF_RENAMED", "STAFF_STATUS_CHANGED", "CLASSROOM_CREATED", "ASSIGNMENT_CREATED", "ASSIGNMENT_REMOVED", "STUDENT_CREATED", "ENROLLMENT_CREATED") for e in audit(engine, name)]
    dumped = _details_text(events)
    for secret in ("audit-new@", "감사 대상", "새 이름", PASSWORD, "argon2", "guardian-audit", "보호자", "감사학생", "token", "csrf"):
        assert secret not in dumped


def test_failed_or_unauthorised_changes_leave_no_audit_row(engine: Engine, world: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    admin, teacher = login("admin"), login("teacher")
    room = send(admin, "POST", "/api/classrooms", {"name": "실패반", "class_type": "REGULAR"}).json()["id"]
    assign = {"staff_user_id": world["teacher2_id"], "assignment_role": "TEACHER", "valid_from": "2026-01-01"}
    assignment_id = send(admin, "POST", f"/api/classrooms/{room}/assignments", assign).json()["id"]
    send(admin, "POST", f"/api/classrooms/{room}/enrollments", {"student_id": world["other_student"], "enrolled_at": "2026-11-02"})
    events = ("STAFF_CREATED", "STAFF_RENAMED", "STAFF_STATUS_CHANGED", "CLASSROOM_CREATED", "ASSIGNMENT_CREATED", "ASSIGNMENT_REMOVED", "STUDENT_CREATED", "ENROLLMENT_CREATED")

    def counts() -> dict:
        return {e: len(audit(engine, e)) for e in events}

    before = counts()
    # Business failures (constraint violations): 409 and no audit row.
    assert send(admin, "POST", "/api/classrooms", {"name": "실패반", "class_type": "REGULAR"}).status_code == 409
    assert send(admin, "POST", f"/api/classrooms/{room}/assignments", assign).status_code == 409
    assert send(admin, "POST", f"/api/classrooms/{room}/enrollments", {"student_id": world["other_student"], "enrolled_at": "2026-11-02"}).status_code == 409
    assert send(admin, "POST", "/api/staff", {"email": "teacher@example.invalid", "display_name": "중복", "password": PASSWORD, "role": "TEACHER"}).status_code == 409
    students = _count(engine, "SELECT count(*) FROM student")
    assert send(admin, "POST", "/api/students", {"name": "s1", "classroom_id": room, "enrolled_at": "2026-11-01"}).status_code == 409
    assert _count(engine, "SELECT count(*) FROM student") == students
    # Teachers cannot make any of these changes (server-side, not only hidden in the UI).
    forbidden = [
        ("POST", "/api/staff", {"email": "x@example.invalid", "display_name": "x", "password": PASSWORD, "role": "TEACHER"}),
        ("PATCH", f"/api/staff/{world['assistant_id']}", {"display_name": "x"}),
        ("PATCH", f"/api/staff/{world['assistant_id']}/status", {"status": "INACTIVE"}),
        ("POST", "/api/classrooms", {"name": "몰래반", "class_type": "REGULAR"}),
        ("POST", f"/api/classrooms/{world['A']}/assignments", {**assign, "staff_user_id": world["assistant2_id"], "assignment_role": "ASSISTANT"}),
        ("DELETE", f"/api/classrooms/{room}/assignments/{assignment_id}", None),
        ("POST", f"/api/classrooms/{world['A']}/enrollments", {"student_id": world["other_student"], "enrolled_at": "2026-11-02"}),
        ("POST", "/api/students", {"name": "몰래학생"}),
    ]
    for method, path, payload in forbidden:
        assert send(teacher, method, path, payload).status_code == 403, path
    assert counts() == before
    assert _count(engine, "SELECT count(*) FROM classroom_staff_assignment WHERE id=:i", i=assignment_id) == 1

    # Same transaction: if the audit row cannot be written, the change itself is not kept.
    original = LearningOpsService._audit

    def broken(self, principal, request_id, event, target, details, target_type="CLASSROOM"):
        original(self, principal, request_id, "X" * 80, target, details, target_type)  # > VARCHAR(50)

    monkeypatch.setattr(LearningOpsService, "_audit", broken)
    assert send(admin, "POST", "/api/classrooms", {"name": "원자성반", "class_type": "REGULAR"}).status_code == 500
    assert send(admin, "DELETE", f"/api/classrooms/{room}/assignments/{assignment_id}").status_code == 500
    assert send(admin, "PATCH", f"/api/staff/{world['assistant_id']}/status", {"status": "INACTIVE"}).status_code == 500
    assert _count(engine, "SELECT count(*) FROM classroom WHERE name='원자성반'") == 0
    assert _count(engine, "SELECT count(*) FROM classroom_staff_assignment WHERE id=:i", i=assignment_id) == 1
    assert _sql(engine, "SELECT status FROM staff_user WHERE id=:i", i=world["assistant_id"]).scalar() == "ACTIVE"
    assert counts() == before


def test_assignments_removed_with_a_staff_account_or_class_stay_on_record(engine: Engine, world: dict) -> None:
    """Assignment rows also disappear by ON DELETE CASCADE when an unused staff account or an
    empty class is deleted; the deletion's audit row keeps their snapshot."""
    admin = login("admin")
    staff_id = send(admin, "POST", "/api/staff", {"email": "short@example.invalid", "display_name": "단기", "password": PASSWORD, "role": "TEACHER"}).json()["id"]
    room = send(admin, "POST", "/api/classrooms", {"name": "빈반", "class_type": "REGULAR"}).json()["id"]
    first = send(admin, "POST", f"/api/classrooms/{room}/assignments", {"staff_user_id": staff_id, "assignment_role": "TEACHER", "valid_from": "2026-01-01"}).json()["id"]
    assert send(admin, "DELETE", f"/api/staff/{staff_id}").json()["mode"] == "HARD"
    [deleted] = audit(engine, "STAFF_DELETED")
    assert [a["assignment_id"] for a in deleted.details["assignments_removed"]] == [first]
    assert "short@" not in _details_text([deleted])

    second = send(admin, "POST", f"/api/classrooms/{room}/assignments", {"staff_user_id": world["teacher2_id"], "assignment_role": "TEACHER", "valid_from": "2026-01-01"}).json()["id"]
    assert send(admin, "DELETE", f"/api/classrooms/{room}").status_code == 204
    [gone] = audit(engine, "CLASSROOM_DELETED")
    assert [a["assignment_id"] for a in gone.details["assignments_removed"]] == [second]
    assert len(audit(engine, "ASSIGNMENT_CREATED")) == 2  # creation records survive the cascades
