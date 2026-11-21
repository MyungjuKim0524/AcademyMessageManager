"""Parser for the academy's weekly workbook. Pure: no database access.

Layout (one sheet per time slot, several class blocks stacked in each sheet)::

    중3 토10 | 출결 | 예습 과제 | 주간 과제 | 문법, 문학, 독서 (15) | 어휘 (10)   <- block header
    김아무개 | 출석 | A        | B        | 12                     | 8          <- student rows
    ...

* A block header is any row whose second cell is "출결".
* Class type comes from the class name: "중3 토10", "고1 토10A" are regular classes; a name that
  starts with a school ("00고2 토10", "**고2 토6") is an exam-prep class. Anything else is an
  error to fix in the workbook (e.g. a typo such as "002 토2").
* Test columns are "<category> (<question count>)"; cells hold the number of correct answers
  ("12") or "12/15".
* Homework grades are A, B or C. Blank cells are "not entered", never a grade or a zero.
"""

import re
from dataclasses import dataclass, field
from io import BytesIO

from openpyxl import load_workbook

from app.errors import CompatibilityError
from app.uploads import MAX_COLUMNS, MAX_ROWS, MAX_SCANNED_ROWS
from app.uploads import check_xlsx_zip as _check_zip
from app.uploads import format_cell as _format

REGULAR = re.compile(r"^(중|고)[1-3]\s+\S")
EXAM_PREP = re.compile(r"^\S+고[1-3]\s+\S")
TEST_HEADER = re.compile(r"^(?P<title>.+?)\s*\((?P<total>\d{1,3})\)\s*$")
FIXED_HEADERS = ("출결", "예습 과제", "주간 과제")
ATTENDANCE = {
    "출석": "PRESENT",
    "지각": "LATE",
    "결석": "ABSENT",
    "인정결석": "EXCUSED",
    "인정 결석": "EXCUSED",
    "PRESENT": "PRESENT",
    "LATE": "LATE",
    "ABSENT": "ABSENT",
    "EXCUSED": "EXCUSED",
}
GRADES = {"A", "B", "C"}
MAX_TITLE = 100


EXAM_PREP_SCHOOL = re.compile(r"^(?P<school>\S+고)[1-3]\s")


def school_of(class_name: str, class_type: str | None) -> str | None:
    """School implied by a class name: exam-prep classes are named after one school
    ("00고2 토10" -> "00고"). Regular classes ("중3 토10") carry no school, so None."""
    if class_type != "EXAM_PREP":
        return None
    match = EXAM_PREP_SCHOOL.match(class_name)
    return match["school"] if match else None


def class_type_of(name: str) -> str | None:
    if REGULAR.match(name):
        return "REGULAR"
    if EXAM_PREP.match(name):
        return "EXAM_PREP"
    return None


@dataclass
class TestColumn:
    title: str
    total: int


@dataclass
class StudentRow:
    sheet: str
    row: int
    name: str
    attendance: str | None
    prework: str | None
    weekly: str | None
    scores: dict[str, int | None]
    issues: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.sheet}!{self.row}"

    @property
    def empty(self) -> bool:
        """Only the first cell is filled (e.g. a placeholder note): skipped, not an error."""
        return (
            self.attendance is None
            and self.prework is None
            and self.weekly is None
            and all(v is None for v in self.scores.values())
            and not [i for i in self.issues if not i.startswith("출결이 비어")]
        )


@dataclass
class ClassBlock:
    sheet: str
    row: int
    class_name: str
    class_type: str | None
    tests: list[TestColumn]
    students: list[StudentRow] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)


def _text(value) -> str:
    return " ".join(_format(value).split())


def _header(sheet: str, row_no: int, cells: list) -> ClassBlock:
    name = _text(cells[0])
    issues: list[str] = []
    class_type = class_type_of(name) if name else None
    if not name:
        issues.append("반 이름이 비어 있습니다")
    elif class_type is None:
        issues.append(
            f"반 이름 '{name}'의 형식을 알 수 없습니다 (정규: '중3 토10' / 내신 대비: '00고2 토10')"
        )
    for expected, actual in zip(FIXED_HEADERS, cells[1:4], strict=False):
        if _text(actual) != expected:
            issues.append(f"'{expected}' 열이 필요합니다")
    tests: list[TestColumn] = []
    for cell in cells[4:]:
        label = _text(cell)
        if not label:
            continue
        match = TEST_HEADER.match(label)
        if not match:
            issues.append(f"시험 열 '{label}'에 문항 수가 없습니다 (예: '어휘 (10)')")
            continue
        # "문법,문학,독서" and "문법, 문학, 독서" are the same category.
        title = re.sub(r"\s*,\s*", ", ", match["title"].strip())[:MAX_TITLE]
        total = int(match["total"])
        if total <= 0:
            issues.append(f"시험 열 '{label}'의 문항 수가 0입니다")
        elif any(t.title == title for t in tests):
            issues.append(f"시험 열 '{title}'이(가) 중복되었습니다")
        else:
            tests.append(TestColumn(title, total))
    return ClassBlock(sheet, row_no, name, class_type, tests, issues=issues)


def _score(raw, column: TestColumn, issues: list[str]) -> int | None:
    text = _text(raw)
    if not text:
        return None
    value, _, denominator = text.partition("/")
    if denominator and denominator.strip() != str(column.total):
        issues.append(f"'{column.title}' 전체 문항 수가 머리글({column.total})과 다릅니다")
        return None
    try:
        score = int(float(value.strip()))
        if float(value.strip()) != score:
            raise ValueError
    except ValueError:
        issues.append(f"'{column.title}' 점수 '{text}'를 숫자로 읽을 수 없습니다")
        return None
    if not 0 <= score <= column.total:
        issues.append(f"'{column.title}' 점수는 0~{column.total} 사이여야 합니다")
        return None
    return score


def _student(block: ClassBlock, row_no: int, cells: list) -> StudentRow:
    issues: list[str] = []
    attendance_text = _text(cells[1]) if len(cells) > 1 else ""
    attendance = ATTENDANCE.get(attendance_text) or ATTENDANCE.get(attendance_text.upper())
    if not attendance_text:
        issues.append("출결이 비어 있습니다")
    elif attendance is None:
        issues.append(f"출결 '{attendance_text}'는 출석/지각/결석/인정결석 중 하나여야 합니다")
    grades = []
    for label, index in (("예습 과제", 2), ("주간 과제", 3)):
        text = _text(cells[index]).upper() if len(cells) > index else ""
        if text and text not in GRADES:
            issues.append(f"{label} 등급 '{text}'는 A/B/C 중 하나여야 합니다")
            text = ""
        grades.append(text or None)
    scores = {
        column.title: _score(cells[4 + i] if len(cells) > 4 + i else None, column, issues)
        for i, column in enumerate(block.tests)
    }
    name = _text(cells[0])[:MAX_TITLE]
    return StudentRow(block.sheet, row_no, name, attendance, grades[0], grades[1], scores, issues)


def parse_workbook(content: bytes) -> list[ClassBlock]:
    _check_zip(content)
    try:
        workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:  # openpyxl raises many error types for broken files
        raise CompatibilityError(400, "INVALID_XLSX", "엑셀 파일을 열 수 없습니다.") from exc
    blocks: list[ClassBlock] = []
    total_rows = scanned = 0
    try:
        for sheet in workbook.worksheets:
            current: ClassBlock | None = None
            # max_col: only the columns that are read are built (the sheet's declared width can
            # be 16,384). Every walked row counts, blank or not (SEC-06).
            rows = sheet.iter_rows(values_only=True, max_col=MAX_COLUMNS)
            for row_no, values in enumerate(rows, start=1):
                scanned += 1
                if scanned > MAX_SCANNED_ROWS:
                    raise CompatibilityError(
                        413, "ROW_LIMIT_EXCEEDED", "행이 너무 많습니다(빈 행 포함)."
                    )
                cells = list(values[:MAX_COLUMNS])
                if not any(_text(v) for v in cells):
                    continue
                total_rows += 1
                if total_rows > MAX_ROWS:
                    raise CompatibilityError(413, "ROW_LIMIT_EXCEEDED", "행이 너무 많습니다.")
                if len(cells) > 1 and _text(cells[1]) == "출결":
                    current = _header(sheet.title, row_no, cells)
                    blocks.append(current)
                elif current is not None:
                    current.students.append(_student(current, row_no, cells))
    finally:
        workbook.close()
    if not blocks:
        raise CompatibilityError(
            400,
            "NO_CLASS_BLOCKS",
            "반 머리글(반 이름 | 출결 | 예습 과제 | 주간 과제 | 시험…)을 찾지 못했습니다.",
        )
    return blocks
