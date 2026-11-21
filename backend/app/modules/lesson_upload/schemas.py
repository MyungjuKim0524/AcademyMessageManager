from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict

RowStatus = Literal["MATCHED", "UNREGISTERED", "INVALID", "SKIPPED"]
Decision = Literal["NEW", "RETURNING", "EXCLUDE"]


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TestColumnView(StrictSchema):
    title: str
    total: int


class AppChange(StrictSchema):
    """A value already in the app that confirming this workbook will replace (scores and
    homework grades follow the workbook — Phase 8.1 rule; this only makes it visible)."""

    field: Literal["score", "prework", "weekly"]
    label: str
    app: str
    upload: str


class MaxScoreChange(StrictSchema):
    title: str
    app: str
    upload: str


class UploadRowView(StrictSchema):
    key: str
    row: int
    name: str
    status: RowStatus
    attendance: str | None
    prework: str | None
    weekly: str | None
    scores: dict[str, int | None]
    issues: list[str]
    warnings: list[str]
    app_attendance: str | None
    attendance_mismatch: bool
    returning_available: bool
    app_changes: list[AppChange] = []
    # Confirming would write nothing for this row (already equal to the app): skipped, no audit.
    unchanged: bool = False
    # The student key (name + school) is already taken by a student outside this class, so the
    # upload cannot register this row as NEW (SEC-01): EXCLUDE it; an administrator enrols an
    # existing student in student / class management.
    existing_student_conflict: bool = False


class UploadBlockView(StrictSchema):
    sheet: str
    row: int
    class_name: str
    class_type: str | None
    classroom_id: int | None
    tests: list[TestColumnView]
    issues: list[str]
    rows: list[UploadRowView]
    max_score_changes: list[MaxScoreChange] = []


class SheetSummary(StrictSchema):
    """A sheet (time slot) of the workbook that holds class blocks."""

    name: str
    class_names: list[str]
    student_rows: int  # non-empty student rows (0 = nothing entered for that time slot yet)


class SheetList(StrictSchema):
    sheets: list[SheetSummary]


class UploadPreview(StrictSchema):
    lesson_date: date
    blocks: list[UploadBlockView]  # chosen sheets only
    can_confirm: bool
    blocking: list[str]
    sheets: list[SheetSummary] = []  # every sheet with class blocks
    selected_sheets: list[str] = []


class DraftSummary(StrictSchema):
    class_name: str
    created: int
    skipped: list[str]


class UploadResult(StrictSchema):
    lesson_date: date
    saved_rows: int  # rows that wrote something
    unchanged_rows: int = 0  # rows already equal to the app: nothing written or audited
    new_students: int
    returned_students: int
    excluded_rows: int
    attendance_mismatches: list[str]
    drafts: list[DraftSummary]
