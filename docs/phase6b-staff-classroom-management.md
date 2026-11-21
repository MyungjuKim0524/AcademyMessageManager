# Phase 6B — 직원 계정 및 담당 반 배정 관리

작성일: 2026-11-17

## 요약

ADMIN 전용 직원 계정 조회·생성·활성/비활성 관리와 담당 반 배정·해제 API 및 React 관리 화면을 구현했다.
격리 테스트 DB(`academy_learningops_test`)에서 Migration 004 적용, Python 전체 53개(PostgreSQL 통합 포함),
Java 47개(PostgreSQL 활성화, 0 skipped), React Vitest 21개·lint·build가 모두 PASS했다.

2026-11-17 사용자 조건부 승인에 따라 개발 DB에 Migration 004를 백업 후 적용했고, 데이터 보존을 확인했다(§6-1).
FastAPI(개발 DB 연결)와 React 개발 서버를 기동했다.

이후 사용자가 브라우저에서 화면 동작을 확인했고(§14), 피드백에 따라 반 중심 배정 화면, 선생님 담당 반 자동 표시,
직원 이름(Migration 005)을 추가했다. Migration 005도 승인 후 개발 DB에 백업·적용·검증했다.

**판정: 조건부 완료.** 다음 항목은 아직 PASS가 아니다.

- §14 변경 후 화면의 브라우저 재확인: **사용자 수동 실행 대기**

## 1. 기존 코드 분석 결과 (Gate A)

| 분류 | 항목 |
|---|---|
| 이미 구현되어 재사용 | `staff_user`·`classroom_staff_assignment`·`auth_session` 모델, Argon2id `hash_password`, 서버 세션 + HttpOnly Cookie + CSRF(`require_admin_csrf`), `require_admin`/`require_authenticated`, `POST /api/classrooms/{id}/assignments`(Phase 6A 배정 생성), `can_access_classroom`·`classrooms_for_principal`의 유효기간(`valid_to`) 기반 담당 반 필터, 공통 `CompatibilityError` 오류 형식 |
| 구현되어 있으나 UI 없음 | Phase 6A 배정 생성 API (React 화면 없음) |
| 일부 수정 필요 | 배정 중복 방지가 DB 제약 없이 처리됨 → 열린 배정(`valid_to IS NULL`) 부분 UNIQUE 인덱스 추가(Migration 004) |
| 새로 구현 | 직원 목록/상세/생성/상태 변경 API, 직원별·반별 배정 목록, 배정 해제 API, 비활성화 시 세션 폐기, 마지막·본인 ADMIN 보호, React 직원 관리 화면 |

배정 생성은 기존 Endpoint·Service(`LearningOpsService.assign`)를 그대로 사용했으며 별도 Endpoint를 만들지 않았다.
Git 실행 파일이 PATH에 없어 `git status` 확인은 Phase 6A와 마찬가지로 BLOCKED이며, 파일 수정 시각으로 변경 범위를 확인했다.

## 2. 새로 추가한 기능

- `GET /api/staff`, `GET /api/staff/{id}`, `POST /api/staff`, `PATCH /api/staff/{id}/status`
- `GET /api/staff/{id}/assignments`, `GET /api/classrooms/{id}/staff`
- `DELETE /api/classrooms/{classroom_id}/assignments/{assignment_id}`
- 직원 비활성화 시 해당 직원의 미폐기 `auth_session` 일괄 폐기(`revoked_at` 설정)
- 마지막 활성 ADMIN / 본인 ADMIN 비활성화 방지 (`SELECT ... FOR UPDATE` 기반)
- Migration `004_phase6b_assignment_integrity`
- React `/staff` 화면 및 ADMIN 전용 메뉴

## 3. 재사용한 기존 기능

`LearningOpsService`/`LearningOpsRepository`/`router` 구조, 인증 Dependency, CSRF 검사, `hash_password`,
`_commit`의 `IntegrityError → 409` 변환 및 Rollback, 배정 생성 API, 담당 반 접근 검사, Ant Design 기반 레이아웃·`ProtectedRoute`·`ApiClientError`.

## 4. 직원 계정 생성 및 활성화 정책

비교한 두 방식 중 **관리자 화면에서 초기 비밀번호를 직접 입력하고 서버에서 즉시 Argon2id 해시**하는 방식을 채택했다.
기존 비밀번호 설정 CLI(`scripts/bootstrap-admin.ps1`)는 최초 ADMIN 부트스트랩용이라 일반 직원 생성 흐름에는 쓰지 않았다.

- ADMIN + CSRF 필요, 공개 회원가입 API 없음
- 비밀번호 12~1024자, `StrictStr`, 기본 비밀번호·하드코딩 없음
- 평문 저장·로그 출력 없음, 응답에 `password`/`hash`/`session` 문자열 미포함(테스트로 확인)
- 입력란 `autoComplete="new-password"`, URL·쿼리 문자열로 전달하지 않음
- 생성 즉시 `ACTIVE`; 요청 본문의 `status` 등 추가 필드는 `extra="forbid"`로 400
- 생성 가능한 Role은 `TEACHER`/`ASSISTANT`만. `ADMIN` 생성 요청은 400
- **Role 변경 API는 구현하지 않음** (권한 상승·관리자 잠금 위험, 기존 정책 부재). Role은 조회만 가능

## 5. API 명세

| Method | Path | 권한 | 성공 | 주요 오류 |
|---|---|---|---|---|
| GET | `/api/staff?limit&offset` | ADMIN | 200 `{items[id,email,role,status,created_at,updated_at],limit,offset}` | 401, 403 |
| GET | `/api/staff/{id}` | ADMIN | 200 StaffView | 404 `STAFF_NOT_FOUND` |
| POST | `/api/staff` `{email,password,role}` | ADMIN+CSRF | 201 StaffView | 400 검증, 403 CSRF, 409 `STAFF_EMAIL_ALREADY_EXISTS` |
| PATCH | `/api/staff/{id}/status` `{status}` | ADMIN+CSRF | 200 StaffView | 404, 409 `SELF_ADMIN_DEACTIVATION_FORBIDDEN`/`LAST_ACTIVE_ADMIN` |
| GET | `/api/staff/{id}/assignments` | ADMIN 또는 본인 | 200 배정 + `classroom_name` | 403 타인 조회, 404 |
| GET | `/api/classrooms/{id}/staff` | ADMIN | 200 배정 + `email`,`staff_status` | 404 `CLASSROOM_NOT_FOUND` |
| POST | `/api/classrooms/{id}/assignments` (기존) | ADMIN+CSRF | 201 | 400 `STAFF_NOT_ASSIGNABLE`/`ASSIGNMENT_ROLE_MISMATCH`/`INVALID_ASSIGNMENT_DATES`, 404, 409 `ASSIGNMENT_ALREADY_EXISTS` |
| DELETE | `/api/classrooms/{cid}/assignments/{aid}` | ADMIN+CSRF | 204 | 404 `ASSIGNMENT_NOT_FOUND` (재해제·반 불일치 포함) |

목록은 `limit` 1~100(기본 50)·`offset` 페이지네이션을 사용한다. 비밀번호 Hash와 세션 Digest는 어떤 응답 모델에도 없다.
배정 해제는 행을 삭제하는 방식이며, 이력 보존이 필요해지면 `valid_to` 종료 방식으로 바꾸는 것을 후속 과제로 둔다.

## 6. DB 변경 여부

`004_phase6b_assignment_integrity` (Additive): `classroom_staff_assignment(classroom_id, staff_user_id) WHERE valid_to IS NULL` 부분 UNIQUE 인덱스 `uq_assignment_open_staff_classroom`.
기존 Migration·테이블은 수정하지 않았다.

| DB | Revision | 비고 |
|---|---|---|
| 테스트 DB | `004_phase6b_assignment_integrity (head)` | 적용 전 중복 열린 배정 0건 확인, `alembic check` 차이 없음 |
| 개발 DB | `004_phase6b_assignment_integrity` → `005_staff_display_name (head)` | 004·005 모두 승인 후 적용, 백업 및 보존 검증 완료 (§6-1, §14-3) |

참고: revision ID가 처음에는 파일명과 같아 `alembic_version.version_num varchar(32)`를 넘어 실패했고(트랜잭션 Rollback, 테스트 DB 003 유지 확인), 32자 이내 ID로 수정한 뒤 적용했다.

### 6-1. 개발 DB 적용 기록 (2026-11-17)

1. **대상 식별**: 컨테이너 `academy-learningops-postgres-dev`(postgres:17.6-alpine, healthy), 포트 `127.0.0.1:55431`,
   라벨 `academy.environment=isolated-development`·`academy.destructive-tests=forbidden`, 볼륨 `academy_learningops_postgres_dev_data`,
   `current_database()=academy_learningops_dev`, `current_user=academy_dev`. Alembic은 `ACADEMY_DB_MODE=development` 허용 목록 검사를 통과한 연결로만 실행했다.
2. **변경 SQL 확인** (`alembic upgrade 003:004 --sql`): 단일 트랜잭션 내
   `CREATE UNIQUE INDEX uq_assignment_open_staff_classroom ON classroom_staff_assignment (classroom_id, staff_user_id) WHERE valid_to IS NULL;`
   및 `alembic_version` 갱신뿐이다. DROP/DELETE/TRUNCATE/컬럼 변경 없음.
3. **백업**: `pg_dump -Fc` → `D:\refactor\backend-architecture\.dev-data\backups\academy_learningops_dev-pre004-20261117-223934.dump`
   (72,492 bytes, SHA-256 `33B9439CBF51F0CEFE0E44FAA0715D89F849BBE5618FDDB91DDE3FDBA89D5620`). `pg_restore --list` 성공(190 entries,
   `staff_user`·`classroom_staff_assignment`·`classroom`·`student`·`enrollment`·`alembic_version` 데이터 포함). 컨테이너 내 임시 파일은 삭제했다. 비밀번호는 출력하지 않았다.
4. **사전 조건**: 중복 열린 배정 0건, 인덱스 미존재 확인 후 `alembic upgrade 004_phase6b_assignment_integrity` 실행 — 성공.
5. **사후 읽기 전용 검증** (`BEGIN READ ONLY`):

| 항목 | 적용 전 | 적용 후 |
|---|---|---|
| Revision | `003_phase6a_enrollment_integrity` | `004_phase6b_assignment_integrity (head)` |
| `uq_assignment_open_staff_classroom` | 없음 | 존재, `indisvalid=true`, `indisunique=true` |
| staff_user (ADMIN/ACTIVE) | 1 (1) | 1 (1) |
| classroom_staff_assignment | 0 | 0 |
| classroom / student / enrollment / auth_session | 1 / 1 / 1 / 1 | 1 / 1 / 1 / 1 |
| staff_user 지문(md5, id·email·role·status·hash) | `363ea436…a325e` | 동일 |
| 배정 지문 | empty | empty |
| `alembic check` | — | No new upgrade operations detected |

오류 없이 완료되어 데이터 수정·강제 진행은 없었다. 기존 Docker 볼륨은 그대로다.

### 6-2. 적용 후 발견·수정한 문제

`backend/scripts/auth_preflight.py`가 개발 DB revision을 `003_phase6a_enrollment_integrity`로 하드코딩하고 있어
004 적용 후 `scripts/start-fastapi.ps1`이 기동을 거부했다. 비교 대상을 Alembic 스크립트 디렉터리의 현재 head로 바꿨다
(이후 Migration 추가 시 같은 문제가 재발하지 않음). Ruff PASS, head 계산값 `004_phase6b_assignment_integrity` 확인, preflight 통과 후 FastAPI 기동 확인.

### 6-3. 브라우저 E2E 준비 상태

| 구성 | 상태 |
|---|---|
| FastAPI `http://127.0.0.1:8000` (개발 DB) | 기동, preflight PASS, `/api/auth/me` 미인증 401 |
| React `http://127.0.0.1:5173` (Vite dev) | 기동, `/` 200, 프록시 경유 `/api/auth/me`·`/api/staff` 401 |

수동 시나리오: ADMIN 로그인 → `/staff`에서 TEACHER 생성 → 반 배정 → 로그아웃 → TEACHER 로그인 → 담당 반·학생 조회 →
ADMIN 재로그인 후 배정 해제 → TEACHER 접근 차단 확인. 개발 DB에 실제 데이터가 생성됨에 유의한다.

## 7. 역할·담당 반 권한 정책

- ADMIN: 직원 조회·생성·상태 변경, 모든 반 배정·해제
- TEACHER/ASSISTANT: 본인 배정 목록과 담당 반·학생 조회만 가능, 배정·직원 변경 API는 403
- 역할은 서버 세션과 DB의 `staff_user`에서 확인하며 Header·본문을 신뢰하지 않음
- 비활성 직원: 로그인 401, 기존 세션 폐기로 `/api/auth/me` 401, 신규 배정 대상 불가
- 배정 해제 즉시 해당 반 목록·학생 조회 차단

## 8. React 관리자 화면

`frontend/src/features/staff/` (`StaffManagementPage.tsx`, `api.ts`, 테스트) 및 `/staff` 라우트(`ProtectedRoute roles={['ADMIN']}`).
`AppLayout` 메뉴의 "직원 관리"는 ADMIN에게만 표시된다.
직원 목록(역할·상태 Tag, 비활성 시각 구분), 등록 폼, 직원 선택 시 담당 반 목록, 반 배정·해제(Popconfirm), 비활성화 확인,
Empty State, 오류 Alert(중복 배정 409 포함), 처리 중 버튼 loading/disabled 처리를 제공한다. 새로운 UI 프레임워크는 도입하지 않았다.

## 9. 보안 및 동시성 검증

`backend/tests/test_phase6b_staff_management_integration.py` (실제 PostgreSQL):

| 항목 | 결과 |
|---|---|
| 미인증 401 / TEACHER 403 | PASS |
| CSRF 없는 POST 403 | PASS |
| 직원 생성 201, 중복 이메일 409 | PASS |
| ADMIN 역할 생성·`status` Mass Assignment·SQL Injection 형태 이메일 400 | PASS |
| 응답 내 password/hash/session 미노출 | PASS |
| 비활성화 → 기존 세션 401, 재로그인 401, 재활성화 후 로그인 200 | PASS |
| 본인 ADMIN 동시 비활성화 2건 → 409/409, ACTIVE ADMIN 2명 유지 | PASS |
| 동시 배정 2건 → 201/409, 행 1개 | PASS |
| 본인 배정 조회 200, 타인 배정 조회 403 (IDOR/BOLA) | PASS |
| 배정 해제 204 → 담당 반 학생 조회 403, 반 목록 비어 있음 | PASS |
| 이미 해제한 배정 재해제 404, 존재하지 않는 직원 400 | PASS |

마지막 ADMIN 보호는 활성 ADMIN 행을 `FOR UPDATE`로 잠근 뒤 판단하므로, 서로 다른 두 ADMIN을 동시에 비활성화하는 경쟁에서도 직렬화된다.
현재 테스트는 본인 비활성화 동시 요청만 직접 검증한다. "두 관리자가 서로를 동시에 비활성화" 시나리오는 별도 테스트가 없다(미해결 문제 참고).

## 10. 실제 PostgreSQL 통합 테스트 결과

2026-11-17, `127.0.0.1:55432/academy_learningops_test` (라벨 `isolated-test`, DB identity 검증 후 TRUNCATE):

- `pytest -m postgres`: 18 PASS (Phase 5·6A 16개 + Phase 6B 2개)
- Java `mvn -DrunPostgresIntegration=true test`: 47 PASS, 0 skipped

## 11. 전체 회귀 테스트 결과

| 항목 | 결과 |
|---|---|
| Ruff (`app tests alembic`) | PASS |
| pytest 전체 (PostgreSQL 포함) | 53 PASS |
| Java Maven (PostgreSQL 활성화) | 47 PASS / 0 fail / 0 skipped |
| React Vitest | 8 files, 21 PASS |
| React lint (oxlint) | PASS |
| React tsc + production build | PASS (기존 500kB chunk 경고만 존재) |
| API 기반 핵심 시나리오 (ADMIN 생성·배정 → TEACHER 조회 → 해제 → 차단) | PASS (통합 테스트) |
| 개발 DB Migration 004 적용 및 데이터 보존 | PASS (§6-1) |
| FastAPI·React 개발 서버 기동 | PASS (§6-3) |
| 실제 브라우저 E2E | **미실행 — 사용자 수동 실행 대기** |

## 12. 미해결 문제

1. 브라우저 E2E 미실행: 서버는 준비됨(§6-3). 사용자가 관리자 비밀번호로 직접 수행 후 결과 기록 필요
2. 이 보고서의 자동 테스트 결과는 `auth_preflight.py` 수정 이전 실행분이다. 해당 스크립트는 테스트 대상이 아니며 Ruff만 재실행했다
3. 두 ADMIN의 상호 동시 비활성화 테스트 추가 권장
4. 배정 해제가 하드 삭제라 배정 이력이 남지 않음 (감사 요구 시 `valid_to` 종료 방식 검토)
5. Git CLI 부재로 변경 diff 검증 BLOCKED
6. 빌드 chunk 크기 경고(기존 이슈), Starlette TestClient `httpx` deprecation 경고

## 13. Phase 7 착수 가능 여부

백엔드·프론트엔드 기능과 자동 테스트 기준으로 **착수 가능**하다.
개발 DB Migration 004는 적용·검증을 마쳤다. 브라우저 E2E가 PASS하면 Phase 6B를 **완전 완료**로 전환한다.

## 14. 후속 변경 — 배정 UX 개선 및 직원 이름 (2026-11-17)

사용자 브라우저 확인 결과 화면은 정상 동작했으나 다음 피드백이 있었다.
(1) 선생님 반 배정 흐름이 매끄럽지 않음, (2) 선생님이 담당 반 학생을 바로 볼 수 없음, (3) 이메일만으로는 직원을 구별하기 어려움.
사용자 결정: 이름은 등록 시 필수·ADMIN 수정 가능, 배정은 **반 중심**, 선생님 화면은 첫 담당 반 자동 표시 + 반 선택.

### 14-1. 백엔드

- Migration `005_staff_display_name`: `staff_user.display_name VARCHAR(100)` NULL 허용 컬럼 추가(기존 계정 유지용)
- `POST /api/staff`: `display_name` 필수(공백 정리, 1~100자, 제어문자 거부)
- `PATCH /api/staff/{id}` (신규, ADMIN+CSRF): `display_name`만 변경 가능. `role` 등 다른 필드는 400
- `GET /api/classrooms/{id}/staff` 응답에 `display_name` 추가, `/api/auth/me`·로그인 응답에 `display_name` 추가
- `scripts/auth_preflight.py`: 하드코딩된 revision 대신 Alembic head와 비교 (004 적용 후 기동 실패 수정)

### 14-2. 프론트엔드

- `/staff`를 탭 2개로 재구성
  - **직원 계정**: 이름 포함 등록, 이름 수정(Modal), 활성/비활성(확인 절차), 행 클릭 시 담당 반 Drawer, 이름 미등록 표시
  - **반별 담당 배정**: 반 목록에서 반 선택(첫 반 자동 선택) → 담당 직원 표(이름·이메일·역할·상태·시작일) → 이름/이메일 검색 드롭다운으로 배정(활성 TEACHER/ASSISTANT 중 미배정자만, 역할 자동, 시작일 기본값 오늘) → 확인 후 해제
- `/students`: 접근 가능한 반 목록을 불러와 첫 반 학생을 자동 표시, 상단 드롭다운으로 반 전환. 담당 반이 없으면 안내 문구. 반 ID 입력칸 제거
- ADMIN 전용 ID 입력식 "직원 배정" 카드 제거(반 중심 배정 화면으로 일원화), 수강 등록의 반 선택을 드롭다운으로 변경
- 사이드바: 이름 우선 표시, TEACHER/ASSISTANT 메뉴명 "담당 반 학생"
- 테스트 설정: Vitest globals 비활성 환경에서 Testing Library cleanup 누락 → `src/test/setup.ts`에 `afterEach(cleanup)` 추가
- 테스트 참고: 이 화면에서 jsdom `getByRole`이 스타일 계산으로 수 분 걸려 무한 대기처럼 보였다. 해당 테스트는 텍스트·라벨 조회로 변경(1.6초)

### 14-3. 개발 DB Migration 005 적용 기록

1. 식별: `academy-learningops-postgres-dev`, `127.0.0.1:55431`, 라벨 `isolated-development`/`destructive-tests=forbidden`, 볼륨 `academy_learningops_postgres_dev_data`, `academy_learningops_dev`/`academy_dev`
2. SQL: `ALTER TABLE staff_user ADD COLUMN display_name VARCHAR(100);` + `alembic_version` 갱신 (단일 트랜잭션, 삭제·변경 없음)
3. 백업: `.dev-data\backups\academy_learningops_dev-pre005-20261117-234018.dump` (73,444 bytes, SHA-256 `6F49BFBE2CF419D31EF2190C0916E1D6FF1736C1E08455C6F1B1832E5CCBA224`), `pg_restore --list` 성공(191 entries)
4. 적용: 성공. 적용 명령 출력이 PowerShell `ErrorActionPreference=Stop`으로 중간에 끊겼으나, 재실행하지 않고 읽기 전용으로 revision 005·컬럼 존재를 먼저 확인했다. `alembic check` 차이 없음
5. 사후 검증 (`BEGIN READ ONLY`):

| 항목 | 적용 전 | 적용 후 |
|---|---|---|
| Revision | 004 | `005_staff_display_name (head)` |
| `display_name` | 없음 | `varchar(100)`, NULL 허용, 기존 2명 모두 NULL |
| staff_user | ADMIN 1, TEACHER 1 (모두 ACTIVE) | 동일 |
| 배정 / 반 / 학생 / 수강 / 세션 | 1 / 1 / 1 / 1 / 3 | 동일 |
| staff·배정·반·학생 지문(md5) | `a3f8…a53b` / `f85e…a4ef` / `9d97…b4ea` / `7587…1b78` | 동일 |
| `uq_assignment_open_staff_classroom` | 존재 | 존재 |

기존 계정 2개는 "이름 미등록"으로 표시되며, ADMIN이 직원 계정 탭에서 이름을 입력하면 된다.

### 14-4. 검증 결과

| 항목 | 결과 |
|---|---|
| Ruff (`app tests alembic scripts`) | PASS |
| pytest 전체 (테스트 DB 005, PostgreSQL 포함) | PASS (이름 검증·수정·Mass Assignment·CSRF·권한·`/me` 이름 테스트 추가) |
| Java Maven (PostgreSQL 활성화) | 47 PASS, 0 skipped |
| React Vitest | 9 files, 25 PASS (신규: 직원 화면 3, 담당 반 화면 2) |
| React lint / tsc / production build | PASS |
| 개발 DB 005 적용 및 보존 | PASS |
| FastAPI(preflight PASS)·React 기동 | PASS, 미인증 401 확인 |
| 변경 화면 브라우저 재확인 | **사용자 수동 실행 대기** |
