"""Benchmark (벤치마크) students for the weekly-upload test workbook: 60 fictional students in the
five "토6" classes, each with a fictional parent e-mail, so that uploading
``.dev-data/samples/가상학생-60명-5개반-토6.xlsx`` matches every row to a registered student
(MATCHED) and the message flow (drafts → review → mock send / retry) can be exercised.

Kept apart from the demo seed (``seed_demo.py``):
- students are "가상학생01"..."가상학생60" (demo: "시연학생…"), parents "벤치보호자NN",
  e-mails ``bench.parentNN@…`` on reserved ``.invalid`` domains only;
- only the five benchmark classes are used, and they must already exist (created by an admin
  in 반 관리); this script never creates, renames or ends a class or an assignment;
- demo students, classes and their records are never read for writing; ``--check`` confirms
  they are still intact.

Writes go through LearningOpsService (validation, business keys, audit rows). The student's
school follows the class exactly as the upload does (``lesson_upload.workbook.school_of``), so
the student key (name + school) is the one the upload looks for.

Re-running is safe: missing students / enrolments are created, an empty parent e-mail is filled
in (e.g. a student first created by an upload), and nothing else is changed. A different
existing e-mail is reported, never overwritten.

Usage (from ``backend``, same shell setup as seed_demo.py, see the Neon guide):
    python scripts/seed_benchmark.py          # register, then verify
    python scripts/seed_benchmark.py --check  # read-only verification
"""

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import date
from uuid import uuid4

from seed_demo import ALLOWED_MODES, SeedError, check_schema  # same folder (read-only reuse)
from seed_demo import STUDENTS as DEMO_STUDENTS
from sqlalchemy import func, select

from app.config import get_settings
from app.db.models.tables import (
    Classroom,
    ClassroomStaffAssignment,
    Enrollment,
    StaffUser,
    Student,
)
from app.db.safety import UnsafeDatabaseError, require_database_url
from app.db.session import create_db_engine, create_session_factory
from app.errors import CompatibilityError
from app.modules.auth.dependencies import Principal
from app.modules.learningops.schemas import (
    EnrollmentCreate,
    StudentContactUpdate,
    StudentCreate,
)
from app.modules.learningops.service import LearningOpsService
from app.modules.lesson_upload.workbook import class_type_of, school_of

SWITCH = "ACADEMY_SEED_BENCHMARK"
STUDENTS_PER_CLASS = 12
# Enrolment start: before any lesson date the workbook will be uploaded for, so every row is
# eligible (``eligible_on``) and matches instead of asking for a "new student" decision.
ENROLLED_AT = date(2026, 9, 1)
CLASS_NAMES = ("고1 토6A", "고1 토6B", "검증고2 토6", "테스트고2 토6", "가짜고2 토6")
# Present in the sample workbook, one of each per class (Mock Sender rules, sender.py):
RETRY_NOS = frozenset({5, 17, 29, 42, 53})  # first send fails, a manual retry succeeds
FAIL_NOS = frozenset({9, 21, 33, 46, 57})  # always rejected (recipient problem)


@dataclass(frozen=True)
class BenchStudent:
    no: int
    name: str
    class_name: str
    class_type: str
    school_name: str | None
    parent_name: str
    parent_email: str


def _domain(no: int) -> str:
    if no in RETRY_NOS:
        return "mock-retry.invalid"
    if no in FAIL_NOS:
        return "mock-fail.invalid"
    return "example.invalid"


def plan() -> tuple[BenchStudent, ...]:
    students = []
    for index, class_name in enumerate(CLASS_NAMES):
        class_type = class_type_of(class_name)
        for offset in range(1, STUDENTS_PER_CLASS + 1):
            no = index * STUDENTS_PER_CLASS + offset
            students.append(
                BenchStudent(
                    no=no,
                    name=f"가상학생{no:02d}",
                    class_name=class_name,
                    class_type=class_type,
                    school_name=school_of(class_name, class_type),
                    parent_name=f"벤치보호자{no:02d}",
                    parent_email=f"bench.parent{no:02d}@{_domain(no)}",
                )
            )
    return tuple(students)


STUDENTS = plan()


# --------------------------------------------------------------------------- guards
def check_target(*, seeding: bool):
    if seeding and os.getenv(SWITCH) != "1":
        raise SeedError(f"{SWITCH}=1 explicit switch is required")
    mode = get_settings().db_mode
    if mode not in ALLOWED_MODES:
        raise SeedError("ACADEMY_DB_MODE must be production (deployment) or test")
    url = require_database_url(get_settings().database_url)
    expected = os.getenv("ACADEMY_SEED_TARGET_HOST", "").strip().lower()
    if not expected or expected != (url.host or "").lower():
        raise SeedError("ACADEMY_SEED_TARGET_HOST must equal the host of ACADEMY_DATABASE_URL")
    return url


def _student_where(name: str, school: str | None):
    return (Student.name == name, func.coalesce(Student.school_name, "") == (school or ""))


def find_classes(db) -> dict[str, Classroom]:
    """The five benchmark classes, exactly by name and type. Never created here."""
    found, problems = {}, []
    for name in CLASS_NAMES:
        rows = list(db.scalars(select(Classroom).where(Classroom.name == name)))
        exact = [r for r in rows if r.class_type == class_type_of(name) and r.is_active]
        if len(exact) != 1:
            problems.append(f"'{name}' ({class_type_of(name)})")
            continue
        found[name] = exact[0]
    db.rollback()
    if problems:
        raise SeedError(
            "benchmark class missing, ended or of another type — create it in 반 관리 first: "
            + ", ".join(problems)
        )
    return found


def find_admin(db) -> StaffUser:
    """Actor for the audit rows: the demo admin if present, else the oldest active admin."""
    admin = db.scalar(
        select(StaffUser)
        .where(StaffUser.role == "ADMIN", StaffUser.status == "ACTIVE")
        .order_by((func.lower(StaffUser.email) != "demo.admin@example.invalid"), StaffUser.id)
    )
    db.rollback()
    if admin is None:
        raise SeedError("no ACTIVE administrator exists; run seed_demo.py or bootstrap_admin.py")
    return admin


# --------------------------------------------------------------------------- seeding
def register(db, classes: dict[str, Classroom], admin: StaffUser) -> dict[str, int]:
    principal = Principal(admin.id, admin.email, "ADMIN", None, admin)  # type: ignore[arg-type]
    ops = LearningOpsService(db)
    request_id = str(uuid4())
    done = {"students": 0, "enrollments": 0, "emails_filled": 0, "emails_kept": 0}
    for plan_row in STUDENTS:
        classroom = classes[plan_row.class_name]
        student = db.scalar(
            select(Student).where(*_student_where(plan_row.name, plan_row.school_name))
        )
        if student is None:
            data = StudentCreate(
                name=plan_row.name,
                school_name=plan_row.school_name,
                parent_name=plan_row.parent_name,
                parent_email=plan_row.parent_email,
                classroom_id=classroom.id,
                enrolled_at=ENROLLED_AT,
            )
            ops.create_student(data, principal, request_id)
            done["students"] += 1
            done["enrollments"] += 1
            continue
        if student.parent_email is None:
            # e.g. created by an earlier upload ("새 학생"): only the empty fields are filled.
            fields = {"parent_email": plan_row.parent_email}
            if student.parent_name is None:
                fields["parent_name"] = plan_row.parent_name
            ops.update_student_contact(
                student.id, StudentContactUpdate(**fields), principal, request_id
            )
            done["emails_filled"] += 1
        elif student.parent_email != plan_row.parent_email:
            done["emails_kept"] += 1  # someone set another address; it is left as it is
        enrolled = db.scalar(
            select(Enrollment.id).where(
                Enrollment.student_id == student.id, Enrollment.classroom_id == classroom.id
            )
        )
        if enrolled is None:
            data = EnrollmentCreate(student_id=student.id, enrolled_at=ENROLLED_AT)
            ops.enroll(classroom.id, data, principal, request_id)
            done["enrollments"] += 1
        db.rollback()  # end the read transaction (services commit their own writes)
    return done


# --------------------------------------------------------------------------- verification
def verify(db) -> tuple[list[str], list[str]]:
    """(problems, notes). Read-only."""
    problems: list[str] = []
    notes: list[str] = []
    classes = {
        name: db.scalar(select(Classroom).where(Classroom.name == name)) for name in CLASS_NAMES
    }
    domains: dict[str, int] = {}
    for row in STUDENTS:
        classroom = classes[row.class_name]
        student = db.scalar(select(Student).where(*_student_where(row.name, row.school_name)))
        if student is None or classroom is None:
            problems.append(f"{row.name}: not registered")
            continue
        enrollment = db.scalar(
            select(Enrollment).where(
                Enrollment.student_id == student.id, Enrollment.classroom_id == classroom.id
            )
        )
        if enrollment is None:
            problems.append(f"{row.name}: not enrolled in {row.class_name}")
        elif enrollment.status != "ACTIVE" or enrollment.enrolled_at > ENROLLED_AT:
            notes.append(
                f"{row.name}: enrolment {enrollment.status} from {enrollment.enrolled_at} "
                "(the upload matches it only on lesson dates it covers)"
            )
        email = student.parent_email
        if email is None:
            problems.append(f"{row.name}: parent e-mail missing")
        elif not email.endswith(".invalid"):
            problems.append(f"{row.name}: parent e-mail is not a .invalid address")
        elif email != row.parent_email:
            notes.append(f"{row.name}: parent e-mail differs from the plan (kept)")
        if email:
            domain = email.rsplit("@", 1)[-1]
            domains[domain] = domains.get(domain, 0) + 1
    for name, classroom in classes.items():
        if classroom is None:
            continue
        roles = dict(
            db.execute(
                select(ClassroomStaffAssignment.assignment_role, func.count())
                .where(
                    ClassroomStaffAssignment.classroom_id == classroom.id,
                    ClassroomStaffAssignment.valid_to.is_(None),
                )
                .group_by(ClassroomStaffAssignment.assignment_role)
            ).all()
        )
        if not roles.get("TEACHER") or not roles.get("ASSISTANT"):
            notes.append(
                f"{name}: open assignments TEACHER={roles.get('TEACHER', 0)} "
                f"ASSISTANT={roles.get('ASSISTANT', 0)} (assign in 반 관리)"
            )
    # Demo data intact: the 12 demo students exist, keep .invalid e-mails, and none of them is
    # enrolled in a benchmark class.
    demo_rows = [
        db.scalar(select(Student).where(*_student_where(s.name, s.school_name)))
        for s in DEMO_STUDENTS
    ]
    present = [r for r in demo_rows if r is not None]
    bench_ids = [c.id for c in classes.values() if c is not None]
    crossed = db.scalar(
        select(func.count())
        .select_from(Enrollment)
        .where(
            Enrollment.student_id.in_([r.id for r in present] or [-1]),
            Enrollment.classroom_id.in_(bench_ids or [-1]),
        )
    )
    if present and (
        any(r.parent_email and not r.parent_email.endswith(".invalid") for r in present)
        or crossed
    ):
        problems.append("demo students were changed or enrolled in a benchmark class")
    db.rollback()
    print(
        f"benchmark students={len(STUDENTS) - sum('not registered' in p for p in problems)}"
        f"/{len(STUDENTS)}, e-mail domains={dict(sorted(domains.items()))}, "
        f"demo students intact={len(present)}/{len(DEMO_STUDENTS)}"
    )
    return problems, notes


# --------------------------------------------------------------------------- entry point
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark students for the upload workbook")
    parser.add_argument("--check", action="store_true", help="read-only verification only")
    args = parser.parse_args(argv)

    url = check_target(seeding=not args.check)
    print(f"target: {url.host} / {url.database} (mode {get_settings().db_mode})")
    engine = create_db_engine()
    try:
        with create_session_factory(engine)() as db:
            check_schema(db)
            if not args.check:
                classes = find_classes(db)
                done = register(db, classes, find_admin(db))
                print("changes: " + ", ".join(f"{k}={v}" for k, v in done.items()))
            problems, notes = verify(db)
    finally:
        engine.dispose()
    for note in notes:
        print(f"NOTE: {note}")
    if problems:
        for problem in problems:
            print(f"CHECK FAILED: {problem}", file=sys.stderr)
        return 1
    print("Benchmark data check passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (SeedError, UnsafeDatabaseError, CompatibilityError) as exc:
        detail = f"{exc.code}: {exc.message}" if isinstance(exc, CompatibilityError) else str(exc)
        print(f"ERROR: {detail}", file=sys.stderr)
        raise SystemExit(1) from None
    except Exception as exc:  # no exception text: it may contain connection details
        print(f"ERROR: benchmark seed failed ({type(exc).__name__})", file=sys.stderr)
        raise SystemExit(1) from None
