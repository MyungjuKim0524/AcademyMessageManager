# ruff: noqa: F811  -- pytest fixtures imported from the Phase 7 suite are injected by name
"""Phase 8.1: class progress grid (학습 현황) and single-cell record correction."""

from datetime import date

import pytest
from sqlalchemy import Engine

# Shared fixtures/helpers from the Phase 7 suite (test functions are not imported).
from test_phase7_academics_integration import (  # noqa: F401  (fixtures are used by name)
    audit,
    engine,
    login,
    make_lesson,
    send,
    world,
)

pytestmark = pytest.mark.postgres
PERIOD = {"date_from": "2026-11-01", "date_to": "2026-11-12"}


def _assessment(client, room: int, title: str, day: str, max_score: int, lesson_id=None) -> int:
    payload = {"title": title, "assessment_date": day, "max_score": max_score}
    if lesson_id is not None:
        payload["lesson_id"] = lesson_id
    response = send(client, "POST", f"/api/classrooms/{room}/assessments", payload)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _progress(client, room: int, **period) -> dict:
    response = client.get(f"/api/classrooms/{room}/progress", params=period or PERIOD)
    assert response.status_code == 200, response.text
    return response.json()


def _cell(grid: dict, enrollment_id: int, key: str) -> dict:
    student = next(s for s in grid["students"] if s["enrollment_id"] == enrollment_id)
    return next(c for c in student["cells"] if c["key"] == key)


def test_progress_grid_shows_lessons_scores_and_eligibility(engine: Engine, world: dict) -> None:
    teacher, assistant = login("teacher"), login("assistant")
    first = make_lesson(teacher, world["A"], "2026-11-03", topic="1회차")
    second = make_lesson(teacher, world["A"], "2026-11-10")
    vocab = _assessment(teacher, world["A"], "어휘", "2026-11-03", 10, first["id"])
    mock = _assessment(teacher, world["A"], "모의고사", "2026-11-05", 100)
    saved = send(
        assistant,
        "PUT",
        f"/api/lessons/{first['id']}/attendance",
        {"items": [{"enrollment_id": world["s1"], "status": "PRESENT"}]},
    )
    assert saved.status_code == 200

    grid = _progress(assistant, world["A"])
    keys = [c["key"] for c in grid["columns"]]
    assert keys == [f"lesson:{first['id']}", f"assessment:{mock}", f"lesson:{second['id']}"]
    assert grid["columns"][0]["assessments"][0]["title"] == "어휘"
    assert grid["columns"][0]["topic"] == "1회차"
    listed = {s["enrollment_id"] for s in grid["students"]}
    # WITHDRAWN without an end date is never a roster member; other classes are not listed.
    assert listed == {world["s1"], world["s2"], world["late_joiner"]}
    s1 = _cell(grid, world["s1"], f"lesson:{first['id']}")
    assert (s1["attendance_status"], s1["result_version"], s1["scores"]) == ("PRESENT", 1, [])
    assert _cell(grid, world["s2"], f"lesson:{first['id']}")["attendance_status"] is None
    assert not _cell(grid, world["late_joiner"], f"lesson:{first['id']}")["eligible"]
    assert _cell(grid, world["late_joiner"], f"lesson:{second['id']}")["eligible"]
    assert vocab

    assert (
        login("teacher2").get(f"/api/classrooms/{world['A']}/progress", params=PERIOD).status_code
        == 403
    )
    bad = {"date_from": "2026-11-12", "date_to": "2026-11-01"}
    assert assistant.get(f"/api/classrooms/{world['A']}/progress", params=bad).status_code == 400
    long = {"date_from": "2026-01-01", "date_to": "2026-11-12"}
    response = assistant.get(f"/api/classrooms/{world['A']}/progress", params=long)
    assert response.status_code == 400 and response.json()["code"] == "DATE_RANGE_TOO_LONG"


def test_assistant_starts_todays_lesson_idempotently_and_records_attendance(
    engine: Engine, world: dict
) -> None:
    teacher, assistant = login("teacher"), login("assistant")
    start = f"/api/classrooms/{world['A']}/lessons/today"
    first = send(assistant, "POST", start)
    assert first.status_code == 200, first.text
    lesson = first.json()["lesson"]
    assert first.json()["created"] is True
    assert (lesson["lesson_date"], lesson["session_no"]) == (date.today().isoformat(), 1)
    again = send(teacher, "POST", start)
    assert again.json() == {"lesson": again.json()["lesson"], "created": False}
    assert again.json()["lesson"]["id"] == lesson["id"]
    [created] = audit(engine, "LESSON_CREATED")
    assert created.details["source"] == "ATTENDANCE_START"

    roll = {"items": [{"enrollment_id": world["s1"], "status": "LATE"}]}
    assert (
        send(assistant, "PUT", f"/api/lessons/{lesson['id']}/attendance", roll).status_code == 200
    )
    # Lesson editing (topic, cancelling, ...) stays with teachers and administrators.
    patch = {"version": lesson["version"], "topic": "x"}
    assert send(assistant, "PATCH", f"/api/lessons/{lesson['id']}", patch).status_code == 403
    assert send(login("teacher2"), "POST", start).status_code == 403
    assert assistant.post(start).status_code == 403  # CSRF token required


def test_start_today_refuses_a_cancelled_lesson(engine: Engine, world: dict) -> None:
    teacher = login("teacher")
    lesson = make_lesson(teacher, world["A"], date.today().isoformat())
    cancel = {"version": lesson["version"], "status": "CANCELLED"}
    assert send(teacher, "PATCH", f"/api/lessons/{lesson['id']}", cancel).status_code == 200
    refused = send(login("assistant"), "POST", f"/api/classrooms/{world['A']}/lessons/today")
    assert (refused.status_code, refused.json()["code"]) == (409, "LESSON_CANCELLED")


def test_one_cell_correction_is_atomic_versioned_and_role_checked(
    engine: Engine, world: dict
) -> None:
    teacher, assistant = login("teacher"), login("assistant")
    lesson = make_lesson(teacher, world["A"], "2026-11-03")
    vocab = _assessment(teacher, world["A"], "어휘", "2026-11-03", 10, lesson["id"])
    mock = _assessment(teacher, world["A"], "모의고사", "2026-11-05", 100)
    path = f"/api/lessons/{lesson['id']}/records/{world['s1']}"

    created = send(assistant, "PUT", path, {"attendance_status": "LATE"})
    assert created.status_code == 200 and created.json() == {"changed": 1}
    score = {"assessment_id": vocab, "result_status": "SCORED", "score": 8}

    # Teacher fixes attendance, grades and the score in one request.
    fixed = send(
        teacher,
        "PUT",
        path,
        {
            "result_version": 1,
            "attendance_status": "PRESENT",
            "prework_grade": "A",
            "weekly_grade": "B",
            "scores": [score],
        },
    )
    assert fixed.status_code == 200, fixed.text
    cell = _cell(_progress(teacher, world["A"]), world["s1"], f"lesson:{lesson['id']}")
    assert (cell["attendance_status"], cell["prework_grade"], cell["weekly_grade"]) == (
        "PRESENT",
        "A",
        "B",
    )
    assert cell["result_version"] == 2
    assert [(s["assessment_id"], s["score"], s["version"]) for s in cell["scores"]] == [
        (vocab, 8.0, 1)
    ]

    # Stale versions are refused and nothing is written.
    stale = send(teacher, "PUT", path, {"result_version": 1, "weekly_grade": "C"})
    assert stale.status_code == 409
    stale_score = {"assessment_id": vocab, "result_status": "NOT_TAKEN", "version": None}
    assert send(teacher, "PUT", path, {"scores": [stale_score]}).status_code == 409

    # An assistant clears one grade and marks the test as not taken: since 2026-11-19 assistants
    # may correct assignment grades and scores too (they also save them via the workbook upload).
    cleared = send(
        assistant,
        "PUT",
        path,
        {
            "result_version": 2,
            "prework_grade": None,
            "scores": [{"assessment_id": vocab, "result_status": "NOT_TAKEN", "version": 1}],
        },
    )
    assert cleared.status_code == 200, cleared.text
    cell = _cell(_progress(teacher, world["A"]), world["s1"], f"lesson:{lesson['id']}")
    assert (cell["prework_grade"], cell["weekly_grade"]) == (None, "B")
    assert cell["scores"][0]["result_status"] == "NOT_TAKEN" and cell["scores"][0]["score"] is None

    # Validation: over the max, an unlinked assessment, grades before any attendance.
    other = f"/api/lessons/{lesson['id']}/records/{world['s2']}"
    too_high = {"assessment_id": vocab, "result_status": "SCORED", "score": 11}
    assert send(teacher, "PUT", other, {"scores": [too_high]}).status_code == 400
    unlinked = {"assessment_id": mock, "result_status": "SCORED", "score": 50}
    assert send(teacher, "PUT", other, {"scores": [unlinked]}).status_code == 400
    response = send(teacher, "PUT", other, {"weekly_grade": "A"})
    assert response.status_code == 400 and response.json()["code"] == "ATTENDANCE_REQUIRED"
    both = send(teacher, "PUT", other, {"attendance_status": "ABSENT", "weekly_grade": "A"})
    assert both.status_code == 200
    assert send(teacher, "PUT", other, {}).status_code == 400
    assert (
        send(teacher, "PUT", other, {"result_version": 1, "attendance_status": None}).status_code
        == 400
    )
    late = f"/api/lessons/{lesson['id']}/records/{world['late_joiner']}"
    assert send(teacher, "PUT", late, {"attendance_status": "PRESENT"}).status_code == 400
    outside = f"/api/lessons/{lesson['id']}/records/{world['other']}"
    assert send(teacher, "PUT", outside, {"attendance_status": "PRESENT"}).status_code == 404
    outsider = {"result_version": 3, "attendance_status": "PRESENT"}
    assert send(login("teacher2"), "PUT", path, outsider).status_code == 403

    grades = audit(engine, "ASSIGNMENT_GRADES_UPDATED")
    assert [g.details["after"] for g in grades] == [
        {"prework": "A", "weekly": "B"},
        {"prework": None, "weekly": "B"},
        {"prework": None, "weekly": "A"},
    ]
    assert [a.details["after"]["status"] for a in audit(engine, "ATTENDANCE_UPDATED")] == [
        "PRESENT"
    ]
    records = teacher.get(
        f"/api/classrooms/{world['A']}/students/{world['s1_student']}/records"
    ).json()
    assert (records["lessons"][0]["prework_grade"], records["lessons"][0]["weekly_grade"]) == (
        None,
        "B",
    )
