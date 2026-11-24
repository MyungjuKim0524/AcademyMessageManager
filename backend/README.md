# Academy LearningOps FastAPI Backend

학원 반·학생·수업·출결·성적과 보호자 안내 메시지 업무를 처리하는 FastAPI 백엔드입니다. 직원 인증과 DB API를 제공합니다.

- `GET /api/health`
- `POST /api/messages/preview`
- `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me`
- 학사·성적 안내 API (`/api/classrooms…`, `/api/lessons…`, `/api/notifications…`, `/api/message-operations…`)
- `POST /api/lesson-uploads/preview|confirm` — 주간 엑셀 업로드 (파일 10 MiB, 5,000행, 64열, XLSX 압축 비율 검사: `app/uploads.py`)

**2026-11-20: 구 CSV/XLSX 가져오기(`/api/imports`, `/api/imports/preview|confirm`, `/api/imports/{id}`)를
FastAPI·React에서 제거했습니다.** 주간 엑셀 업로드가 같은 목적을 대신합니다. 전용 테이블
`import_job`·`import_row`·`import_error`는 Alembic `010_drop_legacy_import_tables`로 삭제합니다
(기록이 남아 있으면 삭제를 거부). 개발 DB 적용: `.\scripts\migrate-dev-db.ps1`.
직원 인증·세션·담당 반 권한은 SQLAlchemy/PostgreSQL을 사용합니다.
Kafka와 Redis는 사용하지 않습니다. 클라우드와 유료 외부 서비스는 사용하지 않습니다.

## 준비 및 실행

Python 3.12 이상이 필요합니다.

```powershell
cd D:\refactor\backend-architecture\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

환경변수 이름은 `.env.example`을 참고합니다. React는 소스 변경 없이 실행 shell의 `VITE_API_BASE_URL=http://127.0.0.1:8000`으로 Python API를 선택할 수 있습니다.

인증 기능을 포함한 로컬 개발 실행은 저장소 루트에서 다음 스크립트를 사용한다. 이 스크립트는
DB URL을 현재 PowerShell 환경변수로 구성하고, 개발 DB identity, Alembic revision, ACTIVE
관리자 존재 여부를 확인한 뒤에만 FastAPI를 시작한다. 비밀번호는 출력하지 않는다.

```powershell
.\scripts\start-fastapi.ps1
```

React Vite proxy의 기본 대상은 FastAPI `127.0.0.1:8000`이다.

## 검증

```powershell
ruff check .
pytest
```

메시지 미리보기 계약 fixture(`../tests/fixtures/contract/message-preview-cases.json`)는
`tests/test_contract_fixtures.py`가 검증합니다. Java 레거시 서버와 응답을 비교하던
`scripts/compare_contract.py`는 Java 코드가 이 저장소에 없어 더 이상 실행 대상이 아닙니다(이전 기록용).

## PostgreSQL 개발·테스트 환경

현재 스키마의 ERD는 [`../docs/database/ERD.md`](../docs/database/ERD.md)에 있다. 모델에서 자동 생성하므로, Migration을 추가한 뒤 다시 만든다(DB 연결 불필요).

```powershell
.\.venv\Scripts\python.exe scripts\generate_erd.py           # ERD.md 다시 생성
.\.venv\Scripts\python.exe scripts\generate_erd.py --check   # 최신이 아니면 exit 1
```

API 명세([`../docs/api/README.md`](../docs/api/README.md), `openapi.json`)도 앱에서 자동 생성한다. 라우트·요청·응답 모델을 바꾼 뒤 다시 만든다(DB 연결 불필요).

```powershell
.\.venv\Scripts\python.exe scripts\generate_openapi.py           # docs/api/ 다시 생성
.\.venv\Scripts\python.exe scripts\generate_openapi.py --check   # 최신이 아니면 exit 1
```

Compose는 서로 다른 계정·포트·volume을 사용하는 두 서비스를 실행합니다.

- 개발: `academy_learningops_dev`, `academy_dev`, `127.0.0.1:55431`
- 테스트: `academy_learningops_test`, `academy_test`, `127.0.0.1:55432`

```powershell
cd D:\refactor\backend-architecture
$env:ACADEMY_DEV_DB_PASSWORD = '<local development secret>'
$env:ACADEMY_TEST_DB_PASSWORD = '<different local test secret>'
docker compose -f compose.postgres-test.yml up -d --wait
.\scripts\run-postgres-integration.ps1
docker compose -f compose.postgres-test.yml stop
```

개발 DB에서 FastAPI를 실행할 때는 `.env.example`의 development 값을 사용합니다. 기본
`pytest`는 DB에 연결하지 않으며, 파괴적 통합 테스트는 wrapper가 test service의 label,
DB명, 사용자와 port를 검증한 경우에만 실행됩니다. 개발 DB는 파괴적 테스트 대상으로
허용되지 않습니다.

`stop`은 두 전용 volume을 삭제하지 않습니다. 빈 DB로 다시 검증해야 할 때만 identity를
확인한 후 별도로 volume 재생성을 결정합니다.

비밀번호는 shell 환경변수 또는 Git에서 제외된 로컬 `.env`에만 둡니다. README,
Compose, 테스트 코드에는 실제 값을 기록하지 않으며 두 DB에서 같은 비밀번호를 재사용하지
않습니다.

DB 계층은 동기 SQLAlchemy Session을 사용합니다. API 의존성 `get_db()`는 요청마다
Session을 열고 항상 닫으며, 예외 시 rollback합니다. 정상 쓰기의 transaction 범위와
commit은 application service가 `with session.begin():`으로 한 번만 소유합니다. Router와
Repository는 임의로 commit하지 않습니다. 현재 Phase 1·2 API는 DB 의존성을 주입하지
않으므로 DB 환경변수 없이 계속 동작합니다.

Alembic 기준선 적용에는 고정 allowlist와 일치하는 `ACADEMY_DB_MODE`/URL이 필요하고,
test 모드는 추가로 `ACADEMY_DB_TEST_MODE=1`을 요구합니다. 빈 개발·테스트 DB에는
`alembic upgrade head`로 기준 스키마(`../sql/schema_postgresql.sql`, 첫 Migration `001_java_schema_baseline`)부터 적용합니다. 이미 13개 테이블이 있는 DB는 schema diff를 먼저
검증하고 나서 수동 `alembic stamp 001_java_schema_baseline`을 검토하며, 자동 stamp하지
않습니다.

## 직원 인증과 DB API 제한

DB API와 인증 API는 기본값에서 404 `DB_API_DISABLED`로 차단됩니다. 로컬 개발·테스트(development/test 모드)에서는
다음 조건을 모두 만족시켜 활성화합니다.

- `ACADEMY_ENABLE_DB_APIS=1`
- `ACADEMY_API_HOST=127.0.0.1` 또는 다른 loopback 주소
- `ACADEMY_DB_MODE=development` 또는 `test`
- 해당 모드의 고정 DB명·사용자·host·port allowlist 일치
- test 모드는 추가로 `ACADEMY_DB_TEST_MODE=1`

```powershell
$env:ACADEMY_ENABLE_DB_APIS = '1'
$env:ACADEMY_API_HOST = '127.0.0.1'
$env:ACADEMY_DB_MODE = 'development'
$encoded = [uri]::EscapeDataString($env:ACADEMY_DEV_DB_PASSWORD)
$env:ACADEMY_DATABASE_URL = "postgresql+psycopg://academy_dev:$encoded@127.0.0.1:55431/academy_learningops_dev"
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

development/test 모드에서는 `0.0.0.0` 등 외부 바인딩이면 활성화 설정이 있어도 DB API가 차단됩니다.
배포용 `ACADEMY_DB_MODE=production`은 루프백 검사를 하지 않는 대신, 시작할 때 설정(`ACADEMY_ENABLE_DB_APIS=1`,
`sslmode`가 있는 운영 DB URL, `ACADEMY_COOKIE_SECURE=1`, 정확한 https CORS 등)을 검증하고 하나라도 어기면
시작하지 않습니다(`app/config.py::production_problems`). 자세한 내용은
[보안 배포 설정 가이드](../docs/deployment/phase11_5_security_deployment_guide.md)를 참고합니다. 이 gate와 별도로
server-side session 인증과 DB 기반 RBAC를 적용합니다(`app/modules/auth/dependencies.py`).

- 역할은 `ADMIN`, `TEACHER`, `ASSISTANT` 세 가지이며, 권한은 화면이 아니라 서버가 판정합니다.
- 직원 계정·반·학생·연락처 관리와 담당 반 배정: ADMIN만 가능합니다(`require_admin`, 쓰기는 `require_admin_csrf`).
- 수업·출결·성적, 엑셀 업로드, 안내 메시지: ADMIN은 전체 반, TEACHER/ASSISTANT는 배정 기간이
  유효한 담당 반만 접근합니다(`require_classroom_access`). 담당하지 않은 반은 403입니다.
- 상태를 바꾸는 요청(POST·PATCH·DELETE)은 세션과 함께 `X-CSRF-Token` 헤더를 검증합니다(`require_csrf`).
  logout과 비밀번호 변경도 포함됩니다. 세션이 없는 로그인·비밀번호 재설정은 JSON 본문만 받고 허용된
  Origin만 통과시켜 CSRF를 막습니다.
- 조회 전용 분석 API(GET)는 CSRF 없이 세션과 담당 반 범위만 검사합니다.

### 최초 로컬 관리자 생성

실제 비밀번호를 파일이나 명령 기록에 남기지 말고 현재 PowerShell 환경변수로만 전달합니다.
스크립트는 기존 계정을 덮어쓰지 않습니다.

```powershell
$env:ACADEMY_BOOTSTRAP_ADMIN = '1'
$env:ACADEMY_BOOTSTRAP_EMAIL = 'admin@example.invalid'
$env:ACADEMY_BOOTSTRAP_PASSWORD = '<12자 이상의 로컬 전용 비밀번호>'
..\scripts\bootstrap-admin.ps1
Remove-Item Env:ACADEMY_BOOTSTRAP_PASSWORD
Remove-Item Env:ACADEMY_BOOTSTRAP_ADMIN
```

로컬 HTTP에서는 `.env.example`처럼 `ACADEMY_COOKIE_SECURE=0`을 사용한다. HTTPS 환경에서는
기본값 `1`을 유지해야 한다. 로그인 rate limit은 로컬 단일 프로세스 메모리 방식이므로 외부
공개·다중 worker 용도가 아니다.

비용 정책과 전체 보안 검증 결과는
[`docs/archive/phases/phase5-auth-rbac-implementation.md`](../docs/archive/phases/phase5-auth-rbac-implementation.md)를 참고한다.

