# ruff: noqa: F811  -- pytest fixtures imported from earlier suites are injected by name
"""Phase 9: notice obligations, status counts, failures and safe manual retry (PostgreSQL)."""

import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from test_phase7_academics_integration import (  # noqa: F401
    FUTURE,
    PAST,
    audit,
    engine,
    login,
    make_lesson,
    send,
    world,
)
from test_phase8_notifications_integration import _approve, _mock, _sql, scene  # noqa: F401

from app.main import app
from app.modules.notifications.sender import MockSender

pytestmark = pytest.mark.postgres
PERIOD = {"date_from": "2026-11-01", "date_to": "2026-11-10"}
OPS = "/api/message-operations"


def _summary(client: TestClient, **period) -> dict:
    response = client.get(f"{OPS}/summary", params=period or PERIOD)
    assert response.status_code == 200, response.text
    return response.json()


def _items(client: TestClient, room: int, **params) -> list[dict]:
    response = client.get(f"{OPS}/obligations", params={"classroom_id": room, **PERIOD, **params})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == len(body["items"])
    return body["items"]


def _retry(client: TestClient, nid: int, key: str | None, csrf: bool = True):
    headers = {"X-CSRF-Token": client.cookies.get("academy_csrf")} if csrf else {}
    if key is not None:
        headers["Idempotency-Key"] = key
    return client.post(f"/api/notifications/{nid}/retry-mock-send", headers=headers)


def _record(client, lesson_id: int, enrollment_id: int, status: str = "PRESENT") -> None:
    item = {"items": [{"enrollment_id": enrollment_id, "status": status}]}
    assert send(client, "PUT", f"/api/lessons/{lesson_id}/attendance", item).status_code == 200


def _draft(client, scene: dict, lesson_id: int, enrollment_id: int, template_id=None) -> dict:
    body = {
        "template_id": template_id or scene["template"]["id"],
        "enrollment_ids": [enrollment_id],
    }
    created = send(client, "POST", f"/api/lessons/{lesson_id}/notifications", body)
    assert created.status_code == 201, created.text
    [nid] = created.json()["created"]
    return client.get(f"/api/notifications/{nid}").json()


def _failed_message(engine: Engine, scene: dict, client, domain: str) -> int:
    """s2 on the scene lesson: recorded, confirmed, mock-sent once → MOCK_FAILED."""
    _sql(
        engine,
        "UPDATE student SET parent_email=:e WHERE id=:s",
        e=f"parent2@{domain}",
        s=scene["s2_student"],
    )
    _record(client, scene["lesson"]["id"], scene["s2"], "ABSENT")
    grade = {"items": [{"enrollment_id": scene["s2"], "result_status": "NOT_TAKEN"}]}
    send(client, "PUT", f"/api/assessments/{scene['assessment']['id']}/grades", grade)
    draft = _draft(client, scene, scene["lesson"]["id"], scene["s2"])
    _approve(client, draft)
    failed = _mock(client, draft["id"], str(uuid.uuid4())).json()
    assert failed["notification"]["status"] == "MOCK_FAILED"
    return draft["id"]


# ------------------------------------------------------------------ sender
def test_mock_sender_rules() -> None:
    sender = MockSender()
    assert sender.send("p@example.invalid", "본문").success
    assert sender.send("p@mock-fail.invalid", "본문", 2).error_code == "MOCK_RECIPIENT_REJECTED"
    first = sender.send("p@mock-retry.invalid", "본문", 1)
    assert (first.success, first.error_code) == (False, "MOCK_TEMPORARY_FAILURE")
    assert "@" not in first.error_message
    assert sender.send("p@mock-retry.invalid", "본문", 2).success
    assert sender.send("p@example.invalid", "  ").error_code == "MOCK_EMPTY_BODY"


# ------------------------------------------------------------ obligations
def test_obligations_separate_due_students_from_exempt_ones(engine: Engine, world: dict) -> None:
    admin, teacher = login("admin"), login("teacher")
    _sql(
        engine,
        "UPDATE student SET parent_email='parent1@example.invalid' WHERE id=:s",
        s=world["s1_student"],
    )
    held = make_lesson(teacher, world["A"], "2026-11-03")  # SCHEDULED, held via attendance
    _record(teacher, held["id"], world["s1"])
    cancelled = make_lesson(teacher, world["A"], "2026-11-04")
    cancel = {"version": cancelled["version"], "status": "CANCELLED"}
    assert send(teacher, "PATCH", f"/api/lessons/{cancelled['id']}", cancel).status_code == 200
    make_lesson(teacher, world["A"], "2026-11-05")  # SCHEDULED, nobody recorded: not held
    paused_day = make_lesson(teacher, world["A"], "2026-11-06", status="COMPLETED")
    make_lesson(teacher, world["A"], FUTURE)  # future lessons are never due
    pause = {"paused_from": "2026-11-06"}
    path = f"/api/classrooms/{world['A']}/enrollments/{world['s2']}/pauses"
    assert send(admin, "POST", path, pause).status_code == 201

    items = _items(teacher, world["A"])
    by = {(i["lesson_date"], i["enrollment_id"]): i for i in items}
    s1, s2, gone = world["s1"], world["s2"], world["withdrawn"]
    # Held lesson: both active students are due; the pause dated later does not change that.
    assert (by[("2026-11-03", s1)]["status"], by[("2026-11-03", s1)]["hints"]) == ("MISSING", [])
    assert by[("2026-11-03", s2)]["status"] == "MISSING"
    assert by[("2026-11-03", s2)]["hints"] == ["보호자 이메일 없음", "출결 미입력"]
    assert by[("2026-11-03", s1)]["next_action"] == "CREATE_DRAFT"
    # Exempt, with reasons: withdrawn (no end date), cancelled, not held, paused on the day.
    assert by[("2026-11-03", gone)]["exempt_reason"] == "NOT_ELIGIBLE"
    assert {by[("2026-11-04", e)]["exempt_reason"] for e in (s1, s2)} == {"LESSON_CANCELLED"}
    assert {by[("2026-11-05", e)]["exempt_reason"] for e in (s1, s2)} == {"LESSON_NOT_HELD"}
    assert by[("2026-11-06", s1)]["status"] == "MISSING"
    assert by[("2026-11-06", s2)]["exempt_reason"] == "NOT_ELIGIBLE"
    assert all(
        i["status"] == "EXEMPT" and i["next_action"] == "NONE" for i in items if not i["obligated"]
    )
    # Enrolled later (11-10) and other classrooms never appear; nor do future lessons.
    assert world["late_joiner"] not in {i["enrollment_id"] for i in items}
    assert world["other"] not in {i["enrollment_id"] for i in items}
    assert FUTURE not in {i["lesson_date"] for i in items}
    assert paused_day

    totals = _summary(teacher)["totals"]
    assert (totals["total"], totals["missing"], totals["exempt"]) == (3, 3, 7)
    assert totals["completion_rate"] == 0.0 and totals["overdue"] is None
    exempt = _items(teacher, world["A"], status="EXEMPT")
    assert len(exempt) == 7 and all(not i["obligated"] for i in exempt)
    # Nothing due → no completion rate (not 0%).
    empty = _summary(teacher, date_from="2026-10-01", date_to="2026-10-31")["totals"]
    assert (empty["total"], empty["completion_rate"]) == (0, None)
    assert _summary(teacher)["deadline_policy"] == "NOT_CONFIGURED"


def test_status_counts_add_up_without_double_counting(engine: Engine, scene: dict) -> None:
    teacher, admin = login("teacher"), login("admin")
    _sql(
        engine,
        "UPDATE student SET parent_email='parent2@example.invalid' WHERE id=:s",
        s=scene["s2_student"],
    )
    lesson = scene["lesson"]
    _record(teacher, lesson["id"], scene["s2"], "ABSENT")
    grade = {"items": [{"enrollment_id": scene["s2"], "result_status": "NOT_TAKEN"}]}
    send(teacher, "PUT", f"/api/assessments/{scene['assessment']['id']}/grades", grade)

    # s1: confirmed and mock-sent → DONE. A second template's draft must not count twice.
    done = _approve(teacher, _draft(teacher, scene, lesson["id"], scene["s1"]))
    assert (
        _mock(teacher, done["id"], str(uuid.uuid4())).json()["notification"]["status"]
        == "MOCK_SENT"
    )
    other = send(
        admin, "POST", "/api/notification-templates", {"name": "보조", "body": "{학생명} 안내"}
    )
    _draft(teacher, scene, lesson["id"], scene["s1"], other.json()["id"])
    # s2: send fails → FAILED, with the stored reason, then the parent e-mail is made unusable.
    _sql(
        engine,
        "UPDATE student SET parent_email='parent2@mock-fail.invalid' WHERE id=:s",
        s=scene["s2_student"],
    )
    failed = _draft(teacher, scene, lesson["id"], scene["s2"], other.json()["id"])
    _approve(teacher, failed)
    _mock(teacher, failed["id"], str(uuid.uuid4()))
    # Second lesson: s1 stays a draft (IN_REVIEW), s2 is confirmed but not sent (READY_TO_SEND).
    second = make_lesson(teacher, scene["A"], "2026-11-04", topic="복습")
    _record(teacher, second["id"], scene["s1"])
    _record(teacher, second["id"], scene["s2"])
    _draft(teacher, scene, second["id"], scene["s1"])
    _approve(teacher, _draft(teacher, scene, second["id"], scene["s2"]))
    # A cancelled message does not satisfy anything.
    cancelled = _draft(teacher, scene, second["id"], scene["s2"], other.json()["id"])
    send(
        teacher,
        "POST",
        f"/api/notifications/{cancelled['id']}/cancel",
        {"version": cancelled["version"]},
    )

    totals = _summary(teacher)["totals"]
    parts = ("missing", "in_review", "ready_to_send", "failed", "done")
    assert {k: totals[k] for k in parts} == {
        "missing": 0,
        "in_review": 1,
        "ready_to_send": 1,
        "failed": 1,
        "done": 1,
    }
    assert totals["total"] == sum(totals[k] for k in parts) == 4
    assert totals["pending"] == 2 and totals["completion_rate"] == 25.0

    items = {(i["lesson_id"], i["enrollment_id"]): i for i in _items(teacher, scene["A"])}
    s1_first = items[(lesson["id"], scene["s1"])]
    assert (s1_first["status"], s1_first["active_messages"], s1_first["attempt_count"]) == (
        "DONE",
        2,
        1,
    )
    s2_first = items[(lesson["id"], scene["s2"])]
    assert s2_first["status"] == "FAILED" and s2_first["next_action"] == "RETRY"
    assert s2_first["failure"]["category"] == "RECIPIENT"
    assert "@" not in s2_first["failure"]["message"]
    assert items[(second["id"], scene["s2"])]["status"] == "READY_TO_SEND"
    assert [i["status"] for i in _items(teacher, scene["A"], status="FAILED")] == ["FAILED"]

    # Classroom endpoint matches the per-classroom row of the summary.
    row = next(c for c in _summary(admin)["classrooms"] if c["classroom_id"] == scene["A"])
    single = teacher.get(f"{OPS}/classrooms/{scene['A']}", params=PERIOD).json()
    assert {k: single[k] for k in parts} == {k: row[k] for k in parts}
    # Admin sees every active classroom; B has nothing due → rate None, not 0%.
    b = next(c for c in _summary(admin)["classrooms"] if c["classroom_id"] == scene["B"])
    assert (b["total"], b["completion_rate"]) == (0, None)
    # A teacher's summary only covers assigned classrooms.
    assert {c["classroom_id"] for c in _summary(teacher)["classrooms"]} == {scene["A"]}


# ------------------------------------------------------------------ retry
def test_manual_retry_keeps_history_and_is_idempotent(engine: Engine, scene: dict) -> None:
    assistant, teacher = login("assistant"), login("teacher")
    nid = _failed_message(engine, scene, teacher, "mock-retry.invalid")
    failed_item = {i["notification_id"]: i for i in _items(teacher, scene["A"])}[nid]
    assert failed_item["failure"]["category"] == "SENDER"

    # The Phase 8 send endpoint still refuses a failed message (its contract is unchanged).
    assert _mock(teacher, nid, str(uuid.uuid4())).json()["code"] == "NOT_APPROVED"
    assert _retry(assistant, nid, None).json()["code"] == "IDEMPOTENCY_KEY_REQUIRED"
    assert _retry(assistant, nid, str(uuid.uuid4()), csrf=False).status_code == 403

    body_before = _sql(
        engine, "SELECT body, approved_at FROM parent_notification WHERE id=:n", n=nid
    ).one()
    key = str(uuid.uuid4())
    retried = _retry(assistant, nid, key)  # assistants may send (Phase 8 policy)
    assert retried.status_code == 200, retried.text
    data = retried.json()
    assert (data["notification"]["status"], data["attempt"]["result"], data["replayed"]) == (
        "MOCK_SENT",
        "MOCK_SUCCESS",
        False,
    )
    # Body and confirmation are untouched; the failed attempt is kept, a new row is added.
    assert (
        _sql(engine, "SELECT body, approved_at FROM parent_notification WHERE id=:n", n=nid).one()
        == body_before
    )
    ledger = _sql(
        engine,
        "SELECT result, error_code FROM notification_send_attempt "
        "WHERE notification_id=:n ORDER BY id",
        n=nid,
    ).all()
    assert ledger == [("MOCK_FAILURE", "MOCK_TEMPORARY_FAILURE"), ("MOCK_SUCCESS", None)]
    retry_event = audit(engine, "NOTIFICATION_MOCK_SEND")[-1].details
    assert (retry_event["from"], retry_event["to"], retry_event["retry"]) == (
        "MOCK_FAILED",
        "MOCK_SENT",
        True,
    )

    replay = _retry(assistant, nid, key).json()
    assert replay["replayed"] is True and replay["attempt"]["id"] == data["attempt"]["id"]
    again = _retry(assistant, nid, str(uuid.uuid4()))
    assert (again.status_code, again.json()["code"]) == (409, "ALREADY_MOCK_SENT")
    assert (
        _sql(
            engine, "SELECT count(*) FROM notification_send_attempt WHERE notification_id=:n", n=nid
        ).scalar()
        == 2
    )

    # Status moves to DONE; the detail shows the full history.
    detail = teacher.get(f"{OPS}/obligations/{scene['lesson']['id']}/{scene['s2']}").json()
    assert detail["status"] == "DONE" and detail["retry_blocked_reason"] is None
    [message] = [m for m in detail["messages"] if m["id"] == nid]
    assert [a["result"] for a in message["attempts"]] == ["MOCK_FAILURE", "MOCK_SUCCESS"]

    # Only failed messages can be retried; a key used for another message is refused.
    draft = _draft(teacher, scene, scene["lesson"]["id"], scene["s1"])
    assert _retry(teacher, draft["id"], str(uuid.uuid4())).json()["code"] == "NOT_FAILED"
    approved = _approve(teacher, draft)
    assert _retry(teacher, approved["id"], str(uuid.uuid4())).json()["code"] == "NOT_FAILED"
    assert _retry(teacher, approved["id"], key).json()["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_retry_refuses_changed_source_and_serialises_concurrent_clicks(
    engine: Engine, scene: dict
) -> None:
    teacher = login("teacher")
    nid = _failed_message(engine, scene, teacher, "mock-fail.invalid")
    # The guardian e-mail was corrected after the failure: the confirmed message is stale.
    _sql(
        engine,
        "UPDATE student SET parent_email='parent2@example.invalid' WHERE id=:s",
        s=scene["s2_student"],
    )
    stale = _retry(teacher, nid, str(uuid.uuid4()))
    assert (stale.status_code, stale.json()["code"]) == (409, "SOURCE_CHANGED")
    detail = teacher.get(f"{OPS}/obligations/{scene['lesson']['id']}/{scene['s2']}").json()
    assert detail["status"] == "FAILED" and detail["retry_blocked_reason"]
    assert (
        _sql(
            engine, "SELECT count(*) FROM notification_send_attempt WHERE notification_id=:n", n=nid
        ).scalar()
        == 1
    )

    # Two staff members retry the same failed message at once: exactly one success.
    current = teacher.get(f"/api/notifications/{nid}").json()
    send(teacher, "POST", f"/api/notifications/{nid}/cancel", {"version": current["version"]})
    _sql(
        engine,
        "UPDATE student SET parent_email='parent2@mock-retry.invalid' WHERE id=:s",
        s=scene["s2_student"],
    )
    draft = _draft(teacher, scene, scene["lesson"]["id"], scene["s2"])
    _approve(teacher, draft)
    assert (
        _mock(teacher, draft["id"], str(uuid.uuid4())).json()["notification"]["status"]
        == "MOCK_FAILED"
    )
    cookies, csrf = dict(teacher.cookies), teacher.cookies.get("academy_csrf")

    def click(_):
        client = TestClient(app, raise_server_exceptions=False, cookies=cookies)
        headers = {"X-CSRF-Token": csrf, "Idempotency-Key": str(uuid.uuid4())}
        return client.post(
            f"/api/notifications/{draft['id']}/retry-mock-send", headers=headers
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(click, range(2))) == [200, 409]
    results = (
        _sql(
            engine,
            "SELECT result FROM notification_send_attempt WHERE notification_id=:n ORDER BY id",
            n=draft["id"],
        )
        .scalars()
        .all()
    )
    assert results == ["MOCK_FAILURE", "MOCK_SUCCESS"]


# ------------------------------------------------------------- security
def test_scope_rbac_idor_csrf_and_revocation(engine: Engine, scene: dict) -> None:
    admin, teacher, assistant = login("admin"), login("teacher"), login("assistant")
    outsider = login("teacher2")
    nid = _failed_message(engine, scene, teacher, "mock-retry.invalid")
    detail_path = f"{OPS}/obligations/{scene['lesson']['id']}/{scene['s2']}"

    assert TestClient(app).get(f"{OPS}/summary", params=PERIOD).status_code == 401
    assert admin.get(detail_path).status_code == 200
    assert assistant.get(detail_path).status_code == 200
    # An unassigned teacher sees no classrooms and cannot read or act on class A.
    hidden = _summary(outsider)
    assert hidden["classrooms"] == [] and hidden["totals"]["total"] == 0
    assert (
        outsider.get(
            f"{OPS}/obligations", params={"classroom_id": scene["A"], **PERIOD}
        ).status_code
        == 403
    )
    assert outsider.get(f"{OPS}/classrooms/{scene['A']}", params=PERIOD).status_code == 403
    assert outsider.get(detail_path).status_code == 403
    assert _retry(outsider, nid, str(uuid.uuid4())).status_code == 403
    # IDOR: class A's lesson with class B's enrollment is not an obligation (no data disclosed).
    assert (
        admin.get(f"{OPS}/obligations/{scene['lesson']['id']}/{scene['other']}").status_code == 404
    )
    assert admin.get(f"{OPS}/obligations/999999/{scene['s1']}").status_code == 404
    # Period validation.
    bad = admin.get(f"{OPS}/summary", params={"date_from": "2026-11-10", "date_to": "2026-11-01"})
    assert (bad.status_code, bad.json()["code"]) == (400, "INVALID_DATE_RANGE")
    long = admin.get(f"{OPS}/summary", params={"date_from": "2026-01-01", "date_to": PAST})
    assert (long.status_code, long.json()["code"]) == (400, "DATE_RANGE_TOO_LONG")

    # Revoked assignment: access is gone at once. Inactive account: session no longer valid.
    assignment = _sql(
        engine,
        "SELECT id FROM classroom_staff_assignment WHERE staff_user_id=:s",
        s=scene["teacher_id"],
    ).scalar()
    send(admin, "DELETE", f"/api/classrooms/{scene['A']}/assignments/{assignment}")
    assert teacher.get(detail_path).status_code == 403
    assert _retry(teacher, nid, str(uuid.uuid4())).status_code == 403
    send(admin, "PATCH", f"/api/staff/{scene['assistant_id']}/status", {"status": "INACTIVE"})
    assert assistant.get(detail_path).status_code == 401
    assert _retry(assistant, nid, str(uuid.uuid4())).status_code == 401
    # Nothing was sent by any refused request.
    assert (
        _sql(
            engine, "SELECT count(*) FROM notification_send_attempt WHERE notification_id=:n", n=nid
        ).scalar()
        == 1
    )


def test_dashboard_todo_lists_unfinished_notices_per_class_lesson_by_urgency(
    engine: Engine, scene: dict
) -> None:
    """Dashboard '성적 안내 할 일' (2026-11-20): which class lesson, what is unfinished, what to do
    next — failed first, then confirmed-but-unsent, then review, then no message yet."""
    teacher = login("teacher")
    lesson = scene["lesson"]["id"]
    _draft(teacher, scene, lesson, scene["s1"])  # s1: waiting for review; s2: no attendance yet
    [item] = teacher.get(f"{OPS}/todo").json()["items"]
    assert (item["classroom_id"], item["lesson_id"], item["next_action"]) == (
        scene["A"],
        lesson,
        "REVIEW",
    )
    assert (item["in_review"], item["missing"], item["missing_no_attendance"]) == (1, 1, 1)

    # An older lesson whose message is confirmed but not sent comes before a review.
    older = make_lesson(teacher, scene["A"], "2026-10-01", topic="복습")  # {수업주제} needs one
    _record(teacher, older["id"], scene["s1"])
    _approve(teacher, _draft(teacher, scene, older["id"], scene["s1"]))
    rows = teacher.get(f"{OPS}/todo").json()["items"]
    assert [(r["lesson_id"], r["next_action"]) for r in rows] == [
        (older["id"], "SEND"),
        (lesson, "REVIEW"),
    ]
    assert rows[1]["missing"] == 1  # s2 on the scene lesson still has no attendance

    # A failed send is the most urgent; a lesson whose notices are all sent leaves the list.
    _failed_message(engine, scene, teacher, "mock-fail.invalid")  # s2 on the scene lesson
    nid = teacher.get(
        "/api/notifications", params={"classroom_id": scene["A"], "lesson_id": older["id"]}
    ).json()["items"][0]["id"]
    assert _mock(teacher, nid, str(uuid.uuid4())).json()["notification"]["status"] == "MOCK_SENT"
    rows = teacher.get(f"{OPS}/todo").json()["items"]
    # The older lesson's sent message is done; only s2 (no attendance there) is left → COMPOSE.
    assert [(r["lesson_id"], r["next_action"], r["failed"]) for r in rows] == [
        (lesson, "RETRY", 1),
        (older["id"], "COMPOSE", 0),
    ]
    assert (rows[1]["ready_to_send"], rows[1]["missing_no_attendance"]) == (0, 1)
    # Only the classes the staff member may see.
    assert login("assistant2").get(f"{OPS}/todo").json()["items"] == []
    assert TestClient(app).get(f"{OPS}/todo").status_code == 401
