"""Phase 11-5-A: demonstration (시연) data for a new, empty deployment database.

Everything here is fictional: names are "시연…", schools are "가상…", and every e-mail uses a
reserved ``.invalid`` domain (RFC 2606), so nothing can ever reach a real person. Parent
addresses on ``mock-retry.invalid`` / ``mock-fail.invalid`` drive the Mock Sender's failure
demos (see ``app/modules/notifications/sender.py``); the sender itself is not touched.

Writes go through the application's own services (LearningOpsService, AcademicsService), so
the same validation, business rules, password hashing (``hash_password``) and audit rows apply
as in the UI. All seed audit rows share one request id.

Safety
- Explicit switch ``ACADEMY_SEED_DEMO=1`` and ``ACADEMY_SEED_TARGET_HOST`` equal to the host of
  ``ACADEMY_DATABASE_URL`` (a typo guard against the wrong database).
- ``ACADEMY_DB_MODE`` must be ``production`` or ``test``; the usual URL checks apply
  (``app/db/safety.py``). The local development database is never a target.
- The database must be at the Alembic head and contain no classes or students other than the
  demo ones (demo data is never mixed into real data).
- Re-running is safe: rows are looked up by their natural keys and created only when missing.
  Existing rows — including anything changed during a demo — are never updated or deleted.
- Passwords come only from environment variables and are never printed or stored in plain text.

Usage (from ``backend``):  python scripts/seed_demo.py          # seed, then verify
                           python scripts/seed_demo.py --check  # read-only verification
"""

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models.tables import (
    Assessment,
    AssessmentResult,
    AuditLog,
    Classroom,
    ClassroomStaffAssignment,
    Enrollment,
    Lesson,
    LessonResult,
    StaffUser,
    Student,
)
from app.db.safety import UnsafeDatabaseError, require_database_url
from app.db.session import create_db_engine, create_session_factory
from app.errors import CompatibilityError
from app.modules.academics.schemas import (
    AssessmentCreate,
    AttendanceBulk,
    AttendanceItem,
    GradeBulk,
    GradeItem,
    LessonCreate,
    RecordUpdate,
)
from app.modules.academics.service import AcademicsService
from app.modules.auth.dependencies import Principal
from app.modules.auth.service import hash_password, password_problem
from app.modules.learningops.schemas import (
    AssignmentCreate,
    ClassroomCreate,
    EnrollmentCreate,
    StaffCreate,
    StudentCreate,
)
from app.modules.learningops.service import LearningOpsService

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"
ALLOWED_MODES = frozenset({"production", "test"})
PASSWORD_ENV = {
    "ADMIN": "ACADEMY_SEED_ADMIN_PASSWORD",
    "TEACHER": "ACADEMY_SEED_TEACHER_PASSWORD",
    "ASSISTANT": "ACADEMY_SEED_ASSISTANT_PASSWORD",
}


class SeedError(RuntimeError):
    pass


# --------------------------------------------------------------------------- the plan
@dataclass(frozen=True)
class StaffPlan:
    key: str
    email: str
    display_name: str
    role: str  # ADMIN | TEACHER | ASSISTANT


@dataclass(frozen=True)
class ClassPlan:
    key: str
    name: str
    class_type: str
    staff: tuple[tuple[str, str], ...]  # (staff key, assignment role)
    topics: tuple[str, ...]  # one per lesson date


@dataclass(frozen=True)
class StudentPlan:
    no: int
    name: str
    school_name: str
    parent_name: str
    parent_email: str | None
    # class key -> attendance per lesson date: P present, L late, A absent, E excused,
    # "-" not recorded (an unrecorded day is never counted as absent).
    attendance: dict[str, str]


STAFF = (
    StaffPlan("admin", "demo.admin@example.invalid", "시연 관리자", "ADMIN"),
    StaffPlan("teacher1", "demo.teacher1@example.invalid", "시연 선생님1", "TEACHER"),
    StaffPlan("teacher2", "demo.teacher2@example.invalid", "시연 선생님2", "TEACHER"),
    StaffPlan("assistant", "demo.assistant@example.invalid", "시연 조교", "ASSISTANT"),
)

# Fixed past dates (Mondays) so a re-run never creates new lessons; all are before today.
LESSON_DATES = tuple(
    date(2026, month, day)
    for month, day in ((10, 12), (10, 19), (10, 26), (11, 2), (11, 9), (11, 16))
)
ASSIGNED_FROM = ENROLLED_AT = date(2026, 9, 1)

CLASSES = (
    ClassPlan(
        "A",
        "시연 정규 A반",
        "REGULAR",
        (("teacher1", "TEACHER"), ("assistant", "ASSISTANT")),
        (
            "일차함수 개념",
            "일차함수 그래프",
            "연립방정식 기초",
            "연립방정식 활용",
            "부등식",
            "단원 정리",
        ),
    ),
    ClassPlan(
        "B",
        "시연 정규 B반",
        "REGULAR",
        (("teacher2", "TEACHER"),),
        ("문장의 구조", "시제", "조동사", "수동태", "관계대명사", "단원 정리"),
    ),
    ClassPlan(
        "C",
        "시연 내신 대비반",
        "EXAM_PREP",
        (("teacher1", "TEACHER"),),
        ("기출 분석 1", "기출 분석 2", "서술형 대비", "오답 정리", "모의 평가", "최종 점검"),
    ),
)

_MID, _HIGH = "가상중학교", "가상고등학교"
STUDENTS = (
    StudentPlan(
        1,
        "시연학생01",
        _MID,
        "시연보호자01",
        "parent01@example.invalid",
        {"A": "PPPPPP", "C": "PPPPPP"},
    ),
    # Mock Sender: the first send fails temporarily, a manual retry succeeds.
    StudentPlan(
        2, "시연학생02", _MID, "시연보호자02", "parent02@mock-retry.invalid", {"A": "PPLPPP"}
    ),
    # 관심 학생 example: absent twice in the last four lessons.
    StudentPlan(3, "시연학생03", _MID, "시연보호자03", "parent03@example.invalid", {"A": "PPPAPA"}),
    # Excused absence: left out of the attendance-rate denominator.
    StudentPlan(4, "시연학생04", _MID, "시연보호자04", "parent04@example.invalid", {"A": "PPPPEP"}),
    # Last lesson not recorded: shown as 미입력 (not absent); a draft cannot be generated.
    StudentPlan(5, "시연학생05", _MID, "시연보호자05", "parent05@example.invalid", {"A": "PPPPP-"}),
    StudentPlan(
        6, "시연학생06", _HIGH, "시연보호자06", "parent06@example.invalid", {"B": "PPPPPP"}
    ),
    # Mock Sender: always rejected (recipient problem, retry cannot help).
    StudentPlan(
        7, "시연학생07", _HIGH, "시연보호자07", "parent07@mock-fail.invalid", {"B": "PPPPPP"}
    ),
    StudentPlan(
        8, "시연학생08", _HIGH, "시연보호자08", "parent08@example.invalid", {"B": "PPPPAP"}
    ),
    # No parent e-mail: draft generation reports the missing recipient.
    StudentPlan(9, "시연학생09", _HIGH, "시연보호자09", None, {"B": "LPPLPP"}),
    StudentPlan(
        10, "시연학생10", _MID, "시연보호자10", "parent10@example.invalid", {"C": "PPPPPP"}
    ),
    StudentPlan(
        11, "시연학생11", _MID, "시연보호자11", "parent11@example.invalid", {"C": "PAPPPP"}
    ),
    StudentPlan(
        12, "시연학생12", _MID, "시연보호자12", "parent12@example.invalid", {"C": "PPPPPP"}
    ),
)

ATTENDANCE_CODES = {"P": "PRESENT", "L": "LATE", "A": "ABSENT", "E": "EXCUSED"}
GRADES = ("A", "B", "C")
# Assessments linked to a lesson (index into LESSON_DATES); 성적요약 then has content.
ASSESSMENTS = (("10월 단원평가", 2), ("11월 단원평가", 5))
MAX_SCORE = Decimal("100.00")


def assignment_grades(student_no: int, lesson_index: int) -> tuple[str, str]:
    """(prework, weekly) grade for a present / late student — deterministic, mostly A/B."""
    return (
        GRADES[(student_no + lesson_index) % 4 % 3],
        GRADES[(student_no * 2 + lesson_index) % 5 % 3],
    )


def assessment_score(student_no: int, assessment_index: int) -> Decimal:
    return Decimal(55 + (student_no * 7 + assessment_index * 13) % 45).quantize(Decimal("0.01"))


def planned_grade(student: StudentPlan, class_key: str, lesson_index: int):
    """Assessment result for a linked lesson: None = not entered (unrecorded attendance),
    NOT_TAKEN for an absence, otherwise a score."""
    mark = student.attendance[class_key][lesson_index]
    if mark == "-":
        return None
    if mark in "AE":
        return ("NOT_TAKEN", None)
    index = next(i for i, (_, li) in enumerate(ASSESSMENTS) if li == lesson_index)
    return ("SCORED", assessment_score(student.no, index))


def expected_counts() -> dict[str, int]:
    enrollments = sum(len(s.attendance) for s in STUDENTS)
    results = sum(
        sum(1 for mark in marks if mark != "-") for s in STUDENTS for marks in s.attendance.values()
    )
    grades = sum(
        1
        for s in STUDENTS
        for class_key in s.attendance
        for _, lesson_index in ASSESSMENTS
        if planned_grade(s, class_key, lesson_index) is not None
    )
    return {
        "staff": len(STAFF),
        "classrooms": len(CLASSES),
        "assignments": sum(len(c.staff) for c in CLASSES),
        "students": len(STUDENTS),
        "enrollments": enrollments,
        "lessons": len(CLASSES) * len(LESSON_DATES),
        "lesson_results": results,
        "assessments": len(CLASSES) * len(ASSESSMENTS),
        "assessment_results": grades,
    }


# --------------------------------------------------------------------------- guards
def read_passwords() -> dict[str, str]:
    passwords = {}
    for role, name in PASSWORD_ENV.items():
        value = os.getenv(name, "")
        emails = [s.email for s in STAFF if s.role == role]
        problem = next((p for p in (password_problem(value, email=e) for e in emails) if p), None)
        if problem:
            raise SeedError(f"{name}: 12-1024 characters, not the account e-mail")
        passwords[role] = value
    if len(set(passwords.values())) != len(passwords):
        raise SeedError("ACADEMY_SEED_*_PASSWORD values must differ per role")
    return passwords


def check_target(*, seeding: bool):
    """The database URL after every check; raises SeedError otherwise. Names only, no values."""
    if seeding and os.getenv("ACADEMY_SEED_DEMO") != "1":
        raise SeedError("ACADEMY_SEED_DEMO=1 explicit switch is required")
    mode = get_settings().db_mode
    if mode not in ALLOWED_MODES:
        raise SeedError("ACADEMY_DB_MODE must be production (deployment) or test")
    url = require_database_url(get_settings().database_url)
    expected = os.getenv("ACADEMY_SEED_TARGET_HOST", "").strip().lower()
    if not expected or expected != (url.host or "").lower():
        raise SeedError("ACADEMY_SEED_TARGET_HOST must equal the host of ACADEMY_DATABASE_URL")
    return url


def alembic_head() -> str:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(ALEMBIC_INI.parent / "alembic"))
    return ScriptDirectory.from_config(config).get_current_head()


def check_schema(db: Session) -> None:
    exists = db.execute(text("SELECT to_regclass('alembic_version') IS NOT NULL")).scalar_one()
    revision = (
        db.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
        if exists
        else None
    )
    db.rollback()
    if revision != alembic_head():
        raise SeedError("the database is not at the Alembic head; run alembic upgrade head first")


def check_demo_only(db: Session) -> None:
    class_keys = {(c.name, c.class_type) for c in CLASSES}
    student_keys = {(s.name, s.school_name) for s in STUDENTS}
    foreign_classes = [
        row
        for row in db.execute(select(Classroom.name, Classroom.class_type)).all()
        if tuple(row) not in class_keys
    ]
    foreign_students = [
        row
        for row in db.execute(select(Student.name, Student.school_name)).all()
        if tuple(row) not in student_keys
    ]
    by_email = {s.email: s for s in STAFF}
    bad_staff = [
        row.email
        for row in db.scalars(
            select(StaffUser).where(func.lower(StaffUser.email).in_(list(by_email)))
        )
        if row.role != by_email[row.email.lower()].role or row.status != "ACTIVE"
    ]
    db.rollback()
    if foreign_classes or foreign_students:
        raise SeedError(
            f"the database holds {len(foreign_classes)} class(es) and {len(foreign_students)} "
            "student(s) that are not demo data; the demo seed only runs on a demo database"
        )
    if bad_staff:
        raise SeedError(f"{len(bad_staff)} demo account(s) exist with another role or status")


# --------------------------------------------------------------------------- seeding
class Seeder:
    def __init__(self, db: Session, passwords: dict[str, str]):
        self.db = db
        self.passwords = passwords
        self.request_id = str(uuid4())
        self.created: dict[str, int] = {}
        self.staff: dict[str, StaffUser] = {}
        self.classes: dict[str, Classroom] = {}
        self.lessons: dict[tuple[str, int], Lesson] = {}
        self.enrollments: dict[tuple[int, str], Enrollment] = {}

    def _count(self, kind: str, n: int = 1) -> None:
        self.created[kind] = self.created.get(kind, 0) + n

    def run(self) -> dict[str, int]:
        self._admin()
        principal = Principal(
            self.staff["admin"].id, self.staff["admin"].email, "ADMIN", None, self.staff["admin"]
        )  # type: ignore[arg-type]  # services use the id and role only
        self.ops = LearningOpsService(self.db)
        self.academics = AcademicsService(self.db, principal, self.request_id)
        self.principal = principal
        self._staff()
        self._classes()
        self._students()
        self._lessons()
        self._attendance_and_assignment_grades()
        self._assessments()
        return self.created

    def _staff_by_email(self, email: str) -> StaffUser | None:
        return self.db.scalar(select(StaffUser).where(func.lower(StaffUser.email) == email))

    def _admin(self) -> None:
        plan = next(s for s in STAFF if s.role == "ADMIN")
        row = self._staff_by_email(plan.email)
        if row is None:
            # StaffCreate only accepts TEACHER / ASSISTANT (admins come from bootstrap_admin.py);
            # the demo admin is created the same way bootstrap_admin.py does it.
            row = StaffUser(
                email=plan.email,
                display_name=plan.display_name,
                password_hash=hash_password(self.passwords["ADMIN"]),
                role="ADMIN",
                status="ACTIVE",
            )
            self.db.add(row)
            self.db.flush()
            self.db.add(
                AuditLog(
                    actor_staff_user_id=None,
                    event_type="STAFF_CREATED",
                    target_type="STAFF_USER",
                    target_id=str(row.id),
                    request_id=UUID(self.request_id),
                    details={"role": "ADMIN", "status": "ACTIVE", "source": "DEMO_SEED"},
                )
            )
            self.db.commit()
            self._count("staff")
        self.staff["admin"] = row

    def _staff(self) -> None:
        for plan in STAFF:
            if plan.role == "ADMIN":
                continue
            row = self._staff_by_email(plan.email)
            if row is None:
                data = StaffCreate(
                    email=plan.email,
                    display_name=plan.display_name,
                    password=self.passwords[plan.role],
                    role=plan.role,
                )
                row = self.ops.create_staff(data, self.principal, self.request_id)
                self._count("staff")
            self.staff[plan.key] = row

    def _classes(self) -> None:
        for plan in CLASSES:
            row = self.db.scalar(
                select(Classroom).where(
                    Classroom.name == plan.name, Classroom.class_type == plan.class_type
                )
            )
            if row is None:
                data = ClassroomCreate(name=plan.name, class_type=plan.class_type)
                row = self.ops.create_classroom(data, self.principal, self.request_id)
                self._count("classrooms")
            if not row.is_active:
                raise SeedError("a demo class has been ended; resume it in 반 관리 first")
            self.classes[plan.key] = row
            for staff_key, role in plan.staff:
                staff = self.staff[staff_key]
                open_assignment = self.db.scalar(
                    select(ClassroomStaffAssignment.id).where(
                        ClassroomStaffAssignment.classroom_id == row.id,
                        ClassroomStaffAssignment.staff_user_id == staff.id,
                        ClassroomStaffAssignment.valid_to.is_(None),
                    )
                )
                if open_assignment is None:
                    data = AssignmentCreate(
                        staff_user_id=staff.id, assignment_role=role, valid_from=ASSIGNED_FROM
                    )
                    self.ops.assign(row.id, data, self.principal, self.request_id)
                    self._count("assignments")

    def _students(self) -> None:
        for plan in STUDENTS:
            row = self.db.scalar(
                select(Student).where(
                    Student.name == plan.name, Student.school_name == plan.school_name
                )
            )
            if row is None:
                data = StudentCreate(
                    name=plan.name,
                    school_name=plan.school_name,
                    parent_name=plan.parent_name,
                    parent_email=plan.parent_email,
                )
                row = self.ops.create_student(data, self.principal, self.request_id)
                self._count("students")
            for class_key in plan.attendance:
                classroom = self.classes[class_key]
                enrollment = self.db.scalar(
                    select(Enrollment).where(
                        Enrollment.student_id == row.id, Enrollment.classroom_id == classroom.id
                    )
                )
                if enrollment is None:
                    data = EnrollmentCreate(student_id=row.id, enrolled_at=ENROLLED_AT)
                    enrollment = self.ops.enroll(
                        classroom.id, data, self.principal, self.request_id
                    )
                    self._count("enrollments")
                self.enrollments[(plan.no, class_key)] = enrollment

    def _lessons(self) -> None:
        for plan in CLASSES:
            classroom = self.classes[plan.key]
            pairs = zip(LESSON_DATES, plan.topics, strict=True)
            for index, (lesson_date, topic) in enumerate(pairs):
                row = self.db.scalar(
                    select(Lesson).where(
                        Lesson.classroom_id == classroom.id,
                        Lesson.lesson_date == lesson_date,
                        Lesson.session_no == 1,
                        Lesson.exam_round.is_(None),
                    )
                )
                if row is None:
                    data = LessonCreate(lesson_date=lesson_date, topic=topic, status="COMPLETED")
                    row = self.academics.create_lesson(classroom.id, data)
                    self._count("lessons")
                self.lessons[(plan.key, index)] = row

    def _results(self, lesson_id: int) -> dict[int, LessonResult]:
        rows = self.db.scalars(select(LessonResult).where(LessonResult.lesson_id == lesson_id))
        found = {row.enrollment_id: row for row in rows}
        self.db.rollback()  # end the read transaction; services start their own
        return found

    def _attendance_and_assignment_grades(self) -> None:
        for (class_key, index), lesson in self.lessons.items():
            planned = [
                (student, self.enrollments[(student.no, class_key)])
                for student in STUDENTS
                if class_key in student.attendance and student.attendance[class_key][index] != "-"
            ]
            if not self._results(lesson.id):  # only a lesson nobody has recorded yet
                items = [
                    AttendanceItem(
                        enrollment_id=enrollment.id,
                        status=ATTENDANCE_CODES[student.attendance[class_key][index]],
                    )
                    for student, enrollment in planned
                ]
                self.academics.save_attendance(lesson.id, AttendanceBulk(items=items))
                self._count("lesson_results", len(items))
            existing = self._results(lesson.id)
            for student, enrollment in planned:
                if student.attendance[class_key][index] not in "PL":
                    continue
                current = existing.get(enrollment.id)
                # Fill empty grades only (e.g. after an interrupted run); never overwrite.
                if (
                    current is None
                    or current.prework_grade is not None
                    or current.weekly_assignment_grade is not None
                ):
                    continue
                prework, weekly = assignment_grades(student.no, index)
                data = RecordUpdate(
                    result_version=current.version, prework_grade=prework, weekly_grade=weekly
                )
                self.academics.update_record(lesson.id, enrollment.id, data)
                self._count("assignment_grades")

    def _assessments(self) -> None:
        for plan in CLASSES:
            classroom = self.classes[plan.key]
            for title, lesson_index in ASSESSMENTS:
                lesson = self.lessons[(plan.key, lesson_index)]
                row = self.db.scalar(
                    select(Assessment).where(
                        Assessment.lesson_id == lesson.id, Assessment.title == title
                    )
                )
                if row is None:
                    data = AssessmentCreate(
                        title=title,
                        assessment_date=lesson.lesson_date,
                        max_score=MAX_SCORE,
                        lesson_id=lesson.id,
                    )
                    row = self.academics.create_assessment(classroom.id, data)
                    self._count("assessments")
                existing_enrollment_ids = set(
                    self.db.scalars(
                        select(AssessmentResult.enrollment_id).where(
                            AssessmentResult.assessment_id == row.id
                        )
                    )
                )
                self.db.rollback()
                items = []
                for student in STUDENTS:
                    if plan.key not in student.attendance:
                        continue
                    grade = planned_grade(student, plan.key, lesson_index)
                    if grade is None:
                        continue
                    status, score = grade
                    enrollment = self.enrollments[(student.no, plan.key)]
                    if enrollment.id in existing_enrollment_ids:
                        continue
                    items.append(
                        GradeItem(enrollment_id=enrollment.id, result_status=status, score=score)
                    )
                if items:
                    self.academics.save_grades(row.id, GradeBulk(items=items))
                    self._count("assessment_results", len(items))


# --------------------------------------------------------------------------- verification
def verify(db: Session) -> list[str]:
    """Read-only comparison of the demo rows with the plan. Ids and counts only."""
    problems: list[str] = []
    expected = expected_counts()
    emails = [s.email for s in STAFF]
    staff = {
        row.email.lower(): row
        for row in db.scalars(select(StaffUser).where(func.lower(StaffUser.email).in_(emails)))
    }
    for plan in STAFF:
        row = staff.get(plan.email)
        if row is None or row.role != plan.role or row.status != "ACTIVE":
            problems.append(f"staff {plan.key}: missing or not ACTIVE {plan.role}")
    classes = {}
    for plan in CLASSES:
        row = db.scalar(
            select(Classroom).where(
                Classroom.name == plan.name, Classroom.class_type == plan.class_type
            )
        )
        if row is None or not row.is_active:
            problems.append(f"class {plan.key}: missing or ended")
            continue
        classes[plan.key] = row
        for staff_key, role in plan.staff:
            member = staff.get(next(s.email for s in STAFF if s.key == staff_key))
            open_rows = db.scalar(
                select(func.count()).where(
                    ClassroomStaffAssignment.classroom_id == row.id,
                    ClassroomStaffAssignment.staff_user_id == (member.id if member else -1),
                    ClassroomStaffAssignment.assignment_role == role,
                    ClassroomStaffAssignment.valid_to.is_(None),
                )
            )
            if open_rows != 1:
                problems.append(f"class {plan.key}: {staff_key} assignment missing")
    counts = {"students": 0, "enrollments": 0, "lessons": 0, "lesson_results": 0}
    counts |= {"assessments": 0, "assessment_results": 0}
    for student in STUDENTS:
        row = db.scalar(
            select(Student).where(
                Student.name == student.name, Student.school_name == student.school_name
            )
        )
        if row is None:
            problems.append(f"student {student.no:02d}: missing")
            continue
        counts["students"] += 1
        if row.parent_email is not None and not row.parent_email.endswith(".invalid"):
            problems.append(f"student {student.no:02d}: parent e-mail is not a .invalid address")
        for class_key, marks in student.attendance.items():
            if class_key not in classes:
                continue
            enrollment = db.scalar(
                select(Enrollment).where(
                    Enrollment.student_id == row.id,
                    Enrollment.classroom_id == classes[class_key].id,
                )
            )
            if enrollment is None:
                problems.append(f"student {student.no:02d}: not enrolled in class {class_key}")
                continue
            counts["enrollments"] += 1
            for index, mark in enumerate(marks):
                result = db.scalar(
                    select(LessonResult)
                    .join(Lesson, Lesson.id == LessonResult.lesson_id)
                    .where(
                        Lesson.classroom_id == classes[class_key].id,
                        Lesson.lesson_date == LESSON_DATES[index],
                        Lesson.session_no == 1,
                        LessonResult.enrollment_id == enrollment.id,
                    )
                )
                if mark == "-":
                    continue  # left unrecorded on purpose; a demo may have recorded it since
                if result is None:
                    problems.append(
                        f"student {student.no:02d}: class {class_key} lesson {index + 1} "
                        "attendance missing"
                    )
                    continue
                counts["lesson_results"] += 1
    for key, classroom in classes.items():
        counts["lessons"] += db.scalar(
            select(func.count()).where(
                Lesson.classroom_id == classroom.id,
                Lesson.lesson_date.in_(LESSON_DATES),
                Lesson.session_no == 1,
            )
        )
        for title, _ in ASSESSMENTS:
            assessment = db.scalar(
                select(Assessment).where(
                    Assessment.classroom_id == classroom.id, Assessment.title == title
                )
            )
            if assessment is None:
                problems.append(f"class {key}: assessment '{title}' missing")
                continue
            counts["assessments"] += 1
            counts["assessment_results"] += db.scalar(
                select(func.count()).where(AssessmentResult.assessment_id == assessment.id)
            )
    for kind, value in counts.items():
        if value < expected[kind]:
            problems.append(f"{kind}: {value} found, {expected[kind]} expected")
    templates = db.execute(
        text(
            "SELECT count(*) FROM notification_template "
            "WHERE is_active AND default_for_class_type IN ('REGULAR','EXAM_PREP')"
        )
    ).scalar_one()
    if templates != 2:
        problems.append("default message templates (migration 009) are missing")
    non_mock = db.execute(
        text("SELECT count(*) FROM notification_send_attempt WHERE channel <> 'MOCK'")
    ).scalar_one()
    if non_mock:
        problems.append("a non-MOCK send attempt exists")
    db.rollback()
    print("demo rows: " + ", ".join(f"{k}={v}" for k, v in counts.items()))
    return problems


# --------------------------------------------------------------------------- entry point
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Demo (시연) seed for a new demo database")
    parser.add_argument("--check", action="store_true", help="read-only verification only")
    args = parser.parse_args(argv)

    url = check_target(seeding=not args.check)
    passwords = None if args.check else read_passwords()
    print(f"target: {url.host} / {url.database} (mode {get_settings().db_mode})")
    engine = create_db_engine()
    try:
        with create_session_factory(engine)() as db:
            check_schema(db)
            if not args.check:
                check_demo_only(db)
                created = Seeder(db, passwords).run()
                print("created: " + (", ".join(f"{k}={v}" for k, v in created.items()) or "none"))
            problems = verify(db)
    finally:
        engine.dispose()
        passwords = None
    if problems:
        for problem in problems:
            print(f"CHECK FAILED: {problem}", file=sys.stderr)
        return 1
    print("Demo data check passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (SeedError, UnsafeDatabaseError, CompatibilityError) as exc:
        detail = f"{exc.code}: {exc.message}" if isinstance(exc, CompatibilityError) else str(exc)
        print(f"ERROR: {detail}", file=sys.stderr)
        raise SystemExit(1) from None
    except Exception as exc:  # no exception text: it may contain connection details
        print(f"ERROR: demo seed failed ({type(exc).__name__})", file=sys.stderr)
        raise SystemExit(1) from None
