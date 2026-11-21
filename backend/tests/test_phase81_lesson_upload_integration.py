# ruff: noqa: F811, E501  -- SQL kept on one line; pytest fixtures imported from the Phase 7 suite are injected by name
"""Phase 8.1: academy workbook upload over the real API and PostgreSQL (fictional data)."""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from test_phase7_academics_integration import (  # noqa: F401
    audit,
    engine,
    login,
    world,
)
from test_phase81_workbook_parser import HEADER, workbook

from app.main import app

pytestmark = pytest.mark.postgres
DAY = "2026-11-03"


def _sql(engine: Engine, sql: str, **params):
    with engine.begin() as connection:
        return connection.execute(text(sql), params)


def _count(engine: Engine, sql: str, **params) -> int:
    return _sql(engine, sql, **params).scalar()


@pytest.fixture()
def setup(engine: Engine, world: dict) -> dict:
    """Class A becomes '중3 토10'; p1 is a paused student; s1 has a parent e-mail."""
    _sql(engine, "UPDATE classroom SET name='중3 토10' WHERE id=:a", a=world["A"])
    _sql(
        engine,
        "UPDATE classroom SET name='00고2 토10', class_type='EXAM_PREP' WHERE id=:b",
        b=world["B"],
    )
    _sql(
        engine,
        "UPDATE student SET parent_email='parent1@example.invalid' WHERE id=:s",
        s=world["s1_student"],
    )
    student = _sql(engine, "INSERT INTO student(name) VALUES('p1') RETURNING id").scalar_one()
    paused = _sql(
        engine,
        "INSERT INTO enrollment(student_id,classroom_id,status,enrolled_at) "
        "VALUES(:s,:c,'ACTIVE','2026-01-01') RETURNING id",
        s=student,
        c=world["A"],
    ).scalar_one()
    _sql(
        engine,
        "INSERT INTO enrollment_pause(enrollment_id,paused_from) VALUES(:e,'2026-10-01')",
        e=paused,
    )
    _sql(engine, "UPDATE enrollment SET status='PAUSED' WHERE id=:e", e=paused)
    # The shared fixture truncates staff_user with CASCADE, which also empties the templates
    # seeded by migration 009, so the per-class-type defaults are recreated here.
    _sql(
        engine,
        "INSERT INTO notification_template(name, body, default_for_class_type) VALUES "
        "('정규반 기본 안내', :regular, 'REGULAR'), ('내신 대비 기본 안내', :exam, 'EXAM_PREP')",
        regular="안녕하세요.\n{학생명} 학생의 {수업일자} 정규 수업 안내입니다.\n출결: {출결}\n"
        "{예습메시지}\n{주간메시지}\n{성적요약}\n{보강메시지}",
        exam="안녕하세요.\n{학생명} 학생의 {수업일자} 내신 대비 수업 안내입니다.\n출결: {출결}\n{성적요약}",
    )
    return {**world, "p1": paused}


def _file(*rows, name="중3 토10") -> bytes:
    return workbook(("10시", [[name, *HEADER], *rows]))


ROWS = (
    ["s1", "출석", "A", "b", 12, 8],
    ["s2", "출석", "B", "B", 10, 9],
    ["신입생", "결석", None, None, None, None],
    ["p1", "출석", "C", "A", 15, 10],
    ["오타학생", "출석", "A", "A", 1, 1],
)


def _post(client: TestClient, path: str, content: bytes, csrf: bool = True, **form):
    headers = {"X-CSRF-Token": client.cookies.get("academy_csrf")} if csrf else {}
    return client.post(
        f"/api/lesson-uploads/{path}",
        files={
            "file": (
                "주간.xlsx",
                content,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        data={"lesson_date": DAY, **form},
        headers=headers,
    )


def test_preview_classifies_rows_and_writes_nothing(engine: Engine, setup: dict) -> None:
    assistant = login("assistant")
    before = _count(engine, "SELECT count(*) FROM lesson") + _count(
        engine, "SELECT count(*) FROM audit_log"
    )
    preview = _post(assistant, "preview", _file(*ROWS))
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["can_confirm"] is True and body["blocking"] == []
    [block] = body["blocks"]
    assert (block["class_type"], block["classroom_id"]) == ("REGULAR", setup["A"])
    status = {r["name"]: (r["status"], r["returning_available"]) for r in block["rows"]}
    assert status == {
        "s1": ("MATCHED", False),
        "s2": ("MATCHED", False),
        "신입생": ("UNREGISTERED", False),
        "p1": ("UNREGISTERED", True),
        "오타학생": ("UNREGISTERED", False),
    }
    after = _count(engine, "SELECT count(*) FROM lesson") + _count(
        engine, "SELECT count(*) FROM audit_log"
    )
    assert after == before  # preview is read-only


def test_confirm_saves_data_resolves_students_and_creates_drafts(
    engine: Engine, setup: dict
) -> None:
    teacher, assistant = login("teacher"), login("assistant")
    # s2's attendance was already entered in the app as LATE for this lesson.
    lesson = teacher.post(
        f"/api/classrooms/{setup['A']}/lessons",
        json={"lesson_date": DAY},
        headers={"X-CSRF-Token": teacher.cookies.get("academy_csrf")},
    ).json()
    teacher.put(
        f"/api/lessons/{lesson['id']}/attendance",
        json={"items": [{"enrollment_id": setup["s2"], "status": "LATE"}]},
        headers={"X-CSRF-Token": teacher.cookies.get("academy_csrf")},
    )
    content = _file(*ROWS)
    rows = {r["name"]: r for r in _post(assistant, "preview", content).json()["blocks"][0]["rows"]}
    assert rows["s2"]["attendance_mismatch"] is True and rows["s2"]["app_attendance"] == "LATE"

    assert _post(assistant, "confirm", content, csrf=False).status_code == 403
    missing = _post(assistant, "confirm", content)
    assert (missing.status_code, missing.json()["code"]) == (400, "DECISION_REQUIRED")
    wrong = {
        rows["p1"]["key"]: "NEW",
        rows["신입생"]["key"]: "NEW",
        rows["오타학생"]["key"]: "EXCLUDE",
    }
    rejected = _post(assistant, "confirm", content, decisions=json.dumps(wrong))
    assert rejected.json()["code"] == "NOT_A_NEW_STUDENT"
    assert (
        _count(engine, "SELECT count(*) FROM lesson_result WHERE enrollment_id=:e", e=setup["s1"])
        == 0
    )  # rolled back

    decisions = {
        rows["신입생"]["key"]: "NEW",
        rows["p1"]["key"]: "RETURNING",
        rows["오타학생"]["key"]: "EXCLUDE",
    }
    confirmed = _post(assistant, "confirm", content, decisions=json.dumps(decisions))
    assert confirmed.status_code == 200, confirmed.text
    result = confirmed.json()
    assert (
        result["saved_rows"],
        result["new_students"],
        result["returned_students"],
        result["excluded_rows"],
    ) == (4, 1, 1, 1)
    assert len(result["attendance_mismatches"]) == 1
    [drafts] = result["drafts"]
    assert drafts["created"] == 1  # s1 only: s2 has a mismatch, others have no parent e-mail
    assert any("보호자 이메일" in note for note in drafts["skipped"])

    # Stored data
    att = dict(
        _sql(
            engine,
            "SELECT enrollment_id, attendance_status FROM lesson_result WHERE lesson_id=:l",
            l=lesson["id"],
        ).all()
    )
    assert att[setup["s1"]] == "PRESENT" and att[setup["s2"]] == "LATE"  # app value kept
    grades = _sql(
        engine,
        "SELECT prework_grade, weekly_assignment_grade FROM lesson_result WHERE lesson_id=:l AND enrollment_id=:e",
        l=lesson["id"],
        e=setup["s1"],
    ).one()
    assert tuple(grades) == ("A", "B")
    assessments = dict(
        _sql(
            engine,
            "SELECT title, max_score::int FROM assessment WHERE lesson_id=:l",
            l=lesson["id"],
        ).all()
    )
    assert assessments == {"문법, 문학, 독서": 15, "어휘": 10}
    s1_scores = dict(
        _sql(
            engine,
            "SELECT a.title, r.score::int FROM assessment_result r JOIN assessment a ON a.id=r.assessment_id WHERE r.enrollment_id=:e",
            e=setup["s1"],
        ).all()
    )
    assert s1_scores == {"문법, 문학, 독서": 12, "어휘": 8}
    new_id = _sql(
        engine,
        "SELECT e.id FROM enrollment e JOIN student s ON s.id=e.student_id WHERE s.name='신입생'",
    ).scalar()
    assert {
        r
        for (r,) in _sql(
            engine, "SELECT result_status FROM assessment_result WHERE enrollment_id=:e", e=new_id
        )
    } == {"NOT_TAKEN"}
    assert (
        _sql(engine, "SELECT status FROM enrollment WHERE id=:e", e=setup["p1"]).scalar()
        == "ACTIVE"
    )
    assert (
        str(
            _sql(
                engine,
                "SELECT resumed_on FROM enrollment_pause WHERE enrollment_id=:e",
                e=setup["p1"],
            ).scalar()
        )
        == DAY
    )
    assert (
        _count(engine, "SELECT count(*) FROM student WHERE name='오타학생'") == 0
    )  # excluded: nothing stored

    body = _sql(
        engine, "SELECT body FROM parent_notification WHERE enrollment_id=:e", e=setup["s1"]
    ).scalar()
    assert "출결: 출석" in body and "문법, 문학, 독서 12/15, 어휘 8/10" in body
    assert "정규 수업" in body  # regular-class default template
    [enrolled] = audit(engine, "ENROLLMENT_CREATED_FROM_UPLOAD")
    # A regular class ('중3 토10') names no school, so the new student's school stays empty.
    assert enrolled.details["school_assigned"] is False
    assert _sql(engine, "SELECT school_name FROM student WHERE name='신입생'").scalar() is None

    # Re-uploading the same workbook updates in place: no duplicates.
    rows = {r["name"]: r for r in _post(assistant, "preview", content).json()["blocks"][0]["rows"]}
    assert rows["신입생"]["status"] == "MATCHED" and rows["p1"]["status"] == "MATCHED"
    again = _post(
        assistant, "confirm", content, decisions=json.dumps({rows["오타학생"]["key"]: "EXCLUDE"})
    )
    assert again.status_code == 200, again.text
    assert again.json()["drafts"][0]["created"] == 0
    assert _count(engine, "SELECT count(*) FROM assessment WHERE lesson_id=:l", l=lesson["id"]) == 2
    assert _count(engine, "SELECT count(*) FROM lesson WHERE classroom_id=:c", c=setup["A"]) == 1
    assert _count(engine, "SELECT count(*) FROM parent_notification") == 1


def test_reupload_lists_app_values_it_replaces_and_audits_them(engine: Engine, setup: dict) -> None:
    """2026-11-20 decision: the workbook stays the source of scores and homework grades, but a
    re-upload must show which values corrected in the app it will replace, and record them."""
    assistant = login("assistant")
    first = _file(["s1", "출석", "A", "B", 12, 8], ["s2", "결석", None, None, None, None])
    assert _post(assistant, "confirm", first).status_code == 200
    # Corrections made in the app afterwards: s1 어휘 8 → 9 and 예습 A → C; s2 (absent) gets a
    # make-up score 5 for 어휘 that the first upload had stored as NOT_TAKEN.
    _sql(engine, "UPDATE assessment_result r SET score = 9 FROM assessment a WHERE a.id = r.assessment_id AND a.title = '어휘' AND r.enrollment_id = :e", e=setup["s1"])
    _sql(engine, "UPDATE lesson_result SET prework_grade = 'C' WHERE enrollment_id = :e", e=setup["s1"])
    _sql(engine, "UPDATE assessment_result r SET result_status = 'SCORED', score = 5 FROM assessment a WHERE a.id = r.assessment_id AND a.title = '어휘' AND r.enrollment_id = :e", e=setup["s2"])

    preview = _post(assistant, "preview", first).json()
    rows = {r["name"]: r for r in preview["blocks"][0]["rows"]}
    assert rows["s1"]["app_changes"] == [
        {"field": "prework", "label": "예습 과제", "app": "C", "upload": "A"},
        {"field": "score", "label": "어휘", "app": "9", "upload": "8"},
    ]
    # A blank cell of an absent student becomes 미응시 — that replaces the make-up score too.
    assert rows["s2"]["app_changes"] == [{"field": "score", "label": "어휘", "app": "5", "upload": "미응시"}]
    assert preview["blocks"][0]["max_score_changes"] == [] and preview["can_confirm"] is True

    assert _post(assistant, "confirm", first).status_code == 200  # the rule itself is unchanged
    s1_vocab = _sql(engine, "SELECT r.score::int FROM assessment_result r JOIN assessment a ON a.id = r.assessment_id WHERE a.title = '어휘' AND r.enrollment_id = :e", e=setup["s1"]).scalar()
    assert s1_vocab == 8
    details = {
        row.details["enrollment_id"]: row.details["changed"]
        for row in _sql(engine, "SELECT details FROM audit_log WHERE event_type = 'UPLOAD_ROW_APPLIED' ORDER BY id DESC LIMIT 2")
    }
    assert details[setup["s1"]] == [
        {"field": "prework", "label": "예습 과제", "before": "C", "after": "A"},
        {"field": "score", "label": "어휘", "before": "9", "after": "8"},
    ]
    assert details[setup["s2"]] == [{"field": "score", "label": "어휘", "before": "5", "after": "미응시"}]

    # A header that lowers 어휘's maximum below the stored 9 → blocked in the preview, with the reason.
    def header(total: int) -> bytes:
        return workbook(("10시", [["중3 토10", "출결", "예습 과제", "주간 과제", "문법, 문학, 독서 (15)", f"어휘 ({total})"], ["s1", "출석", "A", "B", 12, 4]]))

    _sql(engine, "UPDATE assessment_result r SET score = 9 FROM assessment a WHERE a.id = r.assessment_id AND a.title = '어휘' AND r.enrollment_id = :e", e=setup["s1"])
    lowered = _post(assistant, "preview", header(5)).json()
    assert lowered["can_confirm"] is False
    assert lowered["blocks"][0]["max_score_changes"] == [{"title": "어휘", "app": "10", "upload": "5"}]
    assert any("이미 입력된 점수(9)보다 낮습니다" in issue for issue in lowered["blocking"])
    assert _post(assistant, "confirm", header(5)).json()["code"] == "UPLOAD_HAS_ERRORS"
    raised = _post(assistant, "preview", header(12)).json()  # raising it is shown, not blocked
    assert raised["can_confirm"] is True
    assert raised["blocks"][0]["max_score_changes"] == [{"title": "어휘", "app": "10", "upload": "12"}]


def test_time_slot_uploads_save_only_the_chosen_sheets_and_skip_unchanged_rows(
    engine: Engine, setup: dict
) -> None:
    """Decision 2026-11-20: the same day's workbook is uploaded after each time slot (or class by
    class). Only the chosen sheets are checked and saved; rows equal to the app write and audit
    nothing, so splitting the day into uploads leaves the same data and no extra records."""
    admin = login("admin")
    exam_header = ["00고2 토10", "출결", "예습 과제", "주간 과제", "문법, 문학, 독서 (20)", "어휘 (10)"]
    ten = [["중3 토10", *HEADER], ["s1", "출석", "A", "B", 12, 8], ["s2", "결석", None, None, None, None]]
    six = [["중1 토6", *HEADER]]  # not registered: an error in a sheet nobody chose yet

    def book(two_rows: list) -> bytes:
        return workbook(("10시", ten), ("2시", [exam_header, *two_rows]), ("6시", six))

    at_11 = book([])  # the 2시 class has not been held yet
    at_16 = book([["other", "지각", "B", "A", 17, 9]])

    def audits(event: str) -> int:
        return _count(engine, "SELECT count(*) FROM audit_log WHERE event_type = :e", e=event)

    listed = _post(admin, "sheets", at_11)
    assert listed.status_code == 200, listed.text
    assert listed.json()["sheets"] == [
        {"name": "10시", "class_names": ["중3 토10"], "student_rows": 2},
        {"name": "2시", "class_names": ["00고2 토10"], "student_rows": 0},
        {"name": "6시", "class_names": ["중1 토6"], "student_rows": 0},
    ]
    # Without a choice the whole file is checked (as before): the 6시 error blocks everything.
    assert _post(admin, "preview", at_11).json()["can_confirm"] is False
    chosen = _post(admin, "preview", at_11, sheets=["10시"]).json()
    assert chosen["can_confirm"] is True and chosen["blocking"] == []
    assert [b["sheet"] for b in chosen["blocks"]] == ["10시"]
    assert chosen["selected_sheets"] == ["10시"] and len(chosen["sheets"]) == 3
    six_only = _post(admin, "preview", at_11, sheets=["6시"]).json()
    assert six_only["can_confirm"] is False and any("6시" in b for b in six_only["blocking"])
    unknown = _post(admin, "preview", at_11, sheets=["9시"])
    assert (unknown.status_code, unknown.json()["code"]) == (400, "UNKNOWN_SHEET")

    # 11시: 10시 only.
    first = _post(admin, "confirm", at_11, sheets=["10시"]).json()
    assert (first["saved_rows"], first["unchanged_rows"]) == (2, 0)
    assert (audits("UPLOAD_ROW_APPLIED"), audits("LESSON_UPLOAD_APPLIED")) == (2, 1)
    # 16시: same file, 2시 now filled; only 2시 is chosen, 10시 is not touched again.
    second = _post(admin, "confirm", at_16, sheets=["2시"]).json()
    assert (second["saved_rows"], second["unchanged_rows"]) == (1, 0)
    assert (audits("UPLOAD_ROW_APPLIED"), audits("LESSON_UPLOAD_APPLIED")) == (3, 2)

    # Someone re-uploads both slots (class-by-class habit): nothing differs → nothing written.
    again = _post(admin, "preview", at_16, sheets=["10시", "2시"]).json()
    assert all(r["unchanged"] for b in again["blocks"] for r in b["rows"])
    versions = _sql(engine, "SELECT id, version FROM lesson_result ORDER BY id").all()
    quiet = _post(admin, "confirm", at_16, sheets=["10시", "2시"]).json()
    assert (quiet["saved_rows"], quiet["unchanged_rows"]) == (0, 3)
    assert (audits("UPLOAD_ROW_APPLIED"), audits("LESSON_UPLOAD_APPLIED")) == (3, 2)
    assert _sql(engine, "SELECT id, version FROM lesson_result ORDER BY id").all() == versions
    assert _count(engine, "SELECT count(*) FROM lesson") == 2
    assert _count(engine, "SELECT count(*) FROM assessment") == 4

    # An app correction makes exactly that row differ: it is shown, saved and audited alone.
    _sql(engine, "UPDATE assessment_result r SET score = 9 FROM assessment a WHERE a.id = r.assessment_id AND a.title = '어휘' AND r.enrollment_id = :e", e=setup["s1"])
    rows = {r["name"]: r for r in _post(admin, "preview", at_16, sheets=["10시"]).json()["blocks"][0]["rows"]}
    assert (rows["s1"]["unchanged"], rows["s2"]["unchanged"]) == (False, True)
    assert rows["s1"]["app_changes"] == [{"field": "score", "label": "어휘", "app": "9", "upload": "8"}]
    fixed = _post(admin, "confirm", at_16, sheets=["10시"]).json()
    assert (fixed["saved_rows"], fixed["unchanged_rows"]) == (1, 1)
    assert (audits("UPLOAD_ROW_APPLIED"), audits("LESSON_UPLOAD_APPLIED")) == (4, 3)


def test_blocking_errors_and_class_access(engine: Engine, setup: dict) -> None:
    teacher, admin = login("teacher"), login("admin")
    other_class = workbook(("10시", [["00고2 토10", *HEADER], ["other", "출석", "A", "A", 1, 1]]))
    preview = _post(teacher, "preview", other_class).json()
    assert (
        preview["can_confirm"] is False and "담당 반이 아닙니다" in preview["blocks"][0]["issues"]
    )
    assert _post(teacher, "confirm", other_class).json()["code"] == "UPLOAD_HAS_ERRORS"
    assert _post(admin, "preview", other_class).json()["blocks"][0]["issues"] == []

    typo = _file(["s1", "출석", "A", "A", 1, 1], name="002 토10")
    assert _post(admin, "preview", typo).json()["can_confirm"] is False
    unknown = _file(["s1", "출석", "A", "A", 1, 1], name="중1 토10")
    assert (
        "프로그램에 등록되지 않은 반입니다 (관리자가 먼저 반을 등록해야 합니다)"
        in _post(admin, "preview", unknown).json()["blocks"][0]["issues"]
    )
    future = _post(admin, "preview", _file(*ROWS), lesson_date="2099-01-01")
    assert future.status_code == 400
    assert TestClient(app).post("/api/lesson-uploads/preview").status_code == 401
    assert _count(engine, "SELECT count(*) FROM lesson") == 0


def test_admin_designates_default_templates_per_class_type(engine: Engine, setup: dict) -> None:
    admin, teacher = login("admin"), login("teacher")
    csrf = {"X-CSRF-Token": admin.cookies.get("academy_csrf")}
    templates = {t["name"]: t for t in admin.get("/api/notification-templates").json()}
    regular = templates["정규반 기본 안내"]
    assert regular["default_for_class_type"] == "REGULAR"
    created = admin.post(
        "/api/notification-templates",
        json={"name": "새 정규 안내", "body": "{학생명} {출결}"},
        headers=csrf,
    ).json()

    def patch(tid, body):
        return admin.patch(f"/api/notification-templates/{tid}", json=body, headers=csrf)

    moved = patch(
        created["id"], {"version": created["version"], "default_for_class_type": "REGULAR"}
    )
    assert moved.status_code == 200 and moved.json()["default_for_class_type"] == "REGULAR"
    by_name = {t["name"]: t for t in admin.get("/api/notification-templates").json()}
    assert (
        by_name["정규반 기본 안내"]["default_for_class_type"] is None
    )  # previous default released
    assert (
        teacher.patch(
            f"/api/notification-templates/{created['id']}",
            json={"version": 2, "default_for_class_type": "NONE"},
            headers={"X-CSRF-Token": teacher.cookies.get("academy_csrf")},
        ).status_code
        == 403
    )
    cleared = patch(
        created["id"], {"version": moved.json()["version"], "default_for_class_type": "NONE"}
    )
    assert cleared.json()["default_for_class_type"] is None
    off = patch(created["id"], {"version": cleared.json()["version"], "is_active": False}).json()
    refused = patch(created["id"], {"version": off["version"], "default_for_class_type": "REGULAR"})
    assert refused.json()["code"] == "TEMPLATE_INACTIVE"
    exam = by_name["내신 대비 기본 안내"]
    deactivated = patch(exam["id"], {"version": exam["version"], "is_active": False}).json()
    assert deactivated["default_for_class_type"] is None  # inactive templates cannot stay default
