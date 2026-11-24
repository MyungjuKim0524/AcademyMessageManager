# ruff: noqa: F811, E501, E241  -- fixtures injected by name; expectation tables kept on one line
"""Phase 10: attendance / grade analytics against PostgreSQL with a hand-made fictional dataset.

Every expected number below was worked out by hand from the dataset in ``data`` (see the tables
in the comments) — never by re-running the implementation's formulas.
"""

from datetime import date, timedelta

import pytest
from sqlalchemy import Engine, text
from test_phase7_academics_integration import engine, login, world  # noqa: F401

from app.db.models.tables import Enrollment, EnrollmentPause, Student
from app.db.session import create_session_factory

pytestmark = pytest.mark.postgres
FUTURE = (date.today() + timedelta(days=5)).isoformat()
WIDE = {"date_from": "2026-10-01", "date_to": (date.today() + timedelta(days=30)).isoformat()}


def _sql(engine: Engine, sql: str, **params):
    with engine.begin() as connection:
        return connection.execute(text(sql), params)


@pytest.fixture()
def data(engine: Engine, world: dict) -> dict:
    """Class A (world): s1, s2 (from 2026-01-01), late_joiner (from 2026-11-10), withdrawn
    (WITHDRAWN, no end date → never eligible). Added here:
      p_paused  — ACTIVE, paused 2026-10-10, back 2026-10-20
      e_ended   — WITHDRAWN, ended 2026-10-12

    Lessons of A:                       eligible students
      L1 10-05 s1 COMPLETED             s1 s2 p e            (withdrawn has an outside record)
      L2 10-05 s2 COMPLETED (2교시)     s1 s2 p e
      L3 10-15 COMPLETED                s1 s2                (p paused, e ended)
      L4 10-16 CANCELLED                — not a target
      L5 10-17 SCHEDULED, no attendance — "not held"
      L6 10-18 SCHEDULED + 1 record     s1 s2                (held because it has attendance)
      L7 FUTURE SCHEDULED               — after today, not counted
      L8 11-12 COMPLETED                s1 s2 late p

    Attendance (- = not entered):
             L1   L2   L3   L6   L8
      s1     P    P    A    L    P
      s2     L    P    -    -    E
      late                       P
      p      A    -              -
      e      E    L
      withdrawn P (outside)
    """
    a, b = world["A"], world["B"]
    with create_session_factory(engine).begin() as session:
        for name, status, ended in (("p_paused", "ACTIVE", None), ("e_ended", "WITHDRAWN", date(2026, 10, 12))):
            student = Student(name=name)
            session.add(student)
            session.flush()
            row = Enrollment(student_id=student.id, classroom_id=a, status=status,
                             enrolled_at=date(2026, 1, 1), ended_at=ended)
            session.add(row)
            session.flush()
            world[name], world[f"{name}_student"] = row.id, student.id
        session.add(EnrollmentPause(enrollment_id=world["p_paused"], paused_from=date(2026, 10, 10),
                                    resumed_on=date(2026, 10, 20)))

    def lesson(room: int, day: str, status: str, session_no: int = 1) -> int:
        return _sql(engine, "INSERT INTO lesson(classroom_id, lesson_date, status, session_no) "
                    "VALUES(:r, :d, :s, :n) RETURNING id", r=room, d=day, s=status, n=session_no).scalar_one()

    L = {
        1: lesson(a, "2026-10-05", "COMPLETED"), 2: lesson(a, "2026-10-05", "COMPLETED", 2),
        3: lesson(a, "2026-10-15", "COMPLETED"), 4: lesson(a, "2026-10-16", "CANCELLED"),
        5: lesson(a, "2026-10-17", "SCHEDULED"), 6: lesson(a, "2026-10-18", "SCHEDULED"),
        7: lesson(a, FUTURE, "SCHEDULED"), 8: lesson(a, "2026-11-12", "COMPLETED"),
        "B": lesson(b, "2026-10-05", "COMPLETED"),
    }

    def attend(lesson_key, student: str, status: str) -> None:
        _sql(engine, "INSERT INTO lesson_result(lesson_id, enrollment_id, attendance_status) "
             "VALUES(:l, :e, :s)", l=L[lesson_key], e=world[student], s=status)

    for lesson_key, student, status in (
        (1, "s1", "PRESENT"), (1, "s2", "LATE"), (1, "p_paused", "ABSENT"), (1, "e_ended", "EXCUSED"),
        (1, "withdrawn", "PRESENT"),
        (2, "s1", "PRESENT"), (2, "s2", "PRESENT"), (2, "e_ended", "LATE"),
        (3, "s1", "ABSENT"),
        (6, "s1", "LATE"),
        (8, "s1", "PRESENT"), (8, "s2", "EXCUSED"), (8, "late_joiner", "PRESENT"),
        ("B", "other", "PRESENT"),
    ):
        attend(lesson_key, student, status)

    # Assessments of A (max scores differ):
    #   G1 10-05 어휘 /10  linked to L1   G2 10-05 문법 /20 linked to L2 (2교시)
    #   G5 10-05 단어 퀴즈 /5 (unlinked, no results)   G3 10-15 모의고사 /100 (unlinked)
    #   G4 FUTURE 기말 /50 (unlinked, no results)      GB = class B assessment
    def assessment(room: int, title: str, day: str, max_score, lesson_key=None) -> int:
        return _sql(engine, "INSERT INTO assessment(classroom_id, lesson_id, title, assessment_date, max_score) "
                    "VALUES(:r, :l, :t, :d, :m) RETURNING id", r=room,
                    l=L[lesson_key] if lesson_key else None, t=title, d=day, m=max_score).scalar_one()

    G = {
        1: assessment(a, "어휘", "2026-10-05", 10, 1), 2: assessment(a, "문법", "2026-10-05", 20, 2),
        5: assessment(a, "단어 퀴즈", "2026-10-05", 5), 3: assessment(a, "모의고사", "2026-10-15", 100),
        4: assessment(a, "기말", FUTURE, 50), "B": assessment(b, "B반 평가", "2026-10-05", 10),
    }

    def score(key, student: str, status: str, value=None) -> None:
        max_score = {1: 10, 2: 20, 3: 100, "B": 10}[key]
        _sql(engine, "INSERT INTO assessment_result(assessment_id, classroom_id, max_score, enrollment_id, "
             "result_status, score) VALUES(:a, :c, :m, :e, :s, :v)", a=G[key],
             c=b if key == "B" else a, m=max_score, e=world[student], s=status, v=value)

    # G1: s1 10, s2 0 (a real zero), p 미응시, e 미입력, withdrawn 7 (outside the period)
    # G2: s1 15.5, s2 미입력, p 12.25, e 20        G3: s1 80, s2 미응시
    for args in (
        (1, "s1", "SCORED", 10), (1, "s2", "SCORED", 0), (1, "p_paused", "NOT_TAKEN"),
        (1, "withdrawn", "SCORED", 7),
        (2, "s1", "SCORED", 15.5), (2, "p_paused", "SCORED", 12.25), (2, "e_ended", "SCORED", 20),
        (3, "s1", "SCORED", 80), (3, "s2", "NOT_TAKEN"),
        ("B", "other", "SCORED", 9),
    ):
        score(*args)
    return {**world, "L": L, "G": G}


def _get(client, path: str, **params):
    return client.get(path, params=params)


def _by_name(items: list[dict]) -> dict[str, dict]:
    return {item["student_name"]: item for item in items}


def test_class_attendance_counts_match_hand_calculation(data: dict) -> None:
    body = _get(login("teacher"), "/api/analytics/attendance", classroom_id=data["A"], **WIDE).json()
    s = body["summary"]
    # target = 5 (s1) + 5 (s2) + 1 (late) + 3 (p) + 2 (e) = 16
    assert (s["target"], s["recorded"], s["unrecorded"]) == (16, 12, 4)
    assert (s["present"], s["late"], s["absent"], s["excused"]) == (5, 3, 2, 2)
    assert s["outside_records"] == 1  # withdrawn's L1 record
    assert s["record_rate"] == 75.0  # 12 / 16
    assert s["attendance_rate"] == 80.0  # (5 + 3) / (12 - 2)
    # Invariants of the definitions.
    assert s["target"] == s["recorded"] + s["unrecorded"]
    assert s["recorded"] == s["present"] + s["late"] + s["absent"] + s["excused"]
    # L1 L2 L3 L6 L8 held; L5 not held; L4 cancelled and L7 (future) are neither.
    assert (body["held_lessons"], body["not_held_lessons"]) == (5, 1)
    assert body["counted_until"] == date.today().isoformat()


def test_student_attendance_rows_cover_period_rules(data: dict) -> None:
    body = _get(login("teacher"), "/api/analytics/attendance", classroom_id=data["A"], **WIDE).json()
    students = _by_name(body["students"])
    expected = {
        #           target rec unrec P L A E  record  attendance
        "s1":       (5, 5, 0, 3, 1, 1, 0, 100.0, 80.0),
        "s2":       (5, 3, 2, 1, 1, 0, 1, 60.0, 100.0),  # (1+1)/(3-1)
        "late_joiner": (1, 1, 0, 1, 0, 0, 0, 100.0, 100.0),  # only L8 (joined 11-10)
        "p_paused": (3, 1, 2, 0, 0, 1, 0, 33.3, 0.0),  # L3/L6 inside the pause; 0.0 is a real 0
        "e_ended":  (2, 2, 0, 0, 1, 0, 1, 100.0, 100.0),  # ended 10-12: L1, L2 only
    }
    for name, values in expected.items():
        row = students[name]
        got = tuple(row[k] for k in ("target", "recorded", "unrecorded", "present", "late", "absent",
                                     "excused", "record_rate", "attendance_rate"))
        assert got == values, name
    # Never eligible, but has a record: listed with no rates (not 0%).
    withdrawn = students["withdrawn"]
    assert (withdrawn["target"], withdrawn["outside_records"]) == (0, 1)
    assert withdrawn["record_rate"] is None and withdrawn["attendance_rate"] is None
    assert "other" not in students  # class B never leaks in


def test_lesson_level_unrecorded_counts_for_entry_links(data: dict) -> None:
    body = _get(login("assistant"), "/api/analytics/attendance", classroom_id=data["A"], **WIDE).json()
    L = data["L"]
    got = {row["lesson_id"]: (row["target"], row["recorded"], row["unrecorded"]) for row in body["lessons"]}
    assert got == {L[1]: (4, 4, 0), L[2]: (4, 3, 1), L[3]: (2, 1, 1), L[6]: (2, 1, 1), L[8]: (4, 3, 1)}
    assert [row["lesson_id"] for row in body["lessons"]] == [L[1], L[2], L[3], L[6], L[8]]  # date, session


def test_student_attendance_history_and_period_filter(data: dict) -> None:
    client = login("teacher")
    body = _get(client, f"/api/analytics/attendance/students/{data['s2_student']}",
                classroom_id=data["A"], **WIDE).json()
    L = data["L"]
    assert [(r["lesson_id"], r["status"]) for r in body["rows"]] == [
        (L[1], "LATE"), (L[2], "PRESENT"), (L[3], None), (L[6], None), (L[8], "EXCUSED")]
    assert (body["summary"]["target"], body["summary"]["unrecorded"]) == (5, 2)
    # Period 10-10 .. 10-31 for p (paused 10-10 .. 10-19): nothing to take → N/A, not 0%.
    paused = _get(client, f"/api/analytics/attendance/students/{data['p_paused_student']}",
                  classroom_id=data["A"], date_from="2026-10-10", date_to="2026-10-31").json()
    assert paused["rows"] == [] and paused["summary"]["target"] == 0
    assert paused["summary"]["record_rate"] is None


def test_empty_period_returns_zero_counts_and_no_rates(data: dict) -> None:
    body = _get(login("teacher"), "/api/analytics/attendance", classroom_id=data["A"],
                date_from="2026-03-01", date_to="2026-03-31").json()
    assert body["summary"]["target"] == 0 and body["students"] == [] and body["lessons"] == []
    assert body["summary"]["record_rate"] is None and body["summary"]["attendance_rate"] is None


def test_assessment_stats_match_hand_calculation(data: dict) -> None:
    body = _get(login("teacher"), "/api/analytics/grades", classroom_id=data["A"], **WIDE).json()
    G = data["G"]
    # Same-day order: linked by session (G1 1교시, G2 2교시), then unlinked (G5).
    assert [a["assessment_id"] for a in body["assessments"]] == [G[1], G[2], G[5], G[3], G[4]]
    stats = {a["assessment_id"]: a for a in body["assessments"]}

    g1 = stats[G[1]]  # targets s1 s2 p e; scores 10, 0, (p 미응시), (e 미입력); withdrawn 7 outside
    assert (g1["target"], g1["scored"], g1["not_taken"], g1["missing"], g1["outside_records"]) == (4, 2, 1, 1, 1)
    assert g1["entry_rate"] == 75.0  # (2 + 1) / 4
    assert g1["average"] == 5.67 and g1["average_count"] == 3  # (10 + 0 + 7) / 3 = 5.666…
    assert g1["average_percent"] == 56.7  # 5.666… / 10

    g2 = stats[G[2]]  # 15.5, 12.25, 20 of 20; s2 missing
    assert (g2["scored"], g2["missing"], g2["average"], g2["average_percent"]) == (3, 1, 15.92, 79.6)

    g3 = stats[G[3]]  # 10-15: only s1, s2 eligible; 80 and 미응시
    assert (g3["target"], g3["scored"], g3["not_taken"], g3["average"], g3["entry_rate"]) == (2, 1, 1, 80.0, 100.0)

    g5 = stats[G[5]]  # nothing entered: rate 0.0 (real), average N/A
    assert (g5["target"], g5["missing"], g5["entry_rate"], g5["average"], g5["average_percent"]) == (4, 4, 0.0, None, None)

    g4 = stats[G[4]]  # future: scores cannot be entered yet
    assert g4["upcoming"] is True and g4["entry_rate"] is None and g4["average"] is None
    for a in body["assessments"]:
        assert a["target"] == a["scored"] + a["not_taken"] + a["missing"]


def test_assessment_detail_separates_zero_not_taken_and_missing(data: dict) -> None:
    body = _get(login("assistant"), f"/api/analytics/grades/assessments/{data['G'][1]}").json()
    rows = {r["student_name"]: (r["status"], r["score"], r["percent"], r["eligible"]) for r in body["rows"]}
    assert rows == {
        "e_ended": ("MISSING", None, None, True),
        "p_paused": ("NOT_TAKEN", None, None, True),
        "s1": ("SCORED", 10.0, 100.0, True),
        "s2": ("SCORED", 0.0, 0.0, True),  # a real zero is a score
        "withdrawn": ("SCORED", 7.0, 70.0, False),
    }
    assert [r["student_name"] for r in body["rows"]] == sorted(rows)
    assert body["stats"]["average"] == 5.67


def test_student_grade_trend_is_ordered_and_uses_percentages(data: dict) -> None:
    client = login("teacher")
    G = data["G"]
    s1 = _get(client, f"/api/analytics/grades/students/{data['s1_student']}", classroom_id=data["A"], **WIDE).json()
    assert [(r["assessment_id"], r["status"], r["score"], r["percent"]) for r in s1["rows"]] == [
        (G[1], "SCORED", 10.0, 100.0), (G[2], "SCORED", 15.5, 77.5), (G[5], "MISSING", None, None),
        (G[3], "SCORED", 80.0, 80.0), (G[4], "UPCOMING", None, None)]
    s2 = _get(client, f"/api/analytics/grades/students/{data['s2_student']}", classroom_id=data["A"], **WIDE).json()
    assert [(r["status"], r["score"]) for r in s2["rows"]] == [
        ("SCORED", 0.0), ("MISSING", None), ("MISSING", None), ("NOT_TAKEN", None), ("UPCOMING", None)]
    one = _get(client, f"/api/analytics/grades/students/{data['s1_student']}", classroom_id=data["A"],
               date_from="2026-10-15", date_to="2026-10-15").json()
    assert [r["assessment_id"] for r in one["rows"]] == [G[3]]  # a single result is still just one row


def test_access_is_limited_to_assigned_classes_and_ids_cannot_cross_classes(data: dict, engine: Engine) -> None:
    teacher = login("teacher")
    a, b = data["A"], data["B"]
    assert _get(teacher, "/api/analytics/attendance", classroom_id=b, **WIDE).status_code == 403
    assert _get(teacher, "/api/analytics/grades", classroom_id=b, **WIDE).status_code == 403
    assert _get(login("teacher2"), "/api/analytics/attendance", classroom_id=a, **WIDE).status_code == 403
    assert _get(login("admin"), "/api/analytics/attendance", classroom_id=b, **WIDE).status_code == 200
    # A class-B student through an allowed class id → not found; through class B → denied.
    for kind in ("attendance", "grades"):
        path = f"/api/analytics/{kind}/students/{data['other_student']}"
        assert _get(teacher, path, classroom_id=a, **WIDE).status_code == 404
        assert _get(teacher, path, classroom_id=b, **WIDE).status_code == 403
    assert _get(teacher, f"/api/analytics/grades/assessments/{data['G']['B']}").status_code == 403
    assert _get(teacher, "/api/analytics/grades/assessments/999999").status_code == 404
    # Assignment ended yesterday → denied; inactive staff → session rejected.
    _sql(engine, "UPDATE classroom_staff_assignment SET valid_to = current_date - 1 WHERE staff_user_id = :u",
         u=data["teacher_id"])
    assert _get(teacher, "/api/analytics/attendance", classroom_id=a, **WIDE).status_code == 403
    assistant = login("assistant")
    _sql(engine, "UPDATE staff_user SET status = 'INACTIVE' WHERE id = :u", u=data["assistant_id"])
    assert _get(assistant, "/api/analytics/attendance", classroom_id=a, **WIDE).status_code == 401


def test_requests_need_a_session_and_a_valid_period(data: dict) -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    anonymous = TestClient(app, raise_server_exceptions=False)
    assert _get(anonymous, "/api/analytics/attendance", classroom_id=data["A"], **WIDE).status_code == 401
    teacher = login("teacher")
    bad = _get(teacher, "/api/analytics/attendance", classroom_id=data["A"], date_from="2026-10-31", date_to="2026-10-01")
    assert bad.status_code == 400 and bad.json()["code"] == "INVALID_DATE_RANGE"
    long = _get(teacher, "/api/analytics/grades", classroom_id=data["A"], date_from="2025-01-01", date_to="2026-10-01")
    assert long.status_code == 400 and long.json()["code"] == "DATE_RANGE_TOO_LONG"


def test_analytics_reads_never_write(data: dict, engine: Engine) -> None:
    def snapshot():
        return _sql(engine, "SELECT (SELECT count(*) FROM lesson_result), (SELECT count(*) FROM assessment_result), "
                    "(SELECT count(*) FROM audit_log), (SELECT max(updated_at) FROM lesson_result), "
                    "(SELECT max(updated_at) FROM assessment_result)").one()

    client = login("admin")  # logging in writes its own audit row: do it before the snapshot
    before = snapshot()
    for path, params in (
        ("/api/analytics/attendance", {"classroom_id": data["A"], **WIDE}),
        (f"/api/analytics/attendance/students/{data['s1_student']}", {"classroom_id": data["A"], **WIDE}),
        ("/api/analytics/grades", {"classroom_id": data["A"], **WIDE}),
        (f"/api/analytics/grades/assessments/{data['G'][1]}", {}),
        (f"/api/analytics/grades/students/{data['s1_student']}", {"classroom_id": data["A"], **WIDE}),
    ):
        assert client.get(path, params=params).status_code == 200
    assert snapshot() == before
    # GET only: writes are not routed.
    assert client.post("/api/analytics/attendance").status_code in (403, 405)


def test_held_lessons_are_the_same_set_in_message_operations_and_analytics(data: dict) -> None:
    """B-2: 메시지 처리 현황 and 출결 분석 share one "held lesson" rule
    (academics.repository.held_lesson). Same data → same lesson sets; only the student-level
    target differs, by design (an attendance row outside eligibility is an obligation in
    operations but an "outside record" in analytics — docs/analytics/phase10-metric-definitions.md §0)."""
    L = data["L"]
    client = login("teacher")
    period = {"date_from": "2026-10-01", "date_to": "2027-01-01"}  # within the 93-day limit
    analytics = _get(client, "/api/analytics/attendance", classroom_id=data["A"], **period).json()
    ops = _get(client, "/api/message-operations/obligations", classroom_id=data["A"], limit=200, **period).json()
    assert ops["total"] <= 200

    analytics_held = {row["lesson_id"]: row["target"] for row in analytics["lessons"]}
    obligated: dict[int, int] = {}
    for item in ops["items"]:
        if item["obligated"]:
            obligated[item["lesson_id"]] = obligated.get(item["lesson_id"], 0) + 1
    not_held = {i["lesson_id"] for i in ops["items"] if i["exempt_reason"] == "LESSON_NOT_HELD"}
    cancelled = {i["lesson_id"] for i in ops["items"] if i["exempt_reason"] == "LESSON_CANCELLED"}

    held = {L[1], L[2], L[3], L[6], L[8]}  # L6: past SCHEDULED + one attendance row = held
    assert set(analytics_held) == set(obligated) == held
    assert analytics["held_lessons"] == len(held)
    assert not_held == {L[5]} and analytics["not_held_lessons"] == 1  # past SCHEDULED, no rows
    assert cancelled == {L[4]}  # cancelled: never held, listed as exempt in operations
    assert L[7] not in {i["lesson_id"] for i in ops["items"]}  # future: in neither
    # Same eligible students per held lesson; L1 also obliges the withdrawn student's record.
    assert {k: obligated[k] - (1 if k == L[1] else 0) for k in obligated} == analytics_held

def test_watchlist_flags_students_by_rule_with_reasons_and_report_compares_with_the_class(
    engine: Engine, world: dict
) -> None:
    """관심 필요 학생 + 학생 학습 리포트 (rules revised 2026-11-20: each student's most recent
    records — last 4 scored sessions per 평가 항목, last 4 lessons). Hand-made data, dates
    relative to today:

      어휘 (/10) on 5 lessons    s1: 9 9 9 9 9     s2: 6 5 4 3 2
        class average %          75 70 65 60 55 → s2 is −15 −20 −25 −30 −35 %p
        → s2: last 4 all ≥15%p below (LOW_SCORE 4) and the last 3 kept falling by 10%p
          (−25 → −30 → −35, DECLINING); s1 nothing
      주간 과제 C: s1 on lessons 1-4 → 3 of the last 4 lessons (HOMEWORK_C 3)
      예습 과제 C: s2 only on the last lesson → 1 of 4 (below 2: no flag)
      s3 over the last 4 lessons: absent, excused (never counted), present+미응시 ×2
          → 결석 1 + 미응시 2 = 3 (ABSENCE)
      s4: only 2 scored 문법 sessions, far below → too few scores to judge (no flag)
    """
    a, today = world["A"], date.today()
    extra = {}
    with create_session_factory(engine).begin() as session:
        for name in ("s3", "s4"):
            student = Student(name=name)
            session.add(student)
            session.flush()
            row = Enrollment(student_id=student.id, classroom_id=a, status="ACTIVE",
                             enrolled_at=date(2026, 1, 1))
            session.add(row)
            session.flush()
            extra[name] = row.id
    s3, s4 = extra["s3"], extra["s4"]
    days = [(today - timedelta(days=n)).isoformat() for n in (24, 18, 12, 6, 0)]
    s1_scores, s2_scores = [9, 9, 9, 9, 9], [6, 5, 4, 3, 2]
    s3_attendance = ["ABSENT", "ABSENT", "EXCUSED", "PRESENT", "PRESENT"]

    def result(test: int, enrollment: int, status: str, value, max_score: int = 10) -> None:
        _sql(engine, "INSERT INTO assessment_result(assessment_id, classroom_id, max_score, enrollment_id, "
             "result_status, score) VALUES(:t, :r, :m, :e, :s, :v)", t=test, r=a, m=max_score, e=enrollment,
             s=status, v=value)

    for i, day in enumerate(days):
        lesson = _sql(engine, "INSERT INTO lesson(classroom_id, lesson_date, status, session_no) "
                      "VALUES(:r, :d, 'COMPLETED', 1) RETURNING id", r=a, d=day).scalar_one()
        test = _sql(engine, "INSERT INTO assessment(classroom_id, lesson_id, title, assessment_date, max_score) "
                    "VALUES(:r, :l, '어휘', :d, 10) RETURNING id", r=a, l=lesson, d=day).scalar_one()
        rows = [
            (world["s1"], "PRESENT", "A", "C" if 1 <= i <= 3 else "B"),
            (world["s2"], "PRESENT", "C" if i == 4 else "B", "A"),
            (s3, s3_attendance[i], None, None),
        ] + ([(s4, "PRESENT", None, None)] if i >= 3 else [])
        for enrollment, status, prework, weekly in rows:
            _sql(engine, "INSERT INTO lesson_result(lesson_id, enrollment_id, attendance_status, prework_grade, "
                 "weekly_assignment_grade) VALUES(:l, :e, :s, :p, :w)", l=lesson, e=enrollment, s=status,
                 p=prework, w=weekly)
        result(test, world["s1"], "SCORED", s1_scores[i])
        result(test, world["s2"], "SCORED", s2_scores[i])
        result(test, s3, "NOT_TAKEN", None)
        if i >= 3:  # a second 평가 항목 on the last two lessons only
            grammar = _sql(engine, "INSERT INTO assessment(classroom_id, lesson_id, title, assessment_date, "
                           "max_score) VALUES(:r, :l, '문법', :d, 10) RETURNING id", r=a, l=lesson, d=day).scalar_one()
            result(grammar, world["s1"], "SCORED", 10)
            result(grammar, s4, "SCORED", 1)

    teacher = login("teacher")
    body = _get(teacher, "/api/analytics/watchlist", classroom_id=a).json()
    assert (body["window_from"], body["window_to"]) == ((today - timedelta(days=91)).isoformat(), today.isoformat())
    assert len(body["rules"]) == 5
    flagged = {s["student_name"]: [(r["code"], r["count"]) for r in s["reasons"]] for s in body["students"]}
    assert flagged == {
        "s2": [("LOW_SCORE", 4), ("DECLINING", 3)],
        "s1": [("HOMEWORK_C", 3)],
        "s3": [("ABSENCE", 3)],
    }  # s4: two very low 문법 scores are not enough to judge
    assert [s["student_name"] for s in body["students"]] == ["s2", "s1", "s3"]  # most reasons first
    texts = {r["text"] for s in body["students"] for r in s["reasons"]}
    assert texts == {
        "어휘: 최근 4회 중 4회 반 평균보다 15%p 이상 낮음",
        "어휘: 최근 3회 반 대비 위치가 계속 낮아짐 (-25.0 → -30.0 → -35.0%p, 10.0%p 하락)",
        "최근 4회 수업 중 주간 과제 C 등급 3회",
        "최근 4회 수업 중 결석·미응시 3회 (결석 1, 미응시 2)",
    }

    period = {"classroom_id": a, "date_from": (today - timedelta(days=30)).isoformat(), "date_to": today.isoformat()}
    report = _get(teacher, f"/api/analytics/students/{world['s2_student']}/report", **period).json()
    categories = {c["title"]: c for c in report["categories"]}
    assert set(categories) == {"어휘", "문법"}
    # s2 was due for 문법 but has no score: shown as 미입력, never as a number.
    assert [p["status"] for p in categories["문법"]["points"]] == ["MISSING", "MISSING"]
    assert categories["문법"]["average_diff"] is None
    category = categories["어휘"]
    assert category["scored_count"] == 5
    assert [p["class_average_percent"] for p in category["points"]] == [75.0, 70.0, 65.0, 60.0, 55.0]
    assert [p["diff"] for p in category["points"]] == [-15.0, -20.0, -25.0, -30.0, -35.0]
    assert category["average_diff"] == -25.0
    assert [r["code"] for r in report["watch_reasons"]] == ["LOW_SCORE", "DECLINING"]
    assert [row["prework"] for row in report["lessons"]] == ["B", "B", "B", "B", "C"]
    assert report["attendance"]["present"] == 5 and report["attendance"]["attendance_rate"] == 100.0

    # Same access rules as every analytics screen.
    assert login("assistant2").get("/api/analytics/watchlist", params={"classroom_id": a}).status_code == 403
    other = _get(teacher, f"/api/analytics/students/{world['other_student']}/report", **period)
    assert (other.status_code, other.json()["code"]) == (404, "STUDENT_NOT_IN_CLASSROOM")