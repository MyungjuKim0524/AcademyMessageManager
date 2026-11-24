# Phase 7 구현 계획 — 수업·출결·성적 관리

작성일: 2026-11-17 (Stage 1 산출물)

## 1. 기존 구현 분석 결과

### 1-1. 실제 상태 확인

| 항목 | 지시서 전제 | 실제 확인 결과 |
|---|---|---|
| 최종 Alembic revision | 004 | **`005_staff_display_name`** (Phase 6B 후속, 테스트·개발 DB 모두 적용) |
| 개발 DB | `academy_learningops_dev` :55431 | 일치, PostgreSQL 17.6, 라벨 `isolated-development` |
| 테스트 DB | `academy_learningops_test` :55432 | 일치, 라벨 `isolated-test` |
| Git | — | `git` 실행 파일이 PATH에 없음 → diff 점검 BLOCKED, 파일 수정 시각으로 대체 |

### 1-2. 수업·출결·성적 관련 기존 스키마 (Java baseline 001)

- **`lesson`**: `classroom_id`(FK RESTRICT), `lesson_date`, `exam_round`(NULL 허용), timestamps.
  회차 고유키는 `(classroom_id, lesson_date, exam_round)` — 부분 UNIQUE 인덱스 2개
  (`exam_round IS NULL`이면 반·날짜당 1개, 있으면 반·날짜·회차당 1개).
- **`lesson_result`**: `lesson_id`×`enrollment_id` UNIQUE, `attendance_status NOT NULL IN (PRESENT, ABSENT, LATE)`,
  `prework_grade`/`weekly_assignment_grade`(A/B/C), `correct_count`/`total_count`(테스트 정답 수).
- `makeup_request`, `message_draft`가 `lesson_result`를 FK로 참조 (보강·메시지 기능의 원천).
- **`enrollment`**: `status IN (ACTIVE, PAUSED, WITHDRAWN)`, `enrolled_at NOT NULL`, `ended_at NULL`,
  `(student_id, classroom_id)` UNIQUE → 학생·반당 수강 행 1개(재등록 이력 없음).
- **`audit_log`**: `actor_staff_user_id`, `event_type`, `target_type`, `target_id`, `request_id`, `details JSON`, `created_at`.
  현재 `AUTH_LOGIN`/`AUTH_LOGOUT`만 기록. 서비스가 같은 Session에 `AuditLog`를 add 후 commit.
- `set_updated_at()` 트리거 함수가 모든 TimestampMixin 테이블의 `updated_at`을 갱신.

### 1-3. 기존 Java 프로그램의 사용 방식 (호환성 제약)

- `AcademyImportDAO`/`JdbcImportConfirmRepository`: 수업을 `classroom_id, lesson_date, exam_round IS NOT DISTINCT FROM ?`로 찾고,
  `INSERT INTO lesson(classroom_id,lesson_date,exam_round)` — **명시 컬럼 INSERT**.
  `lesson_result`도 명시 컬럼 INSERT/UPDATE.
- `MakeupDAO`: `attendance_status = 'ABSENT'`로 보강 대상을 찾음. `exam_round`를 메시지의 "시험 회차"로 사용.
- 결론: **기본값이 있는 컬럼 추가는 안전**하나, `lesson` 고유키 변경이나 `attendance_status` 값 추가(EXCUSED)는 Java 동작을 바꾼다.

### 1-4. 인증·권한·API 구조

- `get_current_principal`: 세션 쿠키 → DB 세션·직원 상태(ACTIVE) 확인. `require_csrf`, `require_roles`, `require_admin_csrf`.
- 반 접근: `LearningOpsRepository.can_access_classroom(classroom_id, user_id, role)` — ADMIN 전체,
  그 외는 **오늘 유효한** 배정 + `assignment_role == role`. 배정 해제·비활성화 즉시 반영됨(Phase 6B 검증).
- 오류: `CompatibilityError(status, code, message)` → 공통 JSON. Pydantic 검증 오류는 400 `VALIDATION_ERROR`.
- 모듈 구조: `app/modules/{auth,imports,learningops}/{router,service,repository,schemas}.py`.
- 테스트: `tests/test_*_integration.py`가 테스트 DB identity 확인 후 TRUNCATE. `app/db/schema.py`의 `EXPECTED_TABLES`로 스키마 검증.

### 1-5. React

- `router.tsx`에 `/classes` → `ComingSoonPage "수업 관리"` 자리 존재. `AppLayout` 메뉴 "수업 관리 · 준비 중".
- `/students`의 반 선택 패턴(접근 가능한 반 자동 선택), `toApiClientError`, antd 6 컴포넌트 재사용 가능.

## 2. 설계 결정

| 질문 | 결정 | 근거 |
|---|---|---|
| 수업을 표현할 테이블? | 기존 `lesson` 재사용 + 컬럼 확장 | Java Import·보강·메시지가 이미 사용. 중복 테이블은 원천 데이터 이원화 |
| 반 vs 회차 구분 | `classroom` = 반, `lesson` = 회차. 식별 = 기존 `(반, 날짜, exam_round)` | 고유키 변경 시 Java의 `IS NOT DISTINCT FROM` 조회가 다건을 반환할 수 있음 |
| 같은 날 여러 회차 | `exam_round`가 다르면 가능(기존 규칙). 정규반의 같은 날 2회차는 **이번 단계 미지원**(문서화) | 지원하려면 고유키 교체 + Java 수정 필요 → Phase 7 범위 밖 |
| 출결 저장 위치 | 기존 `lesson_result.attendance_status` | 보강(ABSENT 기준)·메시지 원천과 일치. **행 없음 = 미입력** (결석과 구분) |
| 출결 상태 | PRESENT / ABSENT / LATE 유지, EXCUSED 미도입 | 기존 CHECK·Java 매핑과 호환. 추가 시 Java 보강 로직 영향 |
| 성적 연결 | 별도 평가 정의 `assessment` + 학생별 `assessment_result` | 기존 A/B/C·정답 수는 Import 전용 구조. 만점·소수점·미응시 표현 불가 |
| 수강 기간 | `enrollment.enrolled_at ~ ended_at` 기준(아래 §4) | 기존 컬럼으로 충분, 스키마 변경 불필요 |
| 감사 | 기존 `audit_log` 재사용, 같은 트랜잭션 | 구조가 이미 actor·대상·request_id·JSON 지원 |
| 수업 담당 교사 | 컬럼 추가하지 않음. 수업일에 유효한 반 배정으로 도출 | 별도 저장 시 배정과 모순 가능(요구사항의 "모순 없음" 보장) |
| 동시 수정 | `version` 컬럼 낙관적 잠금 + 행 잠금(`FOR UPDATE`) | 일괄 저장에 적합, 두 사용자의 덮어쓰기를 409로 감지 |

## 3. 데이터 모델 (Migration `006_phase7_lessons_grades`)

모두 **추가형** 변경. 기존 행·제약 삭제 없음.

### 3-1. 공통
- 함수 `bump_row_version()`: BEFORE UPDATE 시 `NEW.version := OLD.version + 1`.
  Java의 UPDATE도 version을 올리므로 레거시 경로 변경도 충돌로 감지된다.

### 3-2. `lesson` 확장
- `topic VARCHAR(200) NULL`, `memo VARCHAR(2000) NULL`
- `status VARCHAR(20) NOT NULL DEFAULT 'COMPLETED' CHECK IN ('SCHEDULED','COMPLETED','CANCELLED')`
  — 기존 행과 Java Import 행은 결과가 있는 지난 수업이므로 COMPLETED. API 생성 시 기본 SCHEDULED를 명시 지정.
- `version INTEGER NOT NULL DEFAULT 1`, 트리거 `trg_lesson_version`
- `UNIQUE (id, classroom_id)` — 평가의 수업 연결 복합 FK용

### 3-3. `lesson_result` 확장 (출결)
- `memo VARCHAR(500) NULL`, `version INTEGER NOT NULL DEFAULT 1`, 트리거 `trg_lesson_result_version`
- 트리거 `trg_lesson_result_classroom`: `lesson.classroom_id = enrollment.classroom_id` 강제(DB 수준 교차 검증).
  레거시 컬럼(`classroom_id` 없음)이라 복합 FK 대신 트리거 사용. 개발 DB 불일치 행 0건 확인.

### 3-4. `enrollment`
- `UNIQUE (id, classroom_id)` 추가 — 성적의 반 일치 복합 FK용 (기존 의미 불변)

### 3-5. `assessment` (신규, 평가 정의)
- `classroom_id` FK RESTRICT, `lesson_id NULL`, `title VARCHAR(100) NOT NULL`(공백 불가), `assessment_date DATE NOT NULL`
- `max_score NUMERIC(6,2) NOT NULL CHECK (max_score > 0)`, `version`, timestamps
- FK `(lesson_id, classroom_id) → lesson(id, classroom_id)` — 다른 반 수업 연결 불가
- `UNIQUE (id, classroom_id, max_score)` — 결과 테이블 복합 FK 대상
- 인덱스 `(classroom_id, assessment_date)`

### 3-6. `assessment_result` (신규, 학생별 결과)
- `assessment_id`, `classroom_id`, `max_score`, `enrollment_id`, `result_status IN ('SCORED','NOT_TAKEN')`,
  `score NUMERIC(6,2) NULL`, `memo VARCHAR(500) NULL`, `version`, timestamps
- CHECK: `SCORED`면 `0 <= score <= max_score`, `NOT_TAKEN`이면 `score IS NULL`
- FK `(assessment_id, classroom_id, max_score) → assessment ON UPDATE CASCADE ON DELETE RESTRICT`
  → **만점 초과 점수를 DB가 거부**하며, 만점을 낮출 때 기존 점수가 초과하면 UPDATE 자체가 실패
- FK `(enrollment_id, classroom_id) → enrollment(id, classroom_id)` → 다른 반 학생 점수 불가
- `UNIQUE (assessment_id, enrollment_id)` → 평가·학생당 결과 1개. 인덱스 `enrollment_id`
- **행 없음 = 미입력**, `NOT_TAKEN` = 미응시(0점 아님)

### 3-7. 변경 이력 (`audit_log`)
event_type: `LESSON_CREATED/UPDATED`, `ATTENDANCE_RECORDED/UPDATED`, `ASSESSMENT_CREATED/UPDATED`, `GRADE_RECORDED/UPDATED`.
`details = {before, after, ...}`에 상태·점수·version·날짜 등 **값만** 저장. 메모 본문은 학생 개인정보가 포함될 수 있어
`memo_changed: true/false`만 기록. 학생 이름 미저장(`enrollment_id`로 추적).

## 4. 업무 규칙

- **출결·평가 대상**: 해당 반 수강 행 중 `enrolled_at <= 기준일 AND (ended_at IS NULL OR 기준일 <= ended_at)`,
  단 `status <> 'ACTIVE' AND ended_at IS NULL`(종료일 없는 휴원·퇴원)은 기간을 알 수 없으므로 제외.
  기준일 = 수업일/평가일. 대상이 아니게 된 학생의 **기존 기록은 조회에 계속 표시**(수정만 불가).
- **수업 상태**: SCHEDULED ↔ COMPLETED 자유. CANCELLED는 출결·연결 평가가 없을 때만. CANCELLED → SCHEDULED 복원 가능.
  삭제 API 없음(취소로 대체, FK RESTRICT가 기록 유실 방지).
- **수정 범위**: 출결이나 연결 평가가 있는 수업은 날짜·`exam_round` 변경 불가(대상 학생이 바뀌므로). 주제·메모·상태는 가능.
- **출결 입력**: CANCELLED 수업 불가, 미래 날짜 수업 불가. 평가 점수도 미래 평가일 불가.
  평가일을 바꾸는 것은 결과가 없을 때만.
- **일괄 입력**: 최대 200건, 같은 학생 중복 항목 400. **전부 성공 또는 전부 실패**(단일 트랜잭션 + 감사 로그 포함).
  항목별 `version`: 새 기록은 생략/null, 기존 기록 수정 시 필수. 불일치 → 409 `VERSION_CONFLICT`(전체 롤백).
  동시 신규 생성은 UNIQUE 위반 → 409. 값이 같은 항목은 변경 없음으로 건너뜀(감사 기록 없음).
- 출결 기록 삭제(미입력으로 되돌리기)는 이번 범위에서 제외.

## 5. 권한 정책

| 기능 | ADMIN | 배정 TEACHER | 배정 ASSISTANT |
|---|---|---|---|
| 수업 조회 | O | O | O |
| 수업 생성·수정 | O | O | X |
| 출결 조회 | O | O | O |
| 출결 입력·수정 | O | O | **O** |
| 평가·성적 조회 | O | O | O |
| 평가 생성·수정, 점수 입력 | O | O | X |

- ASSISTANT 출결 허용 근거: 지시서의 "허용된 기록 업무"에 해당하는 일상 업무(출석 체크). 성적·수업 정의는 최소 권한으로 차단.
- 모든 변경 API는 CSRF 필수. 반 접근은 `can_access_classroom` 재사용(오늘 유효 배정 + 역할 일치).
- 리소스 ID 기반 API(`/lessons/{id}`, `/assessments/{id}`)는 리소스의 반을 조회해 같은 검사를 수행 → IDOR/BOLA 차단.
  일괄 입력의 `enrollment_id`는 해당 수업·평가의 반 소속이어야 함(서비스 + DB FK/트리거 이중).
- 비활성 직원은 기존 인증 단계에서 401.

## 6. API (신규 모듈 `app/modules/academics`)

| Method | Path | 권한 |
|---|---|---|
| GET | `/api/classrooms/{cid}/lessons?date_from&date_to&limit&offset` | 반 접근 |
| POST | `/api/classrooms/{cid}/lessons` | ADMIN/TEACHER + CSRF |
| GET | `/api/lessons/{id}` (출결 집계 포함) | 반 접근 |
| PATCH | `/api/lessons/{id}` (`version` 필수) | ADMIN/TEACHER + CSRF |
| GET | `/api/lessons/{id}/attendance` (대상 명단 + 기록/미입력) | 반 접근 |
| PUT | `/api/lessons/{id}/attendance` (단건·일괄 공용) | ADMIN/TEACHER/ASSISTANT + CSRF |
| GET | `/api/classrooms/{cid}/assessments` (입력 건수 집계 포함) | 반 접근 |
| POST | `/api/classrooms/{cid}/assessments` | ADMIN/TEACHER + CSRF |
| GET | `/api/assessments/{id}` | 반 접근 |
| PATCH | `/api/assessments/{id}` (`version` 필수) | ADMIN/TEACHER + CSRF |
| GET | `/api/assessments/{id}/grades` | 반 접근 |
| PUT | `/api/assessments/{id}/grades` (단건·일괄 공용) | ADMIN/TEACHER + CSRF |
| GET | `/api/classrooms/{cid}/students/{sid}/records` (학생별 출결·성적 이력) | 반 접근 + 해당 반 수강생 |

학생 이력을 반 범위 경로로 둔 이유: 다른 반 학생 ID로의 조회를 경로 수준에서 차단(IDOR).

## 7. 변경 파일 (예상)

- 신규: `alembic/versions/006_phase7_lessons_grades.py`, `app/modules/academics/{__init__,router,service,repository,schemas}.py`,
  `tests/test_phase7_academics_integration.py`, `frontend/src/features/classwork/*`, `docs/archive/phases/phase7-*.md`
- 수정: `app/db/models/tables.py`, `app/db/schema.py`(EXPECTED_TABLES), `app/main.py`(router 등록),
  `tests/test_postgres_integration.py`(revision·테이블·트리거 기대값), `frontend/src/app/router.tsx`, `frontend/src/layout/AppLayout.tsx`

## 8. 구현 순서

Stage 2 Migration·모델 → 테스트 DB 적용·제약 테스트 → Stage 3 수업 API → Stage 4 출결 → Stage 5 평가·성적
→ Stage 6 React → Stage 7 전체 회귀·보고. 개발 DB 적용은 Stage 7 이후 **별도 승인**.

## 9. 위험과 대응

| 위험 | 대응 |
|---|---|
| Java Import와 스키마 충돌 | 추가 컬럼 모두 DEFAULT/NULL, 고유키·CHECK 값 불변, Java PostgreSQL 테스트로 검증 |
| 미입력을 결석/0점으로 오해 | 행 없음 = 미입력, API 응답에 `null` 명시, UI "미입력" 태그 |
| 동시 수정 덮어쓰기 | version + `FOR UPDATE`, 409 후 재조회 유도 |
| 일괄 입력 부분 성공 | 단일 트랜잭션, 감사 로그 포함, IntegrityError 시 전체 롤백 |
| 만점 변경 후 초과 점수 | 복합 FK ON UPDATE CASCADE + CHECK로 DB가 거부 |
| 메모의 개인정보가 감사 로그로 복제 | 메모 본문 미기록 |
| 같은 날 정규 2회차 불가 | 문서화, 후속 단계에서 Java와 함께 고유키 개편 |
| jsdom `getByRole` 지연 | 텍스트·라벨 조회 사용(Phase 6B 교훈) |

## 10. 테스트 계획

- PostgreSQL 통합(`tests/test_phase7_academics_integration.py`): 지시서 시나리오 A~H —
  수업 생성·조회, 출결 일괄·수정 이력, 성적 기록·검증(음수·만점 초과·중복·타 반 학생), 배정 해제 후 차단,
  일괄 원자성, 동시 생성·동시 수정, 미배정 TEACHER/ASSISTANT·비활성 직원·CSRF·IDOR.
- DB 제약 직접 검증: 트리거(반 불일치), 복합 FK, CHECK, 만점 축소 거부.
- 회귀: Ruff, pytest 전체, Java Maven(PostgreSQL), Vitest, oxlint, tsc, build.
- 브라우저 E2E(시나리오 J): 개발 DB 승인·적용 후 사용자 수동 절차 제공.

## 11. 완료 기준

- 테스트 DB에 006 적용, 위 자동 테스트 전부 PASS, Java 47개 회귀 PASS
- React 화면에서 수업·출결·성적 기록 흐름 동작(단위 테스트), lint·build PASS
- 최종 보고서 `docs/archive/phases/phase7-lessons-attendance-grades.md` 작성
- 개발 DB 적용과 브라우저 확인은 승인 대기로 명확히 구분
