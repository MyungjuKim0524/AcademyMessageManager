"""Phase 8 Stage 3: template parsing and rendering rules (no database)."""

from dataclasses import replace
from decimal import Decimal

import pytest

from app.domain import AchievementGrade, _pre
from app.modules.notifications.engine import (
    MAKEUP_SENTENCE,
    SAMPLE_CONTEXT,
    GradeLine,
    TemplateError,
    parse_template,
    render,
)

CTX = replace(SAMPLE_CONTEXT, student_name="김하나", classroom_name="수학 A반", topic="이차함수")


def test_parse_accepts_whitelisted_variables_only() -> None:
    assert parse_template("{학생명} {학생명} {출결}") == ["학생명", "출결"]
    for bad, message in (
        ("", "템플릿 본문을 입력해주세요."),
        ("   ", "템플릿 본문을 입력해주세요."),
        ("{password}", "지원하지 않는 변수: {password}"),
        ("{student.__class__}", "지원하지 않는 변수: {student.__class__}"),
        ("{}", "지원하지 않는 변수: {}"),
        ("{학생명", "중괄호 짝이 맞지 않습니다. 변수는 {학생명}처럼 입력해주세요."),
        ("학생명}", "중괄호 짝이 맞지 않습니다. 변수는 {학생명}처럼 입력해주세요."),
        ("{{학생명}}", "중괄호 짝이 맞지 않습니다. 변수는 {학생명}처럼 입력해주세요."),
        ("가" * 2001, "템플릿은 2000자 이하여야 합니다."),
    ):
        with pytest.raises(TemplateError) as error:
            parse_template(bad)
        assert message in error.value.messages


def test_render_substitutes_values_and_keeps_special_characters() -> None:
    result = render("<b>{학생명}</b> & {분반명} {수업일자} {수업주제} {출결} 100% $1 '\"", CTX)
    assert result.ok
    # Plain text: markup and symbols are kept verbatim, never interpreted.
    assert result.body == "<b>김하나</b> & 수학 A반 2026-01-05 이차함수 출석 100% $1 '\""
    assert len(result.source_hash) == 64


def test_missing_data_is_never_invented() -> None:
    template = "{학생명} {출결} {보강메시지} {성적요약} {수업주제}"
    unrecorded = render(template, replace(CTX, attendance=None))
    assert not unrecorded.ok
    assert "출결 미입력 (결석으로 간주하지 않습니다)" in unrecorded.issues
    assert "결석" not in (unrecorded.body or "").replace("결석으로", "")

    no_score = render(
        template, replace(CTX, grades=(GradeLine("단원 평가", None, None, Decimal(20)),))
    )
    assert "'단원 평가' 성적 미입력" in no_score.issues
    assert "0" not in (no_score.body or "").split("평가 결과")[-1]

    assert "수업 주제 미입력" in render(template, replace(CTX, topic=None)).issues
    assert (
        "취소된 수업입니다 (결석으로 안내하지 않습니다)"
        in render(template, replace(CTX, lesson_status="CANCELLED")).issues
    )
    assert (
        "보호자 이메일이 등록되어 있지 않습니다"
        in render(template, replace(CTX, recipient_email=None)).issues
    )
    paused = render(template, replace(CTX, eligible=False, attendance=None))
    assert "수업일 기준 수강 대상이 아닙니다 (휴원·수강 기간 밖)" in paused.issues


def test_unused_variables_do_not_block() -> None:
    # A template without {출결} can be generated even when attendance is not entered.
    assert render("{학생명} 안내", replace(CTX, attendance=None)).ok


def test_attendance_grades_and_legacy_sentences() -> None:
    template = "{출결}|{보강메시지}|{성적요약}|{예습메시지}|{테스트메시지}|{교시}"
    absent = render(
        template,
        replace(CTX, attendance="ABSENT", prework_grade="A", correct_count=13, total_count=39),
    )
    expected = f"결석|{MAKEUP_SENTENCE}|평가 결과: 예시 평가 18.5/20|{_pre(AchievementGrade.A)}"
    assert absent.body == expected + "|테스트 결과는 13/39입니다.|"
    excused = render(template, replace(CTX, attendance="EXCUSED", session_no=2))
    assert excused.body.startswith("인정결석||")  # excused is not a plain absence: no makeup text
    assert excused.body.endswith("|2교시")
    grades = (
        GradeLine("퀴즈", "NOT_TAKEN", None, Decimal("10")),
        GradeLine("단원", "SCORED", Decimal("0"), Decimal("20.00")),
    )
    assert (
        render("{성적요약}", replace(CTX, grades=grades)).body
        == "평가 결과: 퀴즈 미응시, 단원 0/20"
    )
    empty = render("{학생명}\n{성적요약}", replace(CTX, grades=()))
    assert empty.ok and empty.body == "김하나"
    assert "이 수업에 연결된 평가가 없어 성적 요약은 비워집니다." in empty.warnings


def test_blank_lines_and_length_limits() -> None:
    assert render("{학생명}\n\n\n\n{보강메시지}\n\n\n끝", CTX).body == "김하나\n\n끝"
    assert render("{시험회차}", CTX).issues == ["생성된 메시지가 비어 있습니다"]
    long_name = replace(CTX, student_name="가" * 2000)
    assert "생성된 메시지가 2000자를 넘습니다" in render("{학생명} {분반명}", long_name).issues


def test_source_hash_tracks_rendered_inputs_only() -> None:
    base = render("{학생명} {출결}", CTX).source_hash
    assert render("{학생명} {출결}", replace(CTX, attendance="LATE")).source_hash != base
    assert render("{학생명} {출결}", replace(CTX, topic="다른 주제")).source_hash == base
