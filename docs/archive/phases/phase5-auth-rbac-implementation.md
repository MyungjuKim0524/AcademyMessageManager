# Phase 5: 인증·RBAC 안정화 결과

작성일: 2026-11-12  
범위: 로컬 개발 환경, 무료 오픈소스, 직원 인증만

## 1. 완료 범위

### 구현 사실

- `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me`
- ADMIN, TEACHER, ASSISTANT 직원 계정과 ACTIVE/INACTIVE 상태
- Argon2id 비밀번호 hash, 불투명 server-side session, digest-only 저장
- HttpOnly/SameSite session cookie, 환경별 Secure cookie, double-submit CSRF
- 로그인 실패 동일 응답과 IP·IP/email 단위 로컬 rate limit
- 전체 업무 API 인증, Import History/Confirm ADMIN 제한
- Message/Import Preview의 교사·조교 담당 반 제한
- 로그인·로그아웃 audit와 session revoke/expiry 검사
- React 로그인, 인증 상태, 보호 route, 역할별 메뉴, 401/403 처리
- additive Alembic `002_staff_auth_rbac`

학생 로그인, 비밀번호 재설정, 계정 관리 UI, 외부 공개 배포는 구현하지 않았다.

## 2. 비용 0원 원칙 점검

FastAPI, Pydantic, SQLAlchemy, Alembic, Argon2-cffi, PostgreSQL, React와 Docker Desktop의
기존 로컬 설치만 사용했다. AWS/GCP/Azure, 외부 인증 SaaS, 유료 API, 외부 DB, 보안·모니터링
서비스를 생성하지 않았다. 이메일·SMS 발송을 추가하지 않았으며 향후 테스트는 Mock adapter만
사용한다. Codex 모델 사용량과 계정 과금은 저장소 설정으로 통제할 수 없으므로 사용자가 Codex
계정의 사용량·결제 설정을 직접 확인해야 한다.

## 3. 권한 정책

| API | ADMIN | TEACHER | ASSISTANT |
|---|---:|---:|---:|
| Health | 허용 | 허용 | 허용 |
| Message Preview | 전체 반 | 담당 반 | 담당 반 |
| Import Preview | 전체 반 | 파일 내 모든 행이 담당 반일 때 | 파일 내 모든 행이 담당 반일 때 |
| Import History/Detail | 허용 | 거부 | 거부 |
| Import Confirm | CSRF 포함 허용 | 거부 | 거부 |

권한은 cookie의 server-side session과 DB role/배정으로 판정한다. `X-Role` 같은 클라이언트 값은
무시한다. 배정은 `valid_from <= 오늘 <= valid_to`이고 활성 반이며 assignment role과 계정 role이
일치해야 한다.

## 4. DB 변경과 데이터 보호

`staff_user`, `classroom_staff_assignment`, `auth_session`, `audit_log` 네 테이블만 추가했다.
기존 13개 테이블은 삭제·재생성하지 않았다. 테스트 DB에 먼저 적용하고 PostgreSQL 통합 테스트를
통과한 뒤 개발 DB에 적용했다.

- 개발 DB 적용 전 기존 13개 테이블 행 수: 모두 0
- 백업: `data/backups/academy_learningops_dev_before_002_20261112.dump` (Git 제외)
- 백업 크기: 58,674 bytes
- SHA-256: `F8CF9570579E3F38837B816DCB5479FCE8E4B49C6BB4C2A925E07A2671570A9F`
- 개발·테스트 Alembic revision: `002_staff_auth_rbac`
- `alembic check`: 새 upgrade operation 없음

Rollback은 데이터 보존 판단 없이 `alembic downgrade`를 실행하지 않는다. 문제가 생기면 앱을 이전
버전으로 내리고 위 dump를 별도 빈 DB에 restore 검증한 뒤 복구한다.

## 5. 검증 결과

| 검증 | 결과 | 근거 |
|---|---:|---|
| Phase 4 사전 gate | PASS | Java/Python Confirm, replay, History, detail, error 계약 일치 |
| Python Ruff | PASS | `ruff check .` |
| Python 비DB 회귀 | 33 PASS | `pytest -m "not postgres"` |
| Python PostgreSQL | 15 PASS | 격리 test DB 전체 재실행 |
| 인증/RBAC 보안 | 5 PASS | session fixation, enumeration, rate limit, expiry, Secure cookie, CSRF, role/scope |
| Java 전체 | 47 PASS | DB 통합 5개 포함, failure/error/skip 0 |
| React 인증 테스트 | 5 PASS | AuthProvider, ProtectedRoute |
| React 기존 화면 | 15 PASS | Import/Message/History/route/validation |
| React lint | PASS | `oxlint src` |
| React production build | PASS | TypeScript + Vite, 3,284 modules |

ASSISTANT 담당 반 범위와 Secure cookie 설정까지 최종 통합 테스트에 포함했다. Vite build에는
500 kB 초과 chunk 경고가 남지만 build 실패는 아니며,
권한 기능 정확도와 무관한 후속 성능 개선 항목이다. jsdom의 pseudo-element 경고도 테스트 환경
제약이며 assertion 실패는 없었다.

## 6. 로컬 실행

`.env.example`을 참고해 실제 비밀은 현재 shell 또는 Git 제외 `.env`에만 둔다. 개발 DB에는
아직 관리자 계정을 임의 생성하지 않았다. 사용자가 로컬 비밀번호를 정한 뒤 다음처럼 한 번만
부트스트랩한다.

```powershell
$env:ACADEMY_BOOTSTRAP_ADMIN='1'
$env:ACADEMY_BOOTSTRAP_EMAIL='admin@example.invalid'
$env:ACADEMY_BOOTSTRAP_PASSWORD='<12자 이상의 로컬 전용 비밀번호>'
python scripts/bootstrap_admin.py
Remove-Item Env:ACADEMY_BOOTSTRAP_PASSWORD
```

스크립트는 기존 email을 덮어쓰지 않고 ADMIN만 생성하며 비밀번호를 출력하지 않는다. 실행 후
`ACADEMY_BOOTSTRAP_ADMIN`도 제거한다. 실제 사용자 email은 테스트 fixture에 사용하지 않는다.

## 7. 남은 위험과 우선순위

1. 로그인 rate limiter는 단일 프로세스 메모리 방식이다. 로컬 포트폴리오 범위에는 충분하지만
   다중 worker·외부 공개에는 적합하지 않다.
2. HTTPS가 없는 로컬 HTTP에서는 `ACADEMY_COOKIE_SECURE=0`이 필요하다. 외부 공개 환경에서는
   반드시 HTTPS와 Secure cookie가 필요하지만 이번 범위에서는 배포하지 않는다.
3. 계정 생성/비활성화/반 배정 UI가 없다. 다음 vertical slice는 ADMIN 전용 직원 관리 API와
   최소 UI가 적합하다.
4. Vite 큰 chunk와 Vitest 초기화 시간이 길다. 기능 안정화 후 route/library code splitting을
   측정 기반으로 다룬다.
5. FastAPI TestClient가 httpx2 전환을 알리는 deprecation warning을 낸다. 현재 동작에는 영향이
   없고 불필요한 package update 금지 원칙에 따라 이번 단계에서 갱신하지 않았다.

## 8. Phase 6

Kafka와 학습 분석은 구현하지 않고 설계만 작성했다.

- [이벤트 아키텍처 설계](phase6-event-architecture-design.md)
- [학습 분석 설계](phase6-learning-analytics-design.md)
