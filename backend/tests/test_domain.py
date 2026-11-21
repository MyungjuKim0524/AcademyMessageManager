from app.domain import compose_message, validate_preview
from app.models import MessagePreviewRequest


def test_composes_java_default_template_exactly() -> None:
    values, errors = validate_preview(
        MessagePreviewRequest(
            studentName="샘플학생1",
            className="CLASS-DEMO",
            classType="REGULAR",
            lessonDate="2026-10-05",
            testRound="1회차",
            attendance="PRESENT",
            preGrade="A",
            weeklyGrade="B",
            correctCount=13,
            totalCount=39,
        )
    )
    assert errors == [] and values is not None
    assert compose_message(values) == (
        "안녕하세요, JAVA 학원입니다.\n"
        "샘플학생1 학생의 이번 주 정규 수업 학습 현황 안내드립니다.\n\n"
        "예습 과제를 성실하게 수행하였습니다.\n"
        "주간 과제 수행은 양호하나 일부 문항에서 보완이 필요합니다.\n"
        "테스트 결과는 13/39입니다.\n\n오늘도 감사드립니다."
    )


def test_optional_sections_are_removed() -> None:
    values, errors = validate_preview(
        MessagePreviewRequest(
            studentName="김학생",
            className="A반",
            classType="EXAM_PREP",
            lessonDate="2026-08-08",
            attendance="LATE",
            preGrade="",
            weeklyGrade="",
            includeTestResult=False,
        )
    )
    assert errors == [] and values is not None
    message = compose_message(values)
    assert "예습 과제" not in message
    assert "주간 과제" not in message
    assert "테스트 결과" not in message
    assert "\n\n\n" not in message


def test_validation_order_matches_java() -> None:
    _, errors = validate_preview(
        MessagePreviewRequest(
            studentName="",
            className="A반",
            classType="UNKNOWN",
            lessonDate="bad-date",
            attendance="UNKNOWN",
            preGrade="D",
            correctCount=40,
            totalCount=39,
        )
    )
    assert [(error.field, error.message) for error in errors] == [
        ("studentName", "필수 값입니다."),
        ("classType", "허용되지 않은 값입니다."),
        ("attendance", "허용되지 않은 값입니다."),
        ("preGrade", "허용되지 않은 값입니다."),
        ("lessonDate", "ISO 날짜 형식(yyyy-MM-dd)이어야 합니다."),
        ("correctCount", "totalCount보다 클 수 없습니다."),
    ]
