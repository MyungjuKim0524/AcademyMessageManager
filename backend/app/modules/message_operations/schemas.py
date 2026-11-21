from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

ObligationStatus = Literal["MISSING", "IN_REVIEW", "READY_TO_SEND", "FAILED", "DONE", "EXEMPT"]


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Counts(StrictSchema):
    total: int  # obligations due (exempt students are not counted)
    missing: int
    in_review: int
    ready_to_send: int
    failed: int
    done: int
    pending: int  # missing + in_review + ready_to_send
    exempt: int
    overdue: int | None  # None: no deadline policy configured
    completion_rate: float | None  # None when nothing is due (never shown as 0%)


class ClassroomCounts(Counts):
    classroom_id: int
    classroom_name: str
    class_type: str


class Summary(StrictSchema):
    date_from: date
    date_to: date
    deadline_policy: Literal["NOT_CONFIGURED"]
    totals: Counts
    classrooms: list[ClassroomCounts]


class Failure(StrictSchema):
    code: str | None
    category: Literal["RECIPIENT", "VALIDATION", "SENDER", "UNKNOWN"]
    category_label: str
    message: str | None
    attempted_at: datetime


class Obligation(StrictSchema):
    lesson_id: int
    enrollment_id: int
    classroom_id: int
    classroom_name: str
    student_id: int
    student_name: str
    lesson_date: date
    session_no: int
    exam_round: str | None
    topic: str | None
    lesson_status: str
    obligated: bool
    exempt_reason: str | None
    exempt_reason_label: str | None
    status: ObligationStatus
    notification_id: int | None
    notification_status: str | None
    template_name: str | None
    active_messages: int
    processed_at: datetime | None
    attempt_count: int
    failure: Failure | None
    hints: list[str]
    next_action: Literal["CREATE_DRAFT", "REVIEW", "MOCK_SEND", "RETRY", "VIEW_HISTORY", "NONE"]
    overdue: bool | None


class ObligationPage(StrictSchema):
    items: list[Obligation]
    total: int
    limit: int
    offset: int


class AttemptRecord(StrictSchema):
    id: int
    result: str
    error_code: str | None
    error_message: str | None
    attempted_at: datetime


class MessageRecord(StrictSchema):
    id: int
    template_name: str
    status: str
    created_at: datetime
    updated_at: datetime
    approved_at: datetime | None
    attempts: list[AttemptRecord]


class ObligationDetail(Obligation):
    retry_blocked_reason: str | None
    messages: list[MessageRecord]  # every message for this lesson/student, cancelled included


class TodoItem(StrictSchema):
    """One class lesson with unfinished parent notices (dashboard '성적 안내 할 일')."""

    classroom_id: int
    classroom_name: str
    lesson_id: int
    lesson_date: date
    session_no: int
    failed: int
    ready_to_send: int
    in_review: int
    missing: int  # due but no message yet
    missing_no_email: int  # … of which the guardian has no e-mail
    missing_no_attendance: int  # … of which attendance is not entered
    next_action: Literal["RETRY", "SEND", "REVIEW", "COMPOSE"]


class TodoList(StrictSchema):
    date_from: date
    date_to: date
    items: list[TodoItem]
