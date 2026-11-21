from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.errors import FieldError
from app.models import MessagePreviewRequest
from app.modules.notifications.engine import MAKEUP_SENTENCE, PREWORK_SENTENCE, WEEKLY_SENTENCE


class ClassType(StrEnum):
    REGULAR = "REGULAR"
    EXAM_PREP = "EXAM_PREP"


class AttendanceStatus(StrEnum):
    # Java-compatible preview contract only (POST /api/messages/preview, Java enum has the same
    # three values). Stored attendance has a 4th state, EXCUSED, handled by
    # app.modules.notifications.engine — do not add it here without changing the Java contract.
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    LATE = "LATE"


class AchievementGrade(StrEnum):
    A = "A"
    B = "B"
    C = "C"


CLASS_ALIASES = {"정규": ClassType.REGULAR, "내신 대비": ClassType.EXAM_PREP}
ATTENDANCE_ALIASES = {
    "출석": AttendanceStatus.PRESENT,
    "결석": AttendanceStatus.ABSENT,
    "지각": AttendanceStatus.LATE,
}


@dataclass(frozen=True)
class PreviewValues:
    student_name: str
    class_name: str
    class_type: ClassType
    lesson_date: str
    test_round: str
    attendance: AttendanceStatus
    pre_grade: AchievementGrade | None
    weekly_grade: AchievementGrade | None
    correct_count: int | None
    total_count: int | None
    include_pre_grade: bool
    include_weekly_grade: bool
    include_test_result: bool


def _required(errors: list[FieldError], field: str, value: str | None, maximum: int) -> None:
    if value is None or not value.strip():
        errors.append(FieldError(field=field, message="필수 값입니다."))
    elif len(value) > maximum:
        errors.append(FieldError(field=field, message=f"최대 {maximum}자까지 입력할 수 있습니다."))


def _enum(value: str | None, enum_type: type[StrEnum], aliases: dict[str, StrEnum]):
    if value is None:
        raise ValueError
    stripped = value.strip()
    return aliases.get(stripped) or enum_type(stripped.upper())


def _grade(value: str | None) -> AchievementGrade | None:
    if value is None or not value.strip():
        return None
    return AchievementGrade(value.strip().upper())


def validate_preview(
    request: MessagePreviewRequest,
) -> tuple[PreviewValues | None, list[FieldError]]:
    errors: list[FieldError] = []
    _required(errors, "studentName", request.studentName, 100)
    _required(errors, "className", request.className, 100)
    _required(errors, "classType", request.classType, 30)
    _required(errors, "lessonDate", request.lessonDate, 10)
    _required(errors, "attendance", request.attendance, 20)
    if request.testRound is not None and len(request.testRound) > 50:
        errors.append(FieldError(field="testRound", message="최대 50자까지 입력할 수 있습니다."))

    try:
        class_type = _enum(request.classType, ClassType, CLASS_ALIASES)
    except ValueError:
        class_type = None
        errors.append(FieldError(field="classType", message="허용되지 않은 값입니다."))
    try:
        attendance = _enum(request.attendance, AttendanceStatus, ATTENDANCE_ALIASES)
    except ValueError:
        attendance = None
        errors.append(FieldError(field="attendance", message="허용되지 않은 값입니다."))
    try:
        pre_grade = _grade(request.preGrade)
    except ValueError:
        pre_grade = None
        errors.append(FieldError(field="preGrade", message="허용되지 않은 값입니다."))
    try:
        weekly_grade = _grade(request.weeklyGrade)
    except ValueError:
        weekly_grade = None
        errors.append(FieldError(field="weeklyGrade", message="허용되지 않은 값입니다."))
    try:
        parsed_date = datetime.strptime(request.lessonDate or "", "%Y-%m-%d").date()
        if parsed_date.isoformat() != request.lessonDate:
            raise ValueError
    except ValueError:
        errors.append(
            FieldError(field="lessonDate", message="ISO 날짜 형식(yyyy-MM-dd)이어야 합니다.")
        )

    correct, total = request.correctCount, request.totalCount
    if (correct is None) != (total is None):
        errors.append(
            FieldError(
                field="correctCount", message="correctCount와 totalCount는 함께 입력해야 합니다."
            )
        )
    elif correct is not None and total is not None:
        if correct < 0 or correct > 10_000:
            errors.append(FieldError(field="correctCount", message="0 이상 10000 이하여야 합니다."))
        if total <= 0 or total > 10_000:
            errors.append(FieldError(field="totalCount", message="1 이상 10000 이하여야 합니다."))
        if correct > total:
            errors.append(
                FieldError(field="correctCount", message="totalCount보다 클 수 없습니다.")
            )

    if errors:
        return None, errors
    assert class_type is not None and attendance is not None
    return PreviewValues(
        student_name=(request.studentName or "").strip(),
        class_name=(request.className or "").strip(),
        class_type=class_type,
        lesson_date=request.lessonDate or "",
        test_round=(request.testRound or "").strip(),
        attendance=attendance,
        pre_grade=pre_grade,
        weekly_grade=weekly_grade,
        correct_count=correct,
        total_count=total,
        include_pre_grade=request.includePreGrade is not False,
        include_weekly_grade=request.includeWeeklyGrade is not False,
        include_test_result=request.includeTestResult is not False,
    ), []


REGULAR_TEMPLATE = """안녕하세요, JAVA 학원입니다.
{학생명} 학생의 이번 주 정규 수업 학습 현황 안내드립니다.

{예습메시지}
{주간메시지}
{테스트메시지}
{보강메시지}

오늘도 감사드립니다."""

EXAM_PREP_TEMPLATE = """안녕하세요, JAVA 학원입니다.
{학생명} 학생의 내신 대비 학습 현황 안내드립니다.

{예습메시지}
{주간메시지}
{테스트메시지}
{보강메시지}

시험 대비 기간 동안 꾸준히 학습할 수 있도록 지도하겠습니다.
감사합니다."""


# Sentences live in the current message engine (single source); these are thin wrappers kept
# for the Java-compatible preview below.
def _pre(grade: AchievementGrade | None) -> str:
    return PREWORK_SENTENCE[grade.value] if grade is not None else ""


def _weekly(grade: AchievementGrade | None) -> str:
    return WEEKLY_SENTENCE[grade.value] if grade is not None else ""


def compose_message(values: PreviewValues) -> str:
    template = EXAM_PREP_TEMPLATE if values.class_type is ClassType.EXAM_PREP else REGULAR_TEMPLATE
    test = ""
    if values.include_test_result and values.correct_count is not None:
        test = f"테스트 결과는 {values.correct_count}/{values.total_count}입니다."
    makeup = MAKEUP_SENTENCE if values.attendance is AttendanceStatus.ABSENT else ""
    replacements = {
        "{학생명}": values.student_name,
        "{분반명}": values.class_name,
        "{수업일자}": values.lesson_date,
        "{시험회차}": values.test_round,
        "{예습메시지}": _pre(values.pre_grade) if values.include_pre_grade else "",
        "{주간메시지}": _weekly(values.weekly_grade) if values.include_weekly_grade else "",
        "{테스트메시지}": test,
        "{보강메시지}": makeup,
    }
    text = template
    for placeholder, value in replacements.items():
        text = text.replace(placeholder, value)
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    while "\n\n\n" in normalized:
        normalized = normalized.replace("\n\n\n", "\n\n")
    return normalized.strip()
