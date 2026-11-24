# Phase 5 인증 초기 화면 INTERNAL_ERROR 진단 및 수정

작성일: 2026-11-12

## 현상

React 앱 최초 마운트에서 로그인 버튼을 누르기 전에 오류 응답이 관찰됐다. React의
`AuthProvider`는 마운트 즉시 `GET /api/auth/me`를 호출해 기존 세션을 확인한다.

## 실제 원인

서버 로그를 동일 조건으로 재현한 결과, `ACADEMY_DATABASE_URL`이 없는 실행 환경에서
`/api/auth/me`의 `get_current_principal()`보다 `get_db()` 의존성이 먼저 초기화됐다.
따라서 세션 cookie가 없는 사용자도 정상 401 검사에 도달하기 전에
`app.db.safety.UnsafeDatabaseError`가 발생했고 전역 오류 경계가 이를 500
`INTERNAL_ERROR`로 일반화했다.

추가로 다음 실행 구성 불일치가 있었다.

- React Vite proxy가 Phase 5 FastAPI가 아닌 기존 Java `127.0.0.1:8080`을 가리켰다.
- 기존 `start-backend.ps1`은 Java 서버를 시작하며 FastAPI DB 환경을 구성하지 않는다.
- 점검 시점 개발 DB는 `002_staff_auth_rbac`이 적용돼 있었지만 ACTIVE ADMIN은 0건이었다.

관리자 계정, 비밀번호, hash, session token, DB credential은 조회하거나 출력하지 않았다.
관리자 수와 상태·schema metadata만 읽었다.

## 변경

1. cookie 존재·길이를 확인하는 `require_session_token` dependency를 DB dependency보다 먼저
   실행한다. cookie가 없으면 DB 초기화 없이 401 `AUTHENTICATION_REQUIRED`를 반환한다.
2. DB가 필요한 로그인 요청에 DB URL이 없으면 내부 내용을 노출하지 않는 503
   `DATABASE_UNAVAILABLE`로 분류한다.
3. Vite 기본 proxy를 FastAPI `127.0.0.1:8000`으로 변경한다.
4. `scripts/start-fastapi.ps1`을 추가했다. 현재 shell의 개발 DB 비밀번호로 URL을 만들고,
   preflight 통과 후에만 FastAPI를 시작한다.
5. preflight는 DB identity, Alembic `002_staff_auth_rbac`, ACTIVE ADMIN 존재 여부만 확인한다.

인증·CSRF·RBAC 검사는 제거하거나 우회하지 않았다.

## 수정 전후

| 흐름 | 수정 전 | 수정 후 |
|---|---|---|
| cookie 없는 `GET /api/auth/me`, DB URL 누락 | 500 INTERNAL_ERROR | 401 AUTHENTICATION_REQUIRED |
| 로그인, DB URL 누락 | 500 INTERNAL_ERROR | 503 DATABASE_UNAVAILABLE |
| React 최초 마운트의 401 | 익명 처리 로직 존재 | 동일 로직 유지, login 화면 표시 테스트 강화 |
| Vite `/api` proxy | Java 8080 | FastAPI 8000 |
| FastAPI 시작 | 수동 환경 설정, 누락 가능 | preflight 후 시작 |

React 화면은 `http://127.0.0.1:5173`에서 연다. `http://127.0.0.1:8000`은 API 서버이며
React 페이지가 아니다.

## 개발 DB 점검

- PostgreSQL readiness: 정상
- DB/user allowlist: `academy_learningops_dev` / 개발 전용 user 일치
- Alembic: `002_staff_auth_rbac`
- ACTIVE ADMIN: 0건
- auth session/audit: 점검 당시 0건

따라서 preflight는 의도대로 서버 시작을 거부한다. 기존 계정을 삭제하거나 비밀번호를 변경하지
않았다. 사용자가 올바른 개발 DB 환경을 설정해 `bootstrap_admin.py`를 성공 실행한 뒤 preflight를
다시 실행해야 한다.

## 회귀 테스트 및 결과

| 검증 | 결과 |
|---|---:|
| Ruff | PASS |
| Python 비DB 전체 | 35 PASS |
| Python PostgreSQL 전체 | 15 PASS |
| cookie 없는 `/api/auth/me` + DB URL 누락 | 401 PASS |
| 로그인 + DB URL 누락 | 안전한 503 PASS |
| 실제 개발 DB 설정의 cookie 없는 `/api/auth/me` | 401 PASS |
| React AuthProvider/ProtectedRoute | 5 PASS |
| React 기존 화면 | 15 PASS |
| React lint | PASS |
| TypeScript + Vite production build | PASS |

Build에는 기존 500 kB 초과 chunk warning이 남지만 이 인증 장애와 무관하며 build는 성공했다.
TestClient의 httpx2 전환 warning도 기존 알려진 항목으로, 불필요한 package update를 하지 않았다.

## 안전한 실행 순서

```powershell
# ACTIVE ADMIN이 0건일 때만 README 절차로 bootstrap을 수행한다.
$env:ACADEMY_BOOTSTRAP_EMAIL = '<admin email>'
$env:ACADEMY_BOOTSTRAP_PASSWORD = '<12자 이상의 local password>'
.\scripts\bootstrap-admin.ps1
Remove-Item Env:ACADEMY_BOOTSTRAP_PASSWORD

# 성공 후 FastAPI를 preflight와 함께 시작한다.
.\scripts\start-fastapi.ps1

# 다른 terminal에서 React를 시작한다.
.\scripts\start-frontend.ps1
```

브라우저 주소는 `http://127.0.0.1:5173/login`이다.
