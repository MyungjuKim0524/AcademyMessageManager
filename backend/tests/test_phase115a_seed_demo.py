"""Phase 11-5-A: demo seed (scripts/seed_demo.py) — unit tests, no database.

Checks the safety gates (switch, run mode, target host, TLS URL, passwords) and that the
fictional plan satisfies the application's own request schemas and business rules. Running the
seed against a database is a separate, user-approved step."""

import importlib.util
from datetime import date
from pathlib import Path

import pytest

from app.db.safety import UnsafeDatabaseError
from app.modules.academics.schemas import (
    AssessmentCreate,
    AttendanceItem,
    GradeItem,
    LessonCreate,
    RecordUpdate,
)
from app.modules.learningops.schemas import ClassroomCreate, StaffCreate, StudentCreate

BACKEND = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("seed_demo", BACKEND / "scripts" / "seed_demo.py")
seed = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed)

PROD_URL = (
    "postgresql+psycopg://demo_user:not-a-real-secret@ep-demo.example.invalid/neondb"
    "?sslmode=require&channel_binding=require"
)
DUMMY = {  # test-only values, never used anywhere else
    "ACADEMY_SEED_ADMIN_PASSWORD": "unit-test-admin-pass",
    "ACADEMY_SEED_TEACHER_PASSWORD": "unit-test-teacher-pass",
    "ACADEMY_SEED_ASSISTANT_PASSWORD": "unit-test-assistant-pass",
}


@pytest.fixture
def prod_env(monkeypatch):
    for name in ("ACADEMY_DB_TEST_MODE", "ACADEMY_RUN_POSTGRES_INTEGRATION"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ACADEMY_DB_MODE", "production")
    monkeypatch.setenv("ACADEMY_DATABASE_URL", PROD_URL)
    monkeypatch.setenv("ACADEMY_SEED_DEMO", "1")
    monkeypatch.setenv("ACADEMY_SEED_TARGET_HOST", "ep-demo.example.invalid")
    return monkeypatch


# ------------------------------------------------------------------------------ safety gates
def test_seed_requires_the_explicit_switch(prod_env):
    prod_env.delenv("ACADEMY_SEED_DEMO")
    with pytest.raises(seed.SeedError, match="ACADEMY_SEED_DEMO"):
        seed.check_target(seeding=True)
    # The read-only check needs no switch, but still the host guard.
    assert seed.check_target(seeding=False).host == "ep-demo.example.invalid"


@pytest.mark.parametrize("mode", ["development", "", "prod"])
def test_seed_refuses_every_mode_but_production_and_test(prod_env, mode):
    prod_env.setenv("ACADEMY_DB_MODE", mode)
    with pytest.raises(seed.SeedError, match="ACADEMY_DB_MODE"):
        seed.check_target(seeding=True)


@pytest.mark.parametrize("host", ["", "ep-other.example.invalid", "127.0.0.1"])
def test_seed_target_host_must_match_the_url(prod_env, host):
    prod_env.setenv("ACADEMY_SEED_TARGET_HOST", host)
    with pytest.raises(seed.SeedError, match="ACADEMY_SEED_TARGET_HOST"):
        seed.check_target(seeding=True)


def test_seed_target_host_match_is_case_insensitive(prod_env):
    prod_env.setenv("ACADEMY_SEED_TARGET_HOST", "EP-DEMO.example.invalid")
    assert seed.check_target(seeding=True).database == "neondb"


@pytest.mark.parametrize(
    "url",
    [
        PROD_URL.split("?")[0],  # no TLS
        PROD_URL.replace("sslmode=require", "sslmode=prefer"),
        "postgresql+psycopg://academy_dev:x@127.0.0.1:55431/academy_learningops_dev?sslmode=require",
    ],
)
def test_seed_refuses_urls_the_application_refuses(prod_env, url):
    prod_env.setenv("ACADEMY_DATABASE_URL", url)
    prod_env.setenv("ACADEMY_SEED_TARGET_HOST", url.split("@")[1].split("/")[0].split(":")[0])
    with pytest.raises(UnsafeDatabaseError):
        seed.check_target(seeding=True)


# ------------------------------------------------------------------------------ passwords
def test_passwords_come_from_the_environment(monkeypatch):
    for name, value in DUMMY.items():
        monkeypatch.setenv(name, value)
    assert seed.read_passwords() == {
        "ADMIN": DUMMY["ACADEMY_SEED_ADMIN_PASSWORD"],
        "TEACHER": DUMMY["ACADEMY_SEED_TEACHER_PASSWORD"],
        "ASSISTANT": DUMMY["ACADEMY_SEED_ASSISTANT_PASSWORD"],
    }


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("ACADEMY_SEED_ADMIN_PASSWORD", ""),
        ("ACADEMY_SEED_TEACHER_PASSWORD", "short-11ch"),
        ("ACADEMY_SEED_ASSISTANT_PASSWORD", "demo.assistant@example.invalid"),
        ("ACADEMY_SEED_TEACHER_PASSWORD", "demo.teacher2@example.invalid"),
    ],
)
def test_weak_password_is_refused_without_echoing_it(monkeypatch, name, value):
    for env, dummy in DUMMY.items():
        monkeypatch.setenv(env, dummy)
    monkeypatch.setenv(name, value)
    with pytest.raises(seed.SeedError) as error:
        seed.read_passwords()
    assert name in str(error.value)
    assert not value or value not in str(error.value)


def test_passwords_must_differ_per_role(monkeypatch):
    for env in DUMMY:
        monkeypatch.setenv(env, "same-password-for-all")
    with pytest.raises(seed.SeedError, match="differ"):
        seed.read_passwords()


# ------------------------------------------------------------------------------ the plan
def test_plan_uses_only_fictional_values():
    for staff in seed.STAFF:
        assert staff.email.endswith("@example.invalid")
        assert staff.display_name.startswith("시연")
    for student in seed.STUDENTS:
        assert student.name.startswith("시연학생") and student.parent_name.startswith("시연")
        assert student.school_name.startswith("가상")
        assert student.parent_email is None or student.parent_email.endswith(".invalid")
    for plan in seed.CLASSES:
        assert plan.name.startswith("시연")


def test_plan_passes_the_application_request_schemas():
    for staff in seed.STAFF:
        if staff.role != "ADMIN":  # the admin is created like bootstrap_admin.py
            StaffCreate(
                email=staff.email,
                display_name=staff.display_name,
                password="x" * 12,
                role=staff.role,
            )
    for plan in seed.CLASSES:
        ClassroomCreate(name=plan.name, class_type=plan.class_type)
        assert len(plan.topics) == len(seed.LESSON_DATES)
        for lesson_date, topic in zip(seed.LESSON_DATES, plan.topics, strict=True):
            LessonCreate(lesson_date=lesson_date, topic=topic, status="COMPLETED")
        for title, lesson_index in seed.ASSESSMENTS:
            AssessmentCreate(
                title=title,
                assessment_date=seed.LESSON_DATES[lesson_index],
                max_score=seed.MAX_SCORE,
                lesson_id=1,
            )
    for student in seed.STUDENTS:
        StudentCreate(
            name=student.name,
            school_name=student.school_name,
            parent_name=student.parent_name,
            parent_email=student.parent_email,
        )
        for class_key, marks in student.attendance.items():
            assert len(marks) == len(seed.LESSON_DATES)
            for index, mark in enumerate(marks):
                if mark == "-":
                    continue
                AttendanceItem(enrollment_id=1, status=seed.ATTENDANCE_CODES[mark])
                prework, weekly = seed.assignment_grades(student.no, index)
                RecordUpdate(result_version=1, prework_grade=prework, weekly_grade=weekly)
            for _, lesson_index in seed.ASSESSMENTS:
                grade = seed.planned_grade(student, class_key, lesson_index)
                if grade is not None:
                    status, score = grade
                    GradeItem(enrollment_id=1, result_status=status, score=score)
                    assert score is None or 0 <= score <= seed.MAX_SCORE


def test_plan_respects_business_rules():
    # Lessons are COMPLETED and attendance is recorded, so every date must be in the past;
    # enrolments and assignments start before the first lesson.
    assert max(seed.LESSON_DATES) <= date.today()
    assert seed.ENROLLED_AT <= min(seed.LESSON_DATES)
    assert len(set(seed.LESSON_DATES)) == len(seed.LESSON_DATES)
    staff = {s.key: s for s in seed.STAFF}
    for plan in seed.CLASSES:
        for staff_key, role in plan.staff:
            assert staff[staff_key].role == role  # ASSIGNMENT_ROLE_MISMATCH otherwise
        assert any(role == "TEACHER" for _, role in plan.staff)
    keys = [(s.name, s.school_name) for s in seed.STUDENTS]
    assert len(set(keys)) == len(keys)  # uq_student_business_key
    assert len({s.email for s in seed.STAFF}) == len(seed.STAFF)
    assert len({(c.name, c.class_type) for c in seed.CLASSES}) == len(seed.CLASSES)


def test_plan_covers_the_demo_scenarios():
    roles = {s.role for s in seed.STAFF}
    assert roles == {"ADMIN", "TEACHER", "ASSISTANT"}
    # RBAC: teacher2 sees class B only; the assistant sees class A only.
    assigned = {
        key: {c.key for c in seed.CLASSES if any(k == key for k, _ in c.staff)}
        for key in ("teacher1", "teacher2", "assistant")
    }
    assert assigned == {"teacher1": {"A", "C"}, "teacher2": {"B"}, "assistant": {"A"}}
    domains = {s.parent_email.rsplit("@", 1)[1] for s in seed.STUDENTS if s.parent_email}
    assert {"mock-retry.invalid", "mock-fail.invalid", "example.invalid"} <= domains
    assert any(s.parent_email is None for s in seed.STUDENTS)
    marks = "".join(m for s in seed.STUDENTS for m in s.attendance.values())
    assert {"P", "L", "A", "E", "-"} <= set(marks)
    # 관심 학생: some student is absent at least twice in the last four lessons.
    assert any(m[-4:].count("A") >= 2 for s in seed.STUDENTS for m in s.attendance.values())
    assert any(len(s.attendance) > 1 for s in seed.STUDENTS)  # one student in two classes


def test_expected_counts_match_the_plan():
    assert seed.expected_counts() == {
        "staff": 4,
        "classrooms": 3,
        "assignments": 4,
        "students": 12,
        "enrollments": 13,
        "lessons": 18,
        "lesson_results": 77,  # 13 enrolments x 6 lessons, one left unrecorded
        "assessments": 6,
        "assessment_results": 25,  # 13 x 2, minus the unrecorded one
    }


def test_seed_script_has_no_delivery_or_destructive_code():
    source = (BACKEND / "scripts" / "seed_demo.py").read_text(encoding="utf-8")
    for forbidden in ("smtplib", "httpx", "requests", "urllib", "TRUNCATE", "DROP ", "DELETE "):
        assert forbidden not in source
    for call in (".delete(", "delete_", "update_classroom", "update_student_contact"):
        assert call not in source
