# Phase 7.1 — 안정화: 같은 날 복수 회차 · 휴원 기준일 판정 · 인정결석

작성일: 2026-11-18 · 선행 문서: `docs/archive/phases/phase7-lessons-attendance-grades.md`

범위 조정(사용자 지시): Git 설치·PATH 변경·`git init`·GitHub 업로드는 수행하지 않았다.
변경 확인은 수정 시각이 아니라 **파일 내용 검색**으로 했다(§7).

## 1. 결과 요약

| 과제 | 결과 |
|---|---|
| 1. 같은 날 복수 수업 회차 + Java 호환 | 구현·검증 완료. `lesson.session_no`(교시 1~9). Java는 항상 1교시를 대상으로 하도록 조회문 4곳을 수정했다 |
| 2. 휴원 학생의 수업일 기준 판정 | 구현·검증 완료. 날짜가 있는 휴원 이력 `enrollment_pause` + 기간 중복 금지 DB 제약. 휴원 전 수업은 대상, 휴원 기간 수업은 제외 |
| 3. 인정결석(EXCUSED) | 구현·검증 완료. DB·API·화면에 반영. Java 보강 목록은 계속 결석(ABSENT)만 대상 |
| Migration | `007_phase71_sessions_pauses` — 테스트 DB 적용, **개발 DB 적용 완료**(2026-11-18 승인, §4-1) |

## 2. 분석 결과 (Phase 7 대비 문제점)

1. **같은 날 회차**: 고유키가 `(반, 날짜[, exam_round])`라 정규반은 하루 1회만 가능했다.
   Java Import 조회 헬퍼 `id()`는 `ORDER BY` 없이 첫 행을 반환하므로, 단순히 고유키만 넓히면 같은 날 2개 수업 중
   **어느 쪽에 기록될지 정해지지 않는다**(`AcademyImportDAO`, `JdbcImportConfirmRepository`, `SendLogDAO`, `MakeupDAO.findLatestStatus`).
2. **휴원**: 종료일 없는 휴원(PAUSED) 학생은 기간을 알 수 없어 **과거 수업까지 전부** 대상에서 빠졌다.
   Java Import는 CSV 행마다 `UPDATE enrollment SET status=?`로 상태만 바꾸고 날짜를 남기지 않는다.
3. **EXCUSED**: Java는 DB의 `attendance_status`를 열거형으로 변환하지 않는다(문자열 비교, `MakeupDAO`는 `= 'ABSENT'`).
   `AttendanceStatus.from()`은 CSV·미리보기 입력에만 쓰인다 → DB에 EXCUSED가 있어도 Java가 실패하지 않는다.

## 3. 설계 결정

### 3-1. 같은 날 복수 회차
- `lesson.session_no SMALLINT NOT NULL DEFAULT 1 CHECK (1..9)` — 화면 표기는 "교시".
- 고유 인덱스 교체: `uq_lesson_session_without_exam_round (반, 날짜, 교시) WHERE exam_round IS NULL`,
  `uq_lesson_session_with_exam_round (반, 날짜, exam_round, 교시) WHERE exam_round IS NOT NULL`.
  기존 행은 모두 1교시이므로 기존 유일성은 그대로 유지된다(제약이 넓어지기만 함).
- Java: INSERT는 `session_no`를 생략 → 항상 1교시. 조회 4곳에 `session_no = 1`을 추가해 **결정적**으로 1교시만 사용.
  보강 대상 수업 목록(`findAvailableSessions`)은 같은 날 여러 교시가 모두 선택지로 나오도록 정렬만 고정(`교시, id`).
- API: 생성 시 `session_no`(기본 1), 중복 시 409 `LESSON_ALREADY_EXISTS`(다른 교시 지정 안내).
  출결·평가가 있는 수업은 날짜·시험 회차와 마찬가지로 **교시 변경도 불가**(대상 학생·Java 매칭이 바뀌므로).
- 정렬: 날짜 내림차순 → 교시 내림차순.

### 3-2. 휴원 기준일 판정
- 신규 `enrollment_pause(enrollment_id, paused_from, resumed_on NULL, source MANUAL|STATUS_CHANGE)`.
  기간은 `[paused_from, resumed_on)` — 복귀일부터 다시 대상. `resumed_on > paused_from` CHECK.
- **기간 중복 금지는 DB가 보장**: `EXCLUDE USING gist (enrollment_id WITH =, daterange(...) WITH &&)` (`btree_gist` 확장).
- 대상 판정(`eligible_on`, 출결·성적·학생 이력 공통):
  `enrolled_at ≤ 날짜 ≤ ended_at` **그리고** 날짜가 어떤 휴원 기간에도 속하지 않음.
  기간을 알 수 없는 경우는 추정하지 않고 제외: 종료일 없는 WITHDRAWN, **휴원 이력이 없는 기존 PAUSED 행**(7.1 이전 데이터).
- **API 밖의 상태 변경(Java Import)** 도 날짜를 남기도록 트리거 `trg_enrollment_pause_sync`:
  PAUSED가 되면 그날부터 휴원 생성, PAUSED에서 벗어나면 그날 복귀(최소 1일).
  같은 날 휴원→복귀→휴원이 반복되면 새 행 대신 직전 휴원을 이어 연다(중복 제약 위반으로 Import가 실패하지 않도록).
  API는 휴원 행을 먼저 쓰고 상태를 바꾸므로 트리거가 중복 생성하지 않는다.
- **업무 기준일 = 한국 시간**: 컨테이너가 UTC라 `CURRENT_DATE`는 자정~09시에 하루 전 날짜가 된다(테스트에서 실제 발견).
  트리거는 `(CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Seoul')::date`를 사용한다. Python API는 서버 로컬 날짜(현재 KST)를 사용.
- 휴원 API(ADMIN + CSRF): 기록 시 휴원 시작일 ≤ 오늘, 수강 기간 안, 퇴원 수강 불가, 진행 중 휴원이 있으면 409.
  과거의 닫힌 휴원도 기록할 수 있다. 이미 입력된 출결은 삭제하지 않으며 "수강 기간 아님(기존 기록)"으로 표시된다.

### 3-3. 인정결석(EXCUSED)
- `chk_lesson_result_attendance`를 `('PRESENT','ABSENT','LATE','EXCUSED')`로 확장(허용 값 추가만).
- 집계에 `excused` 추가, 화면은 아이콘+"인정결석" 글자로 표시.
- **보강 정책**: Java `MakeupDAO`는 `ABSENT`만 보강 대상으로 조회한다 → 인정결석은 자동 보강 목록에 나오지 않는다.
  보강·학부모 안내에 인정결석을 포함할지는 Phase 8에서 결정(현재 동작을 문서화만 함).
- Java CSV/미리보기는 EXCUSED를 입력할 수 없다(열거형 미변경). 같은 수업·학생을 CSV로 다시 가져오면 CSV 값이 덮어쓴다(기존 Import 의미).

## 4. DB 변경 — `007_phase71_sessions_pauses`

| 변경 | 종류 |
|---|---|
| `lesson.session_no` + `chk_lesson_session_no` | 컬럼·CHECK 추가 |
| `uq_lesson_with/without_exam_round` → `uq_lesson_session_with/without_exam_round` | 고유 인덱스 교체(더 넓은 키, 데이터 변경 없음) |
| `chk_lesson_result_attendance` | 허용 값 추가 |
| `CREATE EXTENSION IF NOT EXISTS btree_gist` | 확장(다운그레이드 시 유지) |
| `enrollment_pause` + `ex_enrollment_pause_overlap` + 트리거 2개(`updated_at`, `pause_sync`) | 테이블·제약·트리거 추가 |

삭제·재작성되는 데이터 없음. downgrade는 EXCUSED 기록이나 2교시 이상 수업이 있으면 **의도적으로 실패**한다(조용한 데이터 손실 방지).

| DB | 상태 |
|---|---|
| 테스트 DB | 적용(head 007), `alembic check` 차이 없음 |
| 개발 DB | **적용 완료** (§4-1) |

### 4-1. 개발 DB 적용 기록 (2026-11-18, 사용자 승인)

1. 식별: `academy-learningops-postgres-dev` healthy, `127.0.0.1:55431`, 라벨 `isolated-development`/`destructive-tests=forbidden`,
   볼륨 `academy_learningops_postgres_dev_data`, `academy_learningops_dev`/`academy_dev`, 적용 전 revision 006.
2. 사전 조건(읽기 전용): 수업·출결·평가 0건, 수강 1건(ACTIVE), PAUSED 0건 → 이력 없는 휴원 데이터 없음, `btree_gist` 사용 가능.
3. SQL 확인(`alembic upgrade 006:007 --sql`): `DROP INDEX` 2개는 더 넓은 새 고유 인덱스를 먼저 만든 뒤 옛 인덱스를 지우는 것,
   `DROP CONSTRAINT`는 출결 CHECK를 EXCUSED 포함으로 재생성하는 것, `UPDATE enrollment_pause`는 트리거 함수 본문(적용 시 실행 안 됨).
   데이터 행 삭제·수정 구문 없음.
4. 백업: `.dev-data\backups\academy_learningops_dev-pre007-20261118-013525.dump` (87,840 bytes,
   SHA-256 `B3E56B19A0597A5A8CBDB76AABDE37FEA6662505D0175FC50670DE467780FBA4`), `pg_restore --list` 성공(224 entries).
5. 적용: `alembic upgrade 007_phase71_sessions_pauses` 성공, `alembic check` 차이 없음.
6. 사후 읽기 전용 검증:

| 항목 | 적용 전 | 적용 후 |
|---|---|---|
| Revision | 006 | `007_phase71_sessions_pauses (head)` |
| 직원 (ADMIN/TEACHER, ACTIVE) | 1 / 1 | 동일 |
| 반·학생·수강·배정·수업·출결·평가·결과·세션·감사 | 1·1·1·1·0·0·0·0·4·7 | 동일 |
| 직원·수강·배정·반·학생 지문(md5) | `9a13…642d` / `e511…b824` / `f85e…a4ef` / `b35c…efba` / `8ff3…ae63` | 동일 |
| 신규 구조 | — | `session_no smallint NOT NULL DEFAULT 1`, 새 고유 인덱스 2개(옛 인덱스 제거), EXCUSED 포함 CHECK, `enrollment_pause` + `ex_enrollment_pause_overlap`, 트리거 2개(KST 날짜), `btree_gist` 1.7 |

7. 서버: Phase 7 코드로 실행 중이던 FastAPI를 종료하고 재기동 → preflight PASS(head 007), OpenAPI에 휴원 API 2개 경로·EXCUSED·`session_no` 확인,
   미인증 401(직접·Vite 프록시). React Vite 개발 서버는 계속 실행 중(`/classes` 200).

개발 중 007 마이그레이션 파일을 두 번 수정했다(시간대 버그, 같은 날 재휴원 결함). 007은 개발 DB에 적용된 적이 없으며,
격리된 테스트 DB에서만 `downgrade 006 → upgrade head`로 다시 적용했다.

## 5. API 변경

| Method | Path | 변경 |
|---|---|---|
| POST/PATCH | `/api/classrooms/{cid}/lessons`, `/api/lessons/{id}` | `session_no` 입력(1~9) |
| GET | 수업 목록·상세·학생 이력 | `session_no` 응답 |
| PUT | `/api/lessons/{id}/attendance` | `status`에 `EXCUSED` 허용 |
| GET | 출결 명단·수업 상세 | `summary.excused` 추가 |
| GET | `/api/classrooms/{cid}/enrollments/{eid}/pauses` | 신규 — 휴원 이력(반 접근 권한) |
| POST | `/api/classrooms/{cid}/enrollments/{eid}/pauses` | 신규 — 휴원 기록(ADMIN+CSRF) |
| POST | `/api/classrooms/{cid}/enrollments/{eid}/pauses/{pid}/resume` | 신규 — 복귀(ADMIN+CSRF) |
| GET | `/api/classrooms/{cid}/students` | 응답에 `enrollment_id` 추가(필드 추가만) |

오류: 400 `PAUSE_IN_FUTURE`/`PAUSE_OUTSIDE_ENROLLMENT`/`INVALID_PAUSE_DATES`, 404 `ENROLLMENT_NOT_FOUND`,
409 `ALREADY_PAUSED`/`PAUSE_OVERLAP`/`PAUSE_NOT_OPEN`/`ENROLLMENT_WITHDRAWN`. 감사 로그 `ENROLLMENT_PAUSE_RECORDED`, `ENROLLMENT_RESUMED`.

## 6. 화면 변경

- 수업 탭: "교시" 입력(기본 1)·목록 열, "시험 회차"와 구분. 수업 표기 `2026-11-03 2교시 (3회차)`(1교시는 생략).
- 출결 탭: 인정결석 버튼(아이콘+글자), 집계에 인정결석.
- 학생·반 관리(`/students`, ADMIN): 상태를 재원/휴원/퇴원 태그로 표시, "휴원 처리"(시작일)·"복귀 처리"(복귀일) 모달.

## 7. 변경 파일 (내용 검색으로 확인, 수정 시각 미사용)

각 항목은 해당 파일에서 Phase 7.1 고유 문자열을 실제로 찾아 확인했다(2026-11-18, 38개 항목 모두 확인).

| 파일 | 핵심 변경 | 확인한 내용(위치) |
|---|---|---|
| `backend/alembic/versions/007_phase71_sessions_pauses.py` (신규) | Migration 007 | `revision = "007_…"`(12), `ex_enrollment_pause_overlap`(89), `Asia/Seoul`(19) |
| `backend/app/db/models/tables.py` | `EnrollmentPause`, 교시·고유 인덱스, EXCUSED CHECK | `class EnrollmentPause`(87), `uq_lesson_session_without_exam_round`(144), EXCUSED(168) |
| `backend/app/db/schema.py` | 기대 테이블에 `enrollment_pause` | (24) |
| `backend/app/modules/academics/repository.py` | 휴원 기간 판정, 휴원 조회 | `paused_on_day`(28), `def open_pause`(281) |
| `backend/app/modules/academics/schemas.py` | EXCUSED, `session_no`, 휴원 모델 | `"EXCUSED"`(8), `class PauseCreate`(285) |
| `backend/app/modules/academics/service.py` | 교시 변경 제한, 휴원·복귀 | 교시 키 검사(232), `def create_pause`(563) |
| `backend/app/modules/academics/router.py` | 휴원 API 3개 | `/resume`(320) |
| `backend/app/modules/learningops/{schemas,router}.py` | 학생 목록 `enrollment_id` | (149), (236) |
| `backend/tests/test_phase71_stabilization_integration.py` (신규) | 7.1 통합 테스트 5개 | (189) |
| `backend/tests/test_phase7_academics_integration.py` | 집계 `excused` 기대값, 잘못된 상태 예시 SICK | (233) |
| `backend/tests/test_phase7_schema_integrity.py` | head 007, 잘못된 상태 예시 SICK | (18) |
| `backend/tests/test_postgres_integration.py` | head 007, 트리거 2개, 006 상태 허용 | (213) |
| `backend/tests/test_db_safety.py` | ORM 테이블 `enrollment_pause` | (79) |
| `src/main/java/.../AcademyImportDAO.java` | 수업 조회 `session_no=1` | (77) |
| `src/main/java/.../JdbcImportConfirmRepository.java` | 수업 조회 `session_no=1` | (140) |
| `src/main/java/.../SendLogDAO.java` | 결과 조회 `session_no=1` | (71) |
| `src/main/java/.../MakeupDAO.java` | 보강 상태 조회 `session_no=1`, 수업 목록 정렬 | (184), (74) |
| `src/test/java/.../PostgreSqlDaoIntegrationTest.java` | Java 호환 테스트 1개 | (209) |
| `frontend/src/features/classwork/{api.ts,common.tsx,AttendanceTab,LessonsTab,GradesTab,StudentRecordsDrawer}.tsx` | EXCUSED, 교시 | 각 파일 확인 |
| `frontend/src/features/classwork/ClassworkPage.test.tsx` | 인정결석·2교시 테스트 | (77) |
| `frontend/src/features/learningops/{api.ts,LearningOpsPage.tsx,LearningOpsPage.test.tsx}` | 휴원·복귀 UI와 테스트 | (9), (81), (65) |

기존 테스트 기대값 변경은 모두 의도된 동작 변경 때문이다: EXCUSED가 유효 값이 되어 "잘못된 상태" 예시를 `SICK`으로 바꿨고,
집계에 `excused` 키가 추가됐으며, 스키마 head·트리거·테이블 목록이 늘었다. 검증을 약화한 변경은 없다.

## 8. 테스트 결과 (2026-11-18, 테스트 DB head 007)

| 항목 | 결과 |
|---|---|
| Ruff | PASS |
| `alembic check` | 차이 없음 |
| pytest 전체 (PostgreSQL 포함) | **69 PASS** (7.1 신규 5) |
| Java Maven (PostgreSQL) | **48 PASS / 0 fail / 0 skip** (7.1 신규 1) |
| React Vitest | **10 files, 33 PASS** (7.1 신규 2: 인정결석·2교시, 휴원·복귀) |
| React lint / tsc / build | PASS (oxlint·tsc는 마지막 수정 후 실행, build는 새 산출물 생성, 기존 500kB chunk 경고만) |
| 개발 DB 007 적용 및 보존 | PASS (§4-1) |
| 브라우저 E2E | 사용자 수행 항목 — 사용자 지시로 Phase 7.1 완료 처리 (세부 결과 미전달, §10) |

참고: 전체 Vitest는 약 380초가 걸려, 처음 10분 제한 실행에서 시간 초과로 중단됐다(그때 보인 build 결과는 이전 실행 로그였으므로
결과로 쓰지 않았다). 남은 테스트 프로세스를 정리한 뒤 제한 없이 다시 실행한 결과를 위에 기재했다.

### 8-1. 브라우저 확인 절차 (`http://127.0.0.1:5173`, 관리자 비밀번호는 사용자가 직접 입력)

1. 수업·출결·성적 → 수업 탭: 같은 날짜로 1교시·2교시 수업 등록 → 같은 교시 재등록 시 오류 안내 확인
2. 출결 탭: 2교시 선택 → 학생에게 "인정결석" 선택·저장 → 집계에 인정결석 1, 결석 0
3. 학생·반 관리: 학생 "휴원 처리"(예: 며칠 전 날짜) → 상태 "휴원" → 휴원 시작일 이후 수업의 출결 명단에서 학생이 빠지고, 이전 수업에는 남아 있는지 확인
4. "복귀 처리"(오늘) → 상태 "재원" → 오늘 이후 수업 명단에 다시 포함되는지 확인
   (테스트 중 입력한 수업·출결·휴원 기록은 개발 DB에 남으며 화면에서 삭제할 수 없다)

7.1 신규 테스트가 검증한 것:
- 같은 날 1·2교시 생성, 같은 교시 중복 409, 교시 0·10 거부, 교시별 독립 출결, 기록 있는 수업의 교시 변경 409, 정렬.
- Java식 INSERT는 1교시, Java가 쓰는 조회가 2교시가 있어도 1행만 반환.
- **Java 실제 코드**: CSV 가져오기 → 같은 날 2교시 + EXCUSED 기록 생성 → XLSX 다시 가져오기 →
  수업 4개·결과 6개, 2교시 EXCUSED 3건 보존, 1교시에는 EXCUSED 없음, 보강 목록 1건(ABSENT만), 메시지 초안은 1교시 결과에 연결.
- EXCUSED 저장·집계·학생 이력·수정 이력(before EXCUSED), 결석 집계와 분리.
- 휴원: 권한(TEACHER 403), 미래·수강 전·잘못된 기간 400, 진행 중 중복 409, 휴원 전 수업 대상/휴원 중 제외/복귀 후 대상,
  복귀 후에도 과거 휴원 기간은 제외, 닫힌 과거 휴원 기록, 기간 겹침 409(DB EXCLUDE), 감사 로그.
- 트리거: 상태만 PAUSED로 바꾸면 오늘(KST)부터 휴원 생성, 같은 상태 재설정은 무변화, ACTIVE로 바꾸면 복귀,
  같은 날 재휴원은 기존 휴원을 이어 열기, 휴원 이력 없는 기존 PAUSED는 제외, PAUSED로 신규 등록된 수강도 날짜 기록.

검증 한계: Java 조회에서 `session_no = 1` 조건을 빼면 "정렬 없는 첫 행"이 되므로 실패가 매번 재현된다는 보장이 없다.
그래서 조건을 제거해 실패를 확인하는 역검증은 하지 않았고, 조건이 있는 상태에서 결과가 결정적인지만 검증했다.

## 9. 남은 위험·미검증

1. 브라우저 확인은 사용자 수행 항목 — 사용자 지시로 완료 처리(세부 결과는 미전달, §10).
2. 휴원 이력이 없는 기존 PAUSED 데이터는 계속 전 기간 제외(추정 금지). 개발 DB에는 해당 데이터 0건.
3. Java Import가 바꾼 휴원/복귀 날짜는 **Import 실행일**(CSV의 수업일 아님). 정확한 날짜는 휴원 API로 기록해야 한다.
4. Java Import는 항상 1교시에 기록한다. 2교시 이상은 Python API·화면에서만 관리된다.
5. 인정결석은 Java 보강 목록에 포함되지 않는다(Phase 8 정책 결정 필요).
6. Python API의 "오늘"은 서버 로컬 날짜(현재 KST)다. 서버 시간대가 바뀌면 트리거(KST 고정)와 어긋날 수 있다 → 업무 시간대 설정화를 후속 과제로 둔다.
7. 휴원 기록·복귀 시 해당 기간에 이미 입력된 출결은 삭제하지 않는다(표시만 "수강 기간 아님").
8. Git CLI 없음 — 사용자 지시에 따라 설치·초기화하지 않았다.

## 10. 판정

**완료** (2026-11-18, 사용자 완료 승인).
세 과제의 구현과 자동 검증(Python 69, Java 48, React 33, lint·tsc·build)은 모두 PASS이며,
개발 DB 007은 승인 후 백업·적용·보존 검증까지 마쳤다.
브라우저 확인(§8-1)은 사용자가 직접 수행하는 항목이며, 사용자가 Phase 7.1 완료 처리를 지시했다.
확인한 단계별 세부 결과는 에이전트에게 전달되지 않았으므로 이 문서에 PASS 수치로 기록하지 않는다.

실행 환경 메모: 에이전트가 백그라운드로 띄운 React 개발 서버는 최대 실행 시간(2시간)에 도달해 자동 종료됐고,
FastAPI 백그라운드 작업도 이후 세션 측에서 종료됐다. 두 서버는 필요할 때 `scripts/start-frontend.ps1`,
`scripts/start-fastapi.ps1`로 다시 시작한다. 개발 DB(007)와 데이터는 영향 없음.
