# Phase 7 — 수업·출결·성적 관리 최종 보고서

작성일: 2026-11-18 · 설계 상세: `docs/phase7-implementation-plan.md` · 진행 기록: `docs/phase7-progress.md`

## 1. 목표 및 구현 범위

반(`classroom`) 안의 개별 수업 회차를 관리하고, 수업 단위 출결과 평가 단위 성적을 기록·수정·조회한다.
담당 반 단위 권한, DB 제약 기반 무결성, 동시 수정 감지, 변경 이력을 함께 구현했다.
제외: 메시지 생성·발송(Phase 8), 분석 대시보드(Phase 10), 출결 기록 삭제(미입력으로 되돌리기), 같은 날 정규반 2회차.

## 2. 기존 코드 분석 결과

- 실제 최종 revision은 지시서의 004가 아니라 **`005_staff_display_name`** (Phase 6B 후속).
- **`lesson`(수업)과 `lesson_result.attendance_status`(출결)가 이미 존재**하며 Java Import·보강(`ABSENT` 기준)·메시지 초안이 사용 중.
  Java는 수업을 `(반, 날짜, exam_round)`로 조회하고, 두 테이블에 명시 컬럼으로 INSERT/UPDATE한다.
- `enrollment`에 `enrolled_at`/`ended_at`/`status`가 있어 수강 기간 판단에 충분.
- `audit_log`(actor·event·target·request_id·JSON)로 변경 이력 표현 가능. 기존 기록은 로그인/로그아웃뿐.
- 반 접근 검사 `can_access_classroom`(오늘 유효 배정 + 역할 일치) 재사용 가능.
- 프론트 `/classes`가 "준비 중" 자리로 존재.

## 3. 설계 결정과 이유

| 결정 | 이유 |
|---|---|
| 수업은 기존 `lesson` 확장 | 새 테이블은 Java Import·보강·메시지와 원천 데이터 이원화 |
| 출결은 기존 `lesson_result` 재사용, **행 없음 = 미입력** | 보강 대상(`ABSENT`)·메시지 원천과 일치. 미입력과 결석이 구조적으로 구분됨 |
| 출결 상태 PRESENT/ABSENT/LATE 유지 (EXCUSED 미도입) | 기존 CHECK·Java 매핑 호환 |
| 회차 식별 = 기존 `(반, 날짜, exam_round)` | 고유키 변경 시 Java 조회가 다건을 반환할 위험. 같은 날 정규반 2회차는 미지원(§13) |
| 성적은 신규 `assessment` + `assessment_result` | 기존 A/B/C·정답 수로는 만점·소수점·미응시 표현 불가 |
| 미응시 `NOT_TAKEN`과 미입력(행 없음) 분리, 0점은 실제 점수 | 지시서 "미입력을 0점으로 해석 금지" |
| 수업 담당 교사 컬럼 없음 | 수업일의 반 배정에서 도출 → 배정과 모순 불가 |
| 낙관적 잠금(version) + `FOR UPDATE`/`FOR SHARE` | 일괄 저장 덮어쓰기 감지, 수업 취소·만점 변경과 입력의 경합 직렬화 |
| ASSISTANT는 출결 입력만 허용 | "허용된 기록 업무" = 출석 체크. 수업 정의·성적은 최소 권한으로 차단 |
| 감사 로그에 메모 본문 미기록 | 메모는 학생 사정 등 개인정보 가능. `memo_changed` 플래그만 기록 |

## 4. DB 스키마 변경 (ERD 설명)

```
classroom 1─* lesson 1─* lesson_result *─1 enrollment *─1 student
    │            └─0..1─* assessment (lesson_id 선택, 같은 반만)
    └──────────1─* assessment 1─* assessment_result *─1 enrollment
```

- `lesson` + `topic`, `memo`, `status`(SCHEDULED/COMPLETED/CANCELLED, 기본 COMPLETED — 기존·Java 행은 지난 수업), `version`, `UNIQUE(id, classroom_id)`
- `lesson_result` + `memo`, `version`, 트리거 `trg_lesson_result_classroom`(수업과 수강의 반 일치 강제, SQLSTATE 23514)
- `enrollment` + `UNIQUE(id, classroom_id)`
- `assessment`: 반 FK, 선택 수업 FK `(lesson_id, classroom_id)`, 제목 공백 금지, `max_score NUMERIC(6,2) > 0`, version
- `assessment_result`: `result_status`(SCORED/NOT_TAKEN), `score NUMERIC(6,2)`,
  CHECK `SCORED → 0 ≤ score ≤ max_score` / `NOT_TAKEN → score IS NULL`,
  복합 FK `(assessment_id, classroom_id, max_score) ON UPDATE CASCADE` → **만점 초과를 DB가 거부, 만점 축소 시 초과 점수가 있으면 UPDATE 실패**,
  복합 FK `(enrollment_id, classroom_id)` → 다른 반 학생 불가, `UNIQUE(assessment_id, enrollment_id)`
- 함수 `bump_row_version()` + 트리거 4개: Java의 UPDATE도 version을 올려 충돌 감지에 포함
- 인덱스: `idx_assessment_classroom_date`, `idx_assessment_result_enrollment` (그 외 기존 인덱스 활용)

## 5. Migration 및 적용 상태

| 항목 | 상태 |
|---|---|
| Revision | `006_phase7_lessons_grades` (down: `005_staff_display_name`), 추가형 |
| 테스트 DB | **적용** · `alembic check` 차이 없음 · downgrade→upgrade 왕복 검증 |
| 개발 DB | **적용 완료** (2026-11-18 사용자 승인, §5-1) |

### 5-1. 개발 DB 적용 기록 (2026-11-18)

1. 식별: `academy-learningops-postgres-dev` healthy, `127.0.0.1:55431`, 라벨 `isolated-development`/`destructive-tests=forbidden`,
   볼륨 `academy_learningops_postgres_dev_data`, `academy_learningops_dev`/`academy_dev`, 적용 전 revision 005.
2. 사전 조건: 반 불일치 출결 0건, `assessment*` 테이블 없음, 수업·출결 0건.
3. SQL 확인(`alembic upgrade 005:006 --sql`): CREATE FUNCTION/TRIGGER/TABLE/INDEX, ALTER TABLE ADD, `alembic_version` UPDATE뿐.
   `DROP/DELETE/TRUNCATE` 문자열 4건은 모두 FK의 `ON DELETE RESTRICT`(삭제 방지 규칙)였다.
4. 백업: `.dev-data\backups\academy_learningops_dev-pre006-20261118-004641.dump` (73,735 bytes,
   SHA-256 `32BEFC1E0D7299B86DBF8041B86AA7FD351F50B6FC8D3838CBDAA6EF83A90A3E`), `pg_restore --list` 성공(191 entries).
5. 적용: `alembic upgrade 006_phase7_lessons_grades` 성공(`cmd /c`로 실행해 출력 중단 없음), `alembic check` 차이 없음.
6. 사후 읽기 전용 검증:

| 항목 | 적용 전 | 적용 후 |
|---|---|---|
| Revision | 005 | `006_phase7_lessons_grades (head)` |
| 직원 (ADMIN/TEACHER, 모두 ACTIVE) | 1 / 1 | 동일 |
| 반·학생·수강·배정·수업·출결·세션·감사 | 1·1·1·1·0·0·4·7 | 동일 |
| 직원·수강·배정·반·학생 지문(md5) | `9a13…642d` / `e511…b824` / `f85e…a4ef` / `b35c…efba` / `8ff3…ae63` | 동일 |
| 신규 구조 | — | 테이블 2, 트리거 7, `lesson`·`lesson_result` 컬럼 6, 제약 9 확인 |

7. 서버: Phase 6B 때 기동한 FastAPI(구 코드)를 종료하고 재기동 → preflight PASS(head 006), OpenAPI에 Phase 7 경로 7개,
   미인증 401(직접·Vite 프록시). React Vite 개발 서버 `/classes` 200.

## 6. API

| Method | Path | 권한 |
|---|---|---|
| GET | `/api/classrooms/{cid}/lessons?date_from&date_to&limit&offset` | 반 접근 |
| POST | `/api/classrooms/{cid}/lessons` | ADMIN/TEACHER + CSRF |
| GET | `/api/lessons/{id}` (출결 집계 포함) | 반 접근 |
| PATCH | `/api/lessons/{id}` (`version` 필수) | ADMIN/TEACHER + CSRF |
| GET | `/api/lessons/{id}/attendance` (대상 명단 + 기록 또는 `null`) | 반 접근 |
| PUT | `/api/lessons/{id}/attendance` (단건·일괄 공용, 최대 200) | ADMIN/TEACHER/ASSISTANT + CSRF |
| GET | `/api/classrooms/{cid}/assessments` (입력 건수 포함) | 반 접근 |
| POST | `/api/classrooms/{cid}/assessments` | ADMIN/TEACHER + CSRF |
| GET | `/api/assessments/{id}` · PATCH (`version` 필수) | 반 접근 · ADMIN/TEACHER + CSRF |
| GET / PUT | `/api/assessments/{id}/grades` | 반 접근 · ADMIN/TEACHER + CSRF |
| GET | `/api/classrooms/{cid}/students/{sid}/records` (학생별 출결·성적 이력) | 반 접근 + 해당 반 수강생 |

주요 오류 코드: 400 `VALIDATION_ERROR`/`INVALID_ATTENDANCE_ITEMS`/`INVALID_GRADE_ITEMS`(필드 `items.{n}.…`)/`LESSON_IN_FUTURE`/`INVALID_LESSON_STATUS`/`INVALID_LESSON_LINK`,
401, 403 `CLASSROOM_ACCESS_DENIED`/`FORBIDDEN`/`CSRF_FAILED`, 404 `LESSON_NOT_FOUND`/`ASSESSMENT_NOT_FOUND`/`STUDENT_NOT_IN_CLASSROOM`,
409 `VERSION_CONFLICT`/`LESSON_ALREADY_EXISTS`/`LESSON_HAS_RECORDS`/`LESSON_CANCELLED`/`ASSESSMENT_HAS_RESULTS`/`MAX_SCORE_BELOW_EXISTING`/`ATTENDANCE_CONFLICT`/`GRADE_CONFLICT`.
점수는 DB `NUMERIC(6,2)`, JSON에서는 숫자로 직렬화.

## 7. 권한 정책

| 기능 | ADMIN | 배정 TEACHER | 배정 ASSISTANT | 미배정·비활성 |
|---|---|---|---|---|
| 수업·출결·평가·이력 조회 | O | O | O | 403 / 401 |
| 수업 생성·수정 | O | O | X | X |
| 출결 입력·수정 | O | O | O | X |
| 평가 생성·수정, 점수 입력 | O | O | X | X |

모든 검사는 서버 세션 기준. 리소스 ID(`lesson`, `assessment`)로 반을 찾아 같은 검사를 수행해 IDOR/BOLA 차단.
배정 해제는 다음 요청부터 즉시 403. UI는 ASSISTANT에게 편집 컨트롤을 숨기지만 보안 근거는 서버 검사다.

## 8. 업무 흐름

- **수업**: 등록(기본 예정) → 진행 후 출결 → 완료. 취소는 출결·연결 평가가 없을 때만, 삭제 API 없음.
  출결/평가가 있으면 날짜·회차 변경 불가(대상 학생이 바뀌므로). 미래 수업은 완료 처리 불가.
- **출결 대상**: `enrolled_at ≤ 수업일 ≤ ended_at(없으면 무기한)`. 종료일 없는 휴원·퇴원은 기간 불명으로 제외.
  대상이 아니게 된 학생의 기존 기록은 표시만(수정 불가). 취소·미래 수업은 입력 불가.
- **성적**: 평가 등록(만점, 선택적 수업 연결) → 학생별 점수/미응시 일괄 입력 → 수정 시 version 필요.
  결과가 있으면 평가일 변경 불가, 기존 최고점보다 낮은 만점으로 변경 불가.

## 9. 트랜잭션·동시성·무결성

- 일괄 입력: 전 항목 검증(반 소속·수강 기간·중복·점수·version) 후에만 쓰기. 하나라도 틀리면 **아무것도 저장되지 않음**.
  데이터 변경과 `audit_log`가 같은 트랜잭션에서 commit, `IntegrityError` 시 전체 rollback → 409.
- 기존 기록은 `SELECT … FOR UPDATE` 후 version 비교. 동시 신규 생성은 UNIQUE 위반으로 한쪽만 성공(409).
- 출결 저장은 수업 행을 `FOR SHARE`, 수업 수정은 `FOR UPDATE` → 저장 도중 수업 취소·날짜 변경 불가. 성적도 평가 행에 동일.
- 값이 같은 항목은 변경 없음으로 건너뜀(이력·version 불변).
- DB 이중 방어: 반 일치 트리거·복합 FK, 점수 CHECK, UNIQUE, 상태 CHECK, RESTRICT FK(기록 있는 수업·평가 삭제 불가).

## 10. 변경 이력

`audit_log.event_type`: `LESSON_CREATED/UPDATED`, `ATTENDANCE_RECORDED/UPDATED`, `ASSESSMENT_CREATED/UPDATED`, `GRADE_RECORDED/UPDATED`.
`actor_staff_user_id`=세션 사용자, `created_at`=시각, `request_id`=요청 추적, `target_type/target_id`=대상 행,
`details.before/after`=상태·점수·날짜·version 값. 학생 이름·메모 본문은 저장하지 않음(`enrollment_id`, `memo_changed`).
이력 조회 API/화면은 이번 범위에서 만들지 않았다(DB 조회로 추적 가능).

## 11. React 화면

메뉴 "수업·출결·성적"(`/classes`, 전 역할). 상단 반 선택(첫 반 자동) + 탭 3개.
- **수업**: 등록 폼(ADMIN/TEACHER), 목록(상태 태그·출결 기록 수), 수정 모달(version 포함, 변경 필드만 전송).
- **출결**(기본 탭): 최근 진행 수업 자동 선택 → 명단, 학생별 출석/지각/결석 버튼(아이콘+글자), 메모, "미입력" 태그,
  집계(대상·기록·미입력·상태별), "미입력 학생 모두 출석", 변경 행만 일괄 저장, 서버 필드 오류를 학생 행에 표시,
  충돌 시 경고 + 새로고침, 저장 중 버튼 비활성화, 취소·미래 수업 안내.
- **성적**: 평가 등록·목록·수정, 학생별 점수 입력·미응시 체크·메모, 저장 전 클라이언트 검증(만점 초과·음수·소수 2자리·빈 값), 서버 재검증 오류 표시.
- 학생 이름 클릭 → 학습 기록 Drawer(출결·성적 이력, "미입력은 결석이나 0점이 아님" 안내).

## 12. 테스트 명령과 실제 결과 (2026-11-18, 테스트 DB 006)

| 항목 | 명령 | 결과 |
|---|---|---|
| Ruff | `ruff check app tests alembic scripts` | PASS |
| Alembic | `alembic upgrade head` · `alembic check` | head 006, 차이 없음 |
| pytest 전체 (PostgreSQL 포함) | `pytest` (`ACADEMY_RUN_POSTGRES_INTEGRATION=1`) | **64 PASS** |
| └ Phase 7 DB 제약 | `tests/test_phase7_schema_integrity.py` | 5 PASS (트리거, CHECK, 복합 FK, 만점 축소, Java식 INSERT, downgrade 왕복) |
| └ Phase 7 API | `tests/test_phase7_academics_integration.py` | 5 PASS (시나리오 A~H) |
| Java Maven | `mvn -DrunPostgresIntegration=true test` | **47 PASS / 0 fail / 0 skip** |
| React Vitest | `npm test -- --run` | **10 files, 31 PASS** (신규 6) |
| React lint / tsc / build | `oxlint src` · `tsc -b && vite build` | PASS (기존 500kB chunk 경고) |
| 개발 DB 006 적용 및 보존 | §5-1 | PASS |
| 브라우저 E2E (시나리오 J) | 사용자 수동 절차 (§12-1) | **NOT RUN — 사용자 수동 실행 대기** |

### 12-1. 브라우저 E2E 수동 절차 (시나리오 J)

`http://127.0.0.1:5173` — 관리자 비밀번호는 사용자가 직접 입력한다. 개발 DB에 실제 기록이 남는다.
1. ADMIN 로그인 → "수업·출결·성적" → 반 선택 → **수업** 탭에서 학생 수강 시작일 이후·오늘 이전 날짜로 수업 등록
2. **출결** 탭: 해당 수업 선택 → 학생이 "미입력"으로 보이는지 확인 → 출석 선택 → 저장 → 저장된 기록 "출석"
3. 같은 학생을 지각으로 바꿔 저장 → 저장된 기록 "지각" (이력은 `audit_log`의 `ATTENDANCE_UPDATED`)
4. **성적** 탭: 평가 등록(만점 10) → 11 입력 시 오류 표시 확인 → 9.5 저장 → 만점을 5로 낮추면 거부되는지 확인
5. 학생 이름 클릭 → 학습 기록에 출결·점수가 보이는지 확인
6. 담당 TEACHER로 로그인 → 같은 반 수업·출결·성적 조회 가능 → 출결·점수 수정 가능
7. ADMIN이 직원 관리 → 반별 담당 배정에서 해당 TEACHER 배정 해제 → TEACHER 화면 새로고침 시 "담당 반이 없습니다" 또는 403 안내

시나리오 매핑: A 수업 생성·조회·권한 / B 출결 일괄 / C 수정 이력(before·after·actor, 메모 미기록) /
D 성적 기록 / E 만점 초과·음수·소수·미응시+점수·중복·타 반 학생 / F 배정 해제·비활성화 / G 일괄 원자성 /
H 동시 생성·동시 수정(출결·성적) / I 기존 테스트 전체 / J NOT RUN.

기존 테스트 기대값 변경(의도된 스키마 추가 반영, 검증 약화 없음): `test_postgres_integration.py`(head 006, 신규 트리거 7개,
허용 테이블 상태를 단계별로 명시), `test_db_safety.py`(ORM 테이블에 2개 추가).

## 13. 남은 결함·위험·미검증

1. 브라우저 E2E 미실행 (개발 DB 006 적용·서버 기동 완료, 사용자 수동 확인 대기)
2. 같은 날 정규반 2회차 미지원 — `exam_round`로만 구분. 개편 시 Java Import 조회 로직 동시 수정 필요
3. EXCUSED(인정결석) 미지원 — Java 보강 로직과 함께 도입 검토
4. 출결 기록 삭제(미입력으로 되돌리기) 없음, 평가 삭제 없음
5. 휴원(PAUSED) 기간 정보가 없어 종료일 없는 휴원 학생은 대상에서 제외됨
6. 변경 이력 조회 화면 없음(DB `audit_log`로만 확인)
7. 성능: 명단은 단일 JOIN, 목록은 상관 서브쿼리 + 기존/신규 인덱스. 실측 부하 테스트는 하지 않음(수치 주장 없음)
8. jsdom 환경에서 antd 화면 렌더가 느려 프론트 테스트 대기 시간을 10초로 설정
9. Git CLI 없음 → diff 점검 BLOCKED (수정 시각 기준 목록으로 대체)

## 14. Phase 8 연계 준비

학생별 `GET /api/classrooms/{cid}/students/{sid}/records`가 수강 정보, 수업 날짜·주제·상태, 출결(미입력=`null`),
평가명·만점·결과(미입력=`null`, 미응시=`NOT_TAKEN`), 각 기록의 `updated_at`을 반환한다.
수업별·평가별 명단 API도 `record: null`로 미입력을 명시한다. 기존 `message_draft`/`makeup_request`는 계속 `lesson_result`를 참조하므로
Phase 8 메시지 생성은 동일한 출결 원천을 사용할 수 있다. 메시지 전용 테이블은 만들지 않았다.

## 15. 수정 파일 (Phase 7 착수 이후 수정 시각 기준, Git 없음)

- 신규: `backend/alembic/versions/006_phase7_lessons_grades.py`, `backend/app/modules/academics/{__init__,schemas,repository,service,router}.py`,
  `backend/tests/test_phase7_schema_integrity.py`, `backend/tests/test_phase7_academics_integration.py`,
  `frontend/src/features/classwork/{api.ts,common.tsx,ClassworkPage.tsx,LessonsTab.tsx,AttendanceTab.tsx,GradesTab.tsx,StudentRecordsDrawer.tsx,ClassworkPage.test.tsx}`,
  `docs/phase7-implementation-plan.md`, `docs/phase7-progress.md`, 본 문서
- 수정: `backend/app/db/models/tables.py`, `backend/app/db/schema.py`, `backend/app/main.py`,
  `backend/tests/test_postgres_integration.py`, `backend/tests/test_db_safety.py`, `frontend/src/app/router.tsx`, `frontend/src/layout/AppLayout.tsx`

## 16. 최종 판정

**조건부 완료.** 자동화 검증(Python 64, Java 47, React 31, lint·build)은 모두 PASS이고,
개발 DB Migration 006은 승인 후 백업·적용·보존 검증까지 마쳤다. 실제 브라우저 E2E(시나리오 J)만 사용자 수동 확인 대기다.
