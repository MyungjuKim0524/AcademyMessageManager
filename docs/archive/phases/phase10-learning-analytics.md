# Phase 10 — 교육 데이터 분석 최종 보고서

작성일: 2026-11-20 · 계획 `phase10-implementation-plan.md` · 산식 `phase10-metric-definitions.md` · 진행 `phase10-progress.md` · 체크리스트 `phase10-manual-test-checklist.md` · EXPLAIN 원본 `phase10-explain-measurement.txt`

## 1. 목표
기존 수업·출결·성적 데이터를 정확하고 해석 가능한 통계로 바꿔, 직원이 반별 출결 상태와 학생별 학습 결과를 빠르게 이해하고 빠진 기록을 입력 화면에서 바로 채우게 한다.

## 2. 구현한 기능
| 지시 | 구현 |
|---|---|
| F1 반별 출결 | 대상·기록·미입력·출석/지각/결석/인정결석·기록 완료율·출석률 + 대상 외 기록 + 진행 기록 없는 수업 수 |
| F2 학생별 출결 | 학생별 요약 표(상태별 정렬로 반복 결석·지각 확인) + 학생 클릭 시 수업별 이력, 각 수업 출결 화면 링크 |
| F3 평가별 성적 | 대상·점수·미응시·미입력·입력 완료율·평균(인원)·평균/만점, 미래 평가 '예정' |
| F4 학생별 추이 | 평가 이력(날짜·평가·점수·만점·%·상태) + 0~100% 고정 축 점·선 차트 |
| F5 필터·탐색 | 반(작업 반 유지)·기간(최근 4주/3개월)·학생·평가, 모두 주소에 저장 |
| F6 시각화 | 출결 상태 누적 막대(범례에 이름·건수·%), 성적 추이 차트 — 각각 표 병기 |
최고·최저점·순위·반간 비교·예측은 구현하지 않음(범위 외).

## 3. 출결 분석 데이터 모델
대상 = (진행된 수업) × (그날 `eligible_on` 수강). 진행된 수업 = 취소 아님·미래 아님·(완료 또는 출결 1건 이상) — 메시지 처리 현황과 같은 정의. `lesson_result` 없음 = 미입력.

## 4. 성적 분석 데이터 모델
대상 = 평가일 기준 `eligible_on` 수강(기존 성적 명단 규칙). `assessment_result` 없음 = 미입력, NOT_TAKEN = 미응시, SCORED 0 = 0점.

## 5. 산식
| 지표 | 산식 | 분모 0 |
|---|---|---|
| 기록 완료율 | 기록 ÷ 대상 | `null`("대상 없음") |
| 출석률 (**사용자 결정**) | (출석+지각) ÷ (기록−인정결석), 미입력 제외 | `null`("계산 불가") |
| 입력 완료율 | (점수+미응시) ÷ 대상, 미래 평가 제외 | `null` |
| 평균 | SCORED 점수 산술 평균(0점 포함) | `null`("점수 없음") |
| 평균·학생 % | 점수 ÷ 만점 × 100 | — |
정밀도: 비율 Decimal ROUND_HALF_UP 소수 1자리(정수 건수에서 계산), 평균은 PostgreSQL `numeric AVG` → `ROUND(,2)`, 백분율 `ROUND(,1)`. 정수화 없음.

## 6. PostgreSQL 설계
대상 집합 CTE(`attendance_pairs` / `grade_pairs`)를 먼저 만들고 결과를 LEFT JOIN → `COUNT(*) FILTER (WHERE …)` 조건부 집계 + `GROUP BY` 학생/수업/평가. 중복 방지는 유니크 제약(학생·반 수강 1건, 수업·수강 1건, 평가·수강 1건)으로 구조적으로 보장되어 `DISTINCT` 불필요. CTE는 `MATERIALIZED`(아래 14절 측정 근거), 학생 단위 조회는 학생 필터를 CTE 안에 둠. 요청당 쿼리 2~4개 고정(N+1 없음). 기간 최대 366일.

## 7. 신규 API (전부 GET, 읽기 전용, 기존 API 변경 없음)
`/api/analytics/attendance`, `/attendance/students/{student_id}`, `/grades`, `/grades/assessments/{assessment_id}`, `/grades/students/{student_id}` (`classroom_id`, `date_from`, `date_to`). 모듈 `backend/app/modules/analytics/`.

## 8–10. UI와 기존 화면 연결
사이드바 '학사 운영 › 출결·성적 분석' 1개 + 화면 안 탭 2개(출결 분석/성적 분석) — 사용자 선호(업무당 메뉴 1개). 링크: 미입력 수업·학생 이력 → `/classes?…&tab=attendance&lesson=…`, 점수 입력 → `/classes?…&tab=progress&day=…`(학습 현황), 진행 기록 없는 수업 → `/classes?…&tab=lessons`, 빈 기간 → 출결·평가 관리. 새 대시보드 없음, 새 라이브러리 없음(antd + 작은 SVG/CSS). 차트 색은 dataviz 검증 스크립트로 확인(출석 #389e0d·지각 #d4b106·결석 #cf1322·인정결석 #722ed1, CVD 최악 인접 ΔE 10.2 PASS, 대비 WARN → 범례 텍스트·표로 보완).

## 11. RBAC·IDOR/BOLA
모든 요청이 기존 `_require_classroom`과 같은 규칙(ADMIN 전체, 그 외 오늘 유효한 배정 반). 학생은 **그 반 수강생일 때만**(아니면 404), 평가는 평가의 반으로 권한 검사. 통합 테스트로 확인: 미배정 반 403, 관리자 허용, 다른 반 학생 id 404/403, 다른 반 평가 403, 배정 종료 403, 비활성 직원 401, 비로그인 401, 잘못된 기간 400.

## 12–13. 데이터 정합성 테스트 (독립 기대값)
`backend/tests/test_phase10_analytics_integration.py` — 손으로 계산한 가상 데이터(학생 6·수업 8·평가 6)로: 전체/혼합/인정결석/미입력/대상 없음/중도 등록/중도 퇴원/휴원/과거 기록(대상 외)/취소 수업/같은 날 2교시/학생별 수업 수 차이/진행 기록 없는 수업, 0점·미응시·미입력·만점 다른 평가·소수점 점수(15.5, 12.25)·같은 날 여러 평가 정렬·이력 1건·미래 평가·대상 판정, 불변식(대상=기록+미입력, 기록=상태 합, 대상=점수+미응시+미입력), 조회 전후 행 수·updated_at·audit_log 불변(읽기 전용).

## 14. 성능 (테스트 DB 합성 데이터에서 실측, 끝나면 rollback)
규모: 반 20 · 수강 607 · 수업 2,089 · 출결 55,682 · 평가 1,046 · 성적 26,546. 1년 기간, 30명 반.
| 쿼리 | 최초 구현 | MATERIALIZED | + 학생 필터 CTE 내부 |
|---|---|---|---|
| 반 출결(학생별) | 369.8 ms | 55.4 ms | **45.9 ms** |
| 반 출결(수업별) | 111.1 ms | 64.6 ms | **42.2 ms** |
| 학생 출결 | 1.6 ms | 44.9 ms | **1.1 ms** |
| 반 성적 | 72.6 ms | 24.2 ms | **21.6 ms** |
| 평가 상세 | 1.8+2.1 ms | 1.0+1.5 ms | **0.7+0.8 ms** |
| 학생 성적 | 1.2 ms | 24.0 ms | **1.0 ms** |
(PostgreSQL Execution Time, EXPLAIN ANALYZE.) 인덱스 사용: `idx_lesson_classroom`, `idx_enrollment_classroom`, `idx_assessment_classroom_date`, `uq_assessment_result`, `idx_lesson_result_enrollment`. 반 단위 출결은 `lesson_result` 해시 조인용 순차 스캔(5.5만 행 ≈ 8 ms) — 현재 규모에서 인덱스 추가 근거 없음. `enrollment_pause`는 btree 없이 순차 스캔(작은 표). **새 인덱스·Migration 없음.** 개발 DB 실데이터(수업 5건)로는 성능 의미가 없어 측정하지 않음.

## 15–17. 회귀·React·E2E (2026-11-20 실제 실행)
| 항목 | 결과 |
|---|---|
| Ruff | PASS |
| pytest 단위 | 39 PASS |
| pytest PostgreSQL 통합(테스트 DB) | **69 PASS**(Phase 10 신규 11 포함, 인증·RBAC·출결·성적·메시지·업로드 회귀) |
| Java `mvn -o test` | 48 실행 · 0 실패 · 6 skip(PostgreSQL 통합은 `-DrunPostgresIntegration` 필요, 미실행 — Java는 GitHub 대상 아님, 구 import 테이블은 010에서 제거됨) |
| Vitest 전체 | **13 files / 82 PASS**(신규 분석 6 + 메뉴 기대값 1) |
| tsc · oxlint(프로젝트 lint 도구, ESLint 미설치) · build | PASS (기존 500kB 청크 경고만) |
| 브라우저 E2E | **NOT RUN** — 자동화 도구 없음. `phase10-manual-test-checklist.md` 16항목 |
기존 테스트 기대값 변경: `AppLayout.test`의 메뉴 목록에 '출결·성적 분석' 추가 1건뿐.

## 18. DB Migration
없음. 개발 DB에는 읽기 전용 count 조회만 함. 테스트 DB 합성 데이터는 트랜잭션 rollback으로 제거.

## 19. 제약·미완료
- 브라우저 실제 화면·좁은 폭 미확인(NOT RUN).
- 학생 목록은 페이지네이션 없음(반 단위, 수십 명 가정). 반 규모가 크게 늘면 재검토.
- 대상 외 기록의 SCORED 점수는 평균에 포함(실제 응시 점수) — 정의 문서 명시. 다르게 원하면 정책 변경 필요.
- 진행 기록 없는 지난 SCHEDULED 수업은 대상에서 빠짐(경고로 노출). 개발 DB에 3건 있음 — 실제 진행했다면 완료 처리 필요.
- 차트 다크 모드 없음(앱 자체가 라이트 전용).

## 20. Phase 11 인계
집계 성능은 반·기간에 선형(위 표), `lesson_result` 순차 스캔은 전체 출결 행 수에 비례 — 수십만 행 이상이면 `(lesson_id, enrollment_id)` 유니크 인덱스 활용 계획 재확인. 현재 Alembic head `010_drop_legacy_import_tables`. 미검증: 브라우저 E2E, 동시 수정 중 조회 일관성(READ COMMITTED 단일 쿼리 단위). 보안 추가 점검: 분석 API 요청 빈도 제한 없음(기존 API와 동일).

## 21. 최종 판정
**조건부 완료** — Stage 1~6 완료, Stage 7은 자동 회귀 전부 통과, 실제 브라우저 E2E만 NOT RUN.
