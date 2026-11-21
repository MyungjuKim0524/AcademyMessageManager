import re
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StrictStr, model_validator


def _clean_display_name(value: str) -> str:
    cleaned = " ".join(value.split())
    if not cleaned:
        raise ValueError("이름을 입력해주세요.")
    if any(not ch.isprintable() for ch in cleaned):
        raise ValueError("이름에 사용할 수 없는 문자가 있습니다.")
    return cleaned


DisplayName = Annotated[
    StrictStr, Field(min_length=1, max_length=100), AfterValidator(_clean_display_name)
]


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ClassroomCreate(StrictSchema):
    name: str = Field(min_length=1, max_length=100)
    class_type: str = Field(pattern="^(REGULAR|EXAM_PREP)$")


class ClassroomUpdate(StrictSchema):
    """Admin class management (2026-11-20): rename (e.g. a typo) and end / resume operation.
    Ending keeps every record and hides the class from daily screens; the class type is fixed."""

    name: Annotated[StrictStr | None, Field(min_length=1, max_length=100)] = None
    is_active: bool | None = None


class ClassroomView(StrictSchema):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    class_type: str
    is_active: bool


class ClassroomPage(StrictSchema):
    items: list[ClassroomView]
    limit: int
    offset: int


class StudentCreate(StrictSchema):
    name: str = Field(min_length=1, max_length=100)
    school_name: str | None = Field(default=None, max_length=120)
    parent_name: str | None = Field(default=None, max_length=100)
    parent_email: str | None = Field(default=None, max_length=255)
    # Optional: enrol the new student in a class in the same transaction (2026-11-20).
    classroom_id: int | None = Field(default=None, gt=0)
    enrolled_at: date | None = None

    @model_validator(mode="after")
    def _enrollment_pair(self):
        if (self.classroom_id is None) != (self.enrolled_at is None):
            raise ValueError("classroom_id and enrolled_at go together")
        return self


EMAIL_PATTERN = r"^[^\s@]+@[^\s@]+\.[^\s@]+$"


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


class StudentContactUpdate(StrictSchema):
    """Guardian contact edit (Phase 8). Omitted fields are kept; null or "" clears a field."""

    parent_name: Annotated[
        StrictStr | None, Field(max_length=100), AfterValidator(_blank_to_none)
    ] = None
    parent_email: Annotated[
        StrictStr | None, Field(max_length=255), AfterValidator(_blank_to_none)
    ] = None

    @model_validator(mode="after")
    def _email_format(self):
        if self.parent_email is not None and not re.match(EMAIL_PATTERN, self.parent_email):
            raise ValueError("invalid email")
        return self


class StudentContactView(StrictSchema):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    parent_name: str | None
    parent_email: str | None


class StudentView(StrictSchema):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    school_name: str | None


class EnrollmentCreate(StrictSchema):
    student_id: int = Field(gt=0)
    enrolled_at: date


class EnrollmentView(StrictSchema):
    model_config = ConfigDict(from_attributes=True)
    id: int
    student_id: int
    classroom_id: int
    status: str
    enrolled_at: date


class AssignmentCreate(StrictSchema):
    staff_user_id: int = Field(gt=0)
    assignment_role: str = Field(pattern="^(TEACHER|ASSISTANT)$")
    valid_from: date
    valid_to: date | None = None


class AssignmentView(StrictSchema):
    model_config = ConfigDict(from_attributes=True)
    id: int
    classroom_id: int
    staff_user_id: int
    assignment_role: str
    valid_from: date
    valid_to: date | None


class AssignmentDetailView(AssignmentView):
    classroom_name: str


class AssignmentPage(StrictSchema):
    items: list[AssignmentDetailView]
    limit: int
    offset: int


class ClassroomStaffAssignmentView(AssignmentView):
    email: str
    display_name: str | None
    staff_status: str


class ClassroomStaffAssignmentPage(StrictSchema):
    items: list[ClassroomStaffAssignmentView]
    limit: int
    offset: int


class StaffCreate(StrictSchema):
    email: StrictStr = Field(
        min_length=3,
        max_length=255,
        pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$",
    )
    display_name: DisplayName
    password: StrictStr = Field(min_length=12, max_length=1024)
    role: str = Field(pattern="^(TEACHER|ASSISTANT)$")


class StaffStatusUpdate(StrictSchema):
    status: str = Field(pattern="^(ACTIVE|INACTIVE)$")


class StaffProfileUpdate(StrictSchema):
    display_name: DisplayName


class StaffDeletion(StrictSchema):
    staff_id: int
    # HARD = removed (no history); SOFT = marked deleted, kept only so records keep the name.
    mode: Literal["HARD", "SOFT"]


class StaffView(StrictSchema):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    display_name: str | None
    role: str
    status: str
    created_at: datetime
    updated_at: datetime


class StaffPage(StrictSchema):
    items: list[StaffView]
    limit: int
    offset: int


class StudentEnrollmentSummary(StrictSchema):
    enrollment_id: int
    classroom_id: int
    classroom_name: str
    status: str
    enrolled_at: date
    classroom_active: bool = True  # False = the class has ended operation (kept for history)


class StudentListItem(StrictSchema):
    """All-students view (administrators only), with every class the student is enrolled in."""

    id: int
    name: str
    school_name: str | None
    parent_name: str | None
    parent_email: str | None
    enrollments: list[StudentEnrollmentSummary]


class StudentPage(StrictSchema):
    items: list[StudentListItem]
    total: int
    limit: int
    offset: int


class ClassroomStudentView(StrictSchema):
    id: int
    enrollment_id: int  # Phase 7.1: needed for the pause/resume actions
    name: str
    school_name: str | None
    enrollment_status: str
    enrolled_at: date
    # Guardian contact is set for ADMIN only; for other roles the keys are omitted.
    parent_name: str | None = None
    parent_email: str | None = None


class ClassroomStudentPage(StrictSchema):
    items: list[ClassroomStudentView]
    limit: int
    offset: int


class PasswordResetCodeIssued(StrictSchema):
    """SEC-10-B: shown once to the administrator; never stored or logged in clear."""

    staff_id: int
    code: str
    expires_at: datetime
