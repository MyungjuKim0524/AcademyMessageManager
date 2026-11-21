# Phase 11-4-B 결과 — 배포 실행 모드와 계정 보안 (SEC-04 · SEC-05 · SEC-10)

작업일: 2026-11-21 · 기준: Phase 11-4-A 완료 코드(`phase11_4_a_performance_results.md`)
원칙: **DB 스키마·Migration 변경 없음. 새 라이브러리·외부 발송(메일·SMS) 없음.** Git이 없어서 수정 전 원본은 이전 세션 scratchpad에, 마무리 단계 원본은 `.dev-data/backups/phase114b-final-20261121-183543/`에 백업했다.
비밀번호·토큰·재설정 코드 원문은 이 문서와 로그에 남기지 않았다.

---

## 1. SEC-04 — 배포 실행 모드 `production`

**문제**: 지금까지는 `ACADEMY_DB_MODE`가 development/test이고 API 호스트가 루프백일 때만 DB API가 열렸다. 그래서 배포하면 로그인과 업무 API가 모두 404였다.

**변경**
- `ACADEMY_DB_MODE=production`을 새로 만들었다. development/test의 기존 제한(루프백 호스트, 고정된 로컬 DB)은 그대로다.
- production에서는 `require_local_db_api`가 루프백 검사를 생략한다. `ACADEMY_ENABLE_DB_APIS=1`은 여전히 필요하다.
- **설정이 안전하지 않으면 시작을 거부한다(fail closed).** `app/main.py`가 import 시점에 `production_problems()`를 호출하고, 문제가 하나라도 있으면 `RuntimeError`를 낸다.
- 오류 메시지에는 **설정 이름만** 들어간다. DB URL·비밀값 같은 값은 들어가지 않는다(단위 테스트로 확인했다).

## 2. 환경별 정책

| 항목 | development | test | production |
|---|---|---|---|
| API 호스트 | 루프백만 | 루프백만 | 제한 없음(`--host 0.0.0.0`) |
| DB 대상 | 로컬 개발 DB(55431) | 격리 테스트 DB(127.0.0.1:55432) | PostgreSQL + `sslmode=require`/`verify-ca`/`verify-full`. 로컬 dev/test DB는 금지 |
| `ACADEMY_ENABLE_DB_APIS` | 1이면 열림 | 1이면 열림 | **1 필수**(아니면 시작 실패) |
| `ACADEMY_COOKIE_SECURE` | 0 가능 | 0 가능 | **1 필수** |
| `ACADEMY_CORS_ORIGINS` | localhost 허용 | localhost 허용 | 정확한 `https://`만. localhost·`127.0.0.1`·`*` 금지 |
| `ACADEMY_TRUSTED_PROXIES` | 자유 | 자유 | `/0` 금지 |
| 테스트 스위치(`ACADEMY_DB_TEST_MODE`, `ACADEMY_RUN_POSTGRES_INTEGRATION`) | — | 필수 | **금지** |
| `ACADEMY_PROXY_DIAGNOSTICS` | 허용 | 허용 | 허용(배포 가이드 6절 점검용, 평소 0) |
| `ACADEMY_SESSION_IDLE_MINUTES` | 1..TTL | 1..TTL | 1..TTL (0 = 무제한은 모든 모드에서 금지) |

구현 위치: `app/config.py::production_problems`, `app/db/safety.py::validate_production_database_url`, `app/security.py::require_local_db_api`.

## 3. SEC-05 — 유휴 세션 만료(서버 기준)

- **기준**: 마지막 활동(`auth_session.last_seen_at`) 이후 `ACADEMY_SESSION_IDLE_MINUTES`(기본 60분) 이상 지나면, 다음 요청에서 세션을 revoke하고 **401 `SESSION_IDLE_EXPIRED`**를 돌려준다. 경계값(정확히 60분)도 만료로 본다.
- **8시간 절대 만료(`ACADEMY_SESSION_TTL_MINUTES=480`)는 그대로다.** 계속 사용 중이어도 8시간이 지나면 끝난다.
- **활동 기록**
  - 60초(`ACTIVITY_WRITE_SECONDS`)에 최대 한 번만 쓴다. 조건부 UPDATE라서 동시 요청이 와도 시각이 뒤로 가지 않는다.
  - 의존성(`get_current_principal` → `_check_idle`) 안에서 바로 commit한다. 그래서 이후 업무 트랜잭션이 실패해도 활동 기록은 남는다.
- **백그라운드 요청**: `X-Academy-Background: 1` 헤더가 붙은 요청은 세션을 연장하지 않는다. 다만 유휴 만료 검사는 똑같이 받는다. 현재 프론트에는 자동 폴링이 없어서 이 헤더를 보내는 곳은 없다. 앞으로 폴링을 넣을 때 쓰기 위한 것이다.
- **시계**: 세션 시각은 모두 `auth.service.utc_now()` 하나를 쓴다. 테스트는 이 함수를 바꿔 시간을 움직인다.
- **로그인**: 로그인할 때 `last_seen_at = now`를 기록한다.
- **프론트**: axios 401 인터셉터가 처리한다. 로그인된 상태에서 401을 받으면 로그아웃 상태로 바꾸고 로그인 화면에 안내를 띄운다.
  - `SESSION_IDLE_EXPIRED`: "오랫동안 사용하지 않아 로그아웃되었습니다. 다시 로그인해주세요."
  - 그 밖의 401: "세션이 만료되었습니다. 다시 로그인해주세요."

## 4. SEC-10-A — 비밀번호 변경

- `POST /api/auth/password` (세션 + CSRF, JSON만). 요청 본문은 `current_password`, `new_password`이다.
- **현재 비밀번호가 틀리면 400 `INVALID_CURRENT_PASSWORD`**를 돌려준다. 401로 하면 위의 인터셉터가 로그아웃시키므로 401을 쓰지 않았다.
- **시도 제한**: 로그인 한도(5회/15분)를 계정별 키 `password-change:{id}`로 재사용한다. 6번째는 429다. 새 비밀번호 규칙 위반으로 실패하면 시도 횟수에서 뺀다.
- **새 비밀번호 규칙 `password_problem()`**: 변경과 재설정이 같이 쓴다. 위반하면 400 `WEAK_PASSWORD`와 구체적인 사유를 돌려준다.
  - 12자 이상, 1024자 이하
  - 공백만으로 된 비밀번호 금지
  - 현재 비밀번호와 달라야 함
  - 이메일과 같으면 안 됨
- **성공**: 현재 세션은 유지하고 **다른 세션은 모두 revoke**한다. 감사 이벤트 `STAFF_PASSWORD_CHANGED`(`other_sessions_revoked` 수만 기록)를 남긴다.
- **화면**: 상단 바의 "비밀번호 변경" 버튼으로 `PasswordChangeModal`을 연다.

## 5. SEC-10-B — 관리자 발급 일회용 재설정 코드

외부로 아무것도 보내지 않는다. 관리자가 코드를 발급해 **대면이나 전화로** 직원에게 전달한다.

- **발급**: `POST /api/staff/{id}/password-reset-code` (관리자 + CSRF)
  - 본인 계정 → 409 `SELF_RESET_FORBIDDEN`(본인은 비밀번호 변경을 쓴다)
  - 비활성 계정 → 409 `STAFF_NOT_ACTIVE`
  - 삭제된 계정 → 404
  - 감사 이벤트 `STAFF_PASSWORD_RESET_ISSUED`가 **저장된 다음에** 코드를 만들어 응답한다. 응답은 `{staff_id, code, expires_at}`이다.
- **사용**: `POST /api/auth/password-reset` (세션 불필요, **JSON만**. 폼 제출은 415). 요청 본문은 `email`, `code`, `new_password`이다.
  - **모든 실패는 똑같이 400 `RESET_FAILED`**다. 없는 계정, 비활성 계정, 틀린 코드, 이미 쓴 코드, 만료된 코드를 구별할 수 없어서 계정이 있는지 추측할 수 없다.
  - 비밀번호 규칙은 **코드를 쓰기 전에** 검사한다. 그래서 규칙 위반(`WEAK_PASSWORD`) 때문에 코드가 사라지지 않는다.
  - 시도 제한: 주소별 20회, 이메일별 5회(로그인 한도와 같다)
  - 성공하면 그 계정의 **모든 세션을 revoke**하고 감사 이벤트 `STAFF_PASSWORD_RESET_COMPLETED`를 남긴다.
- **코드 저장소 `PasswordResetCodes`**
  - 코드는 10자리(`XXXXX-XXXXX`)이며 헷갈리는 0/O, 1/I를 뺐다. 경우의 수는 약 2^50이다.
  - 계정 id와 묶은 SHA-256 다이제스트만 **프로세스 메모리**에 보관한다.
  - 15분 뒤 만료되고, 한 번 쓰면 사라지며, 5회 틀리면 폐기된다. 새로 발급하면 이전 코드는 무효가 된다.
  - 입력은 대소문자를 구별하지 않고, 하이픈·공백은 무시한다.
- **화면**
  - 직원 관리: 활성 직원 행에 "재설정 코드" 버튼이 있다. 확인 창(Popconfirm) 다음에 발급하고, 코드는 모달에 **한 번만** 보여 준다. "전달했습니다"를 누르면 상태에서 지운다. 비활성 행에는 버튼이 없다.
  - 로그인 화면: "재설정 코드로 설정" 폼이 있다.
- **유일한 관리자가 비밀번호를 잊었을 때**: `backend/scripts/bootstrap_admin.py`로 새 관리자를 만들고, 그 관리자가 기존 계정에 재설정 코드를 발급한다(배포 가이드 4절).

## 6. 변경 파일·함수

| 파일 | 내용 |
|---|---|
| `backend/app/config.py` | `Settings.db_mode`, `session_idle_minutes`, `_idle_minutes()`, `production_problems()` |
| `backend/app/db/safety.py` | `validate_production_database_url()`, `validate_test_database_url()`의 production 분기 |
| `backend/app/security.py` | `require_local_db_api`: production이면 루프백 검사 생략 |
| `backend/app/main.py` | production + problems → 시작 거부(`RuntimeError`) |
| `backend/app/modules/auth/service.py` | `utc_now()`, `ACTIVITY_WRITE_SECONDS`, `BACKGROUND_HEADER`, `PasswordResetCodes`, `password_problem()`, `AuthService._set_password / change_password / complete_reset`, 로그인 시 `last_seen_at` |
| `backend/app/modules/auth/dependencies.py` | `get_current_principal` → `_check_idle`(유휴 판정, 활동 기록, 의존성 안 commit) |
| `backend/app/modules/auth/router.py` | `change_password`, `complete_password_reset` |
| `backend/app/modules/auth/schemas.py` | `PasswordChange`, `PasswordChanged`, `PasswordResetComplete`, `PasswordResetDone` |
| `backend/app/modules/learningops/router.py`, `service.py`, `schemas.py` | `issue_password_reset_code`, `PasswordResetCodeIssued` |
| `backend/app/middleware.py` | `JSON_ONLY_PATHS`와 POST 경로 목록에 두 경로 추가 |
| `backend/.env.example` | `ACADEMY_DB_MODE` 세 가지 모드 설명, `ACADEMY_SESSION_IDLE_MINUTES=60` |
| `frontend/src/features/auth/api.ts` | `changePassword`, `completePasswordReset` |
| `frontend/src/features/auth/AuthProvider.tsx` | 401 인터셉터, `notice`(선택 필드), `IDLE_NOTICE`/`EXPIRED_NOTICE` |
| `frontend/src/features/auth/LoginPage.tsx` | 안내 표시, 재설정 코드 폼(`MIN_PASSWORD=12`) |
| `frontend/src/features/auth/PasswordChangeModal.tsx` | 신규 |
| `frontend/src/layout/AppLayout.tsx` | "비밀번호 변경" 버튼 |
| `frontend/src/features/staff/api.ts`, `StaffManagementPage.tsx` | `issueResetCode`, 재설정 코드 버튼·모달 |
| 테스트 | `backend/tests/test_phase114b_runtime_account.py`(신규), `frontend/src/features/auth/LoginPage.test.tsx`(신규), `AuthProvider.test.tsx`·`StaffManagementPage.test.tsx`(추가) |
| 문서 | `docs/deployment/phase11_5_security_deployment_guide.md` 갱신, 이 문서 |

## 7. API·화면 요약

**새 API**

| 메서드·경로 | 권한 | 성공 | 실패 |
|---|---|---|---|
| `POST /api/auth/password` | 세션 + CSRF | 200 `{changed, other_sessions_revoked}` | 400 `INVALID_CURRENT_PASSWORD`, 400 `WEAK_PASSWORD`, 429 |
| `POST /api/staff/{id}/password-reset-code` | 관리자 + CSRF | 200 `{staff_id, code, expires_at}` | 409 `SELF_RESET_FORBIDDEN`, 409 `STAFF_NOT_ACTIVE`, 404 |
| `POST /api/auth/password-reset` | 없음(JSON만) | 200 `{reset: true}` | 400 `RESET_FAILED`, 400 `WEAK_PASSWORD`, 415, 429 |

**새 오류 코드**: `SESSION_IDLE_EXPIRED`(401), `INVALID_CURRENT_PASSWORD`, `WEAK_PASSWORD`, `RESET_FAILED`, `SELF_RESET_FORBIDDEN`, `STAFF_NOT_ACTIVE`

**새 감사 이벤트**(값 대신 개수만 기록)

| 이벤트 | 기록 내용 |
|---|---|
| `STAFF_PASSWORD_CHANGED` | `other_sessions_revoked` |
| `STAFF_PASSWORD_RESET_ISSUED` | 발급자·대상, `role`, `expires_in_minutes`. 코드는 기록하지 않음 |
| `STAFF_PASSWORD_RESET_COMPLETED` | `sessions_revoked` |

**화면**: 상단 바 "비밀번호 변경", 로그인 화면의 만료 안내와 "재설정 코드로 설정", 직원 관리의 "재설정 코드"

## 8. 테스트 결과 (2026-11-21)

| 범위 | 결과 |
|---|---|
| 백엔드 단위 `pytest -m "not postgres"` | **117 passed**(기존 93 + 신규 24), 141 deselected |
| Ruff `ruff check .` | **PASS** |
| PostgreSQL 전체 회귀 `pytest -m postgres` | **141 passed, 0 failed, 0 skipped**(기존 131 + 신규 10), 4분 46초 |
| 프론트 tsc · oxlint | **PASS** |
| 프론트 Vitest 대상 폴더(`features/staff`) | 5 passed(신규 재설정 코드 UI 테스트 포함) |
| 프론트 Vitest 전체 | 15파일 113건 중 **112 passed, 1 failed** |

- **Vitest 실패 1건**: `NotificationsPage > uploads only the chosen time slot and reports rows already equal to the app as skipped`. 이번 단계 이전부터 실패하던 테스트이며 이번 변경과 관련된 파일이 아니다. **회귀가 아니다.**
- **신규 백엔드 테스트(24 + 10)**
  - 단위 24건
    - production 설정 검증: 안전한 설정, 위반 항목별 이름만 보고(parametrize)
    - 로컬 모드 유지, API 게이트
    - subprocess 기동 3건: production 정상 기동 + `/health`, 안전하지 않은 설정이면 시작 거부(비밀값 미출력), development 기동은 기존과 같음
    - 유휴 시간 범위·기본값, 재설정 코드 저장소(1회용·만료·5회 폐기·대체), 비밀번호 규칙
  - PostgreSQL 10건(비파괴, `P114B` 접두사)
    - 유휴 만료, 경계값과 절대 만료, 60초 쓰기 제한과 백그라운드 요청, 동시 요청 활동 기록, 로그아웃·비활성화
    - 비밀번호 변경, 현재 비밀번호 오답 제한
    - 재설정 전체 흐름, 동일 실패 응답과 만료, 비활성 계정·폼 제출 거부
  - 로그(caplog)에 비밀번호·코드 원문이 없는지 확인했다.
- **신규 프론트 테스트**
  - `LoginPage.test.tsx`
  - `AuthProvider` 유휴 만료 1건
  - `StaffManagementPage` 재설정 코드 1건: 비활성 행에 버튼 없음 → 확인 전 미호출 → `issueResetCode(2)` → 코드와 경고 문구 1회 표시 → "전달했습니다" 후 코드 사라짐
  - jsdom은 antd 모달의 닫힘 애니메이션을 끝내지 않는다. 그래서 테스트에서 `animationEnd`/`transitionEnd`를 직접 발생시킨다.

**PostgreSQL 전체 회귀의 초기화 범위**(사용자 조건부 승인 후 실행)
- **실행 전 검증 — 모두 통과**
  - 컨테이너: `/academy-learningops-postgres-test`, 라벨 `academy.environment=isolated-test`·`academy.destructive-tests=allowed`, 포트 `127.0.0.1:55432`
  - DB·사용자: `academy_learningops_test|academy_test`
  - 볼륨: `academy_learningops_postgres_test_data`(테스트 전용)
  - 실행 중인 컨테이너는 테스트 컨테이너 하나뿐이었다. 개발 DB와 `academy-postgres`는 꺼진 상태 그대로였고 접근하지 않았다.
- **실행 전 데이터**
  - 행이 있는 테이블은 `staff_user` 80, `audit_log` 56, `auth_session` 40뿐이었고 나머지 테이블은 0건이었다.
  - 직원 80건은 모두 `p114b…@example.invalid`였다. 감사·세션의 행위자도 모두 이 계정들이었다. 같은 날 앞서 돌린 P114B 테스트가 남긴 가상 데이터이며, 보존할 데이터는 없었다.
- **TRUNCATE 대상**(기존 테스트들의 합집합, `RESTART IDENTITY CASCADE`)
  - `audit_log`, `auth_session`, `classroom_staff_assignment`, `staff_user`
  - `delivery_attempt`, `delivery_job`, `message_draft`, `message_template`, `makeup_request`
  - `assessment_result`, `assessment`, `enrollment_pause`, `lesson_result`, `lesson`, `enrollment`, `student`, `classroom`
  - `notification_send_attempt`, `parent_notification`, `notification_template`
  - phase7·8 스키마 테스트는 downgrade/upgrade도 한다.
- **실행 후**: `staff_user`·`audit_log`·`student`는 0건이고, revision은 `011_staff_deleted_status`(head)다.

## 9. 호환성

- **스키마·Migration 변경 없음**: `auth_session.last_seen_at`은 기존 컬럼을 쓴다.
- **기존 API 응답 형식 변경 없음**.
- **이미 있던 세션**: 기존 `last_seen_at` 값으로 판정한다. 그래서 적용 시점에 60분 넘게 쓰지 않은 세션은 다음 요청에서 바로 만료되고, 다시 로그인하면 된다.
- **로컬 개발 동작 변경 없음**: development/test 모드는 기존과 똑같이 동작한다. subprocess 기동 테스트로 확인했다.
- **새 401 응답**: 유휴 만료는 새 401을 만든다. 프론트는 이를 받아 로그인 화면으로 돌려보내고, 그 밖의 401과 같은 경로로 처리한다.
- **요청마다 쓰기·commit이 생겼다**: `get_current_principal`이 최대 60초에 한 번 활동 시각을 쓰고 commit한다. 기존 PostgreSQL 회귀 131건이 모두 통과해서 트랜잭션 경계가 바뀐 데 따른 영향은 발견되지 않았다.
- **기존 테스트의 useAuth mock**: `notice`를 선택 필드로 두어 기존 mock을 그대로 쓸 수 있다.

## 10. 미구현·보류

- 코드 저장소를 DB나 Redis로 옮기는 일(워커 여러 개 지원). 스키마 변경 없이 한다는 이번 범위에 맞춰 보류했다.
- 이메일·SMS로 재설정 코드를 보내는 기능. 외부 발송은 범위 밖이다.
- 프론트에서 유휴 만료 전에 미리 경고하거나 남은 시간을 표시하는 기능. 서버 기준 만료만 구현했다.
- 프론트 자동 폴링에 `X-Academy-Background` 붙이기. 현재 폴링이 없어서 해당 없음.
- 비밀번호 규칙 강화(유출 비밀번호 목록, 문자 조합). 12자 이상 규칙만 적용했다.
- **실제 Render 환경 확인**: 11-5에서 한다.

## 11. Phase 11-5 인계

1. 배포 가이드(`docs/deployment/phase11_5_security_deployment_guide.md`) 4절의 환경변수를 설정한다.
   - `ACADEMY_DB_MODE=production`
   - `ACADEMY_DATABASE_URL=…?sslmode=require`(가능하면 `verify-full`)
   - `ACADEMY_ENABLE_DB_APIS=1`, `ACADEMY_COOKIE_SECURE=1`, 정확한 https CORS
   - `ACADEMY_SESSION_IDLE_MINUTES=60`
2. 시작 명령은 `uvicorn app.main:app --host 0.0.0.0 --port $PORT --no-proxy-headers --no-access-log`이다. **워커는 1개**다.
3. `alembic upgrade head`를 실행한 뒤 `bootstrap_admin.py`로 최초 관리자를 만든다. Secret 값은 플랫폼 Secret으로만 다룬다.
4. 가이드 6절 0단계(시작 검증, 유휴 만료)와 1~6단계(프록시·주소 진단)를 실제 환경에서 수행한다.
5. 재배포하면 재설정 코드와 로그인 카운터가 초기화된다는 점을 운영자에게 알린다.

## 12. 남은 위험

- **메모리 저장소**: 재설정 코드는 워커 1개를 전제로 한다. 재시작·재배포하면 사라진다(다시 발급하면 된다). 워커를 늘리면 코드가 동작하지 않는다.
- **유휴 판정 정밀도**: 활동 기록을 60초에 한 번만 쓰므로, 판정 기준(마지막 기록 시각)이 실제 마지막 사용보다 최대 1분 앞설 수 있다.
  - 따라서 세션은 설정보다 **최대 약 1분 일찍** 끝날 수 있다. 설정보다 늦게 허용되는 일은 없다(서버 판정, 경계값 `>=`).
  - 11-4-C에서 바로잡았다. 처음에는 "최대 1분 늦을 수 있다"고 잘못 적었다.
  - 화면은 서버를 미리 확인하지 않는다. 만료 안내는 만료 뒤 첫 API 요청 때 뜨며, 그 전까지 화면에 보이는 정보는 만료 전에 받은 것뿐이다.
- **실제 Render 환경 미검증**: production 시작 검증은 로컬에서 subprocess import로만 모의했다. Render의 환경변수 주입, TLS DB 연결, `0.0.0.0` 바인딩은 11-5에서 확인해야 한다.
- **비밀번호 규칙**: 길이 중심이라 약한 12자 비밀번호(반복 문자 등)는 막지 못한다.

## 판정 — **PASS**

- SEC-04, SEC-05, SEC-10(A·B)을 스키마 변경 없이 구현했다.
- 단위 117건, PostgreSQL 전체 회귀 141건, tsc·oxlint·Ruff가 모두 통과했다.
- 프론트 Vitest의 실패 1건은 이전부터 있던 결함으로 회귀가 아니다.
- 남은 위험(12절)은 배포 단계(11-5)에서 확인할 항목이다. 이번 단계를 막는 문제는 아니다.
- Phase 11-4-C와 11-5는 시작하지 않았다.
