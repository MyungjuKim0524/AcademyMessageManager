"""Deterministic parent-message template engine.

Syntax is the one already used by the Java/Python message composer: ``{변수명}`` placeholders,
plain string substitution and blank-line clean-up. There are no expressions, attribute access,
filters or code execution. Only whitelisted variables are accepted.

Missing source data is never invented: unrecorded attendance is not "absent", a missing score
is not 0 and a cancelled lesson is not an absence. Such cases produce *issues*, and a message
with issues cannot be saved (so it can never be approved).
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from decimal import Decimal

MAX_LENGTH = 2000
PLACEHOLDER = re.compile(r"\{([^{}]*)\}")

VARIABLES: dict[str, str] = {
    "학생명": "학생 이름",
    "분반명": "반 이름",
    "수업일자": "수업일 (예: 2026-11-03)",
    "교시": "같은 날 2교시 이상일 때 'N교시', 1교시는 빈 값",
    "시험회차": "시험 회차 (없으면 빈 값)",
    "수업주제": "수업 주제 — 미입력이면 생성 불가",
    "출결": "출석/지각/결석/인정결석 — 미입력이면 생성 불가",
    "보강메시지": "결석일 때 보강 안내 문장, 그 외 빈 값 — 출결 미입력이면 생성 불가",
    "성적요약": "이 수업에 연결된 평가 결과 — 결과 미입력이면 생성 불가, 연결 평가가 없으면 빈 값",
    "예습메시지": "예습 과제 등급 문장 (기존 가져오기 데이터, 없으면 빈 값)",
    "주간메시지": "주간 과제 등급 문장 (기존 가져오기 데이터, 없으면 빈 값)",
    "테스트메시지": "테스트 정답 수 문장 (기존 가져오기 데이터, 없으면 빈 값)",
}

ATTENDANCE_LABEL = {"PRESENT": "출석", "LATE": "지각", "ABSENT": "결석", "EXCUSED": "인정결석"}
# Parent-facing sentences. This module is their single source; the Java-compatible legacy
# preview (app.domain) imports them so both message paths stay word-for-word identical.
# Only a plain absence gets the makeup sentence (EXCUSED does not).
MAKEUP_SENTENCE = "이번 수업은 결석으로 인해 학습 내용 확인이 필요합니다."
# Keys are the stored grade codes (DB CHECK: 'A','B','C').
PREWORK_SENTENCE = {
    "A": "예습 과제를 성실하게 수행하였습니다.",
    "B": "예습 과제를 대체로 수행하였으나 일부 보완이 필요합니다.",
    "C": "예습 과제 수행이 부족하여 추가적인 확인이 필요합니다.",
}
WEEKLY_SENTENCE = {
    "A": "주간 과제를 안정적으로 완료하였습니다.",
    "B": "주간 과제 수행은 양호하나 일부 문항에서 보완이 필요합니다.",
    "C": "주간 과제 수행이 부족하여 가정에서도 추가 학습이 필요합니다.",
}


class TemplateError(ValueError):
    def __init__(self, messages: list[str]):
        super().__init__("; ".join(messages))
        self.messages = messages


def parse_template(body: str) -> list[str]:
    """Return the variables used by ``body`` or raise ``TemplateError``."""
    errors: list[str] = []
    if not body or not body.strip():
        raise TemplateError(["템플릿 본문을 입력해주세요."])
    if len(body) > MAX_LENGTH:
        errors.append(f"템플릿은 {MAX_LENGTH}자 이하여야 합니다.")
    names = PLACEHOLDER.findall(body)
    if "{" in PLACEHOLDER.sub("", body) or "}" in PLACEHOLDER.sub("", body):
        errors.append("중괄호 짝이 맞지 않습니다. 변수는 {학생명}처럼 입력해주세요.")
    unknown = sorted({name for name in names if name not in VARIABLES})
    if unknown:
        errors.append("지원하지 않는 변수: " + ", ".join("{" + n + "}" for n in unknown))
    if errors:
        raise TemplateError(errors)
    return list(dict.fromkeys(names))


@dataclass(frozen=True)
class GradeLine:
    title: str
    result_status: str | None  # None = not entered
    score: Decimal | None
    max_score: Decimal


@dataclass(frozen=True)
class MessageContext:
    student_name: str
    classroom_name: str
    lesson_date: str
    session_no: int
    exam_round: str | None
    topic: str | None
    lesson_status: str
    eligible: bool
    recipient_email: str | None
    attendance: str | None = None  # None = not entered
    prework_grade: str | None = None
    weekly_grade: str | None = None
    correct_count: int | None = None
    total_count: int | None = None
    grades: tuple[GradeLine, ...] = ()


@dataclass
class RenderResult:
    body: str | None
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source_hash: str | None = None

    @property
    def ok(self) -> bool:
        return self.body is not None and not self.issues


def _number(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    return text


def _grade_summary(grades: tuple[GradeLine, ...], issues: list[str], warnings: list[str]) -> str:
    if not grades:
        warnings.append("이 수업에 연결된 평가가 없어 성적 요약은 비워집니다.")
        return ""
    parts = []
    for line in grades:
        if line.result_status is None:
            issues.append(f"'{line.title}' 성적 미입력")
        elif line.result_status == "NOT_TAKEN":
            parts.append(f"{line.title} 미응시")
        else:
            parts.append(f"{line.title} {_number(line.score)}/{_number(line.max_score)}")
    return "평가 결과: " + ", ".join(parts) if parts else ""


def _value(name: str, ctx: MessageContext, issues: list[str], warnings: list[str]) -> str:
    if name == "학생명":
        return ctx.student_name
    if name == "분반명":
        return ctx.classroom_name
    if name == "수업일자":
        return ctx.lesson_date
    if name == "교시":
        return f"{ctx.session_no}교시" if ctx.session_no > 1 else ""
    if name == "시험회차":
        return ctx.exam_round or ""
    if name == "수업주제":
        if not ctx.topic:
            issues.append("수업 주제 미입력")
        return ctx.topic or ""
    if name in ("출결", "보강메시지"):
        if ctx.attendance is None:
            issues.append("출결 미입력 (결석으로 간주하지 않습니다)")
            return ""
        if name == "출결":
            return ATTENDANCE_LABEL[ctx.attendance]
        return MAKEUP_SENTENCE if ctx.attendance == "ABSENT" else ""
    if name == "성적요약":
        return _grade_summary(ctx.grades, issues, warnings)
    if name == "예습메시지":
        return PREWORK_SENTENCE[ctx.prework_grade] if ctx.prework_grade else ""
    if name == "주간메시지":
        return WEEKLY_SENTENCE[ctx.weekly_grade] if ctx.weekly_grade else ""
    if name == "테스트메시지":
        if ctx.correct_count is None or ctx.total_count is None:
            return ""
        return f"테스트 결과는 {ctx.correct_count}/{ctx.total_count}입니다."
    raise TemplateError([f"지원하지 않는 변수: {{{name}}}"])  # unreachable after parse


def _normalize(text: str) -> str:
    # Same clean-up as app.domain.compose_message.
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    while "\n\n\n" in normalized:
        normalized = normalized.replace("\n\n\n", "\n\n")
    return normalized.strip()


def render(template_body: str, ctx: MessageContext) -> RenderResult:
    names = parse_template(template_body)
    issues: list[str] = []
    warnings: list[str] = []
    if ctx.lesson_status == "CANCELLED":
        issues.append("취소된 수업입니다 (결석으로 안내하지 않습니다)")
    if not ctx.eligible and ctx.attendance is None:
        issues.append("수업일 기준 수강 대상이 아닙니다 (휴원·수강 기간 밖)")
    if not ctx.recipient_email:
        issues.append("보호자 이메일이 등록되어 있지 않습니다")
    values = {name: _value(name, ctx, issues, warnings) for name in names}
    text = PLACEHOLDER.sub(lambda m: values[m.group(1)], template_body)
    body = _normalize(text)
    if not body:
        issues.append("생성된 메시지가 비어 있습니다")
    elif len(body) > MAX_LENGTH:
        issues.append(f"생성된 메시지가 {MAX_LENGTH}자를 넘습니다")
    fingerprint = json.dumps(
        {
            "values": values,
            "recipient": ctx.recipient_email,
            "lesson_status": ctx.lesson_status,
            "attendance": ctx.attendance,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return RenderResult(
        body=body or None,
        issues=list(dict.fromkeys(issues)),
        warnings=list(dict.fromkeys(warnings)),
        source_hash=hashlib.sha256(fingerprint.encode()).hexdigest(),
    )


SAMPLE_CONTEXT = MessageContext(
    student_name="가상학생",
    classroom_name="예시반",
    lesson_date="2026-01-05",
    session_no=1,
    exam_round=None,
    topic="예시 수업 주제",
    lesson_status="COMPLETED",
    eligible=True,
    recipient_email="parent@example.invalid",
    attendance="PRESENT",
    grades=(GradeLine("예시 평가", "SCORED", Decimal("18.5"), Decimal("20")),),
)
"""Fictional data for template previews; never real student information."""
