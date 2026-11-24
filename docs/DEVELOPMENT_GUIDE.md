# 개발 가이드 (로컬 환경·테스트·개발 정책)

이 문서는 저장소를 직접 실행·수정하는 개발자를 위한 안내다. 프로젝트 소개는 [README](../README.md)를 본다.

## 1. 준비물

- Python 3.12 이상, Node.js(로컬 검증 24.x)와 npm
- Docker Desktop(PostgreSQL 17.6 컨테이너)
- Windows PowerShell 기준으로 스크립트를 작성했다(`scripts/*.ps1`).

설치·환경변수:
- 백엔드: [`backend/README.md`](../backend/README.md), `backend/.env.example`
- 프론트엔드: [`frontend/README.md`](../frontend/README.md), `frontend/.env.example`

## 2. 로컬 데이터 위치 정책

pip·npm·Ruff·pytest 캐시, coverage, 임시 파일은 프로젝트 안의 `.dev-data/`에 모은다(Git 제외).
테스트나 의존성 명령 전에 아래 스크립트를 현재 PowerShell 세션에만 dot-source한다. 사용자·시스템 전역 환경변수는 바꾸지 않는다.

```powershell
. .\scripts\use-d-drive-dev-env.ps1
```

- 이미 정상 동작하는 가상환경(`backend/.venv`)과 `node_modules`는 다시 설치하지 않는다.
- Docker 컨테이너·볼륨·디스크 이미지는 검증 작업 중에 옮기거나 지우거나 초기화하지 않는다. Docker 데이터 위치는 각자의 PC 설정을 따른다.

## 3. 로컬 DB와 실행

PostgreSQL은 서로 분리된 두 컨테이너를 쓴다(`compose.postgres-test.yml`).

| 용도 | 컨테이너 | 주소 | DB·사용자 | 파괴적 테스트 |
|---|---|---|---|---|
| 개발 | `academy-learningops-postgres-dev` | `127.0.0.1:55431` | `academy_learningops_dev` / `academy_dev` | 금지 |
| 테스트 | `academy-learningops-postgres-test` | `127.0.0.1:55432` | `academy_learningops_test` / `academy_test` | 허용 |

처음 한 번은 의존성을 설치하고 두 컨테이너를 만든다(저장소 루트 기준).

```powershell
# 의존성
cd backend; python -m venv .venv; .\.venv\Scripts\python.exe -m pip install -e ".[dev]"; cd ..
cd frontend; npm ci; cd ..

# DB 컨테이너: compose 파일이 두 비밀번호를 모두 요구한다. 값은 현재 세션에만 둔다.
$env:ACADEMY_DEV_DB_PASSWORD = '<로컬 개발 DB 비밀번호>'
$env:ACADEMY_TEST_DB_PASSWORD = '<다른 로컬 테스트 DB 비밀번호>'
docker compose -f compose.postgres-test.yml up -d --wait
Remove-Item Env:ACADEMY_DEV_DB_PASSWORD, Env:ACADEMY_TEST_DB_PASSWORD
```

- 컨테이너를 만든 뒤에는 아래 스크립트가 비밀번호를 컨테이너 설정에서 읽으므로 다시 입력하지 않는다.
- 멈출 때는 `docker compose -f compose.postgres-test.yml stop`을 쓴다. `stop`은 볼륨을 지우지 않는다.

```powershell
.\scripts\migrate-dev-db.ps1    # 개발 DB에 Alembic Migration 적용(사전 백업 권장)
.\scripts\bootstrap-admin.ps1   # 최초 관리자 생성(ACADEMY_BOOTSTRAP_EMAIL·PASSWORD를 현재 세션에만 설정)
.\scripts\start-fastapi.ps1     # FastAPI 127.0.0.1:8000
.\scripts\start-frontend.ps1    # React(Vite) 127.0.0.1:5173, /api는 FastAPI로 proxy
```

- 각 스크립트는 개발 DB 컨테이너의 라벨·포트를 확인한 뒤에만 실행되고, DB 비밀번호를 출력하지 않는다.
- `start-fastapi.ps1`은 시작 전에 사전 점검(`backend/scripts/auth_preflight.py`)을 한다. 점검 항목은 DB 정체, **Alembic revision이 코드의 head와 같은지**, 활성 관리자 존재다.
  - 새 Migration을 받은 뒤 `migrate-dev-db.ps1`을 실행하지 않으면 "Alembic head … is not applied" 오류로 멈춘다.
  - 개발 DB에는 Migration을 자동으로 적용하지 않는다. 적용 전에 백업한다(`docs/DEVELOPMENT_HISTORY.md` 3절 "개발 DB Migration 011 적용" 사례).

## 4. 테스트

```powershell
. .\scripts\use-d-drive-dev-env.ps1

# 한 번에(DB 불필요): Ruff → pytest(DB 없는 테스트) → lint → Vitest → build
.\scripts\verify-all.ps1

# 개별 실행
cd backend
.\.venv\Scripts\pytest.exe -m "not postgres"
.\.venv\Scripts\ruff.exe check .
cd ..\frontend
npm run lint
npm test
npm run build
```

**PostgreSQL 통합 테스트**는 격리 테스트 DB에서만 실행한다.
- 일부 테스트가 테이블을 `TRUNCATE`하므로, 테스트 DB 외에는 절대 실행하지 않는다.
- 실행 스크립트가 컨테이너 라벨(`academy.environment=isolated-test`)·포트·DB 이름·사용자를 확인하고, 하나라도 다르면 실행을 거부한다.

```powershell
$env:ACADEMY_TEST_DB_PASSWORD = '<로컬 테스트 DB 비밀번호>'   # 현재 세션에만
.\scripts\run-postgres-integration.ps1
Remove-Item Env:ACADEMY_TEST_DB_PASSWORD
```

- 전체 Vitest는 수 분(약 7~10분) 걸린다. 수정 중에는 영향받는 폴더만 실행하고, 마지막에 전체를 한 번 실행한다.
- 커버리지는 측정하지 않는다(도구 미설치). 테스트 수치의 의미는 `docs/DEVELOPMENT_HISTORY.md` 9.8절을 본다.

## 5. 스키마 변경

- 스키마는 Alembic Migration(`backend/alembic/versions/`)으로만 바꾼다.
- Migration을 추가한 뒤에는 ERD를 다시 만든다.

  ```powershell
  cd backend
  .\.venv\Scripts\python.exe scripts\generate_erd.py           # docs/database/ERD.md 갱신
  .\.venv\Scripts\python.exe scripts\generate_erd.py --check   # 최신이 아니면 exit 1
  ```
- API(라우트·요청·응답 모델)를 바꾼 뒤에는 API 명세를 다시 만든다.

  ```powershell
  cd backend
  .\.venv\Scripts\python.exe scripts\generate_openapi.py           # docs/api/openapi.json·README.md 갱신
  .\.venv\Scripts\python.exe scripts\generate_openapi.py --check   # 최신이 아니면 exit 1
  ```
- 첫 Migration `001`은 저장소 루트의 `sql/schema_postgresql.sql`을 읽는다. `007`은 `btree_gist` 확장을 만든다. 운영 DB 적용 시 주의점은 [배포 가이드](deployment/phase11_5_security_deployment_guide.md) 4절에 있다.

## 6. 개발 비용·외부 연동 정책

- 개인 학습·포트폴리오 목적이라 로컬 환경과 무료 오픈소스를 기본으로 쓴다. 배포는 무료 플랜(Neon·Render·Vercel)을 전제로 한다.
- 실제 이메일·SMS는 보내지 않는다. 발송은 `MockSender`만 쓴다(`backend/app/modules/notifications/sender.py`).
- 실제 발송(SMS/LMS)으로 바꾸기 전에는 외부 발송 I/O와 DB 트랜잭션을 분리해야 한다(INT-I1). 자세한 내용은 [Development History 8절](DEVELOPMENT_HISTORY.md#8-future-roadmap)에 있다.
- AI 코딩 도구 사용량과 계정 과금은 저장소로 통제할 수 없으므로 개발자가 직접 확인한다.

## 7. 데이터·비밀정보 원칙

- 샘플 데이터(`data/sample_students.*`, `tests/fixtures/`, `sql/seed_postgresql.sql`)는 모두 가상 데이터다. `example.invalid` 같은 예약 도메인을 쓴다.
- 실제 학생·보호자 정보와 DB 덤프는 저장소에 넣지 않는다. `.gitignore`가 덤프·`.env`·로컬 DB·`.dev-data/`를 제외한다.
- 비밀번호·토큰은 현재 셸의 환경변수로만 넘기고, 파일·로그·명령 기록에 남기지 않는다.
- 실제 운영 시에는 메시지 본문과 보호자 연락처에 대한 보존 기간, 접근 권한, 삭제 절차를 따로 정해야 한다.
