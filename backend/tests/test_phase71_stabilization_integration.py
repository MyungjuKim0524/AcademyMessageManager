# ruff: noqa: F811  -- pytest fixtures imported from the Phase 7 suite are injected by name
"""Phase 7.1: same-day sessions, dated pauses (휴원) and EXCUSED attendance on real PostgreSQL."""

from datetime import date, timedelta

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

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
TODAY = date.today()


def _sql(engine: Engine, sql: str, **params):
    with engine.begin() as connection:
        return connection.execute(text(sql), params)


def _pauses(engine: Engine, enrollment_id: int):
    return _sql(
        engine,
        "SELECT paused_from, resumed_on, source FROM enrollment_pause "
        "WHERE enrollment_id=:e ORDER BY paused_from",
        e=enrollment_id,
    ).all()


def _roster_ids(client, lesson_id: int) -> set[int]:
    roster = client.get(f"/api/lessons/{lesson_id}/attendance").json()
    return {row["enrollment_id"] for row in roster["items"] if row["eligible"]}


# ------------------------------------------------------------ 1. sessions
def test_same_day_sessions_are_distinct_lessons(engine: Engine, world: dict) -> None:
    teacher = login("teacher")
    room = world["A"]
    first = make_lesson(teacher, room, "2026-11-03")
    second = make_lesson(teacher, room, "2026-11-03", session_no=2, topic="보충")
    assert (first["session_no"], second["session_no"]) == (1, 2)

    duplicate = send(
        teacher,
        "POST",
        f"/api/classrooms/{room}/lessons",
        {"lesson_date": "2026-11-03", "session_no": 2},
    )
    assert (duplicate.status_code, duplicate.json()["code"]) == (409, "LESSON_ALREADY_EXISTS")
    for bad in (0, 10):
        assert (
            send(
                teacher,
                "POST",
                f"/api/classrooms/{room}/lessons",
                {"lesson_date": "2026-11-04", "session_no": bad},
            ).status_code
            == 400
        )
    # exam_round lessons are numbered independently from regular ones.
    assert make_lesson(teacher, room, "2026-11-03", exam_round="3회차")["session_no"] == 1

    listed = teacher.get(f"/api/classrooms/{room}/lessons").json()["items"]
    same_day = [
        (row["session_no"], row["exam_round"])
        for row in listed
        if row["lesson_date"] == "2026-11-03"
    ]
    # Ordered by date, then session (desc), then newest first.
    assert same_day == [(2, None), (1, "3회차"), (1, None)]

    # Each session keeps its own attendance.
    item = {"items": [{"enrollment_id": world["s1"], "status": "PRESENT"}]}
    assert send(teacher, "PUT", f"/api/lessons/{first['id']}/attendance", item).status_code == 200
    assert teacher.get(f"/api/lessons/{second['id']}/attendance").json()["summary"]["recorded"] == 0
    moved = send(teacher, "PATCH", f"/api/lessons/{first['id']}", {"version": 1, "session_no": 3})
    assert (moved.status_code, moved.json()["code"]) == (409, "LESSON_HAS_RECORDS")
    assert (
        send(
            teacher, "PATCH", f"/api/lessons/{second['id']}", {"version": 1, "session_no": 1}
        ).status_code
        == 409
    )
    assert (
        send(
            teacher, "PATCH", f"/api/lessons/{second['id']}", {"version": 1, "session_no": 4}
        ).json()["session_no"]
        == 4
    )


def test_session_constraints_and_java_style_lookup(engine: Engine, world: dict) -> None:
    room = world["A"]
    # Java inserts only (classroom_id, lesson_date, exam_round): it always gets session 1.
    java_id = _sql(
        engine,
        "INSERT INTO lesson(classroom_id,lesson_date,exam_round) "
        "VALUES(:c,'2026-11-02',NULL) RETURNING id",
        c=room,
    ).scalar_one()
    _sql(
        engine,
        "INSERT INTO lesson(classroom_id,lesson_date,exam_round,session_no,status) "
        "VALUES(:c,'2026-11-02',NULL,2,'SCHEDULED')",
        c=room,
    )
    with pytest.raises(IntegrityError):  # second Java-style insert collides with session 1
        _sql(
            engine,
            "INSERT INTO lesson(classroom_id,lesson_date,exam_round) VALUES(:c,'2026-11-02',NULL)",
            c=room,
        )
    with pytest.raises(IntegrityError):
        _sql(
            engine,
            "INSERT INTO lesson(classroom_id,lesson_date,session_no) VALUES(:c,'2026-11-09',10)",
            c=room,
        )
    # The lookup the Java import now uses is deterministic even with two sessions that day.
    found = (
        _sql(
            engine,
            "SELECT id FROM lesson WHERE classroom_id=:c AND lesson_date='2026-11-02' "
            "AND exam_round IS NOT DISTINCT FROM NULL AND session_no=1",
            c=room,
        )
        .scalars()
        .all()
    )
    assert found == [java_id]


# ------------------------------------------------------------- 3. EXCUSED
def test_excused_is_recorded_and_distinct_from_absent(engine: Engine, world: dict) -> None:
    teacher, assistant = login("teacher"), login("assistant")
    lesson = make_lesson(teacher, world["A"])
    saved = send(
        assistant,
        "PUT",
        f"/api/lessons/{lesson['id']}/attendance",
        {
            "items": [
                {"enrollment_id": world["s1"], "status": "EXCUSED", "memo": "병결 확인서"},
                {"enrollment_id": world["s2"], "status": "ABSENT"},
            ]
        },
    )
    assert saved.status_code == 200, saved.text
    summary = saved.json()["summary"]
    assert (summary["excused"], summary["absent"], summary["unrecorded"]) == (1, 1, 0)
    records = teacher.get(
        f"/api/classrooms/{world['A']}/students/{world['s1_student']}/records"
    ).json()
    assert records["lessons"][0]["attendance_status"] == "EXCUSED"
    # The Java makeup list keeps selecting only ABSENT rows.
    absent = _sql(
        engine, "SELECT count(*) FROM lesson_result WHERE attendance_status = 'ABSENT'"
    ).scalar()
    assert absent == 1
    changed = send(
        teacher,
        "PUT",
        f"/api/lessons/{lesson['id']}/attendance",
        {
            "items": [
                {
                    "enrollment_id": world["s1"],
                    "status": "PRESENT",
                    "memo": "병결 확인서",
                    "version": 1,
                },
            ]
        },
    )
    assert changed.status_code == 200
    [event] = audit(engine, "ATTENDANCE_UPDATED")
    assert event.details["before"]["status"] == "EXCUSED"


# --------------------------------------------------------------- 2. pauses
def test_pause_dates_decide_roster_membership(engine: Engine, world: dict) -> None:
    admin, teacher = login("admin"), login("teacher")
    room, s1 = world["A"], world["s1"]
    before = make_lesson(admin, room, "2026-11-03")
    during = make_lesson(admin, room, "2026-11-06")
    after = make_lesson(admin, room, "2026-11-12")
    base = f"/api/classrooms/{room}/enrollments/{s1}/pauses"

    assert send(teacher, "POST", base, {"paused_from": "2026-11-05"}).status_code == 403
    assert (
        send(admin, "POST", base, {"paused_from": (TODAY + timedelta(days=1)).isoformat()}).json()[
            "code"
        ]
        == "PAUSE_IN_FUTURE"
    )
    assert (
        send(admin, "POST", base, {"paused_from": "2025-12-31"}).json()["code"]
        == "PAUSE_OUTSIDE_ENROLLMENT"
    )
    assert (
        send(admin, "POST", base, {"paused_from": "2026-11-05", "resumed_on": "2026-11-05"}).json()[
            "code"
        ]
        == "INVALID_PAUSE_DATES"
    )

    opened = send(admin, "POST", base, {"paused_from": "2026-11-05"})
    assert opened.status_code == 201, opened.text
    pause_id = opened.json()["id"]
    assert (
        send(admin, "POST", base, {"paused_from": "2026-11-07"}).json()["code"] == "ALREADY_PAUSED"
    )
    listed = teacher.get(base).json()
    assert (
        listed["enrollment_status"] == "PAUSED" and len(listed["items"]) == 1
    )  # status trigger added nothing

    assert s1 in _roster_ids(teacher, before["id"])  # before the pause: still a member
    assert s1 not in _roster_ids(teacher, during["id"])
    assert s1 not in _roster_ids(teacher, after["id"])  # still paused
    item = {"items": [{"enrollment_id": s1, "status": "PRESENT"}]}
    assert (
        send(teacher, "PUT", f"/api/lessons/{during['id']}/attendance", item).json()["code"]
        == "INVALID_ATTENDANCE_ITEMS"
    )
    assert send(teacher, "PUT", f"/api/lessons/{before['id']}/attendance", item).status_code == 200

    assert (
        send(admin, "POST", f"{base}/{pause_id + 99}/resume", {"resumed_on": "2026-11-10"}).json()[
            "code"
        ]
        == "PAUSE_NOT_OPEN"
    )
    resumed = send(admin, "POST", f"{base}/{pause_id}/resume", {"resumed_on": "2026-11-10"})
    assert resumed.status_code == 200 and resumed.json()["resumed_on"] == "2026-11-10"
    assert teacher.get(base).json()["enrollment_status"] == "ACTIVE"
    assert s1 not in _roster_ids(teacher, during["id"])  # the past pause still applies
    assert s1 in _roster_ids(teacher, after["id"])
    assert _pauses(engine, s1) == [(date(2026, 11, 5), date(2026, 11, 10), "MANUAL")]

    # A historical (closed) pause may be recorded; overlaps are rejected by the database.
    assert (
        send(
            admin, "POST", base, {"paused_from": "2026-10-01", "resumed_on": "2026-10-05"}
        ).status_code
        == 201
    )
    overlap = send(admin, "POST", base, {"paused_from": "2026-10-04", "resumed_on": "2026-10-06"})
    assert (overlap.status_code, overlap.json()["code"]) == (409, "PAUSE_OVERLAP")
    [resume_event] = audit(engine, "ENROLLMENT_RESUMED")
    assert resume_event.actor_staff_user_id == world["admin_id"]
    assert (resume_event.details["status_before"], resume_event.details["status_after"]) == (
        "PAUSED",
        "ACTIVE",
    )
    assert len(audit(engine, "ENROLLMENT_PAUSE_RECORDED")) == 2

    records = teacher.get(f"/api/classrooms/{room}/students/{world['s1_student']}/records").json()
    shown = {row["lesson_date"] for row in records["lessons"]}
    assert "2026-11-06" not in shown and {"2026-11-03", "2026-11-12"} <= shown


def test_status_changes_outside_the_api_leave_dated_pauses(engine: Engine, world: dict) -> None:
    teacher = login("teacher")
    s2 = world["s2"]
    old = make_lesson(teacher, world["A"], "2026-11-03")
    # The Java import changes only enrollment.status; the trigger dates the pause.
    _sql(engine, "UPDATE enrollment SET status='PAUSED' WHERE id=:e", e=s2)
    assert _pauses(engine, s2) == [(TODAY, None, "STATUS_CHANGE")]
    assert s2 in _roster_ids(teacher, old["id"])  # past lessons are no longer wiped out
    _sql(engine, "UPDATE enrollment SET status='PAUSED' WHERE id=:e", e=s2)  # same status: no-op
    _sql(engine, "UPDATE enrollment SET status='ACTIVE' WHERE id=:e", e=s2)
    assert _pauses(engine, s2) == [(TODAY, TODAY + timedelta(days=1), "STATUS_CHANGE")]

    with pytest.raises(IntegrityError):  # overlapping pause rows are rejected by EXCLUDE
        _sql(
            engine,
            "INSERT INTO enrollment_pause(enrollment_id,paused_from,resumed_on) VALUES(:e,:f,NULL)",
            e=s2,
            f=TODAY,
        )

    # Re-paused before that pause ended (repeated imports on one day): the pause continues.
    _sql(engine, "UPDATE enrollment SET status='PAUSED' WHERE id=:e", e=s2)
    assert _pauses(engine, s2) == [(TODAY, None, "STATUS_CHANGE")]

    # Legacy PAUSED rows without any pause history keep the conservative rule (excluded).
    _sql(engine, "DELETE FROM enrollment_pause WHERE enrollment_id=:e AND resumed_on IS NULL", e=s2)
    assert s2 not in _roster_ids(teacher, old["id"])

    # An enrollment inserted as PAUSED (Java import of a 휴원 row) is dated from that day.
    student = _sql(engine, "INSERT INTO student(name) VALUES('new') RETURNING id").scalar_one()
    new = _sql(
        engine,
        "INSERT INTO enrollment(student_id,classroom_id,status,enrolled_at) "
        "VALUES(:s,:c,'PAUSED','2026-01-01') RETURNING id",
        s=student,
        c=world["A"],
    ).scalar_one()
    assert _pauses(engine, new) == [(TODAY, None, "STATUS_CHANGE")]
