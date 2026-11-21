# Phase 10 — 통계 지표 정의 (Stage 2)

작성일: 2026-11-20 · 근거: 실제 스키마·서비스 규칙(`docs/phase10-implementation-plan.md` 1절)

## 0. 공통 정의
- **진행된 수업(held lesson)**: `lesson.status <> 'CANCELLED'` AND `lesson_date <= 오늘` AND (`status = 'COMPLETED'` OR 그 수업에 `lesson_result` 1건 이상). 메시지 처리 현황(`message_operations`)과 **같은 정의**.
- **진행 기록 없는 수업**: 지난 날짜 + `SCHEDULED` + 출결 0건. 대상에서 빠지므로 **건수를 별도 경고로 표시**.
- **수업일 자격(eligible)**: `academics.repository.eligible_on(day)` — `enrolled_at ≤ day ≤ ended_at(없으면 무기한)`, 그날 휴원 기간 아님(`paused_from ≤ day < resumed_on`), 종료일 없는 WITHDRAWN·휴원 이력 없는 구 PAUSED는 기간을 알 수 없어 **대상 아님**(추정 안 함). 기존 출결·성적 입력 화면과 같은 규칙.
- **대상 외 기록**: 자격이 없는 날짜에 존재하는 출결·성적 행(과거·업로드 기록). 대상 통계·비율에 넣지 않고 건수만 따로 표시.
- **계산 불가**: 분모가 0이면 비율·평균은 `null`(API) / "대상 없음" 등(UI). **0%로 표시하지 않음**.
- **정밀도**: 건수는 SQL 정수 집계, 비율은 그 정수로 Python `Decimal` 계산 후 ROUND_HALF_UP 소수 1자리. 점수 평균은 PostgreSQL `numeric AVG`(정수화 없음) → `ROUND(,2)`, 평균·학생 백분율은 반올림 전 평균으로 `ROUND(,1)`(0.5는 0에서 먼 쪽). UI는 API 값을 그대로 표시.
- **기간**: `date_from ≤ 날짜 ≤ date_to`(양끝 포함), 최대 366일. 출결은 `min(date_to, 오늘)`까지만 대상(미래 수업은 진행 전).

## 1. 출결 지표
| Metric | Definition | Numerator | Denominator | Inclusion | Exclusion | Null Policy | Precision | Edge Cases | Source | Verification |
|---|---|---|---|---|---|---|---|---|---|---|
| 출결 대상 건수 `target` | 출결을 기록해야 했던 학생·수업 조합 수 | — | — | 진행된 수업 × 그날 자격 있는 수강 | 취소·미래·진행 기록 없는 수업, 자격 없는 날 | — | 정수 | 같은 날 여러 회차는 회차마다 1건 | lesson, enrollment, enrollment_pause | 중도 등록·퇴원·휴원·취소·다회차 사례 |
| 기록 완료 `recorded` | 대상 중 출결이 입력된 건수 | — | — | 대상 ∩ `lesson_result` 존재 | 대상 외 기록 | 행 없음 = 미입력 | 정수 | — | lesson_result | `recorded = present+late+absent+excused` |
| 미입력 `unrecorded` | 대상 중 출결이 없는 건수 | — | — | 대상 ∩ 행 없음 | — | **결석으로 보지 않음** | 정수 | — | — | `target = recorded + unrecorded` |
| 상태별 건수 | 대상 중 각 상태 건수 | — | — | 대상 ∩ 상태 | — | — | 정수 | 4상태만(PRESENT/LATE/ABSENT/EXCUSED, CHECK 제약) | lesson_result | 혼합 사례 |
| 출결 입력 완료율 `record_rate`(2026-11-21 화면 이름 변경, 이전 '기록 완료율') | 해야 할 출결 중 입력된 비율 | recorded | target | — | — | target = 0 → `null` | % 소수 1자리 | — | — | 독립 계산 |
| 출석률 `attendance_rate` | 입력된 출결 중 수업에 온 비율 (**사용자 결정 2026-11-20**) | present + late | recorded − excused | 지각 = 출석 인정 | 인정결석은 분모·분자 제외, 미입력 제외 | 분모 0 → `null` | % 소수 1자리 | 모두 인정결석 → `null` | lesson_result | 독립 계산 |
| 대상 외 기록 `outside_records` | 자격 없는 날의 출결 행 | — | — | 진행된 수업 ∩ 자격 없음 ∩ 행 존재 | 비율 계산 전부 | — | 정수 | 과거 기록 | lesson_result | 과거 수강 이력 사례 |
| 진행 기록 없는 수업 `not_held_lessons` | 지난 SCHEDULED + 출결 0건 수업 수 | — | — | 기간 내 | — | — | 정수 | 개발 DB에 3건 존재 | lesson | 사례 |

학생별 지표는 같은 정의를 학생(수강) 단위로 적용. 수업별 미입력은 같은 정의를 수업 단위로 적용(입력 화면 링크용).

## 2. 성적 지표
| Metric | Definition | Numerator | Denominator | Inclusion | Exclusion | Null Policy | Precision | Edge Cases | Source | Verification |
|---|---|---|---|---|---|---|---|---|---|---|
| 평가 대상 `target` | 평가일 기준 자격 있는 수강생 수 | — | — | `eligible_on(assessment_date)` (기존 성적 명단 규칙) | 자격 없음 | — | 정수 | — | assessment, enrollment, enrollment_pause | 중도 등록·휴원 |
| 점수 입력 `scored` | 대상 중 점수가 있는 학생 | — | — | 대상 ∩ SCORED | — | 0점 포함 | 정수 | — | assessment_result | 0점 사례 |
| 미응시 `not_taken` | 대상 중 미응시로 기록 | — | — | 대상 ∩ NOT_TAKEN | 평균에서 제외 | — | 정수 | — | assessment_result | — |
| 미입력 `missing` | 대상 중 결과 행이 없는 학생 | — | — | 대상 ∩ 행 없음 | — | **0점 아님** | 정수 | 미래 평가는 입력 불가 기간 → `upcoming` 표시 | — | `target = scored + not_taken + missing` |
| 입력 완료율 `entry_rate` | 대상 중 결과(점수 또는 미응시)가 기록된 비율 | scored + not_taken | target | — | 대상 외 기록 | target 0 또는 미래 평가 → `null` | % 소수 1자리 | — | — | 독립 계산 |
| 평균 점수 `average` | 실제 점수의 산술 평균 | Σ score (SCORED) | SCORED 건수 | 해당 평가의 **모든 SCORED**(대상 외 기록 포함 — 실제 응시 점수이므로) | NOT_TAKEN, 미입력 | SCORED 0건 → `null` | 소수 2자리 | 0점 포함 | assessment_result | 소수점 점수·0점 사례 |
| 평균 백분율 `average_percent` | 평균 ÷ 만점 × 100 | average | max_score(>0, CHECK) | — | — | average null → null | % 소수 1자리 | 만점 다른 평가끼리 비교 문구 없음 | assessment | 만점 다른 평가 |
| 평균 산출 인원 `average_count` | 평균에 쓰인 점수 수 | — | — | 모든 SCORED | — | — | 정수 | 대상 외 기록이 있으면 `scored`와 다를 수 있음 | — | 사례 |

### 학생 성적 추이
| 항목 | 정의 |
|---|---|
| 포함 평가 | 반의 기간 내 평가 중 그 학생이 평가일에 자격이 있었거나 결과가 있는 것 |
| 상태 | SCORED(점수) / NOT_TAKEN(미응시) / MISSING(대상인데 결과 없음) / UPCOMING(미래 평가) |
| 백분율 | `score / max_score × 100`, SCORED에서만, 소수 1자리. 그 외 `null` |
| 정렬 | 평가일 ↑, 연결 수업 회차 ↑(연결 없으면 뒤), 평가 ID ↑ — 같은 날 여러 평가도 항상 같은 순서 |
| 해석 제한 | 점수 1건이면 추이 없음. 서로 다른 평가의 원점수·백분율은 난이도가 달라 직접 비교 불가 — 화면에 명시. 향상·하락 자동 판정·순위·반간 비교 **하지 않음** |

## 3. 해당 없음으로 확인된 항목
- 평가 취소·무효 상태: 스키마에 없음(`assessment`에 status 없음). 연결 수업 취소는 서비스가 막음(기록·평가 연결 시 취소 불가).
- 출결 중복: `uq_lesson_result(lesson_id, enrollment_id)`. 성적 중복: `uq_assessment_result`. 학생·반 수강 중복: `uq_enrollment_student_classroom`.
- 출결 상태 추가: 하지 않음(4상태 CHECK 그대로).
