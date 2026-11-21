"""Phase 8.1: academy workbook parser (no database). All names are fictional."""

from io import BytesIO

import pytest
from openpyxl import Workbook

from app.errors import CompatibilityError
from app.modules.lesson_upload.workbook import class_type_of, parse_workbook, school_of

HEADER = ["출결", "예습 과제", "주간 과제", "문법, 문학, 독서 (15)", "어휘 (10)"]


def workbook(*sheets: tuple[str, list[list]]) -> bytes:
    book = Workbook()
    book.remove(book.active)
    for title, rows in sheets:
        sheet = book.create_sheet(title)
        for row in rows:
            sheet.append(row)
    buffer = BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def test_class_type_rule() -> None:
    assert class_type_of("중3 토10") == "REGULAR"
    assert class_type_of("고1 토10A") == "REGULAR"
    assert class_type_of("00고2 토10") == "EXAM_PREP"
    assert class_type_of("**고2 토6") == "EXAM_PREP"
    assert class_type_of("002 토2") is None  # typo for "00고2 토2"
    assert class_type_of("중4 토10") is None


def test_school_follows_exam_prep_class_name() -> None:
    assert school_of("00고2 토10", "EXAM_PREP") == "00고"
    assert school_of("검증고2 내신", "EXAM_PREP") == "검증고"
    assert school_of("**고2 토6", "EXAM_PREP") == "**고"
    assert school_of("중3 토10", "REGULAR") is None  # regular classes name no school
    assert school_of("고1 토10A", "REGULAR") is None


def test_blocks_students_scores_and_validation() -> None:
    content = workbook(
        (
            "10시",
            [
                ["중3 토10", *HEADER],
                ["가상학생1", "출석", "A", "b", 12, "8/10"],
                ["가상학생2", "결석", None, None, None, None],
                [None, None, None, None, None, None],
                ["가상학생3", "인정결석", "D", "A", 16, "x"],
                ["00고2 토10", "출결", "예습 과제", "주간 과제", "문학, 독서 (20)", "어휘"],
                ["가상학생4", "O", "A", "A", 20, None],
            ],
        ),
        ("2시", [["002 토2", *HEADER], ["학생이름", None, None, None, None, None]]),
    )
    first, exam, typo = parse_workbook(content)

    assert (first.class_name, first.class_type, first.issues) == ("중3 토10", "REGULAR", [])
    assert [(t.title, t.total) for t in first.tests] == [("문법, 문학, 독서", 15), ("어휘", 10)]
    s1, s2, s3 = first.students
    assert (s1.attendance, s1.prework, s1.weekly, s1.scores) == (
        "PRESENT",
        "A",
        "B",
        {"문법, 문학, 독서": 12, "어휘": 8},
    )
    assert s1.issues == [] and s1.key == "10시!2"
    assert (s2.attendance, s2.scores, s2.issues) == (
        "ABSENT",
        {"문법, 문학, 독서": None, "어휘": None},
        [],
    )
    assert s3.attendance == "EXCUSED"
    assert "예습 과제 등급 'D'는 A/B/C 중 하나여야 합니다" in s3.issues
    assert "'문법, 문학, 독서' 점수는 0~15 사이여야 합니다" in s3.issues
    assert "'어휘' 점수 'x'를 숫자로 읽을 수 없습니다" in s3.issues

    assert exam.class_type == "EXAM_PREP"
    assert "시험 열 '어휘'에 문항 수가 없습니다 (예: '어휘 (10)')" in exam.issues
    assert "출결 'O'는 출석/지각/결석/인정결석 중 하나여야 합니다" in exam.students[0].issues

    assert typo.class_type is None and typo.issues[0].startswith("반 이름 '002 토2'의 형식")
    [placeholder] = typo.students
    assert placeholder.empty  # a note in the name column only is skipped, not an error


def test_rejects_non_workbooks_and_files_without_blocks() -> None:
    with pytest.raises(CompatibilityError):
        parse_workbook(b"not a workbook")
    with pytest.raises(CompatibilityError) as error:
        parse_workbook(workbook(("시트", [["아무 내용"]])))
    assert error.value.code == "NO_CLASS_BLOCKS"
