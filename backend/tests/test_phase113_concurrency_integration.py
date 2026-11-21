# ruff: noqa: E501  -- SQL kept on one line
"""Phase 11-3-B: concurrency regressions over the real API and the isolated PostgreSQL test DB.

Non-destructive by design (unlike the older suites): no TRUNCATE. Every test inserts its own
fictional rows under a random "P113B<hex>" prefix, so the module can run at any time without
resetting the database. Interleavings are forced with threading.Event pause points around
service functions (patched in this process only) and lock waits are detected from
pg_stat_activity, not from sleeps.
"""

import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.db.session import create_db_engine, get_engine, get_session_factory
from app.main import app
from app.modules.auth.service import hash_password, login_rate_limiter

pytestmark = pytest.mark.postgres
PASSWORD = "correct horse battery staple"
DAY = "2026-11-03"
TEMPLATE = "{학생명} 학생 {수업일자} {분반명}\n출결: {출결}\n{성적요약}"
TIMEOUT = 20


@pytest.fixture(scope="module")
def engine() -> Engine:
    if os.getenv("ACADEMY_RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("ACADEMY_RUN_POSTGRES_INTEGRATION=1 is required")
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    db = create_db_engine()
    with db.connect() as c:
        assert c.execute(text("SELECT current_database(), current_user")).one() == (
            "academy_learningops_test",
            "academy_test",
        )
    yield db
    db.dispose()
    get_engine.cache_clear()
    get_session_factory.cache_clear()


@pytest.fixture(autouse=True)
def env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in {
        "ACADEMY_ENABLE_DB_APIS": "1",
        "ACADEMY_DB_MODE": "test",
        "ACADEMY_DB_TEST_MODE": "1",
        "ACADEMY_COOKIE_SECURE": "0",
        "ACADEMY_API_HOST": "127.0.0.1",
    }.items():
        monkeypatch.setenv(key, value)
    login_rate_limiter.clear()


# ------------------------------------------------------------------------------- helpers
def q(engine: Engine, sql: str, **params):
    with engine.begin() as connection:
        return connection.execute(text(sql), params)


def scene(
    engine: Engine,
    *,
    assessment: bool = True,
    students: int = 2,
    email_domain: str = "example.invalid",
) -> dict:
    """A fictional class: admin + assigned teacher, students with guardian e-mails, one past
    lesson with attendance, optionally a linked 15-point test with scores, an active template."""
    sfx = uuid.uuid4().hex[:8]
    ids: dict = {"sfx": sfx}
    pw = hash_password(PASSWORD)
    for role in ("admin", "teacher"):
        ids[role] = q(
            engine,
            "INSERT INTO staff_user(email,display_name,password_hash,role,status) VALUES(:e,:d,:p,:r,'ACTIVE') RETURNING id",
            e=f"p113b-{sfx}-{role}@example.invalid",
            d=f"P113B {role}",
            p=pw,
            r=role.upper(),
        ).scalar_one()
    ids["class_name"] = f"중3 Q{sfx}"
    ids["classroom"] = q(
        engine,
        "INSERT INTO classroom(name,class_type) VALUES(:n,'REGULAR') RETURNING id",
        n=ids["class_name"],
    ).scalar_one()
    q(
        engine,
        "INSERT INTO classroom_staff_assignment(classroom_id,staff_user_id,assignment_role,valid_from) VALUES(:c,:s,'TEACHER','2026-01-01')",
        c=ids["classroom"],
        s=ids["teacher"],
    )
    ids["lesson"] = q(
        engine,
        "INSERT INTO lesson(classroom_id,lesson_date,session_no,status,topic) VALUES(:c,:d,1,'COMPLETED','P113B') RETURNING id",
        c=ids["classroom"],
        d=date.fromisoformat(DAY),
    ).scalar_one()
    if assessment:
        ids["assessment"] = q(
            engine,
            "INSERT INTO assessment(classroom_id,lesson_id,title,assessment_date,max_score) VALUES(:c,:l,'어휘',:d,15) RETURNING id",
            c=ids["classroom"],
            l=ids["lesson"],
            d=date.fromisoformat(DAY),
        ).scalar_one()
    for i in range(1, students + 1):
        sid = q(
            engine,
            "INSERT INTO student(name,parent_email) VALUES(:n,:m) RETURNING id",
            n=f"P113B{sfx}학생{i}",
            m=f"guardian{i}-{sfx}@{email_domain}",
        ).scalar_one()
        eid = q(
            engine,
            "INSERT INTO enrollment(student_id,classroom_id,status,enrolled_at) VALUES(:s,:c,'ACTIVE','2026-01-01') RETURNING id",
            s=sid,
            c=ids["classroom"],
        ).scalar_one()
        ids[f"s{i}"], ids[f"e{i}"] = sid, eid
        q(
            engine,
            "INSERT INTO lesson_result(lesson_id,enrollment_id,attendance_status) VALUES(:l,:e,'PRESENT')",
            l=ids["lesson"],
            e=eid,
        )
        if assessment:
            q(
                engine,
                "INSERT INTO assessment_result(assessment_id,classroom_id,max_score,enrollment_id,result_status,score) VALUES(:a,:c,15,:e,'SCORED',:s)",
                a=ids["assessment"],
                c=ids["classroom"],
                e=eid,
                s=10 + i,
            )
    ids["template"] = q(
        engine,
        "INSERT INTO notification_template(name,body,is_active) VALUES(:n,:b,true) RETURNING id",
        n=f"P113B {sfx}",
        b=TEMPLATE,
    ).scalar_one()
    return ids


def login(ids: dict, role: str) -> TestClient:
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/api/auth/login",
        json={"email": f"p113b-{ids['sfx']}-{role}@example.invalid", "password": PASSWORD},
    )
    assert response.status_code == 200, response.text
    return client


def call(client: TestClient, method: str, path: str, payload=None, headers=None):
    merged = {"X-CSRF-Token": client.cookies.get("academy_csrf"), **(headers or {})}
    return client.request(method, path, json=payload, headers=merged)


def wait_for_lock_waiter(engine: Engine, future, timeout: float = TIMEOUT) -> bool:
    """True once another session of this DB waits on a lock; False if ``future`` finished first
    (it did not wait). Polls pg_stat_activity — no fixed sleeps decide the outcome."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        waiting = q(
            engine,
            "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND wait_event_type='Lock' AND pid<>pg_backend_pid()",
        ).scalar_one()
        if waiting:
            return True
        if future.done():
            return False
        time.sleep(0.02)
    raise AssertionError("neither a lock wait nor completion was observed")


class Pause:
    """Wraps ``owner.name`` so the first call stops after running (``after=True``) or before."""

    def __init__(self, monkeypatch, owner, name: str, *, after: bool = True):
        self.reached, self.release = threading.Event(), threading.Event()
        original = getattr(owner, name)
        used = {"done": False}

        def wrapper(*args, **kwargs):
            first = not used["done"]
            used["done"] = True
            if first and not after:
                self.reached.set()
                assert self.release.wait(TIMEOUT)
            result = original(*args, **kwargs)
            if first and after:
                self.reached.set()
                assert self.release.wait(TIMEOUT)
            return result

        monkeypatch.setattr(owner, name, wrapper)


# ------------------------------------------------------------------------- INT-03 lesson link
def _empty_lesson(engine: Engine, ids: dict) -> int:
    return q(
        engine,
        "INSERT INTO lesson(classroom_id,lesson_date,session_no,status) VALUES(:c,'2026-11-04',1,'COMPLETED') RETURNING id",
        c=ids["classroom"],
    ).scalar_one()


def _assessment_payload(lesson_id: int) -> dict:
    return {
        "title": f"P113B {uuid.uuid4().hex[:6]}",
        "assessment_date": "2026-11-04",
        "max_score": "10",
        "lesson_id": lesson_id,
    }


def _linked(engine: Engine, lesson_id: int) -> tuple:
    return tuple(
        q(
            engine,
            "SELECT l.status, count(a.id) FROM lesson l LEFT JOIN assessment a ON a.lesson_id=l.id WHERE l.id=:l GROUP BY l.status",
            l=lesson_id,
        ).one()
    )


def test_int03_assessment_on_a_normal_lesson_and_refused_on_a_cancelled_one(engine: Engine) -> None:
    ids = scene(engine, assessment=False, students=1)
    teacher, admin = login(ids, "teacher"), login(ids, "admin")
    ok_lesson = _empty_lesson(engine, ids)
    assert (
        call(
            teacher,
            "POST",
            f"/api/classrooms/{ids['classroom']}/assessments",
            _assessment_payload(ok_lesson),
        ).status_code
        == 201
    )
    cancelled = q(
        engine,
        "INSERT INTO lesson(classroom_id,lesson_date,session_no,status) VALUES(:c,'2026-11-05',1,'CANCELLED') RETURNING id",
        c=ids["classroom"],
    ).scalar_one()
    refused = call(
        teacher,
        "POST",
        f"/api/classrooms/{ids['classroom']}/assessments",
        _assessment_payload(cancelled),
    )
    assert (refused.status_code, refused.json()["code"]) == (400, "INVALID_LESSON_LINK")
    assert _linked(engine, cancelled) == ("CANCELLED", 0)
    assert admin.get(f"/api/lessons/{ok_lesson}").status_code == 200


def test_int03_assessment_first_then_cancel_is_refused(engine: Engine, monkeypatch) -> None:
    """Creation checked the lesson and is about to insert; a cancel arrives. Former result
    (11-3-A R4): both succeeded. Now the cancel waits for the creation and then sees a record."""
    from app.modules.academics.service import AcademicsService

    ids = scene(engine, assessment=False, students=1)
    teacher, admin = login(ids, "teacher"), login(ids, "admin")
    lesson = _empty_lesson(engine, ids)
    pause = Pause(monkeypatch, AcademicsService, "_check_lesson_link")
    with ThreadPoolExecutor(max_workers=2) as pool:
        creating = pool.submit(
            call,
            teacher,
            "POST",
            f"/api/classrooms/{ids['classroom']}/assessments",
            _assessment_payload(lesson),
        )
        assert pause.reached.wait(TIMEOUT)
        cancelling = pool.submit(
            call, admin, "PATCH", f"/api/lessons/{lesson}", {"version": 1, "status": "CANCELLED"}
        )
        cancel_waited = wait_for_lock_waiter(engine, cancelling)
        pause.release.set()
        created, cancelled = creating.result(TIMEOUT), cancelling.result(TIMEOUT)
    assert cancel_waited, "the cancel must wait for the creation that already checked the lesson"
    assert created.status_code == 201
    assert (cancelled.status_code, cancelled.json()["code"]) == (409, "LESSON_HAS_RECORDS")
    assert _linked(engine, lesson) == ("COMPLETED", 1)


def test_int03_cancel_first_then_creation_rechecks_and_is_refused(
    engine: Engine, monkeypatch
) -> None:
    """The cancel holds the lesson; a creation arrives. It must wait and then see CANCELLED —
    not insert an assessment for a lesson that became cancelled meanwhile."""
    from app.modules.academics.repository import AcademicsRepository

    ids = scene(engine, assessment=False, students=1)
    teacher, admin = login(ids, "teacher"), login(ids, "admin")
    lesson = _empty_lesson(engine, ids)
    pause = Pause(
        monkeypatch, AcademicsRepository, "lesson_has_records"
    )  # cancel: locked + checked
    with ThreadPoolExecutor(max_workers=2) as pool:
        cancelling = pool.submit(
            call, admin, "PATCH", f"/api/lessons/{lesson}", {"version": 1, "status": "CANCELLED"}
        )
        assert pause.reached.wait(TIMEOUT)
        creating = pool.submit(
            call,
            teacher,
            "POST",
            f"/api/classrooms/{ids['classroom']}/assessments",
            _assessment_payload(lesson),
        )
        create_waited = wait_for_lock_waiter(engine, creating)
        pause.release.set()
        cancelled, created = cancelling.result(TIMEOUT), creating.result(TIMEOUT)
    assert create_waited
    assert cancelled.status_code == 200
    assert (created.status_code, created.json()["code"]) == (400, "INVALID_LESSON_LINK")
    assert _linked(engine, lesson) == ("CANCELLED", 0)  # nothing partially saved
    audits = q(
        engine,
        "SELECT count(*) FROM audit_log WHERE event_type='ASSESSMENT_CREATED' AND details->>'classroom_id'=:c",
        c=str(ids["classroom"]),
    ).scalar_one()
    assert audits == 0


# ----------------------------------------------------------------- INT-01 send vs source writes
def approved(ids: dict, admin: TestClient, n: int = 2) -> list[int]:
    made = call(
        admin,
        "POST",
        f"/api/lessons/{ids['lesson']}/notifications",
        {"template_id": ids["template"], "enrollment_ids": [ids[f"e{i}"] for i in range(1, n + 1)]},
    )
    assert made.status_code == 201 and len(made.json()["created"]) == n, made.text
    for nid in made.json()["created"]:
        version = admin.get(f"/api/notifications/{nid}").json()["version"]
        assert (
            call(
                admin, "POST", f"/api/notifications/{nid}/approve", {"version": version}
            ).status_code
            == 200
        )
    return made.json()["created"]


def mock_send(client: TestClient, nid: int, *, retry: bool = False):
    path = "retry-mock-send" if retry else "mock-send"
    return call(
        client,
        "POST",
        f"/api/notifications/{nid}/{path}",
        None,
        {"Idempotency-Key": str(uuid.uuid4())},
    )


def message_state(engine: Engine, nid: int) -> tuple:
    return tuple(
        q(
            engine,
            "SELECT n.status, (SELECT count(*) FROM notification_send_attempt a WHERE a.notification_id=n.id), (SELECT count(*) FROM audit_log g WHERE g.target_type='PARENT_NOTIFICATION' AND g.target_id=n.id::text AND g.event_type='NOTIFICATION_MOCK_SEND') FROM parent_notification n WHERE n.id=:n",
            n=nid,
        ).one()
    )


def version_of(engine: Engine, table: str, where: str, **params) -> int:
    return q(engine, f"SELECT version FROM {table} WHERE {where}", **params).scalar_one()


def writers(engine: Engine, ids: dict, admin: TestClient, teacher: TestClient) -> dict:
    """Each source write that can change student 1's message (fictional values)."""
    return {
        "attendance": lambda: call(
            teacher,
            "PUT",
            f"/api/lessons/{ids['lesson']}/attendance",
            {
                "items": [
                    {
                        "enrollment_id": ids["e1"],
                        "status": "ABSENT",
                        "version": version_of(
                            engine,
                            "lesson_result",
                            "lesson_id=:l AND enrollment_id=:e",
                            l=ids["lesson"],
                            e=ids["e1"],
                        ),
                    }
                ]
            },
        ),
        "grade": lambda: call(
            teacher,
            "PUT",
            f"/api/assessments/{ids['assessment']}/grades",
            {
                "items": [
                    {
                        "enrollment_id": ids["e1"],
                        "result_status": "SCORED",
                        "score": "3",
                        "version": version_of(
                            engine,
                            "assessment_result",
                            "assessment_id=:a AND enrollment_id=:e",
                            a=ids["assessment"],
                            e=ids["e1"],
                        ),
                    }
                ]
            },
        ),
        "max_score": lambda: call(
            teacher,
            "PATCH",
            f"/api/assessments/{ids['assessment']}",
            {
                "version": version_of(engine, "assessment", "id=:a", a=ids["assessment"]),
                "max_score": "20",
            },
        ),
        "contact": lambda: call(
            admin,
            "PATCH",
            f"/api/students/{ids['s1']}/contact",
            {"parent_email": f"changed-{ids['sfx']}@example.invalid"},
        ),
        "new_linked_test": lambda: call(
            teacher,
            "POST",
            f"/api/classrooms/{ids['classroom']}/assessments",
            {
                "title": "추가평가",
                "assessment_date": DAY,
                "max_score": "10",
                "lesson_id": ids["lesson"],
            },
        ),
        "class_name": lambda: call(
            admin, "PATCH", f"/api/classrooms/{ids['classroom']}", {"name": f"중3 R{ids['sfx']}"}
        ),
        "lesson_topic": lambda: call(
            admin,
            "PATCH",
            f"/api/lessons/{ids['lesson']}",
            {
                "version": version_of(engine, "lesson", "id=:l", l=ids["lesson"]),
                "topic": "P113B 변경",
            },
        ),
    }


def test_int01_normal_first_send_and_retry(engine: Engine) -> None:
    ids = scene(engine, students=1)
    admin = login(ids, "admin")
    [nid] = approved(ids, admin, 1)
    sent = mock_send(admin, nid)
    assert sent.status_code == 200 and sent.json()["notification"]["status"] == "MOCK_SENT"
    assert message_state(engine, nid) == ("MOCK_SENT", 1, 1)

    retry_ids = scene(engine, students=1, email_domain="mock-retry.invalid")  # first attempt fails
    admin2 = login(retry_ids, "admin")
    [rid] = approved(retry_ids, admin2, 1)
    assert mock_send(admin2, rid).json()["notification"]["status"] == "MOCK_FAILED"
    retried = mock_send(admin2, rid, retry=True)
    assert retried.status_code == 200 and retried.json()["notification"]["status"] == "MOCK_SENT"
    assert message_state(engine, rid) == ("MOCK_SENT", 2, 2)


def test_int01_changed_source_blocks_first_send_and_retry(engine: Engine) -> None:
    ids = scene(engine, students=1)
    admin, teacher = login(ids, "admin"), login(ids, "teacher")
    [nid] = approved(ids, admin, 1)
    assert writers(engine, ids, admin, teacher)["attendance"]().status_code == 200
    refused = mock_send(admin, nid)
    assert (refused.status_code, refused.json()["code"]) == (409, "SOURCE_CHANGED")
    assert message_state(engine, nid) == ("APPROVED", 0, 0)

    retry_ids = scene(engine, students=1, email_domain="mock-retry.invalid")
    admin2, teacher2 = login(retry_ids, "admin"), login(retry_ids, "teacher")
    [rid] = approved(retry_ids, admin2, 1)
    assert mock_send(admin2, rid).json()["notification"]["status"] == "MOCK_FAILED"
    assert writers(engine, retry_ids, admin2, teacher2)["grade"]().status_code == 200
    refused = mock_send(admin2, rid, retry=True)
    assert (refused.status_code, refused.json()["code"]) == (409, "SOURCE_CHANGED")
    assert message_state(engine, rid) == ("MOCK_FAILED", 1, 1)


@pytest.mark.parametrize(
    "writer",
    [
        "attendance",
        "grade",
        "max_score",
        "contact",
        "new_linked_test",
        "class_name",
        "lesson_topic",
    ],
)
def test_int01_source_write_during_send_waits_for_the_send(
    engine: Engine, monkeypatch, writer: str
) -> None:
    """Former result (11-3-A R1): the write did not wait and the message was recorded as sent
    with the old data. Now the write waits until the send committed; the sent body matches the
    data at the moment of sending, and the write is applied afterwards."""
    from app.modules.notifications.service import NotificationService

    ids = scene(engine)
    admin, teacher = login(ids, "admin"), login(ids, "teacher")
    [nid, _] = approved(ids, admin, 2)
    pause = Pause(monkeypatch, NotificationService, "_reject_changed_source")  # source checked
    write = writers(engine, ids, admin, teacher)[writer]
    with ThreadPoolExecutor(max_workers=2) as pool:
        sending = pool.submit(mock_send, admin, nid)
        assert pause.reached.wait(TIMEOUT)
        writing = pool.submit(write)
        waited = wait_for_lock_waiter(engine, writing)
        pause.release.set()
        sent, written = sending.result(TIMEOUT), writing.result(TIMEOUT)
    assert waited, f"{writer}: the source write must wait for the in-flight send"
    assert sent.status_code == 200 and sent.json()["notification"]["status"] == "MOCK_SENT"
    assert written.status_code in (200, 201), written.text
    assert message_state(engine, nid) == ("MOCK_SENT", 1, 1)


@pytest.mark.parametrize("writer", ["attendance", "grade"])
def test_int01_send_waiting_for_a_write_rechecks_and_refuses(
    engine: Engine, monkeypatch, writer: str
) -> None:
    """The write holds its locks first; the send waits, re-reads after the wait and refuses."""
    from app.modules.academics.service import AcademicsService

    ids = scene(engine)
    admin, teacher = login(ids, "admin"), login(ids, "teacher")
    [nid, _] = approved(ids, admin, 2)
    pause = Pause(monkeypatch, AcademicsService, "_validate_items")  # runs after the writer's locks
    write = writers(engine, ids, admin, teacher)[writer]
    with ThreadPoolExecutor(max_workers=2) as pool:
        writing = pool.submit(write)
        assert pause.reached.wait(TIMEOUT)
        sending = pool.submit(mock_send, admin, nid)
        waited = wait_for_lock_waiter(engine, sending)
        pause.release.set()
        written, sent = writing.result(TIMEOUT), sending.result(TIMEOUT)
    assert waited, "the send must wait for the source write"
    assert written.status_code == 200
    assert (sent.status_code, sent.json()["code"]) == (409, "SOURCE_CHANGED")
    assert message_state(engine, nid) == ("APPROVED", 0, 0)  # no success record, no attempt


def test_int01_concurrent_sends_of_one_message_succeed_once(engine: Engine) -> None:
    ids = scene(engine, students=1)
    admin = login(ids, "admin")
    [nid] = approved(ids, admin, 1)
    barrier = threading.Barrier(2)

    def go(_):
        barrier.wait(TIMEOUT)
        return mock_send(
            TestClient(app, raise_server_exceptions=False, cookies=dict(admin.cookies)), nid
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        answers = sorted((r.status_code, r.json().get("code")) for r in pool.map(go, range(2)))
    assert answers == [(200, None), (409, "ALREADY_MOCK_SENT")]
    assert message_state(engine, nid) == ("MOCK_SENT", 1, 1)


def test_int01_lock_timeout_and_failed_write_leave_nothing_behind(
    engine: Engine, monkeypatch
) -> None:
    from app.modules.notifications.repository import NotificationRepository
    from app.modules.notifications.service import NotificationService

    ids = scene(engine, students=1)
    admin = login(ids, "admin")
    [nid] = approved(ids, admin, 1)
    # 1) Lock wait gives up (bounded lock_timeout for this test only): nothing is recorded.
    original = NotificationRepository.lock_sources

    def impatient(self, row):
        self.db.execute(text("SET LOCAL lock_timeout = '300ms'"))
        return original(self, row)

    monkeypatch.setattr(NotificationRepository, "lock_sources", impatient)
    with engine.connect() as holder:
        trans = holder.begin()
        holder.execute(text("SELECT 1 FROM lesson WHERE id=:l FOR SHARE"), {"l": ids["lesson"]})
        timed_out = mock_send(admin, nid)
        trans.rollback()
    # Phase 11-4-A: a lock wait that gives up is a retryable conflict (409), no longer a bare 500.
    assert timed_out.status_code == 409 and timed_out.json()["code"] == "TRANSACTION_CONFLICT"
    assert message_state(engine, nid) == ("APPROVED", 0, 0)
    monkeypatch.setattr(NotificationRepository, "lock_sources", original)
    # 2) The audit row cannot be written: the attempt and the status change roll back with it.
    original_audit = NotificationService._audit

    def broken(self, event, target_type, target_id, details):
        original_audit(self, "X" * 80, target_type, target_id, details)  # > VARCHAR(50)

    monkeypatch.setattr(NotificationService, "_audit", broken)
    assert mock_send(admin, nid).status_code == 500
    assert message_state(engine, nid) == ("APPROVED", 0, 0)
    monkeypatch.setattr(NotificationService, "_audit", original_audit)
    assert mock_send(admin, nid).json()["notification"]["status"] == "MOCK_SENT"  # recovers


def test_int01_parallel_sends_and_attendance_writes_never_record_a_stale_send(
    engine: Engine,
) -> None:
    """Bounded contention: 6 sends and 6 attendance changes (one per student) start together.
    Invariant: no message is MOCK_SENT if its student's attendance change committed before the
    send (audit ids are taken inside each transaction, after its locks)."""
    ids = scene(engine, assessment=False, students=6)
    admin, teacher = login(ids, "admin"), login(ids, "teacher")
    created = approved(ids, admin, 6)
    barrier = threading.Barrier(12)

    def send_one(nid):
        barrier.wait(TIMEOUT)
        return mock_send(
            TestClient(app, raise_server_exceptions=False, cookies=dict(admin.cookies)), nid
        )

    def write_one(i):
        barrier.wait(TIMEOUT)
        client = TestClient(app, raise_server_exceptions=False, cookies=dict(teacher.cookies))
        return call(
            client,
            "PUT",
            f"/api/lessons/{ids['lesson']}/attendance",
            {"items": [{"enrollment_id": ids[f"e{i}"], "status": "LATE", "version": 1}]},
        )

    with ThreadPoolExecutor(max_workers=12) as pool:
        sends = [pool.submit(send_one, nid) for nid in created]
        writes = [pool.submit(write_one, i) for i in range(1, 7)]
        codes = [f.result(TIMEOUT).status_code for f in sends + writes]
    assert 500 not in codes  # no deadlock / unexpected error
    for i, nid in enumerate(created, start=1):
        status = q(engine, "SELECT status FROM parent_notification WHERE id=:n", n=nid).scalar_one()
        sent_at = q(
            engine,
            "SELECT min(id) FROM audit_log WHERE event_type='NOTIFICATION_MOCK_SEND' AND target_id=:n",
            n=str(nid),
        ).scalar_one()
        changed_at = q(
            engine,
            "SELECT min(id) FROM audit_log WHERE event_type='ATTENDANCE_UPDATED' AND details->>'enrollment_id'=:e",
            e=str(ids[f"e{i}"]),
        ).scalar_one()
        if status == "MOCK_SENT":
            assert changed_at is None or changed_at > sent_at, (
                f"student {i}: sent after the change committed"
            )
        else:
            assert status == "APPROVED"


# ------------------------------------------------------------ INT-04 duplicate upload confirm
def _workbook(ids: dict, rows: list) -> bytes:
    from test_phase81_workbook_parser import workbook

    return workbook(
        ("10시", [[ids["class_name"], "출결", "예습 과제", "주간 과제", "어휘 (10)"], *rows])
    )


def _upload(client: TestClient, path: str, content: bytes, **form):
    return client.post(
        f"/api/lesson-uploads/{path}",
        files={
            "file": (
                "w.xlsx",
                content,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        data={"lesson_date": DAY, **form},
        headers={"X-CSRF-Token": client.cookies.get("academy_csrf")},
    )


def _upload_scene(engine: Engine, newcomer: str | None = None):
    ids = scene(engine, assessment=False, students=1)
    teacher = login(ids, "teacher")
    newcomer = newcomer or f"신규Q{ids['sfx']}"
    content = _workbook(
        ids, [[f"P113B{ids['sfx']}학생1", "출석", "A", "B", 9], [newcomer, "출석", "A", "A", 8]]
    )
    rows = {
        r["name"]: r
        for b in _upload(teacher, "preview", content).json()["blocks"]
        for r in b["rows"]
    }
    import json as _json

    return ids, teacher, content, newcomer, _json.dumps({rows[newcomer]["key"]: "NEW"})


def _upload_counts(engine: Engine, ids: dict, newcomer: str) -> dict:
    row = q(
        engine,
        """SELECT (SELECT count(*) FROM student WHERE name=:n),
        (SELECT count(*) FROM enrollment e JOIN student s ON s.id=e.student_id WHERE s.name=:n),
        (SELECT count(*) FROM lesson WHERE classroom_id=:c),
        (SELECT count(*) FROM lesson_result r JOIN lesson l ON l.id=r.lesson_id WHERE l.classroom_id=:c),
        (SELECT count(*) FROM audit_log WHERE event_type='ENROLLMENT_CREATED_FROM_UPLOAD' AND details->>'classroom_id'=:cs),
        (SELECT count(*) FROM audit_log WHERE event_type='LESSON_UPLOAD_APPLIED' AND details->>'classroom_id'=:cs)""",
        n=newcomer,
        c=ids["classroom"],
        cs=str(ids["classroom"]),
    ).one()
    return dict(
        zip(
            ("students", "enrollments", "lessons", "results", "enrol_audits", "applied_audits"),
            row,
            strict=True,
        )
    )


EXPECTED_ONCE = {
    "students": 1,
    "enrollments": 1,
    "lessons": 1,
    "results": 2,
    "enrol_audits": 1,
    "applied_audits": 1,
}


def test_int04_identical_confirm_twice_at_once_is_idempotent(engine: Engine, monkeypatch) -> None:
    """Former result (11-3-A R3): 200 + misleading 409 EXISTING_STUDENT_ELSEWHERE. Now the later
    request waits, re-reads and answers like a sequential re-send: 200 with nothing changed."""
    from app.modules.lesson_upload.service import LessonUploadService

    ids, teacher, content, newcomer, decisions = _upload_scene(engine)
    pause = Pause(
        monkeypatch, LessonUploadService, "_apply_block", after=False
    )  # first: analysed, not applied
    other = TestClient(app, raise_server_exceptions=False, cookies=dict(teacher.cookies))
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(_upload, teacher, "confirm", content, decisions=decisions)
        assert pause.reached.wait(TIMEOUT)
        second = pool.submit(_upload, other, "confirm", content, decisions=decisions)
        waited = wait_for_lock_waiter(engine, second)
        pause.release.set()
        answers = [first.result(TIMEOUT), second.result(TIMEOUT)]
    assert [a.status_code for a in answers] == [200, 200], [a.text for a in answers]
    assert waited, "the second confirm must wait for the first"
    assert (answers[0].json()["new_students"], answers[1].json()["new_students"]) == (1, 0)
    assert answers[1].json()["saved_rows"] == 0 and answers[1].json()["unchanged_rows"] == 2
    assert _upload_counts(engine, ids, newcomer) == EXPECTED_ONCE  # no duplicates, audits once


def test_int04_sequential_resend_matches_the_concurrent_answer(engine: Engine) -> None:
    ids, teacher, content, newcomer, decisions = _upload_scene(engine)
    first = _upload(teacher, "confirm", content, decisions=decisions)
    again = _upload(teacher, "confirm", content, decisions=decisions)
    assert (first.status_code, again.status_code) == (200, 200)
    assert (
        again.json()["new_students"],
        again.json()["saved_rows"],
        again.json()["unchanged_rows"],
    ) == (0, 0, 2)
    assert _upload_counts(engine, ids, newcomer) == EXPECTED_ONCE


def test_int04_different_content_at_once_is_applied_in_order(engine: Engine, monkeypatch) -> None:
    """No idempotency key exists for uploads: different content is not a duplicate. Both are
    applied one after the other under the existing rules (later workbook values win, H2)."""
    from app.modules.lesson_upload.service import LessonUploadService

    ids, teacher, content, newcomer, decisions = _upload_scene(engine)
    changed = _workbook(
        ids, [[f"P113B{ids['sfx']}학생1", "출석", "C", "B", 4], [newcomer, "출석", "A", "A", 8]]
    )
    pause = Pause(monkeypatch, LessonUploadService, "_apply_block", after=False)
    other = TestClient(app, raise_server_exceptions=False, cookies=dict(teacher.cookies))
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(_upload, teacher, "confirm", content, decisions=decisions)
        assert pause.reached.wait(TIMEOUT)
        second = pool.submit(_upload, other, "confirm", changed, decisions=decisions)
        assert wait_for_lock_waiter(engine, second)
        pause.release.set()
        answers = [first.result(TIMEOUT), second.result(TIMEOUT)]
    assert [a.status_code for a in answers] == [200, 200], [a.text for a in answers]
    assert answers[1].json()["saved_rows"] == 1  # only the changed row
    stored = q(
        engine,
        "SELECT r.prework_grade FROM lesson_result r JOIN lesson l ON l.id=r.lesson_id WHERE l.classroom_id=:c AND r.enrollment_id=:e",
        c=ids["classroom"],
        e=ids["e1"],
    ).scalar_one()
    assert stored == "C"


def test_int04_same_new_name_in_two_classes_at_once_is_still_a_conflict(
    engine: Engine, monkeypatch
) -> None:
    """A real identity conflict (SEC-01): two classes register the same new name at the same
    time. One wins; the other is refused — never linked to the other class's student."""
    from app.modules.lesson_upload.service import LessonUploadService

    shared = f"동명Q{uuid.uuid4().hex[:8]}"
    ids_a, teacher_a, content_a, _, decisions_a = _upload_scene(engine, shared)
    ids_b, teacher_b, content_b, _, decisions_b = _upload_scene(engine, shared)
    pause = Pause(monkeypatch, LessonUploadService, "_apply_block", after=False)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(_upload, teacher_a, "confirm", content_a, decisions=decisions_a)
        assert pause.reached.wait(TIMEOUT)
        second = _upload(
            teacher_b, "confirm", content_b, decisions=decisions_b
        )  # other class: no wait
        pause.release.set()
        late = first.result(TIMEOUT)
    assert second.status_code == 200
    assert (late.status_code, late.json()["code"]) == (409, "EXISTING_STUDENT_ELSEWHERE")
    owners = (
        q(
            engine,
            "SELECT e.classroom_id FROM enrollment e JOIN student s ON s.id=e.student_id WHERE s.name=:n",
            n=shared,
        )
        .scalars()
        .all()
    )
    assert owners == [ids_b["classroom"]]  # not reused by class A
    assert (
        _upload_counts(engine, ids_a, shared)["lessons"] == 1
    )  # A: lesson existed, nothing else saved
    assert (
        q(
            engine,
            "SELECT count(*) FROM lesson_result r JOIN lesson l ON l.id=r.lesson_id WHERE l.classroom_id=:c",
            c=ids_a["classroom"],
        ).scalar_one()
        == 1
    )


# ------------------------------------------------------- INT-02 cached test rows in one session
def _keep_linked_tests_alive(monkeypatch) -> list:
    """Hold strong references to the Assessment objects the source check loads — the situation
    in which a session's identity map hands back old attribute values without populate_existing."""
    from app.modules.notifications.repository import NotificationRepository

    kept: list = []
    original = NotificationRepository.linked_grades

    def keep(self, lesson, enrollment_ids):
        assessments, results = original(self, lesson, enrollment_ids)
        kept.extend(assessments)
        return assessments, results

    monkeypatch.setattr(NotificationRepository, "linked_grades", keep)
    return kept


def _change_after_first(monkeypatch, owner, name: str, change) -> None:
    original = getattr(owner, name)
    calls = {"n": 0}

    def wrapper(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        calls["n"] += 1
        if calls["n"] == 1:
            change()  # another staff member's committed change between message 1 and 2
        return result

    monkeypatch.setattr(owner, name, wrapper)


@pytest.mark.parametrize("path", ["batch-approve", "batch-mock-send"])
def test_int02_batch_detects_a_max_score_change_even_with_cached_test_rows(
    engine: Engine, monkeypatch, path: str
) -> None:
    from app.modules.notifications.service import NotificationService

    ids = scene(engine)
    admin = login(ids, "admin")
    made = call(
        admin,
        "POST",
        f"/api/lessons/{ids['lesson']}/notifications",
        {"template_id": ids["template"], "enrollment_ids": [ids["e1"], ids["e2"]]},
    )
    created = made.json()["created"]
    if path == "batch-mock-send":
        for nid in created:
            version = admin.get(f"/api/notifications/{nid}").json()["version"]
            assert (
                call(
                    admin, "POST", f"/api/notifications/{nid}/approve", {"version": version}
                ).status_code
                == 200
            )
        items = [{"id": nid, "idempotency_key": str(uuid.uuid4())} for nid in created]
        step = "mock_send"
    else:
        items = [
            {"id": nid, "version": admin.get(f"/api/notifications/{nid}").json()["version"]}
            for nid in created
        ]
        step = "approve"
    kept = _keep_linked_tests_alive(monkeypatch)
    _change_after_first(
        monkeypatch,
        NotificationService,
        step,
        lambda: q(engine, "UPDATE assessment SET max_score=20 WHERE id=:a", a=ids["assessment"]),
    )
    response = call(
        admin, "POST", f"/api/lessons/{ids['lesson']}/notifications/{path}", {"items": items}
    )
    results = [(r["outcome"], r["code"]) for r in response.json()["results"]]
    assert kept, "the cached test rows were kept alive"
    assert results[1] == ("SKIPPED", "SOURCE_CHANGED"), results
    assert results[0][0] in ("APPROVED", "MOCK_SENT")
