# Phase 11-4 릴리스 준비도 · 배포 인계 (11-4-A · B · C)

작업일: 2026-11-21 · 대상: Phase 11-5(GitHub → Supabase → Render → Vercel)를 직접 수행하는 사람
근거 문서: `phase11_2_*`, `phase11_3_integrity_audit.md`, `phase11_3_integrity_remediation.md`, `phase11_4_a_performance_results.md`, `phase11_4_b_runtime_account_results.md`, `docs/deployment/phase11_5_security_deployment_guide.md`

**이 문서는 로컬 코드와 로컬 테스트로 확인한 사실만 PASS로 적는다.** Render·Vercel·Supabase에서는 아무것도 실행하지 않았다. 클라우드 항목은 모두 "배포 시 확인"으로 남긴다. 비밀번호·키·토큰 값은 이 문서에 없다.

표기
- ✅ 로컬에서 실행해 확인
- 🔎 코드·설정 파일을 읽어 확인
- ☁️ 배포 환경에서 확인 필요
- ⏭ 향후 고도화
- ⛔ 배포 차단

---

## 최종 판정 (요약)

| 구분 | 판정 |
|---|---|
| **로컬 코드 기준** | **READY**: 자동 테스트 전부와 Production Build가 통과했다. 알려진 Critical·High 결함은 없다. |
| **배포 전체** | **CONDITIONALLY READY**: 클라우드 환경 확인 항목(12절 ☁️)이 남아 있다. 각 항목의 영향·완화 방법·확인 시점은 12절에 적었다. |
| 미해결 배포 차단 결함 | **없음** |

---

## 1. Phase 11-4-A · B · C 결과 요약

| 단계 | 내용 | 결과 |
|---|---|---|
| 11-4-A 성능·예외 처리 | 일괄 처리 쿼리 증폭 제거(PERF-01), 진도표 단일 조회(PERF-02), 업로드 본문 선형 버퍼링(RES-01), DB 연결 `connect_timeout=5`(RES-02), DB 장애 → 503 `DATABASE_UNAVAILABLE`, 잠금 충돌 → 409 `TRANSACTION_CONFLICT`(ERR-01·02) | PASS(기존 문서) |
| 11-4-B 실행 모드·계정 보안 | `ACADEMY_DB_MODE=production`과 시작 시 설정 검증(SEC-04), 서버 기준 유휴 세션 만료(SEC-05), 비밀번호 변경과 관리자 발급 일회용 재설정 코드(SEC-10) | PASS(기존 문서) |
| 11-4-C 회귀·릴리스 준비 | 기존 프론트 테스트 실패 1건 원인 해결, 모의 발송 문구 1곳 정정, 11-4-B 문서의 유휴 만료 오차 방향 정정, 배포 준비도 점검 | 이 문서 |

**11-4-C 코드·문서 변경**(DB 스키마·Migration·백엔드 코드 변경 없음)
- 원본 백업: `.dev-data/backups/phase114c-20261121-190341/`

| 파일 | 변경 | 이유 |
|---|---|---|
| `frontend/src/features/notifications/NotificationsPage.test.tsx` | 시간대 체크박스를 "체크될 때까지만" 클릭하도록 수정 | 2절 |
| `frontend/src/features/notifications/BatchReview.tsx` | 집계 문구 `발송 실패`/`발송 완료` → `모의 발송 실패`/`모의 발송 완료` | 실제 발송 성공으로 오인될 수 있는 유일한 문구(Stage 4.5-C) |
| `docs/reviews/phase11_4_b_runtime_account_results.md`, `docs/deployment/phase11_5_security_deployment_guide.md` | "유휴 만료가 최대 1분 **늦을** 수 있다" → "최대 1분 **일찍** 끝날 수 있다, 늦게 허용되는 일은 없다" | 4.5-B 검증 결과 방향이 반대였다 |

## 2. 수정한 프론트엔드 테스트와 원인

**대상**: `NotificationsPage > uploads only the chosen time slot and reports rows already equal to the app as skipped`
- 11-4-B까지 계속 실패하던 테스트다. 단독 실행에서도 매번 실패했다(결정적 실패).

**증상**: 시간대 체크박스를 클릭한 직후 체크 상태가 `false`로 남는다. 그래서 '미리보기' 버튼이 계속 비활성이다.

**원인 — 분류 4: 비동기 상태 처리·타이밍**
- antd 6.6.5의 `Checkbox.Group`은 각 옵션 값을 렌더 뒤 effect(`registerValue`)로 등록한다.
- `toggleOption`은 `onChange`에 넘길 값에서 **등록되지 않은 값을 걸러낸다**(`node_modules/antd/es/checkbox/Group.js`).
- 테스트는 시트 목록이 그려진 바로 그 순간, 등록 effect가 반영되기 전에 클릭했다. 그래서 `onChange([])`가 호출됐다.
- 클릭 뒤 200ms를 기다리면 통과하는 것을 확인해 원인을 확정했다(진단용 코드는 제거했다).

**실제 기능 결함이 아니라고 본 근거**
- 등록은 같은 렌더 주기 안에 끝난다. 사람은 옵션이 화면에 나타난 그 프레임 안에 클릭할 수 없다.
- 컴포넌트(`UploadTab.tsx`)의 선택·활성 조건(`!file || !lessonDate || busy || sheetsLoading || selectedSheets.length === 0`)은 정상이다.

**수정**: 아직 체크되지 않았을 때만 다시 클릭하고, 체크될 때까지 `waitFor`로 기다린다.
- 테스트의 기대값은 그대로다. 미리보기 요청 인자 `['2시']`, 변경 없음 행 표시, 확정 인자를 모두 그대로 검증한다.
- 삭제하거나 skip한 테스트는 없다.
- 6가지 분류 중 나머지(실제 기능 결함, API 계약 변경, 오래된 Fixture, 환경·의존성, 11-4-B 회귀)에 해당하는 실패는 없었다.

## 3. 전체 테스트 실행 결과 (2026-11-21)

| 범위 | 명령 | 결과 |
|---|---|---|
| ✅ 백엔드 단위 | `pytest -m "not postgres"` | **117 passed** |
| ✅ Ruff | `ruff check .` | **PASS** |
| ✅ PostgreSQL 전체 회귀(TRUNCATE 포함) | `pytest -m postgres` | **141 passed, 0 failed, 0 skipped**(4분 46초). 11-4-B 마지막 백엔드 변경 뒤 사용자 조건부 승인으로 실행. 11-4-C에서는 백엔드 코드를 바꾸지 않았다 |
| ✅ PostgreSQL 비파괴 회귀(11-4-C 재실행) | 동시성 11-3, 11-4-A, 11-4-B 모듈 | **36 passed** |
| ✅ 인증·세션·CSRF·RBAC | 위 PostgreSQL 전체 회귀에 포함 | 포함 PASS |
| ✅ 프론트 Vitest 전체 | `npx vitest run --maxWorkers=2` | **15파일 113 passed, 0 failed** |
| ✅ 문구 수정 뒤 영향 폴더 | `features/notifications`, `message-operations`, `dashboard` | **42 passed** |
| ✅ 타입 검사 | `tsc -b` | **PASS** |
| ✅ oxlint | `npx oxlint src` | **PASS** |
| ✅ Production Build | `npm run build`(`tsc -b && vite build`) | **PASS** |
| — Browser E2E | — | **미실행**. 자동화 환경(Playwright 등)이 없어서 새로 설치하지 않았다. 11절의 수동 시나리오로 대신한다 |
| — Java(legacy) 테스트 | `mvn test` | **미실행**. 배포 대상이 아니다(9절 참고). 2026-11-21부터 Java는 저장소에서 제외했다 |

**PostgreSQL 전체 회귀 격리 확인**(11-4-B 결과 문서 8절과 같다)
- 컨테이너 `academy-learningops-postgres-test`, 라벨 `isolated-test`/`allowed`, `127.0.0.1:55432`, `academy_learningops_test|academy_test`, 테스트 전용 볼륨
- 실행 전 데이터는 `p114b…@example.invalid` 가상 데이터뿐이었다.
- 개발 DB와 `academy-postgres`는 꺼진 상태로 두었고 접근하지 않았다. 실제 개인정보와 외부 발송은 쓰지 않았다.

**Stage 2 주요 흐름별 자동 테스트**(Vitest 113건)
- 각 흐름은 아래 테스트로 확인했다. 실제 브라우저 확인은 11절 체크리스트로 남긴다.

| 흐름 | 테스트 파일(건수) |
|---|---|
| 로그인·로그아웃, 유휴 만료 안내, 재설정 폼 | `auth/LoginPage`(5), `auth/AuthProvider`(3), `auth/ProtectedRoute`(3) |
| 비밀번호 변경·재설정 코드 발급 | `layout/AppLayout`(3), `staff/StaffManagementPage`(5) |
| 직원·학생·반 관리 | `staff`(5), `learningops/LearningOpsPage`(10), `learningops/api.test.ts` |
| Excel 업로드 미리보기·확정, 메시지 생성·검토·확정·모의 발송 | `notifications/NotificationsPage`(23) |
| 수업·출결·성적 입력 | `classwork/ClassworkPage`(16) |
| 실패·재시도 | `message-operations/MessageOperationsPage`(12) |
| 분석 | `analytics/AnalyticsPage`(8) |
| 대시보드 | `dashboard/DashboardPage`(7) |

- **권한**
  - 메뉴 숨김·`ProtectedRoute`는 화면 편의일 뿐이다.
  - 실제 권한은 서버가 판정한다. 직원·반 생성/수정/삭제·학생 연락처 API는 `require_admin`/`require_admin_csrf`, 반 데이터는 `require_classroom_access`가 막는다(🔎 `learningops/router.py`).
  - 서버 권한 판정은 PostgreSQL RBAC 회귀로 확인했다(✅).

## 4. Backend · Frontend 빌드 상태

| 항목 | 상태 | 근거 |
|---|---|---|
| Python | 🔎 `requires-python = ">=3.12"`. 로컬 3.12.10으로 검증 | `backend/pyproject.toml` |
| 의존성 | ✅ 고정 버전 10개가 설치본과 모두 일치, `pip check` 이상 없음 | fastapi 0.162.0, uvicorn 0.54.0, SQLAlchemy 2.1.8, psycopg[binary] 3.3.8, alembic 1.20.1, pydantic 2.14.2, argon2-cffi 25.1.0, openpyxl 3.1.5, defusedxml 0.7.1, python-multipart 0.0.33 |
| 설치 방법 | 🔎 `backend`에서 `pip install .`(hatchling, `packages=["app"]`). `requirements.txt`는 없다 | ☁️ Render 빌드에서 확인 |
| 엔트리포인트 | 🔎 `app.main:app` | `backend/app/main.py` |
| Health Check | ✅ `GET /api/health` → `{"status":"UP"}`. DB에 접근하지 않는다 | 11-4-B 단위 테스트(production 프로세스 기동 + `/health`) |
| production 시작 검증 | ✅ 안전하지 않은 설정이면 시작을 거부하고, 오류에는 설정 이름만 나온다 | 11-4-B subprocess 테스트 3건 |
| Node | 🔎 `engines`·`.nvmrc` 없음. 로컬 v24.11.1, npm 11.6.2로 빌드 | ☁️ Vercel Node 버전 지정 |
| 패키지 매니저 | 🔎 npm, `frontend/package-lock.json` | `npm ci` 권장 |
| Vite 빌드 | ✅ `dist/` 생성 | `ApiClientError-*.js` 청크가 662kB(gzip 216kB)라 500kB 경고가 나온다. 기능에는 영향 없음(⏭ 코드 분할) |

## 5. 실행 명령과 환경변수 이름

**Backend 시작**(Render Start Command, 워커 1)
```
uvicorn app.main:app --host 0.0.0.0 --port $PORT --no-proxy-headers --no-access-log
```

**Migration**(운영 환경변수를 설정한 셸에서 `backend` 디렉터리 기준, `alembic.ini` 위치)
```
alembic upgrade head
```
- 최신 revision은 `011_staff_deleted_status`다(🔎 `backend/alembic/versions/` 001~011, ✅ 테스트 DB에서 head 확인).
- `alembic/env.py`도 앱과 같은 `require_database_url` 검사를 거친다. 그래서 production 모드에서는 TLS가 없는 URL이나 로컬 DB를 거부한다.
- **(2026-11-22 추가)** 001은 저장소 루트의 `sql/schema_postgresql.sql`을 읽으므로 **저장소 전체가 있는 위치**에서 실행해야 한다. 007은 `CREATE EXTENSION IF NOT EXISTS btree_gist`를 실행하므로 **확장을 만들 권한**이 필요하다. 상세는 배포 가이드 4절 "DB 마이그레이션".

**최초 관리자**(한 번만. 값은 셸에서만 입력하고 기록하지 않는다)
```
ACADEMY_BOOTSTRAP_ADMIN=1 ACADEMY_BOOTSTRAP_EMAIL=<…> ACADEMY_BOOTSTRAP_PASSWORD=<12자 이상> python scripts/bootstrap_admin.py
```

**Backend 환경변수**(🔎 `app/config.py`, `app/db/safety.py`)

| 이름 | 운영 값 | 필수 |
|---|---|---|
| `ACADEMY_DB_MODE` | `production` | 필수 |
| `ACADEMY_DATABASE_URL` | `postgresql+psycopg://…?sslmode=require`(또는 `verify-ca`/`verify-full`) | 필수, Secret |
| `ACADEMY_ENABLE_DB_APIS` | `1` | 필수 |
| `ACADEMY_COOKIE_SECURE` | `1`(기본값도 1) | 0 금지 |
| `ACADEMY_CORS_ORIGINS` | `https://<Vercel 운영 도메인>` | 필수 |
| `ACADEMY_SESSION_TTL_MINUTES` / `ACADEMY_SESSION_IDLE_MINUTES` | `480` / `60` | 기본값 사용 가능 |
| `ACADEMY_LOGIN_ATTEMPT_LIMIT` / `_IP_ATTEMPT_LIMIT` / `_ACCOUNT_ATTEMPT_LIMIT` / `_WINDOW_SECONDS` | 5 / 20 / 20 / 900 | 기본값 |
| `ACADEMY_EDGE_SECRET`, `ACADEMY_EDGE_SECRET_HEADER` | 48자 이상 무작위 / 기본 `x-academy-edge-secret` | 구성 A, Secret |
| `ACADEMY_CLIENT_IP_HEADER` | `cf-connecting-ip` | 가이드 2절 |
| `ACADEMY_TRUSTED_PROXIES` | 비움 | `/0` 금지 |
| `ACADEMY_PROXY_DIAGNOSTICS` | `0`(점검할 때만 1) | |
| `ACADEMY_API_DOCS` / `ACADEMY_HSTS_MAX_AGE` | `0` / 가이드 5절 | |
| `ACADEMY_LOG_LEVEL` | `INFO` | |
| `ACADEMY_SESSION_COOKIE` / `ACADEMY_CSRF_COOKIE` | 기본 `academy_session` / `academy_csrf` | CSRF 쿠키 이름은 바꾸지 않는다 |
| 설정 금지 | `ACADEMY_DB_TEST_MODE`, `ACADEMY_RUN_POSTGRES_INTEGRATION` | 있으면 시작 실패 |

- `postgresql://`(드라이버 생략) 형식도 동작한다. SQLAlchemy 2.1의 기본 PostgreSQL 드라이버가 psycopg 3이기 때문이다(✅ 로컬 확인. `psycopg2`는 설치되어 있지 않다).
- **세션 서명 Secret은 없다.** 세션·CSRF 토큰은 `secrets.token_urlsafe(32)`로 만들고, DB에는 SHA-256 다이제스트만 저장한다(🔎 `auth/service.py`). 그래서 Secret 회전 절차가 필요 없다.

**Frontend 환경변수**(🔎 `frontend/src/shared/api/client.ts`)
- `VITE_API_BASE_URL`: **비워 둔다**. 같은 출처의 `/api`로 호출한다.
- `VITE_CSRF_COOKIE`: 기본 `academy_csrf`. 백엔드 `ACADEMY_CSRF_COOKIE`와 같아야 한다.

## 6. GitHub 업로드 전 비밀정보 점검

✅ 로컬 점검 결과
- 저장소 안(`node_modules`·`.venv`·`.dev-data`·`dist`·`target` 제외)에서 하드코딩된 비밀번호·키·토큰을 찾지 못했다.
  - README의 `YOUR_DB_PASSWORD`와 테스트의 가상 이메일 상수는 자리표시자다.
- `.env`, `config.properties`, `*.pem`, `*.key`, `credentials.json` 파일이 없다.
- `compose.postgres-test.yml`은 비밀번호를 `${ACADEMY_*_DB_PASSWORD:?…}` 환경변수로만 받는다.
- 앱 코드에 개발 DB 주소(55431)가 있는 곳은 허용 목록 상수(`ALLOWED_DATABASES`)뿐이다. production 모드에서는 이 주소를 **거부**하는 데 쓰인다.
- 샘플 데이터(`data/sample_students.*`, `.dev-data/samples/`)는 가상 이름과 `example.invalid` 주소만 쓴다.

**`.gitignore`로 제외되는지 첫 커밋 전에 `git status`로 꼭 확인할 것**

| 경로 | 이유 |
|---|---|
| `.dev-data/` | 캐시, 테스트 로그, 백업 |
| `data/backups/*.dump` | **개발 DB 덤프. 실제 데이터가 들어 있을 수 있다** |
| `backend/.venv/`, `frontend/node_modules/`, `frontend/dist/`, `target/` | 생성물 |
| `.env`, `.env.*`(`.env.example` 제외) | 비밀값 |
| `.ruff_cache/`, `frontend/.ruff_cache/`, `backend/refactorbackend-architecture.dev-datapytest-cache/` | 루트 `.gitignore`에는 없지만 폴더 안에 `*` `.gitignore`가 있어 제외된다. 마지막 폴더는 예전에 경로가 잘못 합쳐져 생긴 pytest 캐시라 지워도 된다 |

- Java legacy 앱(`src/`, `pom.xml`)에는 실제 SMTP 발송 코드(`EmailSendService.java`)가 있다.
  - 배포 대상이 아니고, 설정 파일 `config.properties`는 `.gitignore`로 제외된다.
  - `config.properties.example`에는 SMTP 호스트·포트만 있다.

> **2026-11-21 후속 반영(Phase 11-5 Step 1)**: 위 점검 이후 다음이 바뀌었다. 최신 상태는 `DEVELOPMENT_HISTORY.md` 3절 "11-5 Step 1"을 따른다.
> - **Java 제외**: `.gitignore`에 `/src/`, `/pom.xml`, `/scripts/start-backend.ps1`을 추가해 Java 레거시를 업로드에서 뺐다. `sql/`과 `tests/fixtures/`는 Python이 쓰므로 남겼다.
> - **덤프 제외 보강**: `*.dump`, `*.backup`, `*.bak`, `*.sqlite`, `*.sqlite3`, `*.db`, `.ruff_cache/`를 경로와 관계없이 제외한다.
> - **README 정리**: 루트 README의 Java 빌드 설명을 지웠다. 그래서 위의 `YOUR_DB_PASSWORD` 자리표시자도 더는 없다.
> - **스크립트 정리**: `scripts/run-postgres-integration.ps1`과 `scripts/verify-all.ps1`에서 Maven 단계를 빼고, `verify-all.ps1`은 Ruff·pytest로 바꿨다.
> - **개인 정보 정리**: 문서 3개의 Windows 사용자명 경로를 `%USERPROFILE%`로 바꿨다.
> - 업로드 대상은 294개 파일이며, 알려진 민감정보는 없다(판정 READY, 업로드는 사용자 승인 대기).

## 7. Supabase DB 생성과 Migration 준비 (☁️ 11-5)

1. 프로젝트를 만든다. DB 비밀번호는 비밀번호 관리자에만 보관한다.
2. 연결 문자열을 고른다.
   - **Session pooler(포트 5432)** 또는 Direct connection을 쓴다.
   - ☁️ **Transaction pooler(6543)는 피한다.** psycopg 3은 같은 쿼리를 5번 넘게 실행하면 prepared statement를 쓰는데(`prepare_threshold`), 트랜잭션 풀링과 충돌할 수 있다. 코드에서 이를 끄는 설정은 없다.
   - ☁️ Supabase Direct connection이 IPv6 전용인지, Render에서 IPv4로 닿는지 확인한다. 안 되면 Session pooler를 쓴다.
3. URL 끝에 `?sslmode=require`를 붙인다. 없으면 앱과 Alembic이 시작을 거부한다.
   - CA 인증서를 준비할 수 있으면 `verify-full`을 쓴다.
4. Supabase 대시보드(Database → Extensions)에서 **`btree_gist`를 먼저 켠다**. Migration 007이 이 확장을 쓴다.
5. **저장소 전체가 있는 곳**(Render 셸에서 루트의 `sql/`이 보이는지 ☁️ 확인, 안 보이면 저장소를 받은 로컬 PC)에서 운영 환경변수를 설정한다. 그다음 `backend` 디렉터리에서 `alembic upgrade head`를 실행하고, 결과가 `011_staff_deleted_status`인지 확인한다. 001이 루트의 `sql/schema_postgresql.sql`을 읽는다.
6. `bootstrap_admin.py`로 최초 관리자를 만든다.
7. **시연 데이터**
   - 별도 Seed 스크립트는 없다(🔎).
   - 화면에서 가상 데이터를 넣는다. 반·직원 등록 → `.dev-data/samples/가상학생-업로드확인.xlsx` 형식의 **가상** 엑셀 업로드 → 초안 생성 → 모의 발송.
   - 실제 학생·보호자 정보는 넣지 않는다.
8. **분리와 초기화**
   - 테스트 DB(로컬 55432)와 시연 DB(Supabase)는 물리적으로 분리되어 있다. production 모드에서는 로컬 dev/test URL과 테스트 스위치가 거부된다(✅ 단위 테스트).
   - TRUNCATE 테스트는 `test` 모드와 로컬 테스트 DB 대상에서만 돌아서 Supabase에 닿을 수 없다.
   - 시연 DB를 초기화·복원하는 자동 절차는 없다. ☁️ 초기화가 필요하면 Supabase 백업이나 새 프로젝트로 처리하고 `alembic upgrade head`부터 다시 한다.

## 8. Render FastAPI 배포 설정 (☁️ 11-5)

| 항목 | 값 |
|---|---|
| Root Directory | `backend` |
| Build Command | `pip install .` |
| Start Command | 5절의 uvicorn 명령. `--workers`는 쓰지 않는다(워커 1) |
| Python 버전 | 3.12 고정 권장. ☁️ Render에서 지정하는 방법 확인(예: `PYTHON_VERSION` 환경변수) |
| Health Check Path | `/api/health` |
| 환경변수 | 5절 표. Secret은 Render Secret에만 넣는다 |
| 확인 | 배포 가이드 6절 0~6단계(시작 검증, 유휴 만료, 주소 진단, 위조 차단, 로그) |

## 9. Vercel React 배포 설정 (☁️ 11-5)

| 항목 | 값 |
|---|---|
| Root Directory | `frontend` |
| Install / Build | `npm ci` / `npm run build` |
| Output | `dist` |
| Node | 로컬 검증 버전 24.x에 맞춘다 |
| 환경변수 | `VITE_API_BASE_URL`은 비워 둔다 |

- 저장소에 `vercel.json`은 없다. Render 주소가 정해져야 쓸 수 있으므로 11-5에서 만든다.
- 앱이 `createBrowserRouter`를 쓰므로(🔎 `src/app/router.tsx`) SPA 대체 경로가 필요하다. `/api` 규칙을 먼저 둔다.

```json
{
  "rewrites": [
    { "source": "/api/:path*", "destination": "https://<Render 서비스 주소>/api/:path*" },
    { "source": "/(.*)", "destination": "/index.html" }
  ]
}
```

- ☁️ 이 Rewrite에 비밀 헤더 `X-Academy-Edge-Secret`을 붙이는 방법은 `vercel.json`만으로는 확인하지 못했다(가이드 2절 확인 필요 ①). 붙일 수 없으면 구성 A′로 운영한다.
- ☁️ 새로고침·직접 URL(`/notifications` 등)이 index.html로 열리는지, `/assets/*`가 정상인지 확인한다.

## 10. 세션 · CSRF · CORS · 프록시 주의사항

🔎 코드 확인 결과
- **쿠키**
  - 세션 쿠키: `HttpOnly; Secure; SameSite=Lax; Path=/`, Domain 없음. 응답이 Vercel을 거치므로 Vercel 도메인에 묶인다.
  - CSRF 쿠키: 같은 설정에 HttpOnly만 없다(프론트가 읽어 `X-CSRF-Token` 헤더로 보낸다).
- **같은 출처 필수**: 브라우저가 Render 주소를 직접 부르면 Lax 쿠키가 붙지 않는다.
- **Origin 정책**
  - `Origin` 헤더가 있고 `ACADEMY_CORS_ORIGINS`에 없으면 모든 요청이 403 `CORS_FORBIDDEN`이다.
  - Vercel Rewrite는 브라우저의 `Origin`(운영 도메인)을 그대로 전달한다고 보고 이 값을 운영 도메인으로 설정한다. ☁️ 로그인이 403이면 이 값부터 확인한다.
- **CORS**: 허용된 출처에만 `Access-Control-Allow-Credentials: true`를 준다. 와일드카드는 production에서 시작 실패다.
- **JSON 전용 경로**: `/api/messages/preview`, `/api/auth/login`, `/api/auth/password`, `/api/auth/password-reset`. 폼 제출은 415다.
- **프록시**
  - `--no-proxy-headers`로 uvicorn의 헤더 해석을 끈다. 주소는 앱(`resolve_client`)이 판정한다.
  - `ACADEMY_TRUSTED_PROXIES`의 `/0`은 시작 실패다.
- **단일 워커 제약**: 로그인 시도 카운터, 알려진 주소, 비밀번호 재설정 코드가 모두 프로세스 메모리에 있다. 워커를 늘리거나 인스턴스를 여러 개 띄우면 안 된다(☁️ Render 자동 확장을 끈다).
- **로그**
  - `--no-access-log`로 쿼리 문자열(`?q=<학생 이름>`)이 남는 접근 로그를 끈다.
  - 앱 로그는 경로만 남기고, 예외는 유형과 SQLSTATE만 남긴다.
  - ☁️ 플랫폼(Render·Vercel) HTTP 로그는 별도로 확인한다.

## 11. 사용자 수동 E2E 시나리오 체크리스트 (11-5 배포 직후, 가상 데이터만)

로컬에서 먼저 한 번(`scripts/start-fastapi.ps1` + `scripts/start-frontend.ps1`), 배포 후 다시 한 번 수행한다.

- **인증**
  - [ ] 관리자 로그인 → 대시보드 → 로그아웃 → 뒤로가기로 업무 화면이 열리지 않음
  - [ ] 틀린 비밀번호 6회 → 6번째에 "잠시 후" 안내(429)
- **유휴 만료**
  - [ ] (점검용으로 `ACADEMY_SESSION_IDLE_MINUTES`를 줄인 상태) 방치 → 다음 클릭에서 "오랫동안 사용하지 않아 로그아웃되었습니다. 다시 로그인해주세요." → 다시 로그인하면 정상
  - [ ] 끝나면 60으로 되돌린다
- **비밀번호 변경**
  - [ ] 상단 "비밀번호 변경"에서 현재 비밀번호를 틀리면 오류만 나고 로그아웃되지 않음
  - [ ] 성공 → 다른 브라우저의 같은 계정이 다음 요청에서 로그아웃
- **재설정 코드**
  - [ ] 관리자가 직원 행에서 "재설정 코드" 발급 → 코드는 모달에 한 번만 표시
  - [ ] 직원이 로그인 화면의 "재설정 코드로 설정"으로 새 비밀번호 설정 → 로그인
  - [ ] 같은 코드로 다시 시도하면 실패
  - [ ] 비활성 직원 행에는 버튼이 없음, 본인 계정은 거부
- **권한**
  - [ ] 선생님 계정에서 직원 관리 메뉴가 안 보임
  - [ ] 주소창에 직접 입력하거나 API를 직접 호출해도 403 또는 화면 차단
  - [ ] 담당하지 않은 반이 보이지 않음
- **직원·반·학생**
  - [ ] 반 등록, 직원 등록, 담당 배정 → 선생님 계정에서 그 반만 보임
  - [ ] 같은 반 이름을 다시 등록하면 충돌 안내(409)
- **엑셀 업로드**
  - [ ] 가상 엑셀 → 시간대 선택 → 미리보기(저장 안 됨 안내) → 확정 → 결과 카드와 초안 수
  - [ ] 같은 파일을 다시 올리면 "변경 없음(생략)"
- **수업·출결·성적**
  - [ ] 출결 입력·저장
  - [ ] 두 탭에서 같은 수업을 동시에 수정 → 늦게 저장한 쪽이 충돌 안내를 받고, 덮어쓰기는 일어나지 않음
- **메시지**
  - [ ] 검토·발송 탭에서 일괄 확정 → 모의 발송 → "모의 발송 성공 … (실제 문자·이메일은 전송되지 않음)"
  - [ ] 실제 메일함에 아무것도 오지 않음
  - [ ] 모의 발송 버튼을 빠르게 두 번 눌러도 한 번만 처리됨
- **실패·재시도**
  - [ ] 보호자 이메일이 `…@mock-retry.invalid`인 가상 학생 → 첫 발송 실패 → 메시지 운영 화면에서 재시도 → 성공
  - [ ] `…@mock-fail.invalid`는 계속 실패하고 "수신자" 사유가 표시됨
- **분석**
  - [ ] 출결률(미입력 제외), 성적, 관심 학생 화면이 열리고, 데이터 없는 반은 빈 상태 안내가 나옴
- **오류 상태**
  - [ ] Render를 잠시 중지 → 빈 화면이 아니라 오류 안내가 나옴 → 재시작 후 복구
    - Vercel Rewrite가 502/504 같은 오류 응답을 대신 돌려주므로, 안내는 "요청을 처리하지 못했습니다." 같은 일반 문구일 수 있다.
    - "백엔드 API에 연결할 수 없습니다"는 응답 자체가 없을 때만 나온다. ☁️ 실제 문구 확인
- **배포 보안**
  - [ ] 배포 가이드 6·8절 점검 수행: 쿠키 속성, `/docs` 404, 다른 출처 403, 주소 진단, 진단 끈 뒤 404

## 12. 잔여 위험과 배포 차단 여부 (Stage 4.5)

### A. SEC-10 비밀번호 재설정 — 차단 결함 없음

| 검증 | 결과 |
|---|---|
| 일회성·만료·시도 제한 | ✅ 단위(저장소: 1회용, 15분 만료, 5회 오답 폐기, 새 발급 시 대체) + PostgreSQL(전체 흐름, 재사용 실패, 만료) |
| 발급 권한 | ✅ 관리자 + CSRF만 가능. 본인 409, 비활성 409, 삭제 404. 코드는 발급한 관리자 응답에만 들어간다 |
| 소비 권한·신원 | 🔎 이메일 + 코드가 일치하고 계정이 활성일 때만 성공한다. 실패는 모두 동일한 400 `RESET_FAILED`(계정 존재 추론 불가). 주소별 20회, 이메일별 5회로 제한된다. 코드 공간은 약 2^50이다 |
| 노출 방지 | ✅ caplog 테스트로 로그에 코드·비밀번호가 없음을 확인. 감사에는 개수·만료 분만 남는다. 접근 로그는 끈다 |
| 재시작 | 🔎 메모리 전용이라 재시작하면 모든 코드가 사라진다. 소비 시 "없는 코드"가 되어 `RESET_FAILED`다. 관리자가 다시 발급하면 된다 |
| 단일 워커 | 기록됨(10절). ☁️ Render 인스턴스 1개 |

- **수용한 위험**
  - 관리자는 다른 관리자 계정에도 코드를 발급할 수 있다. 관리자 권한 자체가 전권이므로 차단 결함으로 보지 않는다.
  - 이 경우 대상 계정의 모든 세션이 끊기고 감사 기록 `STAFF_PASSWORD_RESET_ISSUED`/`_COMPLETED`가 남는다.
- **신원 확인**: 코드를 대면·전화로 전달하는 운영 절차에 의존한다(화면 안내 문구 있음).
- 권한 없는 사용자가 코드를 얻는 경로는 찾지 못했다.

### B. SEC-05 유휴 세션 만료 — 차단 결함 없음

- ✅ **경계값**: 정확히 60분이면 401 `SESSION_IDLE_EXPIRED`다. 이때 세션이 revoke되므로 다음 요청은 `SESSION_EXPIRED`이며 되살아나지 않는다.
- ✅ **8시간 절대 만료**는 그대로다.
- **1분 오차의 정체**: UI 표시 지연이 아니다. 서버가 활동 시각을 60초에 한 번만 기록해서 생기는 판정 오차다.
  - 방향은 **이르게**다. 최대 1분 일찍 만료되고, 늦게 허용되지 않는다.
  - 만료된 세션으로 API가 허용되는 경우는 없다(보안 결함 없음).
- 🔎 **Polling**: 프론트에 자동 Polling이 없다(`refetchInterval`·`setInterval` API 호출 없음, react-query는 health 1곳). 그래서 화면을 열어 둔다고 세션이 연장되지 않는다.
  - 서버는 `X-Academy-Background: 1` 요청을 연장하지 않는다(✅ 테스트).
- 🔎 **화면 일관성**
  - 만료 뒤 첫 API 요청의 401에서 axios 인터셉터가 로그아웃 상태로 바꾸고 로그인 화면에 안내를 띄운다.
  - 그 전까지 화면에는 만료 전에 받은 데이터만 남는다. 새 데이터는 서버가 막는다.
  - 로그인·재설정 요청의 401/400은 로그아웃을 일으키지 않는다(`OWN_401`).

### C. Mock Sender 운영 안전성 — 차단 결함 없음

- 🔎 **발송 경로**
  - 발송 경로는 `MockSender` 하나다(`notifications/sender.py`: "Nothing leaves this process"). 실행 모드와 관계없이 항상 이 경로다. 바꾸는 설정이 없다.
  - 백엔드 앱 코드에 `smtplib`·`httpx`·`requests`·`urllib.request`·`aiohttp` import가 없다. 그래서 외부 I/O 경로가 없다.
- 🔎 **DB 상태**: `MOCK_SENT`/`MOCK_FAILED`, 채널 `MOCK`이다.
- 🔎 **화면 표시**
  - "모의 발송 성공 (실제 미전송)", "이 단계의 발송은 모의 발송입니다. 실제 문자·이메일은 전송되지 않습니다.", 운영 화면의 "모의 발송 완료"
  - 11-4-C에서 유일하게 "발송 완료"로만 나오던 집계 문구도 "모의 발송 완료"로 바꿨다.
- ⏭ **INT-I1**: 실제 SMS/LMS로 바꾸려면 발송 I/O를 트랜잭션 밖으로 빼는 아웃박스(`SENDING`) 설계가 먼저 필요하다. 스키마 승인이 필요해 이번에는 구현하지 않았다.

### D. API 오류 계약 — 일치

| 상황 | 백엔드 | React 처리 |
|---|---|---|
| 세션 만료 | 401 `SESSION_IDLE_EXPIRED` / `SESSION_EXPIRED` | 인터셉터가 로그아웃시키고 원인별 안내 |
| 권한 부족 | 403 `FORBIDDEN`, `CLASSROOM_ACCESS_DENIED`, `CSRF_FAILED` | 서버 문구 표시 |
| 학생 식별 충돌 | 409 `STUDENT_BUSINESS_KEY_CONFLICT`, `DUPLICATE_ENROLLMENT` | 서버 문구 표시 |
| 동시 수정 | 409 `VERSION_CONFLICT`, `ATTENDANCE_CONFLICT`, `SOURCE_CHANGED`, `TRANSACTION_CONFLICT` | 경고(노란색)로 표시하고 다시 불러오기(`LessonsTab`, `AttendanceTab`, `GradesTab`, `ReviewTab`) |
| 중복 요청 | `IDEMPOTENCY_KEY_REQUIRED`/`_REUSED`, 같은 키 재요청은 replay | 응답이 없으면 키를 유지해 재전송 시 replay(`BatchReview`) |
| 비밀번호 | 400 `INVALID_CURRENT_PASSWORD`, `WEAK_PASSWORD`, `RESET_FAILED`, 409 `SELF_RESET_FORBIDDEN`/`STAFF_NOT_ACTIVE` | 400이므로 로그아웃되지 않고 문구 표시(✅ `LoginPage`·`StaffManagementPage` 테스트) |
| 예상하지 못한 오류 | 500 `INTERNAL_ERROR`(문구 고정), 503 `DATABASE_UNAVAILABLE` | 서버 문구 표시. 응답이 없으면 `NETWORK_ERROR` 안내. 업로드 확정은 "저장 여부 알 수 없음" 안내 |

- 상태 코드는 바꾸지 않았다.
- 프론트는 대부분 서버의 `message`를 그대로 보여 준다. 코드에 따라 갈라지는 곳은 위 표의 코드뿐이고, 모두 백엔드에 실제로 있는 코드다(🔎).

### 남은 위험 목록

| # | 위험 | 영향 | 완화 | 확인 시점 | 차단 |
|---|---|---|---|---|---|
| R1 | 실제 Render 기동·환경변수 주입 미검증 | 시작 실패 시 서비스 불가 | 시작 검증이 설정 이름만 보여 주므로 고치기 쉽다 | ☁️ 11-5 가이드 6절 0단계 | 아님 |
| R2 | Supabase 연결 방식(TLS, IPv4, pooler와 prepared statement) | DB 오류 503 | Session pooler(5432) + `sslmode=require` | ☁️ 11-5 첫 Migration | 아님 |
| R3 | Vercel Rewrite 비밀 헤더 가능 여부 | 구성 A′면 로그인 제한이 송신 주소 단위로 묶임 | 가이드 3·7절 | ☁️ 11-5 | 아님 |
| R4 | 메모리 저장소(로그인 카운터·재설정 코드) | 워커 여러 개면 한도 N배, 코드 무효 / 재시작 시 초기화 | 워커 1·인스턴스 1, 재발급 | ☁️ Render 설정 | 아님 |
| R5 | 플랫폼 HTTP 로그의 쿼리 문자열 | 학생 이름이 플랫폼 로그에 남을 수 있음 | 로그 접근 권한·보존 기간 제한 | ☁️ 11-5 | 아님 |
| R6 | 무료 플랜 유휴 정지·콜드 스타트 | 첫 요청 지연, 재시작 시 R4 초기화 | 시연 전 미리 깨우기 | ☁️ | 아님 |
| R7 | 큰 JS 청크(662kB) | 첫 로딩 지연 | ⏭ 코드 분할 | — | 아님 |
| R8 | Browser E2E 자동화 없음 | 화면 회귀를 사람이 확인해야 함 | 11절 체크리스트 | 11-5 전·후 | 아님 |
| R9 | INT-I1(발송 I/O가 트랜잭션 안에 있음) | Mock에서는 무해. 실제 발송으로 바꾸면 이중 발송 위험 | 실제 발송 도입 전 아웃박스 | ⏭ | 아님(Mock 유지 조건) |

## 13. 최종 판정

**로컬 코드 기준: READY**
- ✅ 주요 자동 테스트와 Production Build가 통과했다. 백엔드 단위 117, PostgreSQL 141(+ 11-4-C 비파괴 36), Vitest 113, tsc, oxlint, Ruff, vite build.
- ✅ 알려진 Critical·High 결함이 없다. 기존 프론트 실패 1건은 테스트 타이밍 문제로 원인을 해결했다.
- ✅ 인증·세션·CSRF·RBAC 회귀가 없다(PostgreSQL 전체 회귀).
- ✅ SEC-04: production 실행 모드와 시작 검증을 로컬 subprocess로 확인했다.
- ✅ SEC-05·10: 보안 계약을 검증했다(12-A·B).
- ✅ Mock Sender 운영 안전성을 확인했다(12-C).
- ✅ 테스트 DB를 격리했고 비밀정보를 노출하지 않았다(3·6절).
- 🔎 필수 환경변수와 실행 명령을 문서화했다(5절, 배포 가이드).

**배포 전체: CONDITIONALLY READY**
- 클라우드 항목 R1~R6은 아직 확인하지 않았다. **PASS로 표시하지 않는다.**
- 각 항목의 확인 방법과 시점은 위 표, 7~9절, 배포 가이드 6절에 있다.

**미해결 배포 차단 결함: 없음**

GitHub Push, Supabase 생성·Migration, Render·Vercel 배포, 유료 서비스 활성화는 수행하지 않았다(사용자가 11-5에서 직접 진행).
