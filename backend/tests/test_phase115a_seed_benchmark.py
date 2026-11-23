"""Benchmark students (scripts/seed_benchmark.py) — unit tests, no database.

The plan must line up with the upload parser (class type, school, names) so that the sample
workbook matches every row, use only reserved .invalid addresses, and stay apart from the demo
seed. Running the script against a database is a separate, user-approved step."""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.modules.learningops.schemas import StudentContactUpdate, StudentCreate
from app.modules.lesson_upload.workbook import class_type_of, parse_workbook, school_of

BACKEND = Path(__file__).resolve().parents[1]
SCRIPTS = BACKEND / "scripts"
SAMPLE = BACKEND.parent / ".dev-data" / "samples" / "가상학생-60명-5개반-토6.xlsx"


def _load(name: str):
    if str(SCRIPTS) not in sys.path:  # seed_benchmark imports seed_demo from its own folder
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bench = _load("seed_benchmark")
demo = _load("seed_demo")

PROD_URL = (
    "postgresql+psycopg://demo_user:not-a-real-secret@ep-demo.example.invalid/neondb"
    "?sslmode=require&channel_binding=require"
)


@pytest.fixture
def prod_env(monkeypatch):
    for name in ("ACADEMY_DB_TEST_MODE", "ACADEMY_RUN_POSTGRES_INTEGRATION"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ACADEMY_DB_MODE", "production")
    monkeypatch.setenv("ACADEMY_DATABASE_URL", PROD_URL)
    monkeypatch.setenv("ACADEMY_SEED_BENCHMARK", "1")
    monkeypatch.setenv("ACADEMY_SEED_TARGET_HOST", "ep-demo.example.invalid")
    return monkeypatch


# ------------------------------------------------------------------------------ guards
def test_benchmark_has_its_own_switch(prod_env):
    prod_env.delenv("ACADEMY_SEED_BENCHMARK")
    prod_env.setenv("ACADEMY_SEED_DEMO", "1")  # the demo switch does not open this script
    with pytest.raises(bench.SeedError, match="ACADEMY_SEED_BENCHMARK"):
        bench.check_target(seeding=True)
    assert bench.check_target(seeding=False).host == "ep-demo.example.invalid"


def test_benchmark_target_guards(prod_env):
    prod_env.setenv("ACADEMY_SEED_TARGET_HOST", "ep-other.example.invalid")
    with pytest.raises(bench.SeedError, match="ACADEMY_SEED_TARGET_HOST"):
        bench.check_target(seeding=True)
    prod_env.setenv("ACADEMY_DB_MODE", "development")
    with pytest.raises(bench.SeedError, match="ACADEMY_DB_MODE"):
        bench.check_target(seeding=True)


# ------------------------------------------------------------------------------ the plan
def test_plan_matches_the_upload_parser():
    assert len(bench.STUDENTS) == 60
    assert len({s.name for s in bench.STUDENTS}) == 60
    types = {name: class_type_of(name) for name in bench.CLASS_NAMES}
    assert types == {
        "고1 토6A": "REGULAR",
        "고1 토6B": "REGULAR",
        "검증고2 토6": "EXAM_PREP",
        "테스트고2 토6": "EXAM_PREP",
        "가짜고2 토6": "EXAM_PREP",
    }
    for name in bench.CLASS_NAMES:
        members = [s for s in bench.STUDENTS if s.class_name == name]
        assert len(members) == 12
        for s in members:
            # Same school the upload gives a new student of that class, i.e. the same key.
            assert s.class_type == types[name]
            assert s.school_name == school_of(name, types[name])


@pytest.mark.skipif(not SAMPLE.exists(), reason="sample workbook is local (.dev-data)")
def test_every_sample_workbook_row_has_a_planned_student():
    planned = {(s.class_name, s.name) for s in bench.STUDENTS}
    rows = [(b.class_name, r.name) for b in parse_workbook(SAMPLE.read_bytes()) for r in b.students]
    assert len(rows) == 60 and set(rows) == planned
    present = {
        r.name for b in parse_workbook(SAMPLE.read_bytes()) for r in b.students
        if r.attendance in ("PRESENT", "LATE")
    }
    # Mock retry / fail scenarios only happen for students who get a draft (attended).
    for no in bench.RETRY_NOS | bench.FAIL_NOS:
        assert f"가상학생{no:02d}" in present


def test_emails_are_fictional_and_cover_the_mock_scenarios():
    emails = [s.parent_email for s in bench.STUDENTS]
    assert len(set(emails)) == 60
    assert all(e.startswith("bench.parent") and e.endswith(".invalid") for e in emails)
    domains = [e.rsplit("@", 1)[1] for e in emails]
    assert domains.count("mock-retry.invalid") == 5
    assert domains.count("mock-fail.invalid") == 5
    assert domains.count("example.invalid") == 50
    for name in bench.CLASS_NAMES:  # one retry and one failure in every class
        class_domains = [s.parent_email.rsplit("@", 1)[1] for s in bench.STUDENTS
                         if s.class_name == name]
        assert class_domains.count("mock-retry.invalid") == 1
        assert class_domains.count("mock-fail.invalid") == 1
    assert all(s.parent_name.startswith("벤치보호자") for s in bench.STUDENTS)


def test_plan_passes_the_application_request_schemas():
    for s in bench.STUDENTS:
        StudentCreate(
            name=s.name,
            school_name=s.school_name,
            parent_name=s.parent_name,
            parent_email=s.parent_email,
            classroom_id=1,
            enrolled_at=bench.ENROLLED_AT,
        )
        StudentContactUpdate(parent_email=s.parent_email, parent_name=s.parent_name)


def test_benchmark_is_kept_apart_from_the_demo_seed():
    bench_keys = {(s.name, s.school_name) for s in bench.STUDENTS}
    demo_keys = {(s.name, s.school_name) for s in demo.STUDENTS}
    assert not bench_keys & demo_keys
    assert not {s.name for s in bench.STUDENTS} & {s.name for s in demo.STUDENTS}
    assert not set(bench.CLASS_NAMES) & {c.name for c in demo.CLASSES}
    demo_emails = {s.parent_email for s in demo.STUDENTS} | {s.email for s in demo.STAFF}
    assert not {s.parent_email for s in bench.STUDENTS} & demo_emails


# ------------------------------------------------------------------------------ behaviour
class RecordingDB:
    """Stands in for a Session: answers reads from a queue and records every method used."""

    def __init__(self, scalars=()):
        self.calls: list[str] = []
        self._queue = list(scalars)

    def scalar(self, _query):
        self.calls.append("scalar")
        return self._queue.pop(0) if self._queue else None

    def scalars(self, _query):
        self.calls.append("scalars")
        return []

    def execute(self, _query):
        self.calls.append("execute")
        return SimpleNamespace(all=list, scalar_one=lambda: 0, scalar_one_or_none=lambda: None)

    def rollback(self):
        self.calls.append("rollback")

    def __getattr__(self, name):  # add / flush / commit / delete / merge …
        def write(*_args, **_kwargs):
            self.calls.append(name)

        return write


class RecordingOps:
    calls: list[str] = []

    def __init__(self, _db):
        pass

    def __getattr__(self, name):
        def call(*_args, **_kwargs):
            RecordingOps.calls.append(name)

        return call


CLASSES = {name: SimpleNamespace(id=i + 1) for i, name in enumerate(bench.CLASS_NAMES)}
ADMIN = SimpleNamespace(id=1, email="demo.admin@example.invalid")


def _register(monkeypatch, per_student):
    RecordingOps.calls = []
    monkeypatch.setattr(bench, "LearningOpsService", RecordingOps)
    queue = [value for s in bench.STUDENTS for value in per_student(s)]
    db = RecordingDB(queue)
    done = bench.register(db, CLASSES, ADMIN)
    return done, RecordingOps.calls, db.calls


def test_rerun_on_complete_data_changes_nothing(monkeypatch):
    def existing(s):  # student with the planned e-mail, already enrolled
        row = SimpleNamespace(id=s.no, parent_email=s.parent_email, parent_name=s.parent_name)
        return [row, 99]

    done, ops, db_calls = _register(monkeypatch, existing)
    assert ops == [] and set(db_calls) <= {"scalar", "rollback"}
    assert done == {"students": 0, "enrollments": 0, "emails_filled": 0, "emails_kept": 0}


def test_first_run_creates_each_student_with_enrolment_once(monkeypatch):
    done, ops, db_calls = _register(monkeypatch, lambda s: [None])
    assert ops == ["create_student"] * 60
    assert done["students"] == done["enrollments"] == 60
    assert set(db_calls) <= {"scalar", "rollback"}  # writes only through the service


def test_empty_contact_is_filled_and_a_different_email_is_kept(monkeypatch):
    def mixed(s):
        if s.no % 2:  # created by an upload: no contact yet, not enrolled here
            return [SimpleNamespace(id=s.no, parent_email=None, parent_name=None), None]
        other = SimpleNamespace(id=s.no, parent_email="other@example.invalid", parent_name="x")
        return [other, 7]

    done, ops, _ = _register(monkeypatch, mixed)
    assert ops.count("update_student_contact") == 30 and ops.count("enroll") == 30
    assert "create_student" not in ops
    assert done["emails_filled"] == 30 and done["emails_kept"] == 30


def test_check_only_reads(monkeypatch):
    db = RecordingDB()
    problems, _ = bench.verify(db)
    assert set(db.calls) <= {"scalar", "scalars", "execute", "rollback"}
    assert any("not registered" in p for p in problems)  # empty answers are reported


def test_benchmark_script_only_adds_and_fills_in():
    source = (SCRIPTS / "seed_benchmark.py").read_text(encoding="utf-8")
    for forbidden in (
        "TRUNCATE", "DROP ", "DELETE ", ".delete(", "delete_", "create_classroom",
        "update_classroom", ".assign(", "create_staff", "smtplib", "httpx", "urllib",
    ):
        assert forbidden not in source
