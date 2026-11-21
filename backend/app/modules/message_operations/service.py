"""Phase 9 message operations.

Notice obligation (계산형, no table): one obligation per (held lesson, enrolled student).
* A lesson is *held* when it is not cancelled, is not in the future, and is COMPLETED or has at
  least one attendance row. Past SCHEDULED lessons without any attendance are "not held".
  The rule is ``academics.repository.held_lesson``, shared with 출결 분석 (analytics).
* Students of a held lesson: eligible on the lesson date (``eligible_on``: enrolment period and
  dated pauses), or with an attendance row for that lesson — the same roster Phase 8 uses when
  generating drafts.
Everyone else inside the enrolment period is listed as EXEMPT with a reason, never as missing.

Each obligation has exactly one processing status, derived from its most advanced active
(non-cancelled) message, so the per-status counts always add up to the obligation total.
"""

from datetime import date, timedelta

from app.db.models.tables import Classroom, Lesson
from app.errors import CompatibilityError
from app.modules.auth.dependencies import Principal
from app.modules.notifications.service import NotificationService

from .repository import OperationsRepository

MAX_PERIOD_DAYS = 93
STATUSES = ("MISSING", "IN_REVIEW", "READY_TO_SEND", "FAILED", "DONE")
STATUS_OF_MESSAGE = {
    "DRAFT": "IN_REVIEW",
    "READY_FOR_REVIEW": "IN_REVIEW",
    "APPROVED": "READY_TO_SEND",
    "MOCK_FAILED": "FAILED",
    "MOCK_SENT": "DONE",
}
# When one (lesson, student) has several active messages (different templates), the most
# advanced one decides the obligation status.
PROGRESS = {"DRAFT": 1, "READY_FOR_REVIEW": 2, "APPROVED": 3, "MOCK_FAILED": 4, "MOCK_SENT": 5}
NEXT_ACTION = {
    "MISSING": "CREATE_DRAFT",
    "IN_REVIEW": "REVIEW",
    "READY_TO_SEND": "MOCK_SEND",
    "FAILED": "RETRY",
    "DONE": "VIEW_HISTORY",
    "EXEMPT": "NONE",
}
# Dashboard to-do: obligation status → counter, and the urgency order with the action it needs.
TODO_COUNT = {
    "FAILED": "failed",
    "READY_TO_SEND": "ready_to_send",
    "IN_REVIEW": "in_review",
    "MISSING": "missing",
}
TODO_ORDER = (
    ("failed", "RETRY"),
    ("ready_to_send", "SEND"),
    ("in_review", "REVIEW"),
    ("missing", "COMPOSE"),
)
EXEMPT_REASON = {
    "LESSON_CANCELLED": "수업 취소",
    "LESSON_NOT_HELD": "진행 기록 없음 (예정 상태·출결 없음)",
    "NOT_ELIGIBLE": "휴원·수강 대상 아님",
}
# Failure categories come only from the stored Mock Sender error code — never guessed.
FAILURE_CATEGORY = {
    "MOCK_RECIPIENT_REJECTED": ("RECIPIENT", "수신 대상 정보 오류"),
    "MOCK_EMPTY_BODY": ("VALIDATION", "데이터 검증 실패"),
    "MOCK_TEMPORARY_FAILURE": ("SENDER", "모의 발송기 일시 실패"),
}


def _fail(status: int, code: str, message: str):
    raise CompatibilityError(status, code, message)


def failure_view(attempt) -> dict:
    category, label = FAILURE_CATEGORY.get(attempt.error_code, ("UNKNOWN", "원인 불명"))
    return {
        "code": attempt.error_code,
        "category": category,
        "category_label": label,
        "message": attempt.error_message,  # stored safe text (no address, no internals)
        "attempted_at": attempt.attempted_at,
    }


def completion_rate(done: int, total: int) -> float | None:
    """Share of obligations satisfied by a successful mock send; None when nothing is due."""
    return None if total == 0 else round(done * 100 / total, 1)


class OperationsService:
    def __init__(self, db, principal: Principal, request_id: str | None = None):
        self.db = db
        self.principal = principal
        self.request_id = request_id
        self.repo = OperationsRepository(db)

    # ---------------------------------------------------------------- scope
    @staticmethod
    def check_period(date_from: date, date_to: date) -> None:
        if date_from > date_to:
            _fail(400, "INVALID_DATE_RANGE", "조회 기간을 확인해주세요.")
        if (date_to - date_from).days >= MAX_PERIOD_DAYS:
            _fail(400, "DATE_RANGE_TOO_LONG", "한 번에 최대 3개월까지 조회할 수 있습니다.")

    def classroom(self, classroom_id: int) -> Classroom:
        classroom = self.repo.classroom(classroom_id)
        if classroom is None or not classroom.is_active:
            _fail(404, "CLASSROOM_NOT_FOUND", "반을 찾을 수 없습니다.")
        if not self.repo.can_access(classroom_id, self.principal.user_id, self.principal.role):
            _fail(403, "CLASSROOM_ACCESS_DENIED", "담당 반에만 접근할 수 있습니다.")
        return classroom

    # ----------------------------------------------------------- obligations
    def items(self, classrooms: list[Classroom], date_from: date, date_to: date) -> list[dict]:
        """Every obligation and exemption in the period (future lessons are never due)."""
        today = date.today()
        last_day = min(date_to, today)
        if date_from > last_day:
            return []
        names = {c.id: c.name for c in classrooms}
        lessons = {
            lesson.id: lesson for lesson in self.repo.lessons(list(names), date_from, last_day)
        }
        ids = list(lessons)
        held_ids = self.repo.held_lessons(ids, today)
        messages: dict[tuple[int, int], list] = {}
        for notification, template_name in self.repo.notifications(ids):
            key = (notification.lesson_id, notification.enrollment_id)
            messages.setdefault(key, []).append((notification, template_name))
        attempts: dict[int, list] = {}
        all_ids = [n.id for group in messages.values() for n, _ in group]
        for attempt in self.repo.attempts(all_ids):
            attempts.setdefault(attempt.notification_id, []).append(attempt)

        result = []
        for row in self.repo.roster(ids):
            lesson: Lesson = lessons[row.lesson_id]
            enrollment, student = row.Enrollment, row.Student
            eligible, attended = bool(row.eligible), row.result_id is not None
            held = lesson.id in held_ids  # academics.repository.held_lesson (shared rule)
            if lesson.status == "CANCELLED":
                reason = "LESSON_CANCELLED" if eligible or attended else None
            elif not held:
                reason = "LESSON_NOT_HELD" if eligible else None
            elif eligible or attended:
                reason = ""  # obligated
            else:
                reason = "NOT_ELIGIBLE"
            if reason is None:
                continue  # not a student of the class on that day: neither due nor exempt
            item = {
                "lesson_id": lesson.id,
                "enrollment_id": enrollment.id,
                "classroom_id": lesson.classroom_id,
                "classroom_name": names[lesson.classroom_id],
                "student_id": student.id,
                "student_name": student.name,
                "lesson_date": lesson.lesson_date,
                "session_no": lesson.session_no,
                "exam_round": lesson.exam_round,
                "topic": lesson.topic,
                "lesson_status": lesson.status,
                "obligated": reason == "",
                "exempt_reason": reason or None,
                "exempt_reason_label": EXEMPT_REASON.get(reason) if reason else None,
                "status": "EXEMPT",
                "notification_id": None,
                "notification_status": None,
                "template_name": None,
                "active_messages": 0,
                "processed_at": None,
                "attempt_count": 0,
                "failure": None,
                "hints": [],
                "next_action": "NONE",
                "overdue": None,  # deadline policy not configured (see plan §4)
            }
            if item["obligated"]:
                self._classify(item, messages.get((lesson.id, enrollment.id), []), attempts)
                if item["status"] == "MISSING":
                    if not student.parent_email:
                        item["hints"].append("보호자 이메일 없음")
                    if not attended:
                        item["hints"].append("출결 미입력")
            result.append(item)
        result.sort(
            key=lambda i: (
                -i["lesson_date"].toordinal(),
                -i["session_no"],
                i["classroom_name"],
                i["student_name"],
                i["enrollment_id"],
            )
        )
        return result

    @staticmethod
    def _classify(item: dict, group: list, attempts: dict[int, list]) -> None:
        item["active_messages"] = len(group)
        if not group:
            item["status"] = "MISSING"
        else:
            notification, template_name = max(group, key=lambda g: (PROGRESS[g[0].status], g[0].id))
            tried = attempts.get(notification.id, [])
            item.update(
                status=STATUS_OF_MESSAGE[notification.status],
                notification_id=notification.id,
                notification_status=notification.status,
                template_name=template_name,
                attempt_count=len(tried),
                processed_at=tried[-1].attempted_at if tried else notification.updated_at,
            )
            if notification.status == "MOCK_FAILED" and tried:
                item["failure"] = failure_view(tried[-1])
        item["next_action"] = NEXT_ACTION[item["status"]]

    # ------------------------------------------------------------- summaries
    @staticmethod
    def counts(items: list[dict]) -> dict:
        counts = {s.lower(): 0 for s in STATUSES}
        exempt = 0
        for item in items:
            if item["obligated"]:
                counts[item["status"].lower()] += 1
            else:
                exempt += 1
        total = sum(counts.values())
        return {
            "total": total,
            **counts,
            "pending": counts["missing"] + counts["in_review"] + counts["ready_to_send"],
            "exempt": exempt,
            "overdue": None,
            "completion_rate": completion_rate(counts["done"], total),
        }

    def summary(self, date_from: date, date_to: date) -> dict:
        self.check_period(date_from, date_to)
        classrooms = self.repo.visible_classrooms(self.principal.user_id, self.principal.role)
        items = self.items(classrooms, date_from, date_to)
        rows = []
        for classroom in classrooms:
            mine = [i for i in items if i["classroom_id"] == classroom.id]
            rows.append(
                {
                    "classroom_id": classroom.id,
                    "classroom_name": classroom.name,
                    "class_type": classroom.class_type,
                    **self.counts(mine),
                }
            )
        return {
            "date_from": date_from,
            "date_to": date_to,
            "deadline_policy": "NOT_CONFIGURED",
            "totals": self.counts(items),
            "classrooms": rows,
        }

    def todo(self) -> dict:
        """Dashboard '성적 안내 할 일' (2026-11-20): one row per class lesson that still has
        unfinished notices, whatever the date (within the 3-month query limit), most urgent first:
        a failed send, then confirmed-but-unsent, then waiting for review, then no message yet."""
        today = date.today()
        date_from = today - timedelta(days=MAX_PERIOD_DAYS - 1)
        classrooms = self.repo.visible_classrooms(self.principal.user_id, self.principal.role)
        groups: dict[tuple[int, int], dict] = {}
        for item in self.items(classrooms, date_from, today):
            if not item["obligated"] or item["status"] == "DONE":
                continue
            row = groups.setdefault(
                (item["classroom_id"], item["lesson_id"]),
                {
                    "classroom_id": item["classroom_id"],
                    "classroom_name": item["classroom_name"],
                    "lesson_id": item["lesson_id"],
                    "lesson_date": item["lesson_date"],
                    "session_no": item["session_no"],
                    "failed": 0,
                    "ready_to_send": 0,
                    "in_review": 0,
                    "missing": 0,
                    "missing_no_email": 0,
                    "missing_no_attendance": 0,
                },
            )
            row[TODO_COUNT[item["status"]]] += 1
            if item["status"] == "MISSING":
                row["missing_no_email"] += "보호자 이메일 없음" in item["hints"]
                row["missing_no_attendance"] += "출결 미입력" in item["hints"]
        ranked = []
        for row in groups.values():
            # The most urgent unfinished kind decides the action and the order.
            rank = next(i for i, (key, _) in enumerate(TODO_ORDER) if row[key])
            row["next_action"] = TODO_ORDER[rank][1]
            ranked.append((rank, row["lesson_date"], row["session_no"], row["classroom_name"], row))
        ranked.sort(key=lambda entry: entry[:4])
        return {"date_from": date_from, "date_to": today, "items": [entry[4] for entry in ranked]}

    def classroom_summary(self, classroom_id: int, date_from: date, date_to: date) -> dict:
        self.check_period(date_from, date_to)
        classroom = self.classroom(classroom_id)
        return {
            "classroom_id": classroom.id,
            "classroom_name": classroom.name,
            "class_type": classroom.class_type,
            **self.counts(self.items([classroom], date_from, date_to)),
        }

    def obligations(self, classroom_id, date_from, date_to, status, limit: int, offset: int):
        self.check_period(date_from, date_to)
        items = self.items([self.classroom(classroom_id)], date_from, date_to)
        if status is not None:
            items = [i for i in items if i["status"] == status]
        return items[offset : offset + limit], len(items)

    # ---------------------------------------------------------------- detail
    def obligation_detail(self, lesson_id: int, enrollment_id: int) -> dict:
        lesson = self.db.get(Lesson, lesson_id)
        if lesson is None:
            _fail(404, "OBLIGATION_NOT_FOUND", "안내 대상을 찾을 수 없습니다.")
        classroom = self.classroom(lesson.classroom_id)  # 403 before anything is disclosed
        found = [
            i
            for i in self.items([classroom], lesson.lesson_date, lesson.lesson_date)
            if i["lesson_id"] == lesson_id and i["enrollment_id"] == enrollment_id
        ]
        if not found:
            _fail(404, "OBLIGATION_NOT_FOUND", "안내 대상을 찾을 수 없습니다.")
        item = found[0]
        rows = self.repo.notifications([lesson_id], active_only=False)
        mine = [(n, name) for n, name in rows if n.enrollment_id == enrollment_id]
        attempts: dict[int, list] = {}
        for attempt in self.repo.attempts([n.id for n, _ in mine]):
            attempts.setdefault(attempt.notification_id, []).append(attempt)
        retry_blocked = None
        if item["status"] == "FAILED":
            notifications = NotificationService(self.db, self.principal, self.request_id)
            failed = next(n for n, _ in mine if n.id == item["notification_id"])
            if notifications.source_changed(failed):
                retry_blocked = (
                    "생성 후 원본(수업·출결·성적·연락처)이 바뀌어 재시도할 수 없습니다. "
                    "취소 후 다시 생성하세요."
                )
        return {
            **item,
            "retry_blocked_reason": retry_blocked,
            "messages": [
                {
                    "id": n.id,
                    "template_name": name,
                    "status": n.status,
                    "created_at": n.created_at,
                    "updated_at": n.updated_at,
                    "approved_at": n.approved_at,
                    "attempts": [
                        {
                            "id": a.id,
                            "result": a.result,
                            "error_code": a.error_code,
                            "error_message": a.error_message,
                            "attempted_at": a.attempted_at,
                        }
                        for a in attempts.get(n.id, [])
                    ],
                }
                for n, name in mine
            ],
        }
