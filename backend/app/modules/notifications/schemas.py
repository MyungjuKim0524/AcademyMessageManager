from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StrictBool, StrictStr

NotificationStatus = Literal[
    "DRAFT", "READY_FOR_REVIEW", "APPROVED", "MOCK_SENT", "MOCK_FAILED", "CANCELLED"
]
MAX_BATCH = 100


def _name(value: str) -> str:
    cleaned = " ".join(value.split())
    if not cleaned:
        raise ValueError("required")
    return cleaned


TemplateName = Annotated[StrictStr, Field(min_length=1, max_length=100), AfterValidator(_name)]
Body = Annotated[StrictStr, Field(min_length=1, max_length=2000)]


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ------------------------------------------------------------- templates
class TemplateCreate(StrictSchema):
    name: TemplateName
    body: Body


class TemplateUpdate(StrictSchema):
    version: int = Field(ge=1)
    name: TemplateName | None = None
    body: Body | None = None
    is_active: StrictBool | None = None
    # Phase 8.1: default template for workbook uploads. "NONE" removes the designation.
    default_for_class_type: Literal["REGULAR", "EXAM_PREP", "NONE"] | None = None


class TemplateValidate(StrictSchema):
    body: StrictStr = Field(max_length=4000)


class TemplateView(StrictSchema):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    body: str
    is_active: bool
    version: int
    default_for_class_type: str | None
    created_at: datetime
    updated_at: datetime


class TemplateVariable(StrictSchema):
    name: str
    description: str


class TemplateValidation(StrictSchema):
    ok: bool
    errors: list[str]
    variables: list[str]
    sample_body: str | None
    sample_issues: list[str]


# ------------------------------------------------------ generation flow
class GenerateRequest(StrictSchema):
    template_id: int = Field(gt=0)
    # Omitted = every student on the lesson roster (eligible or already recorded).
    enrollment_ids: list[Annotated[int, Field(gt=0)]] | None = Field(
        default=None, min_length=1, max_length=MAX_BATCH
    )


class PreviewItem(StrictSchema):
    enrollment_id: int
    student_id: int | None
    student_name: str | None
    ok: bool
    body: str | None
    issues: list[str]
    warnings: list[str]
    existing_notification_id: int | None


class PreviewResponse(StrictSchema):
    lesson_id: int
    template_id: int
    template_version: int
    items: list[PreviewItem]


class SkippedItem(StrictSchema):
    enrollment_id: int
    student_name: str | None
    reasons: list[str]
    existing_notification_id: int | None


class GenerateResponse(StrictSchema):
    created: list[int]
    skipped: list[SkippedItem]


# ----------------------------------------------------- review / approval
class VersionOnly(StrictSchema):
    version: int = Field(ge=1)


class BodyUpdate(StrictSchema):
    version: int = Field(ge=1)
    body: Body


class NotificationListItem(StrictSchema):
    id: int
    classroom_id: int
    lesson_id: int
    lesson_date: date
    session_no: int
    enrollment_id: int
    student_name: str
    template_id: int
    template_name: str
    status: str
    recipient: str  # masked
    version: int
    updated_at: datetime


class NotificationPage(StrictSchema):
    items: list[NotificationListItem]
    limit: int
    offset: int


class AttemptView(StrictSchema):
    id: int
    channel: str
    result: str
    error_code: str | None
    error_message: str | None
    requested_by: str | None
    attempted_at: datetime


class HistoryEvent(StrictSchema):
    event_type: str
    actor: str | None
    created_at: datetime
    details: dict


class NotificationDetail(NotificationListItem):
    # Full address so the staff member who confirms/sends can check it; lists stay masked.
    recipient_email: str
    body: str
    template_version: int
    created_by: str | None
    approved_by: str | None
    approved_at: datetime | None
    source_changed: bool
    attempts: list[AttemptView]
    history: list[HistoryEvent]


class MockSendResponse(StrictSchema):
    notification: NotificationDetail
    attempt: AttemptView
    replayed: bool


# ------------------------------------------------ class batch (2026-11-20)
class BatchMessage(NotificationListItem):
    body: str
    source_changed: bool  # confirming / sending is refused for this message
    attention: list[str]  # facts worth a second look (결석, 인정결석, 미응시, 0점); never blocking


class BatchView(StrictSchema):
    lesson_id: int
    classroom_id: int
    items: list[BatchMessage]


class BatchApproveItem(StrictSchema):
    id: int = Field(gt=0)
    version: int = Field(ge=1)


class BatchApproveRequest(StrictSchema):
    items: list[BatchApproveItem] = Field(min_length=1, max_length=MAX_BATCH)


class BatchSendItem(StrictSchema):
    id: int = Field(gt=0)
    idempotency_key: UUID  # one key per message, reused by the client until it gets an answer


class BatchSendRequest(StrictSchema):
    items: list[BatchSendItem] = Field(min_length=1, max_length=MAX_BATCH)


class BatchResult(StrictSchema):
    id: int
    student_name: str | None
    outcome: Literal["APPROVED", "MOCK_SENT", "MOCK_FAILED", "SKIPPED"]
    code: str | None  # why it was skipped, or the mock sender's error code
    message: str | None
    replayed: bool = False


class BatchResponse(StrictSchema):
    results: list[BatchResult]
