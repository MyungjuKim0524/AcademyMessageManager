# ruff: noqa: F811  -- pytest fixtures imported from the Phase 7 suite are injected by name
"""Phase 8 Stages 4-6: preview, drafts, review/approval and mock send on real PostgreSQL."""

import json
import socket
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from test_phase7_academics_integration import (  # noqa: F401
    PAST,
    audit,
    engine,
    login,
    make_lesson,
    send,
    world,
)

from app.main import app

pytestmark = pytest.mark.postgres
TEMPLATE = (
    "{학생명} 학생 {수업일자} 수업 안내\n주제: {수업주제}\n출결: {출결}\n{보강메시지}\n{성적요약}"
)


def _sql(engine: Engine, sql: str, **params):
    with engine.begin() as connection:
        return connection.execute(text(sql), params)


def _count(engine: Engine, table: str) -> int:
    return _sql(engine, f"SELECT count(*) FROM {table}").scalar()


@pytest.fixture()
def scene(engine: Engine, world: dict) -> dict:
    """Lesson with s1 present + scored, s2 not recorded; parents have fictional e-mails."""
    _sql(
        engine,
        "UPDATE student SET parent_email='parent1@example.invalid' WHERE id=:s",
        s=world["s1_student"],
    )
    _sql(
        engine,
        "UPDATE student SET parent_email='parent2@mock-fail.invalid' WHERE id=:s",
        s=world["s2_student"],
    )
    admin, teacher = login("admin"), login("teacher")
    template = send(
        admin, "POST", "/api/notification-templates", {"name": "기본", "body": TEMPLATE}
    )
    assert template.status_code == 201, template.text
    lesson = make_lesson(teacher, world["A"], topic="이차함수")
    att = {"items": [{"enrollment_id": world["s1"], "status": "PRESENT"}]}
    assert send(teacher, "PUT", f"/api/lessons/{lesson['id']}/attendance", att).status_code == 200
    assessment = send(
        teacher,
        "POST",
        f"/api/classrooms/{world['A']}/assessments",
        {
            "title": "단원 평가",
            "assessment_date": PAST,
            "max_score": 20,
            "lesson_id": lesson["id"],
        },
    ).json()
    grades = {"items": [{"enrollment_id": world["s1"], "result_status": "SCORED", "score": 18}]}
    assert (
        send(teacher, "PUT", f"/api/assessments/{assessment['id']}/grades", grades).status_code
        == 200
    )
    return {**world, "template": template.json(), "lesson": lesson, "assessment": assessment}


def _draft_for_s1(client: TestClient, scene: dict) -> dict:
    body = {"template_id": scene["template"]["id"], "enrollment_ids": [scene["s1"]]}
    created = send(client, "POST", f"/api/lessons/{scene['lesson']['id']}/notifications", body)
    assert created.status_code == 201, created.text
    [notification_id] = created.json()["created"]
    return client.get(f"/api/notifications/{notification_id}").json()


def _approve(teacher: TestClient, detail: dict) -> dict:
    approved = send(
        teacher,
        "POST",
        f"/api/notifications/{detail['id']}/approve",
        {"version": detail["version"]},
    )
    assert approved.status_code == 200, approved.text
    return approved.json()


# --------------------------------------------------------------- templates
def test_template_management_and_validation(engine: Engine, scene: dict) -> None:
    admin, teacher, assistant = login("admin"), login("teacher"), login("assistant")
    bad = send(
        admin, "POST", "/api/notification-templates", {"name": "나쁜", "body": "{password} {학생명"}
    )
    assert (bad.status_code, bad.json()["code"]) == (400, "INVALID_TEMPLATE")
    assert {f["message"] for f in bad.json()["fields"]} >= {"지원하지 않는 변수: {password}"}
    assert (
        send(
            teacher, "POST", "/api/notification-templates", {"name": "x", "body": "{학생명}"}
        ).status_code
        == 403
    )
    assert (
        send(
            admin, "POST", "/api/notification-templates", {"name": "기본", "body": "{학생명}"}
        ).status_code
        == 409
    )
    assert (
        send(
            assistant, "POST", "/api/notification-templates/validate", {"body": "{학생명}"}
        ).status_code
        == 403
    )
    checked = send(admin, "POST", "/api/notification-templates/validate", {"body": TEMPLATE}).json()
    assert checked["ok"] and checked["sample_body"].startswith("가상학생 학생")
    variables = {v["name"] for v in teacher.get("/api/notification-templates/variables").json()}
    assert {"학생명", "출결", "성적요약", "수업주제"} <= variables

    tid = scene["template"]["id"]
    off = send(
        admin, "PATCH", f"/api/notification-templates/{tid}", {"version": 1, "is_active": False}
    )
    assert off.json()["is_active"] is False and off.json()["version"] == 2
    assert (
        teacher.get("/api/notification-templates").json() == []
    )  # staff see active templates only
    assert len(admin.get("/api/notification-templates").json()) == 1
    request = {"template_id": tid}
    blocked = send(
        teacher, "POST", f"/api/lessons/{scene['lesson']['id']}/notifications/preview", request
    )
    assert blocked.json()["code"] == "TEMPLATE_NOT_AVAILABLE"
    stale = send(
        admin, "PATCH", f"/api/notification-templates/{tid}", {"version": 1, "is_active": True}
    )
    assert stale.json()["code"] == "VERSION_CONFLICT"


# ------------------------------------------------------- preview / drafts
def test_preview_writes_nothing_and_reports_missing_data(engine: Engine, scene: dict) -> None:
    assistant = login("assistant")
    path = f"/api/lessons/{scene['lesson']['id']}/notifications"
    before = (_count(engine, "parent_notification"), _count(engine, "audit_log"))
    preview = send(assistant, "POST", f"{path}/preview", {"template_id": scene["template"]["id"]})
    assert preview.status_code == 200, preview.text
    items = {item["enrollment_id"]: item for item in preview.json()["items"]}
    assert set(items) == {scene["s1"], scene["s2"]}  # roster: eligible students only
    s1, s2 = items[scene["s1"]], items[scene["s2"]]
    assert s1["ok"] and "출결: 출석" in s1["body"] and "평가 결과: 단원 평가 18/20" in s1["body"]
    assert not s2["ok"]
    assert "출결 미입력 (결석으로 간주하지 않습니다)" in s2["issues"]
    assert "'단원 평가' 성적 미입력" in s2["issues"]
    assert "결석" not in (s2["body"] or "").replace("결석으로", "")
    assert (_count(engine, "parent_notification"), _count(engine, "audit_log")) == before

    outsider = send(
        assistant,
        "POST",
        f"{path}/preview",
        {"template_id": scene["template"]["id"], "enrollment_ids": [scene["other"]]},
    )
    assert outsider.json()["items"][0]["issues"] == ["이 수업의 반 학생이 아닙니다"]
    assert (
        outsider.json()["items"][0]["student_name"] is None
    )  # nothing about the other class leaks
    paused = send(
        assistant,
        "POST",
        f"{path}/preview",
        {"template_id": scene["template"]["id"], "enrollment_ids": [scene["late_joiner"]]},
    )
    assert (
        "수업일 기준 수강 대상이 아닙니다 (휴원·수강 기간 밖)"
        in paused.json()["items"][0]["issues"]
    )
    assert (
        send(
            login("teacher2"), "POST", f"{path}/preview", {"template_id": scene["template"]["id"]}
        ).status_code
        == 403
    )
    dup = {"template_id": scene["template"]["id"], "enrollment_ids": [scene["s1"], scene["s1"]]}
    assert send(assistant, "POST", f"{path}/preview", dup).json()["code"] == "DUPLICATE_ENROLLMENT"
    too_many = {"template_id": scene["template"]["id"], "enrollment_ids": list(range(1, 102))}
    assert send(assistant, "POST", f"{path}/preview", too_many).status_code == 400


def test_bulk_drafts_are_idempotent_and_skip_blocked_students(engine: Engine, scene: dict) -> None:
    assistant = login("assistant")
    path = f"/api/lessons/{scene['lesson']['id']}/notifications"
    request = {"template_id": scene["template"]["id"]}
    assert assistant.post(path, json=request).status_code == 403  # CSRF required
    first = send(assistant, "POST", path, request).json()
    assert len(first["created"]) == 1
    [skipped] = first["skipped"]
    assert (
        skipped["enrollment_id"] == scene["s2"]
        and "출결 미입력 (결석으로 간주하지 않습니다)" in skipped["reasons"]
    )
    again = send(assistant, "POST", path, request).json()
    assert again["created"] == []
    assert {s["existing_notification_id"] for s in again["skipped"]} == {first["created"][0], None}
    assert _count(engine, "parent_notification") == 1
    [event] = audit(engine, "NOTIFICATION_CREATED")
    assert event.actor_staff_user_id == scene["assistant_id"] and "body" not in event.details

    detail = assistant.get(f"/api/notifications/{first['created'][0]}").json()
    assert detail["status"] == "DRAFT" and detail["recipient"] == "p***@example.invalid"
    assert detail["created_by"] == "assistant" and detail["source_changed"] is False


# ------------------------------------------------------- review / approval
def test_review_edit_approve_revoke_and_history(engine: Engine, scene: dict) -> None:
    teacher, assistant = login("teacher"), login("assistant")
    detail = _draft_for_s1(assistant, scene)
    nid = detail["id"]
    edited = send(
        assistant,
        "PATCH",
        f"/api/notifications/{nid}",
        {"version": 1, "body": "수정된 안내 <script>x</script>"},
    )
    assert edited.status_code == 200 and edited.json()["body"] == "수정된 안내 <script>x</script>"
    assert (
        send(
            assistant, "PATCH", f"/api/notifications/{nid}", {"version": 1, "body": "늦은 수정"}
        ).json()["code"]
        == "VERSION_CONFLICT"
    )
    assert (
        send(
            assistant, "PATCH", f"/api/notifications/{nid}", {"version": 2, "body": "   "}
        ).status_code
        == 400
    )
    submitted = send(assistant, "POST", f"/api/notifications/{nid}/submit", {"version": 2}).json()
    assert submitted["status"] == "READY_FOR_REVIEW"
    # Academy policy: the assistant who prepares the message confirms ("approves") it.
    approved = _approve(assistant, submitted)
    assert (approved["status"], approved["approved_by"]) == ("APPROVED", "assistant")
    locked = send(
        teacher, "PATCH", f"/api/notifications/{nid}", {"version": 4, "body": "승인 후 수정"}
    )
    assert (locked.status_code, locked.json()["code"]) == (409, "NOTIFICATION_LOCKED")
    assert (
        send(teacher, "POST", f"/api/notifications/{nid}/submit", {"version": 4}).json()["code"]
        == "INVALID_TRANSITION"
    )
    unassigned = send(
        login("assistant2"), "POST", f"/api/notifications/{nid}/revoke", {"version": 4}
    )
    assert unassigned.status_code == 403
    revoked = send(teacher, "POST", f"/api/notifications/{nid}/revoke", {"version": 4}).json()
    assert (revoked["status"], revoked["approved_by"], revoked["approved_at"]) == (
        "DRAFT",
        None,
        None,
    )
    assert [h["event_type"] for h in revoked["history"]] == [
        "NOTIFICATION_CREATED",
        "NOTIFICATION_EDITED",
        "NOTIFICATION_SUBMITTED",
        "NOTIFICATION_APPROVED",
        "NOTIFICATION_APPROVAL_REVOKED",
    ]
    assert "수정된 안내" not in json.dumps(
        [h["details"] for h in revoked["history"]], ensure_ascii=False
    )

    # Template edits never rewrite existing messages.
    admin = login("admin")
    tid = scene["template"]["id"]
    send(
        admin,
        "PATCH",
        f"/api/notification-templates/{tid}",
        {"version": 1, "body": "{학생명} 새 문구"},
    )
    after = teacher.get(f"/api/notifications/{nid}").json()
    assert after["body"] == "수정된 안내 <script>x</script>" and after["template_version"] == 1


def test_source_changes_block_approval_until_regenerated(engine: Engine, scene: dict) -> None:
    teacher = login("teacher")
    detail = _draft_for_s1(teacher, scene)
    att = {"items": [{"enrollment_id": scene["s1"], "status": "LATE", "version": 1}]}
    assert (
        send(teacher, "PUT", f"/api/lessons/{scene['lesson']['id']}/attendance", att).status_code
        == 200
    )
    current = teacher.get(f"/api/notifications/{detail['id']}").json()
    assert current["source_changed"] is True and "출결: 출석" in current["body"]  # snapshot kept
    blocked = send(
        teacher,
        "POST",
        f"/api/notifications/{detail['id']}/approve",
        {"version": current["version"]},
    )
    assert (blocked.status_code, blocked.json()["code"]) == (409, "SOURCE_CHANGED")
    cancelled = send(
        teacher,
        "POST",
        f"/api/notifications/{detail['id']}/cancel",
        {"version": current["version"]},
    ).json()
    assert cancelled["status"] == "CANCELLED"
    regenerated = _draft_for_s1(teacher, scene)  # a cancelled message no longer blocks a new one
    assert "출결: 지각" in regenerated["body"]
    assert _approve(teacher, regenerated)["status"] == "APPROVED"


def _attempts_and_sends(engine: Engine, nid: int) -> tuple[int, int]:
    attempts = _sql(
        engine, "SELECT count(*) FROM notification_send_attempt WHERE notification_id=:n", n=nid
    ).scalar()
    sends = _sql(
        engine,
        "SELECT count(*) FROM audit_log WHERE event_type='NOTIFICATION_MOCK_SEND' AND target_id=:t",
        t=str(nid),
    ).scalar()
    return attempts, sends


def test_confirmed_message_is_not_sent_after_its_attendance_changed(
    engine: Engine, scene: dict
) -> None:
    """Phase 10.5 H1: the first send now applies the same source check as the retry."""
    teacher = login("teacher")
    approved = _approve(teacher, _draft_for_s1(teacher, scene))
    assert teacher.get(f"/api/notifications/{approved['id']}").json()["source_changed"] is False
    att = {"items": [{"enrollment_id": scene["s1"], "status": "LATE", "version": 1}]}
    assert (
        send(teacher, "PUT", f"/api/lessons/{scene['lesson']['id']}/attendance", att).status_code
        == 200
    )
    current = teacher.get(f"/api/notifications/{approved['id']}").json()
    # The detail now warns for a confirmed message too (it said False before the fix).
    assert (current["status"], current["source_changed"]) == ("APPROVED", True)
    blocked = _mock(teacher, approved["id"], str(uuid.uuid4()))
    assert (blocked.status_code, blocked.json()["code"]) == (409, "SOURCE_CHANGED")
    assert "모의 발송할 수 없습니다" in blocked.json()["message"]
    after = teacher.get(f"/api/notifications/{approved['id']}").json()
    assert after["status"] == "APPROVED" and after["attempts"] == []  # nothing recorded as sent
    assert _attempts_and_sends(engine, approved["id"]) == (0, 0)


def test_confirmed_message_is_not_sent_after_a_score_it_shows_changed(
    engine: Engine, scene: dict
) -> None:
    """A score change makes a message stale only when its template prints scores."""
    admin, teacher = login("admin"), login("teacher")
    with_scores = _approve(teacher, _draft_for_s1(teacher, scene))  # TEMPLATE has {성적요약}
    plain = send(
        admin,
        "POST",
        "/api/notification-templates",
        {"name": "출결만", "body": "{학생명} 학생 {수업일자} 출결: {출결}"},
    ).json()
    created = send(
        teacher,
        "POST",
        f"/api/lessons/{scene['lesson']['id']}/notifications",
        {"template_id": plain["id"], "enrollment_ids": [scene["s1"]]},
    ).json()["created"]
    without_scores = _approve(teacher, teacher.get(f"/api/notifications/{created[0]}").json())
    grades = {
        "items": [
            {"enrollment_id": scene["s1"], "result_status": "SCORED", "score": 15, "version": 1}
        ]
    }
    saved = send(teacher, "PUT", f"/api/assessments/{scene['assessment']['id']}/grades", grades)
    assert saved.status_code == 200, saved.text

    blocked = _mock(teacher, with_scores["id"], str(uuid.uuid4()))
    assert (blocked.status_code, blocked.json()["code"]) == (409, "SOURCE_CHANGED")
    assert _attempts_and_sends(engine, with_scores["id"]) == (0, 0)
    # The attendance-only message is still accurate: it is sent normally.
    plain_detail = teacher.get(f"/api/notifications/{without_scores['id']}").json()
    assert plain_detail["source_changed"] is False
    key = str(uuid.uuid4())
    sent = _mock(teacher, without_scores["id"], key)
    assert sent.status_code == 200 and sent.json()["notification"]["status"] == "MOCK_SENT"
    # Idempotency is kept: replaying the same key after a later change returns the stored result.
    att = {"items": [{"enrollment_id": scene["s1"], "status": "LATE", "version": 1}]}
    send(teacher, "PUT", f"/api/lessons/{scene['lesson']['id']}/attendance", att)
    replay = _mock(teacher, without_scores["id"], key)
    assert replay.status_code == 200 and replay.json()["replayed"] is True
    assert _attempts_and_sends(engine, without_scores["id"]) == (1, 1)


def test_failed_message_shows_the_change_and_retry_stays_blocked(
    engine: Engine, scene: dict
) -> None:
    teacher = login("teacher")
    att = {"items": [{"enrollment_id": scene["s2"], "status": "ABSENT"}]}
    send(teacher, "PUT", f"/api/lessons/{scene['lesson']['id']}/attendance", att)
    grade = {"items": [{"enrollment_id": scene["s2"], "result_status": "NOT_TAKEN"}]}
    send(teacher, "PUT", f"/api/assessments/{scene['assessment']['id']}/grades", grade)
    body = {"template_id": scene["template"]["id"], "enrollment_ids": [scene["s2"]]}
    [nid] = send(
        teacher, "POST", f"/api/lessons/{scene['lesson']['id']}/notifications", body
    ).json()["created"]
    _approve(teacher, teacher.get(f"/api/notifications/{nid}").json())
    failed = _mock(teacher, nid, str(uuid.uuid4())).json()  # parent2@mock-fail.invalid
    assert failed["notification"]["status"] == "MOCK_FAILED"
    change = {"items": [{"enrollment_id": scene["s2"], "status": "EXCUSED", "version": 1}]}
    send(teacher, "PUT", f"/api/lessons/{scene['lesson']['id']}/attendance", change)
    assert teacher.get(f"/api/notifications/{nid}").json()["source_changed"] is True
    retry = teacher.post(
        f"/api/notifications/{nid}/retry-mock-send",
        headers={
            "X-CSRF-Token": teacher.cookies.get("academy_csrf"),
            "Idempotency-Key": str(uuid.uuid4()),
        },
    )
    assert (retry.status_code, retry.json()["code"]) == (409, "SOURCE_CHANGED")
    assert "재시도할 수 없습니다" in retry.json()["message"]
    assert _attempts_and_sends(engine, nid) == (1, 1)  # only the original failed attempt


def test_concurrent_approvals_produce_one_transition(engine: Engine, scene: dict) -> None:
    teacher = login("teacher")
    detail = _draft_for_s1(teacher, scene)

    def approve(_):
        client = TestClient(app, raise_server_exceptions=False, cookies=dict(teacher.cookies))
        return send(
            client,
            "POST",
            f"/api/notifications/{detail['id']}/approve",
            {"version": detail["version"]},
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(approve, range(2))) == [200, 409]
    assert len(audit(engine, "NOTIFICATION_APPROVED")) == 1


# --------------------------------------------------------------- mock send
def _mock(client: TestClient, nid: int, key: str | None):
    headers = {"X-CSRF-Token": client.cookies.get("academy_csrf")}
    if key is not None:
        headers["Idempotency-Key"] = key
    return client.post(f"/api/notifications/{nid}/mock-send", headers=headers)


def test_mock_send_is_idempotent_and_never_touches_the_network(
    engine: Engine, scene: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_network(*_args, **_kwargs):
        raise AssertionError("mock sender must not open network connections")

    monkeypatch.setattr(socket, "create_connection", no_network)
    # Academy policy: assistants confirm and send; an unassigned assistant cannot.
    teacher, assistant = login("teacher"), login("assistant")
    draft = _draft_for_s1(assistant, scene)
    assert _mock(assistant, draft["id"], str(uuid.uuid4())).json()["code"] == "NOT_APPROVED"
    _approve(assistant, draft)
    assert _mock(assistant, draft["id"], None).json()["code"] == "IDEMPOTENCY_KEY_REQUIRED"
    assert _mock(assistant, draft["id"], "not-a-uuid").status_code == 400
    assert _mock(login("assistant2"), draft["id"], str(uuid.uuid4())).status_code == 403
    assert (
        teacher.post(
            f"/api/notifications/{draft['id']}/mock-send",
            headers={"Idempotency-Key": str(uuid.uuid4())},
        ).status_code
        == 403
    )  # CSRF

    key = str(uuid.uuid4())
    first = _mock(assistant, draft["id"], key)
    assert first.status_code == 200, first.text
    body = first.json()
    assert (body["notification"]["status"], body["attempt"]["result"], body["replayed"]) == (
        "MOCK_SENT",
        "MOCK_SUCCESS",
        False,
    )
    assert body["attempt"]["channel"] == "MOCK"
    replay = _mock(teacher, draft["id"], key).json()
    assert replay["replayed"] is True and replay["attempt"]["id"] == body["attempt"]["id"]
    again = _mock(teacher, draft["id"], str(uuid.uuid4()))
    assert (again.status_code, again.json()["code"]) == (409, "ALREADY_MOCK_SENT")
    assert _count(engine, "notification_send_attempt") == 1
    assert (
        _sql(engine, "SELECT count(*) FROM delivery_job").scalar() == 0
    )  # Java real-send log untouched
    detail = teacher.get(f"/api/notifications/{draft['id']}").json()
    assert [a["result"] for a in detail["attempts"]] == ["MOCK_SUCCESS"]
    assert detail["history"][-1]["event_type"] == "NOTIFICATION_MOCK_SEND"


def test_mock_failure_is_recorded_and_not_retried_here(engine: Engine, scene: dict) -> None:
    teacher = login("teacher")
    att = {"items": [{"enrollment_id": scene["s2"], "status": "ABSENT"}]}
    send(teacher, "PUT", f"/api/lessons/{scene['lesson']['id']}/attendance", att)
    grade = {"items": [{"enrollment_id": scene["s2"], "result_status": "NOT_TAKEN"}]}
    send(teacher, "PUT", f"/api/assessments/{scene['assessment']['id']}/grades", grade)
    body = {"template_id": scene["template"]["id"], "enrollment_ids": [scene["s2"]]}
    [nid] = send(
        teacher, "POST", f"/api/lessons/{scene['lesson']['id']}/notifications", body
    ).json()["created"]
    draft = teacher.get(f"/api/notifications/{nid}").json()
    assert "출결: 결석" in draft["body"] and "단원 평가 미응시" in draft["body"]
    _approve(teacher, draft)
    failed = _mock(teacher, nid, str(uuid.uuid4())).json()
    assert (failed["notification"]["status"], failed["attempt"]["error_code"]) == (
        "MOCK_FAILED",
        "MOCK_RECIPIENT_REJECTED",
    )
    assert "@" not in failed["attempt"]["error_message"]  # no recipient in the error
    assert (
        _mock(teacher, nid, str(uuid.uuid4())).json()["code"] == "NOT_APPROVED"
    )  # retry is Phase 9
    rows = _sql(
        engine,
        "SELECT result, error_code FROM notification_send_attempt WHERE notification_id=:n",
        n=nid,
    ).all()
    assert rows == [("MOCK_FAILURE", "MOCK_RECIPIENT_REJECTED")]
    current = teacher.get(f"/api/notifications/{nid}").json()
    assert (
        send(
            teacher, "POST", f"/api/notifications/{nid}/cancel", {"version": current["version"]}
        ).json()["status"]
        == "CANCELLED"
    )


def test_concurrent_mock_sends_and_key_reuse(engine: Engine, scene: dict) -> None:
    teacher = login("teacher")
    approved = _approve(teacher, _draft_for_s1(teacher, scene))

    def fire(key):
        client = TestClient(app, raise_server_exceptions=False, cookies=dict(teacher.cookies))
        return _mock(client, approved["id"], key).status_code

    keys = [str(uuid.uuid4()), str(uuid.uuid4())]
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(fire, keys)) == [200, 409]
    assert (
        _sql(
            engine, "SELECT count(*) FROM notification_send_attempt WHERE result='MOCK_SUCCESS'"
        ).scalar()
        == 1
    )
    other = _sql(
        engine, "SELECT idempotency_key::text FROM notification_send_attempt LIMIT 1"
    ).scalar()

    # A second, freshly approved message (its fictional parent domain makes the mock fail).
    att = {"items": [{"enrollment_id": scene["s2"], "status": "PRESENT"}]}
    send(teacher, "PUT", f"/api/lessons/{scene['lesson']['id']}/attendance", att)
    grade = {"items": [{"enrollment_id": scene["s2"], "result_status": "SCORED", "score": 1}]}
    send(teacher, "PUT", f"/api/assessments/{scene['assessment']['id']}/grades", grade)
    body = {"template_id": scene["template"]["id"], "enrollment_ids": [scene["s2"]]}
    [nid] = send(
        teacher, "POST", f"/api/lessons/{scene['lesson']['id']}/notifications", body
    ).json()["created"]
    _approve(teacher, teacher.get(f"/api/notifications/{nid}").json())

    # Same key sent twice at once: the second waits for the row lock and replays the first result.
    same = str(uuid.uuid4())

    def fire_second(key):
        client = TestClient(app, raise_server_exceptions=False, cookies=dict(teacher.cookies))
        return _mock(client, nid, key).json()

    with ThreadPoolExecutor(max_workers=2) as pool:
        answers = list(pool.map(fire_second, [same, same]))
    assert sorted(a["replayed"] for a in answers) == [False, True]
    assert len({a["attempt"]["id"] for a in answers}) == 1
    count = "SELECT count(*) FROM notification_send_attempt WHERE notification_id=:n"
    assert _sql(engine, count, n=nid).scalar() == 1

    # Reusing a key that belongs to another message is rejected.
    assert _mock(teacher, nid, other).json()["code"] == "IDEMPOTENCY_KEY_REUSED"


# ------------------------------------------------------------- authorization
def test_cross_classroom_access_revocation_and_inactive_staff(engine: Engine, scene: dict) -> None:
    admin, teacher, assistant = login("admin"), login("teacher"), login("assistant")
    detail = _draft_for_s1(teacher, scene)
    nid = detail["id"]
    outsiders = [login("teacher2"), login("assistant2")]
    for client in outsiders:
        assert client.get(f"/api/notifications/{nid}").status_code == 403  # IDOR by id
        assert (
            client.get("/api/notifications", params={"classroom_id": scene["A"]}).status_code == 403
        )
        assert (
            send(
                client, "PATCH", f"/api/notifications/{nid}", {"version": 1, "body": "x"}
            ).status_code
            == 403
        )
        assert (
            send(client, "POST", f"/api/notifications/{nid}/approve", {"version": 1}).status_code
            == 403
        )
    assert (
        teacher.get("/api/notifications", params={"classroom_id": scene["A"]}).json()["items"][0][
            "id"
        ]
        == nid
    )
    assert TestClient(app).get(f"/api/notifications/{nid}").status_code == 401

    assignment = _sql(
        engine,
        "SELECT id FROM classroom_staff_assignment WHERE staff_user_id=:s",
        s=scene["teacher_id"],
    ).scalar()
    send(admin, "DELETE", f"/api/classrooms/{scene['A']}/assignments/{assignment}")
    assert teacher.get(f"/api/notifications/{nid}").status_code == 403
    assert _mock(teacher, nid, str(uuid.uuid4())).status_code == 403
    send(admin, "PATCH", f"/api/staff/{scene['assistant_id']}/status", {"status": "INACTIVE"})
    assert assistant.get(f"/api/notifications/{nid}").status_code == 401
    assert admin.get(f"/api/notifications/{nid}").status_code == 200


# ------------------------------------------------------- guardian contact
def test_admin_updates_guardian_contact_and_drafts_notice_it(engine: Engine, scene: dict) -> None:
    admin, teacher = login("admin"), login("teacher")
    student = scene["s1_student"]
    path = f"/api/students/{student}/contact"
    assert teacher.get(path).status_code == 403
    assert send(teacher, "PATCH", path, {"parent_email": "x@example.invalid"}).status_code == 403
    assert admin.get(path).json()["parent_email"] == "parent1@example.invalid"
    assert admin.patch(path, json={"parent_email": "x@example.invalid"}).status_code == 403  # CSRF
    assert send(admin, "PATCH", path, {"parent_email": "not-an-email"}).status_code == 400
    assert send(admin, "PATCH", path, {"name": "바꾼 이름"}).status_code == 400  # mass assignment
    assert admin.get("/api/students/999999/contact").status_code == 404

    draft = _draft_for_s1(teacher, scene)
    updated = send(
        admin,
        "PATCH",
        path,
        {"parent_email": "  New.Parent@Example.invalid ", "parent_name": "보호자"},
    )
    assert updated.status_code == 200, updated.text
    assert (updated.json()["parent_email"], updated.json()["parent_name"]) == (
        "new.parent@example.invalid",
        "보호자",
    )
    [event] = audit(engine, "STUDENT_CONTACT_UPDATED")
    assert event.actor_staff_user_id == scene["admin_id"]
    assert event.details == {
        "changed": ["parent_email", "parent_name"],
        "parent_email_present": True,
    }
    assert "example" not in json.dumps(event.details)

    # The unconfirmed draft still holds the old address, so it cannot be confirmed any more.
    current = teacher.get(f"/api/notifications/{draft['id']}").json()
    assert current["source_changed"] is True and current["recipient"] == "p***@example.invalid"
    blocked = send(
        teacher,
        "POST",
        f"/api/notifications/{draft['id']}/approve",
        {"version": current["version"]},
    )
    assert blocked.json()["code"] == "SOURCE_CHANGED"
    send(
        teacher, "POST", f"/api/notifications/{draft['id']}/cancel", {"version": current["version"]}
    )
    regenerated = _draft_for_s1(teacher, scene)
    # Detail shows the full address to assigned staff (who confirm/send); lists stay masked.
    assert regenerated["recipient"] == "n***@example.invalid"
    assert regenerated["recipient_email"] == "new.parent@example.invalid"
    listed = teacher.get("/api/notifications", params={"classroom_id": scene["A"]}).json()["items"]
    assert "recipient_email" not in listed[0] and listed[-1]["recipient"].startswith("n***@")

    # Guardian contact appears in the student list for administrators only.
    students = f"/api/classrooms/{scene['A']}/students"
    by_admin = {row["id"]: row for row in admin.get(students).json()["items"]}
    assert by_admin[student]["parent_email"] == "new.parent@example.invalid"
    assert by_admin[student]["parent_name"] == "보호자"
    by_teacher = teacher.get(students)
    assert "parent" not in by_teacher.text  # keys are absent, not merely null
    assert by_teacher.json()["items"][0]["enrollment_id"]  # other fields unaffected

    # Unchanged values are a no-op; clearing the e-mail blocks new messages.
    assert send(admin, "PATCH", path, {"parent_name": "보호자"}).status_code == 200
    assert len(audit(engine, "STUDENT_CONTACT_UPDATED")) == 1
    assert send(admin, "PATCH", path, {"parent_email": ""}).json()["parent_email"] is None
    preview = send(
        teacher,
        "POST",
        f"/api/lessons/{scene['lesson']['id']}/notifications/preview",
        {"template_id": scene["template"]["id"], "enrollment_ids": [scene["s1"]]},
    ).json()
    assert "보호자 이메일이 등록되어 있지 않습니다" in preview["items"][0]["issues"]


# ------------------------------------------------ class batch (2026-11-20)
def _two_drafts(teacher: TestClient, scene: dict) -> dict[str, dict]:
    """s1 present + 18/20 (parent1@example.invalid); s2 absent + 미응시 (mock sender rejects)."""
    lesson = scene["lesson"]["id"]
    att = {"items": [{"enrollment_id": scene["s2"], "status": "ABSENT"}]}
    assert send(teacher, "PUT", f"/api/lessons/{lesson}/attendance", att).status_code == 200
    grade = {"items": [{"enrollment_id": scene["s2"], "result_status": "NOT_TAKEN"}]}
    send(teacher, "PUT", f"/api/assessments/{scene['assessment']['id']}/grades", grade)
    body = {"template_id": scene["template"]["id"]}
    created = send(teacher, "POST", f"/api/lessons/{lesson}/notifications", body).json()["created"]
    assert len(created) == 2
    view = teacher.get(f"/api/lessons/{lesson}/notifications/batch").json()
    return {item["student_name"]: item for item in view["items"]}


def _batch(client: TestClient, scene: dict, action: str, items: list[dict]):
    path = f"/api/lessons/{scene['lesson']['id']}/notifications/batch-{action}"
    return send(client, "POST", path, {"items": items})


def test_class_batch_confirms_the_chosen_messages_and_sends_each_on_its_own(
    engine: Engine, scene: dict
) -> None:
    """One class lesson on one screen: chosen messages are confirmed, confirmed ones are sent.
    Each message keeps its own version check, transaction, idempotency key and audit row."""
    assistant = login("assistant")
    drafts = _two_drafts(assistant, scene)
    s1, s2 = drafts["s1"], drafts["s2"]
    assert (s1["status"], s1["attention"], s1["source_changed"]) == ("DRAFT", [], False)
    assert s2["attention"] == ["결석", "미응시"] and "출결: 결석" in s2["body"]
    assert s1["recipient"] == "p***@example.invalid"  # masked, as in the list

    chosen = [
        {"id": s1["id"], "version": s1["version"]},
        {"id": s2["id"], "version": s2["version"]},
    ]
    approved = _batch(assistant, scene, "approve", [*chosen, {"id": 999999, "version": 1}])
    assert approved.status_code == 200, approved.text
    outcome = {r["id"]: (r["outcome"], r["code"]) for r in approved.json()["results"]}
    assert outcome == {
        s1["id"]: ("APPROVED", None),
        s2["id"]: ("APPROVED", None),
        999999: ("SKIPPED", "NOT_IN_LESSON"),
    }
    events = audit(engine, "NOTIFICATION_APPROVED")
    assert len(events) == 2 and all(e.details["batch"] is True for e in events)
    # The same request again: the versions are stale now, so nothing is confirmed twice.
    again = _batch(assistant, scene, "approve", chosen).json()["results"]
    assert {r["code"] for r in again} == {"VERSION_CONFLICT"}
    assert len(audit(engine, "NOTIFICATION_APPROVED")) == 2

    keys = {s1["id"]: str(uuid.uuid4()), s2["id"]: str(uuid.uuid4())}
    items = [{"id": nid, "idempotency_key": key} for nid, key in keys.items()]
    sent = _batch(assistant, scene, "mock-send", items).json()["results"]
    by_id = {r["id"]: r for r in sent}
    assert (by_id[s1["id"]]["outcome"], by_id[s1["id"]]["replayed"]) == ("MOCK_SENT", False)
    assert (by_id[s2["id"]]["outcome"], by_id[s2["id"]]["code"]) == (
        "MOCK_FAILED",
        "MOCK_RECIPIENT_REJECTED",
    )  # one failure does not stop or undo the other message
    assert _count(engine, "notification_send_attempt") == 2
    assert all(e.details["batch"] is True for e in audit(engine, "NOTIFICATION_MOCK_SEND"))

    # The answer was lost and the client repeats the request with the same keys: replayed.
    repeat = {r["id"]: r for r in _batch(assistant, scene, "mock-send", items).json()["results"]}
    assert repeat[s1["id"]]["replayed"] and repeat[s2["id"]]["replayed"]
    assert _count(engine, "notification_send_attempt") == 2
    # A new key retries the failed message (as '모의 발송 재시도'); the sent one is refused.
    fresh = [{"id": nid, "idempotency_key": str(uuid.uuid4())} for nid in keys]
    retried = {r["id"]: r for r in _batch(assistant, scene, "mock-send", fresh).json()["results"]}
    assert retried[s2["id"]]["outcome"] == "MOCK_FAILED"
    assert (retried[s1["id"]]["outcome"], retried[s1["id"]]["code"]) == (
        "SKIPPED",
        "ALREADY_MOCK_SENT",
    )
    assert _attempts_and_sends(engine, s2["id"]) == (2, 2)
    assert _attempts_and_sends(engine, s1["id"]) == (1, 1)


def test_class_batch_skips_changed_messages_and_respects_access(
    engine: Engine, scene: dict
) -> None:
    teacher = login("teacher")
    drafts = _two_drafts(teacher, scene)
    s1, s2 = drafts["s1"], drafts["s2"]
    # s1's attendance changes after generation: shown on the batch screen and never confirmed.
    att = {"items": [{"enrollment_id": scene["s1"], "status": "LATE", "version": 1}]}
    path = f"/api/lessons/{scene['lesson']['id']}/attendance"
    assert send(teacher, "PUT", path, att).status_code == 200
    view = teacher.get(f"/api/lessons/{scene['lesson']['id']}/notifications/batch").json()
    changed = {i["student_name"]: i["source_changed"] for i in view["items"]}
    assert changed == {"s1": True, "s2": False}
    items = [{"id": s1["id"], "version": s1["version"]}, {"id": s2["id"], "version": s2["version"]}]
    results = {r["id"]: r for r in _batch(teacher, scene, "approve", items).json()["results"]}
    assert (results[s1["id"]]["outcome"], results[s1["id"]]["code"]) == (
        "SKIPPED",
        "SOURCE_CHANGED",
    )
    assert results[s2["id"]]["outcome"] == "APPROVED"
    assert teacher.get(f"/api/notifications/{s1['id']}").json()["status"] == "DRAFT"
    # A confirmed message whose source changes is not sent by the batch either.
    grade = {
        "items": [
            {"enrollment_id": scene["s2"], "result_status": "SCORED", "score": 5, "version": 1}
        ]
    }
    grades_path = f"/api/assessments/{scene['assessment']['id']}/grades"
    assert send(teacher, "PUT", grades_path, grade).status_code == 200
    blocked = _batch(
        teacher, scene, "mock-send", [{"id": s2["id"], "idempotency_key": str(uuid.uuid4())}]
    )
    assert blocked.json()["results"][0]["code"] == "SOURCE_CHANGED"
    assert _count(engine, "notification_send_attempt") == 0

    # Access, CSRF and request shape.
    lesson = scene["lesson"]["id"]
    assert login("assistant2").get(f"/api/lessons/{lesson}/notifications/batch").status_code == 403
    no_csrf = teacher.post(
        f"/api/lessons/{lesson}/notifications/batch-approve", json={"items": items}
    )
    assert no_csrf.status_code == 403
    duplicate = _batch(teacher, scene, "approve", [items[1], items[1]])
    assert (duplicate.status_code, duplicate.json()["code"]) == (400, "DUPLICATE_NOTIFICATION")
    assert _batch(teacher, scene, "approve", []).status_code in (400, 422)
    assert TestClient(app).get(f"/api/lessons/{lesson}/notifications/batch").status_code == 401
