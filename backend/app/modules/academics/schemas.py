from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, PlainSerializer

LessonStatus = Literal["SCHEDULED", "COMPLETED", "CANCELLED"]
AttendanceStatus = Literal["PRESENT", "ABSENT", "LATE", "EXCUSED"]
ResultStatus = Literal["SCORED", "NOT_TAKEN"]

MIN_DATE, MAX_DATE = date(2000, 1, 1), date(2100, 12, 31)


def _date_in_range(value: date) -> date:
    if not MIN_DATE <= value <= MAX_DATE:
        raise ValueError("date out of range")
    return value


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _required_text(value: str) -> str:
    cleaned = " ".join(value.split())
    if not cleaned:
        raise ValueError("required")
    return cleaned


BusinessDate = Annotated[date, AfterValidator(_date_in_range)]


def optional_text(max_length: int):
    # Length is checked on the raw string first, then blanks are normalised to None.
    return Annotated[str | None, Field(max_length=max_length), AfterValidator(_optional_text)]


# Scores are exact decimals in the database and plain JSON numbers on the wire.
Score = Annotated[Decimal, PlainSerializer(float, return_type=float)]


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Page(StrictSchema):
    limit: int
    offset: int


# ---------- Lessons ----------


SessionNo = Annotated[int, Field(ge=1, le=9)]


class LessonCreate(StrictSchema):
    lesson_date: BusinessDate
    session_no: SessionNo = 1
    exam_round: optional_text(50) = None
    topic: optional_text(200) = None
    memo: optional_text(2000) = None
    status: Literal["SCHEDULED", "COMPLETED"] = "SCHEDULED"


class LessonUpdate(StrictSchema):
    version: int = Field(ge=1)
    lesson_date: BusinessDate | None = None
    session_no: SessionNo | None = None
    exam_round: optional_text(50) = None
    topic: optional_text(200) = None
    memo: optional_text(2000) = None
    status: LessonStatus | None = None


class AttendanceSummary(StrictSchema):
    eligible: int
    recorded: int
    unrecorded: int
    present: int
    absent: int
    late: int
    excused: int


class LessonView(StrictSchema):
    model_config = ConfigDict(from_attributes=True)
    id: int
    classroom_id: int
    lesson_date: date
    session_no: int
    exam_round: str | None
    topic: str | None
    memo: str | None
    status: str
    version: int
    created_at: datetime
    updated_at: datetime


class TodayLesson(StrictSchema):
    """Result of "오늘 수업 시작": today's first-session lesson, created only if missing."""

    lesson: LessonView
    created: bool


class LessonListItem(LessonView):
    attendance_recorded: int


class LessonPage(Page):
    items: list[LessonListItem]


class LessonDetail(LessonView):
    attendance: AttendanceSummary


# ---------- Attendance ----------


class AttendanceItem(StrictSchema):
    enrollment_id: int = Field(gt=0)
    status: AttendanceStatus
    memo: optional_text(500) = None
    version: int | None = Field(default=None, ge=1)


class AttendanceBulk(StrictSchema):
    items: list[AttendanceItem] = Field(min_length=1, max_length=200)


class AttendanceRecord(StrictSchema):
    status: str
    memo: str | None
    version: int
    updated_at: datetime


class AttendanceRow(StrictSchema):
    enrollment_id: int
    student_id: int
    student_name: str
    school_name: str | None
    eligible: bool
    record: AttendanceRecord | None


class AttendanceRoster(StrictSchema):
    lesson: LessonView
    summary: AttendanceSummary
    items: list[AttendanceRow]
    changed: int | None = None


# ---------- Assessments and grades ----------


class AssessmentCreate(StrictSchema):
    title: Annotated[str, Field(min_length=1, max_length=100), AfterValidator(_required_text)]
    assessment_date: BusinessDate
    max_score: Decimal = Field(gt=0, le=Decimal("9999.99"), decimal_places=2)
    lesson_id: int | None = Field(default=None, gt=0)


class AssessmentUpdate(StrictSchema):
    version: int = Field(ge=1)
    title: Annotated[
        str | None,
        Field(min_length=1, max_length=100),
        AfterValidator(lambda v: None if v is None else _required_text(v)),
    ] = None
    assessment_date: BusinessDate | None = None
    max_score: Decimal | None = Field(default=None, gt=0, le=Decimal("9999.99"), decimal_places=2)
    lesson_id: int | None = Field(default=None, gt=0)


class GradeSummary(StrictSchema):
    eligible: int
    scored: int
    not_taken: int
    unrecorded: int


class AssessmentView(StrictSchema):
    model_config = ConfigDict(from_attributes=True)
    id: int
    classroom_id: int
    lesson_id: int | None
    title: str
    assessment_date: date
    max_score: Score
    version: int
    created_at: datetime
    updated_at: datetime


class AssessmentListItem(AssessmentView):
    scored: int
    not_taken: int


class AssessmentPage(Page):
    items: list[AssessmentListItem]


class AssessmentDetail(AssessmentView):
    grades: GradeSummary


class GradeItem(StrictSchema):
    enrollment_id: int = Field(gt=0)
    result_status: ResultStatus
    score: Decimal | None = None
    memo: optional_text(500) = None
    version: int | None = Field(default=None, ge=1)


class GradeBulk(StrictSchema):
    items: list[GradeItem] = Field(min_length=1, max_length=200)


class GradeRecord(StrictSchema):
    result_status: str
    score: Score | None
    memo: str | None
    version: int
    updated_at: datetime


class GradeRow(StrictSchema):
    enrollment_id: int
    student_id: int
    student_name: str
    school_name: str | None
    eligible: bool
    record: GradeRecord | None


class GradeRoster(StrictSchema):
    assessment: AssessmentView
    summary: GradeSummary
    items: list[GradeRow]
    changed: int | None = None


# ---------- Student history (Phase 8 source) ----------


class StudentLessonRecord(StrictSchema):
    lesson_id: int
    lesson_date: date
    session_no: int
    exam_round: str | None
    topic: str | None
    lesson_status: str
    attendance_status: str | None
    prework_grade: str | None = None
    weekly_grade: str | None = None
    memo: str | None
    updated_at: datetime | None


class StudentGradeRecord(StrictSchema):
    assessment_id: int
    title: str
    assessment_date: date
    max_score: Score
    result_status: str | None
    score: Score | None
    memo: str | None
    updated_at: datetime | None


class StudentRecords(StrictSchema):
    student_id: int
    student_name: str
    enrollment_id: int
    enrollment_status: str
    enrolled_at: date
    ended_at: date | None
    lessons: list[StudentLessonRecord]
    assessments: list[StudentGradeRecord]


# ---------- Class progress grid (Phase 8.1: 학습 현황) ----------

AssignmentGrade = Literal["A", "B", "C"]


class ProgressAssessment(StrictSchema):
    id: int
    title: str
    max_score: Score
    version: int


class ProgressColumn(StrictSchema):
    """One column of the grid: a lesson (with its linked assessments) or a stand-alone
    assessment that is not linked to any lesson."""

    key: str  # "lesson:<id>" | "assessment:<id>"
    kind: Literal["LESSON", "ASSESSMENT"]
    lesson_id: int | None
    day: date
    session_no: int | None
    exam_round: str | None
    topic: str | None
    lesson_status: str | None
    assessments: list[ProgressAssessment]


class ProgressScore(StrictSchema):
    assessment_id: int
    result_status: str
    score: Score | None
    memo: str | None  # kept as-is when a stand-alone assessment score is corrected
    version: int


class ProgressCell(StrictSchema):
    key: str
    eligible: bool
    attendance_status: str | None
    prework_grade: str | None
    weekly_grade: str | None
    result_version: int | None
    scores: list[ProgressScore]


class ProgressStudent(StrictSchema):
    enrollment_id: int
    student_id: int
    student_name: str
    enrollment_status: str
    cells: list[ProgressCell]


class ClassProgress(StrictSchema):
    classroom_id: int
    date_from: date
    date_to: date
    columns: list[ProgressColumn]
    students: list[ProgressStudent]


class RecordScore(StrictSchema):
    assessment_id: int = Field(gt=0)
    result_status: ResultStatus
    score: Decimal | None = None
    version: int | None = Field(default=None, ge=1)


class RecordUpdate(StrictSchema):
    """Correct one student's record for one lesson in a single transaction.

    Omitted fields are kept. ``prework_grade``/``weekly_grade`` set to null clear the grade;
    attendance can be changed but not cleared. ``result_version`` is the lesson_result version
    the client saw (null when there was no record yet).
    """

    result_version: int | None = Field(default=None, ge=1)
    attendance_status: AttendanceStatus | None = None
    prework_grade: AssignmentGrade | None = None
    weekly_grade: AssignmentGrade | None = None
    scores: list[RecordScore] = Field(default_factory=list, max_length=20)


class RecordSaved(StrictSchema):
    changed: int


# ---------- Enrollment pauses (Phase 7.1) ----------


class PauseCreate(StrictSchema):
    paused_from: BusinessDate
    resumed_on: BusinessDate | None = None


class PauseResume(StrictSchema):
    resumed_on: BusinessDate


class PauseView(StrictSchema):
    model_config = ConfigDict(from_attributes=True)
    id: int
    enrollment_id: int
    paused_from: date
    resumed_on: date | None
    source: str
    created_at: datetime


class PausePage(StrictSchema):
    enrollment_id: int
    enrollment_status: str
    items: list[PauseView]
