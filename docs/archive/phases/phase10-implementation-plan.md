# Phase 10 — 교육 데이터 분석: Stage 1 분석·구현 계획

작성일: 2026-11-20 · 산식: `docs/analytics/phase10-metric-definitions.md` · 진행: `docs/archive/phases/phase10-progress.md`

## 0. 작업 환경 사실
- Git 없음(설치·초기화 안 됨) → 변경 전 백업(스크래치패드) + 변경 파일을 진행 문서에 기록. `git init`·커밋·업로드 하지 않음.
- 컨테이너: `academy-learningops-postgres-dev`(127.0.0.1:55431, `academy_learningops_dev`), `academy-learningops-postgres-test`(127.0.0.1:55432, 파괴적 테스트 허용 라벨). 지시서의 `academy-postgres` 컨테이너는 이 환경에 없음 → 건드릴 대상 없음.
- Alembic head: `010_drop_legacy_import_tables`(개발 DB도 010 적용 확인, 읽기 전용 조회).
- 개발 DB 규모(읽기 전용 count): 반 2 · 수강 5 · 휴원 이력 1 · 수업 5(취소 0, **지난 SCHEDULED 3**) · 출결 7 · 평가 4 · 성적 6(미응시 0). 성능 판단은 테스트 DB 합성 데이터로 한다.
- Phase 9.6에서 구 CSV/XLSX Import·`import_*` 테이블은 제거됨(사용자 승인). 지시서 12.1의 "Import 회귀"는 현재 업로드 기능(`/api/lesson-uploads`) 회귀로 대체.

## 1. 실제 구현 상태 (코드 기준)
| 영역 | 위치 | 분석에 쓰는 사실 |
|---|---|---|
| 수강 | `enrollment` (`uq_enrollment_student_classroom` = 학생·반당 1건), `enrolled_at`·`ended_at`·`status(ACTIVE/PAUSED/WITHDRAWN)` | 학생+반 → 수강 1건이라 JOIN 중복 없음 |
| 휴원 | `enrollment_pause(paused_from, resumed_on)` + 겹침 금지 EXCLUDE(gist) | 날짜별 휴원 재현 가능 |
| 수업일 자격 | `academics.repository.eligible_on(day)` (SQL 식) | 수강 기간 안 + 그날 휴원 아님. **알 수 없는 기간은 추정하지 않음**(종료일 없는 WITHDRAWN, 휴원 이력 없는 구 PAUSED → 대상 아님) |
| 수업 | `lesson(status SCHEDULED/COMPLETED/CANCELLED, session_no 1~9)` | 같은 날 여러 회차 가능 |
| 출결 | `lesson_result(attendance_status NOT NULL ∈ PRESENT/LATE/ABSENT/EXCUSED)`, `uq_lesson_result(lesson_id, enrollment_id)` | **행 없음 = 미입력**(결석과 구분됨), 학생·수업당 1행 보장 |
| 평가 | `assessment(max_score NUMERIC(6,2) > 0, assessment_date, lesson_id NULL 가능)` | 평가마다 만점 다름, 취소 상태 없음 |
| 성적 | `assessment_result(result_status ∈ SCORED/NOT_TAKEN, score NUMERIC(6,2))`, `uq_assessment_result(assessment_id, enrollment_id)`, CHECK: SCORED ⇔ score NOT NULL, 0 ≤ score ≤ max | **행 없음 = 미입력, NOT_TAKEN = 미응시, SCORED 0 = 실제 0점**이 DB에서 구분됨 |
| 업무 규칙(서비스) | `academics/service.py` | 취소 수업·미래 수업에는 출결 기록 불가, 기록 있는 수업은 취소 불가, 미래 평가에는 점수 기록 불가 |
| "진행된 수업" | `message_operations/service.py` | 취소 아님 + 미래 아님 + (COMPLETED 또는 출결 1건 이상). 지난 SCHEDULED + 출결 없음 = "진행 기록 없음" |
| 평가 대상 | `academics.repository.grade_roster` | 평가일 기준 `eligible_on` 학생 (기존 성적 입력 화면과 동일) |
| 권한 | `AcademicsService._require_classroom` → `LearningOpsRepository.can_access_classroom` | ADMIN 전체, TEACHER/ASSISTANT는 **오늘 유효한** 같은 역할 배정 반만. 비활성 직원·만료 세션은 인증 단계에서 401 |
| 기존 조회 | `GET /api/classrooms/{id}/progress`(하루~93일 격자), 출결 명단·성적 명단 | 분석과 같은 자격 규칙을 이미 사용 |

## 2. 6.2 질문에 대한 답
| 질문 | 답 |
|---|---|
| 출결 대상 학생 결정 | 수업일 기준 `eligible_on` (수강 기간 + 휴원 이력) |
| 특정 날짜 자격 재현 | 가능 — `enrolled_at`·`ended_at`·`enrollment_pause` 날짜 이력. 재현 불가 경우(종료일 없는 퇴원, 이력 없는 구 휴원)는 기존 규칙대로 대상 아님(추정 안 함) |
| 출결 미입력 표현 | `lesson_result` 행 없음 |
| 지각·인정결석 | `LATE`, `EXCUSED` (CHECK 제약) |
| 평가 만점 저장 | `assessment.max_score`(결과 행에도 FK로 복제·일치 보장) |
| 미입력 vs 0점 | 구분됨(행 없음 / SCORED 0) + 미응시(NOT_TAKEN) 별도 |
| 평가 대상 판정 | 가능 — 기존 성적 명단과 같은 평가일 기준 자격 |
| 권한 재사용 | 가능 — `_require_classroom` 그대로 |
| 대시보드 연결 | 새 대시보드 안 만듦. 사이드바 1개 항목(사용자 선호: 업무당 메뉴 1개 + 화면 내 탭) |

## 3. 출결 통계 제약
- 대상 집합 = (진행된 수업) × (그날 자격 있는 수강). 출결 테이블만 세면 미입력을 셀 수 없으므로 **대상 집합을 먼저 만든 뒤 LEFT JOIN**.
- 자격 밖인데 기록이 있는 경우(과거 기록) → 대상 통계에서 빼고 "대상 외 기록"으로 따로 표시.
- 지난 SCHEDULED + 출결 없음 수업은 대상에서 빠지므로(진행 기록 없음) **건수를 별도 경고로 표시**(숨은 미입력 방지).
- 출석률: 지각·인정결석 처리 정책이 코드·문서 어디에도 없음 → **사용자 결정 필요**(Stage 2).

## 4. 성적 통계 제약
- 평균 = SCORED 점수만(0점 포함, 미응시·미입력 제외), PostgreSQL `numeric AVG`(정수화 없음).
- 평가 대상 = 평가일 기준 자격(기존 성적 명단 규칙) → 입력 완료율 계산 가능. 미래 평가는 "예정"(입력 불가 기간)으로 미입력에 넣지 않음.
- 만점이 평가마다 달라 원점수 비교 금지 → 백분율(점수/만점) 병기, 서로 다른 평가 비교 문구 없음.
- 평가 취소 상태 없음(지시서 "유효하지 않은 평가 상태"는 해당 없음, 문서화).

## 5. 신규 API 계획 (읽기 전용, 새 모듈 `app/modules/analytics`)
| 메서드·경로 | 내용 |
|---|---|
| `GET /api/analytics/attendance?classroom_id&date_from&date_to` | 반 요약 + 학생별 요약 + 수업별 미입력(입력 화면 링크용) + 진행 기록 없는 수업 수 |
| `GET /api/analytics/attendance/students/{student_id}?classroom_id&date_from&date_to` | 학생의 수업별 출결 이력 |
| `GET /api/analytics/grades?classroom_id&date_from&date_to` | 평가별 요약(대상·입력·미응시·미입력·평균·평균 백분율) |
| `GET /api/analytics/grades/assessments/{assessment_id}` | 평가 상세(학생별 점수) |
| `GET /api/analytics/grades/students/{student_id}?classroom_id&date_from&date_to` | 학생 성적 추이 |
- 권한: 모든 요청이 `_require_classroom`(평가 상세는 평가의 반) 통과 필수. 학생 경로는 **그 반의 수강생인지** 확인(IDOR 차단).
- 기간: 최대 366일(반 단위 데이터, 학생 수십 명 → 학생 목록 페이지네이션 불필요, 문서화).
- 집계는 서버 SQL(`GROUP BY` + `COUNT(*) FILTER`), 요청당 고정 쿼리 수(N+1 없음).

## 6. React 화면 계획
- 사이드바 '학사 운영'에 **"출결·성적 분석"** 1개 → `/analytics?tab=attendance|grades&classroom&from&to&student`.
- 탭 1 출결 분석: 조회 조건 → 핵심 수치 → 상태 분포(누적 막대, 표 병기) → 학생별 표 → 학생 상세(수업별 이력, 출결 입력 화면 링크) + 미입력 수업 목록(입력 화면 링크).
- 탭 2 성적 분석: 평가별 표 → 평가 상세(학생 점수, 학습 현황 링크) → 학생 추이(백분율 0~100 고정 축 점·선, 표 병기).
- 반 선택은 Phase 9.6 작업 반 유지(`shared/workingContext`) 재사용. 차트 라이브러리 없음 → antd + 작은 SVG/CSS(새 의존성 없음).
- 링크 대상(기존 지원 범위만): `/classes?classroom&tab=attendance&lesson`, `/classes?classroom&tab=progress&day`.

## 7. 변경 대상 파일
신규: `backend/app/modules/analytics/{__init__,repository,service,schemas,router}.py`, `backend/tests/test_phase10_analytics_integration.py`, `frontend/src/features/analytics/*`, docs 5종. 변경: `backend/app/main.py`(라우터 등록), `frontend/src/app/router.tsx`, `frontend/src/layout/AppLayout.tsx`(+test).

## 8. 테스트 계획
독립 기대값(손으로 계산한 작은 가상 데이터셋)으로 PostgreSQL 통합 테스트: 출결 13사례·성적 11사례(지시서 11.1), 불변조건, RBAC/IDOR(미배정·배정 해제·비활성·student_id/assessment_id 변조), 읽기 전용(조회 전후 행 수·audit_log 불변), EXPLAIN(테스트 DB 합성 데이터). React: 컴포넌트 테스트(빈·부분·오류·차트 데이터 표). 회귀: ruff, pytest 전체, Vitest 전체, tsc, oxlint, build. Java(mvn): 실행 가능 여부 확인 후 수행 또는 NOT RUN 사유 기록. 브라우저 E2E: 자동화 도구 없음 → NOT RUN + 수동 체크리스트.

## 9. Migration 필요 여부
**불필요(계획 단계 판단)** — 기존 스키마로 모든 지표 계산 가능. 인덱스는 테스트 DB EXPLAIN에서 실제 문제 확인 시에만 검토(그때도 테스트 DB 선검증 + 개발 DB는 승인 후).

## 10. 주요 위험
| 위험 | 대응 |
|---|---|
| 출석률 정책 미확정 | 사용자 결정 전 계산하지 않음(`null` + 정책 대기 표시) |
| 진행 여부 불명 수업(지난 SCHEDULED) | 대상에서 제외하되 건수 경고 + 수업 화면 링크 |
| 자격 밖 기록 | 대상 통계와 분리해 "대상 외 기록"으로 표시 |
| JOIN 중복 | 유니크 제약(학생·반, 수업·수강, 평가·수강)으로 구조적 차단 + 테스트로 확인 |
| `enrollment_pause`에 btree 인덱스 없음 | EXCLUDE gist 인덱스 사용 여부를 EXPLAIN으로 확인 |
| 권한 우회 | 반 권한 + 학생 소속 + 평가 소속 서버 검사, 테스트로 확인 |

## 11. 구현 순서
Stage 2 산식 확정 → Stage 3 출결 API+테스트 → Stage 4 성적 API+테스트 → Stage 5 화면+테스트 → Stage 6 정합성·보안·EXPLAIN → Stage 7 회귀·문서.
