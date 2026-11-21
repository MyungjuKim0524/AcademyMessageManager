"""Response models. Rates and averages are ``None`` when they cannot be computed (never 0)."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, PlainSerializer

# Same JSON shape as the academics API: decimals as numbers. Values are already rounded in SQL.
Number = Annotated[Decimal, PlainSerializer(float, return_type=float)]


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AttendanceCounts(Schema):
    target: int
    recorded: int
    unrecorded: int
    present: int
    late: int
    absent: int
    excused: int
    outside_records: int
    record_rate: Number | None
    attendance_rate: Number | None


class StudentAttendance(AttendanceCounts):
    enrollment_id: int
    student_id: int
    student_name: str
    enrollment_status: str


class LessonAttendance(Schema):
    lesson_id: int
    lesson_date: date
    session_no: int
    topic: str | None
    target: int
    recorded: int
    unrecorded: int


class AttendancePolicy(Schema):
    held_lesson: str
    attendance_rate: str


class AttendanceAnalytics(Schema):
    classroom_id: int
    date_from: date
    date_to: date
    counted_until: date
    policy: AttendancePolicy
    summary: AttendanceCounts
    held_lessons: int
    not_held_lessons: int
    students: list[StudentAttendance]
    lessons: list[LessonAttendance]


class AttendanceHistoryRow(Schema):
    lesson_id: int
    lesson_date: date
    session_no: int
    topic: str | None
    eligible: bool
    status: Literal["PRESENT", "LATE", "ABSENT", "EXCUSED"] | None
    prework: str | None = None  # 예습 과제 grade of that lesson (A/B/C), None = not entered
    weekly: str | None = None  # 주간 과제 grade


class StudentAttendanceHistory(Schema):
    classroom_id: int
    student_id: int
    student_name: str
    enrollment_id: int
    date_from: date
    date_to: date
    counted_until: date
    summary: AttendanceCounts
    rows: list[AttendanceHistoryRow]


class AssessmentStats(Schema):
    assessment_id: int
    title: str
    assessment_date: date
    max_score: Number
    lesson_id: int | None
    upcoming: bool
    target: int
    scored: int
    not_taken: int
    missing: int
    outside_records: int
    entry_rate: Number | None
    average: Number | None
    average_count: int
    average_percent: Number | None


class GradeAnalytics(Schema):
    classroom_id: int
    date_from: date
    date_to: date
    assessments: list[AssessmentStats]


GradeStatus = Literal["SCORED", "NOT_TAKEN", "MISSING", "UPCOMING"]


class AssessmentStudentRow(Schema):
    enrollment_id: int
    student_id: int
    student_name: str
    eligible: bool
    status: GradeStatus
    score: Number | None
    percent: Number | None


class AssessmentDetail(Schema):
    classroom_id: int
    stats: AssessmentStats
    rows: list[AssessmentStudentRow]


class GradeTrendRow(Schema):
    assessment_id: int
    title: str
    assessment_date: date
    max_score: Number
    lesson_id: int | None
    eligible: bool
    status: GradeStatus
    score: Number | None
    percent: Number | None


class StudentGradeTrend(Schema):
    classroom_id: int
    student_id: int
    student_name: str
    enrollment_id: int
    date_from: date
    date_to: date
    rows: list[GradeTrendRow]


# ----------------------------------------- 관심 필요 학생 · 학생 학습 리포트 (2026-11-20)
class WatchReason(Schema):
    code: Literal["LOW_SCORE", "DECLINING", "HOMEWORK_C", "ABSENCE"]
    title: str | None  # 평가 항목 for the score rules
    count: int
    text: str


class WatchStudent(Schema):
    enrollment_id: int
    student_id: int
    student_name: str
    reasons: list[WatchReason]


class Watchlist(Schema):
    classroom_id: int
    window_from: date
    window_to: date
    rules: list[str]
    students: list[WatchStudent]


class ReportPoint(GradeTrendRow):
    class_average_percent: Number | None  # same session, scored students
    diff: Number | None  # student % − class average %, scored sessions only


class ReportCategory(Schema):
    title: str  # 평가 항목 (the workbook's test column name)
    points: list[ReportPoint]
    scored_count: int
    average_diff: Number | None  # mean position against the class over the period


class StudentReport(Schema):
    classroom_id: int
    student_id: int
    student_name: str
    enrollment_id: int
    date_from: date
    date_to: date
    categories: list[ReportCategory]
    attendance: AttendanceCounts
    lessons: list[AttendanceHistoryRow]
    watch_reasons: list[WatchReason]
