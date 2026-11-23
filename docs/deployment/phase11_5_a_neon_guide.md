# Phase 11-5-A Neon PostgreSQL 배포 실행 가이드

작성: 2026-11-23 · 대상: Neon(DB) → Render(FastAPI) → Vercel(React) 배포를 직접 수행하는 사람
관련 문서: `phase11_5_security_deployment_guide.md`(Render·Vercel 보안 설정), `docs/reviews/phase11_4_release_readiness.md`

이 문서의 명령은 저장소 코드(`backend/app/db/*`, `backend/alembic/*`, `backend/scripts/seed_demo.py`)를 기준으로 썼다.
Neon·Render 화면 이름과 무료 플랜 한도는 바뀔 수 있다. ☁️ 표시는 실제 화면이나 실행 결과로 확인해야 하는 항목이다.
비밀번호와 연결 문자열 값은 이 문서·채팅·커밋 어디에도 적지 않는다.

---

## 0. 코드 기준 호환성 요약

| 항목 | 코드에서 확인한 내용 | Neon 영향 |
|---|---|---|
| 드라이버 | `psycopg[binary]==3.3.8`(번들 libpq 18.4), `SQLAlchemy==2.1.8` | SNI·`channel_binding`을 지원해 Neon 요구사항을 충족한다 |
| Engine | 동기(sync) `create_engine` 1개(`app/db/session.py`). async는 쓰지 않는다 | — |
| URL | `ACADEMY_DATABASE_URL` 하나를 앱과 Alembic(`alembic/env.py`)이 함께 쓴다. `make_url`로 파싱하고, 쿼리 인자는 그대로 libpq에 전달된다 | `?sslmode=require&channel_binding=require`가 그대로 전달된다(로컬에서 파싱 확인) |
| TLS 검사 | production 모드에서 `sslmode`가 `require`/`verify-ca`/`verify-full`이 아니면 시작과 Migration을 거부한다 | Neon 기본 문자열(`sslmode=require`)을 통과한다 |
| Pool | `pool_size=5`, `max_overflow=5`, `pool_pre_ping=True`, `pool_recycle=1800`, `pool_timeout=10`, `connect_timeout=5` | 휴면 뒤 끊긴 연결은 pre-ping이 걸러 내고 다시 연결한다 |
| 세션 상태 | `SET`, `LISTEN`, 임시 테이블, 세션 advisory lock을 쓰지 않는다. 트랜잭션 범위 `pg_advisory_xact_lock`만 쓴다(업로드 확정) | Pooled 연결과도 충돌하는 구조는 아니다 |
| prepared statement | psycopg 3 기본값(`prepare_threshold=5`). 코드에서 끄는 설정은 없다 | Pooled(PgBouncer 트랜잭션 모드)에서는 ☁️ 지원 여부를 확인해야 한다 |
| DB 객체 | plpgsql 함수와 트리거만 쓴다. RLS·Role·GRANT·SECURITY DEFINER·특정 클라우드 전용 스키마는 없다 | 소유자 계정 하나로 충분하다 |
| 확장 | `btree_gist`(Migration 007, `CREATE EXTENSION IF NOT EXISTS`) | ☁️ 첫 Migration에서 생성되는지 확인한다 |

**연결 정책 — Migration과 Runtime 모두 Direct connection을 쓴다**
- Render는 프로세스 1개(워커 1)다. 앱이 직접 여는 연결은 최대 10개(5+5)다. 그래서 PgBouncer를 거쳐 얻는 이득이 거의 없다.
- Pooled 연결은 PgBouncer 트랜잭션 모드다. psycopg 3의 자동 prepared statement가 여기서 제대로 동작하는지는 코드로 보장할 수 없다(☁️ Neon 설정에 달려 있다). Direct는 이 위험 자체가 없다.
- 그 결과 환경변수가 `ACADEMY_DATABASE_URL` 하나로 끝나고, Migration 전용 변수도 필요 없다(코드 변경 없음).
- Pooled 연결은 연결 수가 모자랄 때만 검토한다. 그때는 4절과 같은 절차로 따로 검증한다.

## 1. Neon 프로젝트 만들기 (사용자 직접)

1. Neon 콘솔에서 새 프로젝트를 만든다.
   - **Postgres 버전 17**을 고른다. 로컬 개발·테스트는 17.6이다.
   - **Region은 Render 서비스와 같은 지역**을 고른다. 지연이 줄어든다(☁️ 두 서비스에 공통으로 있는 지역 확인).
2. 무료 플랜인지 확인한다. 결제 수단 등록이나 유료 플랜 업그레이드는 하지 않는다.
3. 기본 데이터베이스(`neondb`)와 소유자 역할을 그대로 쓴다. 추가 Role이나 GRANT는 필요 없다.

## 2. 연결 문자열 확인 위치

- 프로젝트 대시보드의 **Connect**(연결 정보) 창을 연다(☁️ 화면 이름은 바뀔 수 있다).
- **Connection pooling을 끈 상태의 문자열(Direct)**을 복사한다.
  - 호스트에 `-pooler`가 **없는** 것이 Direct다.
  - `-pooler`가 붙은 호스트는 Pooled다. 이번 구성에서는 쓰지 않는다.
- 받은 문자열을 이렇게 바꿔서 쓴다.
  - 접두사: `postgresql://` → `postgresql+psycopg://`
  - 끝의 `?sslmode=require&channel_binding=require`는 그대로 둔다.
  - 비밀번호에 `@ : / ? # %` 같은 문자가 있으면 URL 인코딩한다.

```
postgresql+psycopg://<role>:<password>@<endpoint-id>.<region>.aws.neon.tech/neondb?sslmode=require&channel_binding=require
```

## 3. 환경변수를 안전하게 등록하기 (로컬 PowerShell)

Render 무료 인스턴스에서 Shell이나 Pre-deploy 명령을 쓸 수 있는지는 확인되지 않았다(☁️). 그래서 Migration과 Seed는 **로컬 PowerShell 새 창**에서 Neon으로 실행한다.

- 값은 `Read-Host -AsSecureString`으로 입력한다. 화면과 PowerShell 명령 기록(PSReadLine history)에 남지 않는다.
- `$env:` 값은 그 창에만 있다. 창을 닫으면 사라진다. 사용자·시스템 환경변수나 `.env` 파일은 만들지 않는다(앱은 `.env`를 읽지 않는다).

```powershell
cd D:\refactor\backend-architecture\backend
. ..\scripts\use-d-drive-dev-env.ps1          # 캐시·임시 파일을 D: 드라이브로
.\.venv\Scripts\Activate.ps1

function Read-Secret([string]$Prompt) {
    [System.Net.NetworkCredential]::new('', (Read-Host $Prompt -AsSecureString)).Password
}
$env:ACADEMY_DB_MODE = 'production'
$env:ACADEMY_DATABASE_URL = Read-Secret 'Neon Direct URL'
Remove-Item env:ACADEMY_DB_TEST_MODE, env:ACADEMY_RUN_POSTGRES_INTEGRATION -ErrorAction SilentlyContinue
```

**접속 대상 확인**(DB에 접속하지 않음. 비밀번호 없이 host·db·sslmode만 출력)
```powershell
python -c "from app.config import get_settings; from app.db.safety import require_database_url as r; u=r(get_settings().database_url); print(u.host, u.database, u.query.get('sslmode'))"
```
- host가 `….neon.tech`이고 `-pooler`가 없는지, db가 `neondb`인지, sslmode가 `require`인지 확인한다.
- production 모드에서는 로컬 개발 DB(55431)와 테스트 DB(55432)를 가리키는 URL이 거부된다. 그래서 이 창의 명령은 로컬 DB에 닿을 수 없다.

## 4. Alembic Migration 적용

`backend` 디렉터리에서 실행한다. 001은 저장소 루트의 `sql/schema_postgresql.sql`을 읽으므로, 저장소 전체가 있는 위치에서 실행해야 한다.

```powershell
alembic heads            # 오프라인: 011_staff_deleted_status (head) 1개
alembic current          # 새 DB: revision 없음(빈 출력)이어야 한다
alembic upgrade head     # 001 → 011 순서로 적용
alembic current          # 011_staff_deleted_status (head)
```

- `alembic current`에 revision이 이미 나오면 **새 DB가 아니다**. 멈추고 대상을 다시 확인한다.
- `downgrade`는 운영 DB에서 쓰지 않는다. 001의 downgrade는 전체 테이블을 지운다.
- 실패하면 오류의 SQLSTATE와 객체 이름만 확인한다.
  - `alembic/env.py`는 한 번의 `upgrade` 전체를 **하나의 트랜잭션**으로 실행한다. PostgreSQL은 DDL도 롤백되므로, 중간에 실패하면 그 실행분 전체가 취소되고 DB는 빈 상태로 돌아간다.
  - 원인을 고친 뒤 `alembic current`가 빈 출력인지 확인하고 다시 실행한다.

## 5. Migration 성공 확인

- `alembic current` = `011_staff_deleted_status (head)`
- Neon 콘솔 SQL Editor(읽기 전용 쿼리)에서 확인한다.

```sql
SELECT version_num FROM alembic_version;                       -- 011_staff_deleted_status
SELECT extname FROM pg_extension WHERE extname = 'btree_gist'; -- 1행
SELECT count(*) FROM information_schema.tables
 WHERE table_schema = 'public' AND table_type = 'BASE TABLE';  -- 21 (앱 테이블 20 + alembic_version)
SELECT name, default_for_class_type FROM notification_template ORDER BY id;
  -- 3행: 수업 안내 (기본) / 정규반 기본 안내(REGULAR) / 내신 대비 기본 안내(EXAM_PREP)
SELECT to_regclass('import_job');                              -- NULL (Migration 010에서 삭제)
```

## 6. 시연 데이터 Seed

`backend/scripts/seed_demo.py`는 앱 서비스(`LearningOpsService`, `AcademicsService`)와 `hash_password`를 그대로 써서 가상 데이터를 넣는다.

**만드는 데이터**(모두 가상)

| 종류 | 내용 |
|---|---|
| 계정 4개 | `demo.admin@`(관리자), `demo.teacher1@`·`demo.teacher2@`(선생님), `demo.assistant@`(조교). 도메인은 모두 `example.invalid` |
| 반 3개 | 시연 정규 A반(teacher1 + assistant), 시연 정규 B반(teacher2), 시연 내신 대비반(EXAM_PREP, teacher1) |
| 학생 12명, 수강 13건 | 시연학생01~12, 가상중/고등학교. 01번은 두 반에 수강 |
| 수업 18개 | 반마다 2026-10-12 ~ 11-16 월요일 6회, 완료 상태 |
| 출결 77건, 과제 등급 | 출석·지각·결석·인정결석이 모두 있고, 1건은 일부러 미입력. 관심 학생 예시(최근 4회 중 결석 2회) 포함 |
| 평가 6개, 성적 25건 | 반마다 10월·11월 단원평가(수업 연결, 100점 만점). 결석은 `NOT_TAKEN` |

- **메시지 시연용 보호자 주소**
  - `@mock-retry.invalid`: 첫 발송이 실패하고 재시도하면 성공한다.
  - `@mock-fail.invalid`: 항상 실패한다.
  - 이메일이 없는 학생이 있다. 초안 생성 때 수신자 없음 오류가 나는 것을 보여 줄 수 있다.
- **메시지 초안은 만들지 않는다.** 생성 → 검토 → 모의 발송은 화면에서 직접 시연한다. 기본 템플릿은 Migration 008·009가 이미 넣었다.
- 실제 발송 경로는 없다(`MockSender` 고정). Seed는 발송 코드를 import하지 않는다.

**실행**(3절의 창에서 이어서)

```powershell
$env:ACADEMY_SEED_DEMO = '1'
$env:ACADEMY_SEED_TARGET_HOST = '<3절에서 출력된 host 그대로>'
$env:ACADEMY_SEED_ADMIN_PASSWORD = Read-Secret '시연 관리자 비밀번호(12자 이상)'
$env:ACADEMY_SEED_TEACHER_PASSWORD = Read-Secret '시연 선생님 비밀번호(다른 값)'
$env:ACADEMY_SEED_ASSISTANT_PASSWORD = Read-Secret '시연 조교 비밀번호(다른 값)'
python scripts/seed_demo.py
```

**안전장치**(하나라도 어기면 아무것도 쓰지 않고 종료)
- `ACADEMY_SEED_DEMO=1`이 필요하다.
- `ACADEMY_DB_MODE`는 `production`이나 `test`여야 한다. `ACADEMY_SEED_TARGET_HOST`는 URL의 host와 같아야 한다.
- DB가 Alembic head여야 한다.
- 시연용이 아닌 반이나 학생이 있으면 거부한다. 실제 데이터와 섞지 않기 위해서다.
- 같은 이메일의 계정이 다른 역할이거나 비활성 상태면 거부한다.
- 비밀번호는 12~1024자여야 하고, 계정 이메일과 달라야 하며, 역할마다 달라야 한다. 값은 출력하지 않는다.

**다시 실행해도 안전하다**
- 이메일, 반 이름+유형, 학생 이름+학교, 수업 날짜로 찾고, 없을 때만 만든다.
- 기존 행은 수정하거나 지우지 않는다. 시연 중에 바꾼 내용도 그대로 둔다.
- 출결은 아직 아무도 기록하지 않은 수업에만 넣는다. 성적은 결과가 하나도 없는 평가에만 넣는다.
- 중간에 끊겼다면 같은 명령을 다시 실행해 이어서 채운다.
- 모든 감사 기록에는 실행 1회당 같은 request id가 붙는다.

**끝나면** 창을 닫는다. Seed 변수는 Render에 넣지 않는다.

## 7. Seed 후 무결성 확인

```powershell
python scripts/seed_demo.py --check   # 읽기 전용: 계획 대비 개수·배정·출결·평가·템플릿·MOCK 채널
```
- 출력이 `Demo data check passed.`여야 한다.
- 시연하면서 데이터를 더 넣어도 "부족"만 실패로 본다.

SQL Editor 교차 확인(읽기 전용):
```sql
SELECT role, status, count(*) FROM staff_user GROUP BY 1, 2;              -- ADMIN 1, TEACHER 2, ASSISTANT 1 (bootstrap 관리자를 따로 만들었다면 ADMIN +1)
SELECT count(*) FROM student WHERE parent_email NOT LIKE '%.invalid';    -- 0
SELECT count(*) FROM lesson_result;                                       -- 77
SELECT count(*) FROM assessment_result;                                   -- 25
SELECT count(*) FROM notification_send_attempt WHERE channel <> 'MOCK';  -- 0
```

로그인 확인은 Render·Vercel 배포 뒤 운영 도메인에서 한다(8절, 보안 가이드 6절).
- `demo.teacher2@example.invalid`에는 B반만 보여야 한다.
- 조교 계정에는 A반만 보이고, 직원 관리 메뉴가 없어야 한다.

## 7-1. 업로드 벤치마크 학생 60명 (선택)

`backend/scripts/seed_benchmark.py`는 업로드 시험용 엑셀(`.dev-data/samples/가상학생-60명-5개반-토6.xlsx`, Git 제외)의 학생 60명을 보호자 이메일과 함께 **미리 등록**한다. 그러면 업로드할 때 모든 행이 기존 학생으로 연결(MATCHED)되고, 메시지 생성 → 검토 → 모의 발송까지 시험할 수 있다.

- **선행 조건**: 관리자가 반 관리에서 반 5개를 먼저 만든다. 스크립트는 반과 담당 배정을 만들지 않는다.
  - 정규: `고1 토6A`, `고1 토6B`
  - 내신 대비: `검증고2 토6`, `테스트고2 토6`, `가짜고2 토6`
- **데이터**
  - 학생: `가상학생01`~`60`, 반마다 12명
  - 학교: 정규반은 비움. 내신반은 업로드와 같은 규칙으로 검증고·테스트고·가짜고
  - 보호자: `벤치보호자NN`, 이메일 `bench.parentNN@…`
  - 이메일 도메인: `example.invalid` 50명, `mock-retry.invalid` 5명(05·17·29·42·53, 첫 발송 실패 후 재시도 성공), `mock-fail.invalid` 5명(09·21·33·46·57, 항상 실패). 반마다 1명씩이고 모두 엑셀에서 출석한 학생이다.
  - 수강 시작일: 2026-09-01. **업로드할 수업일은 이 날짜 이후**로 고른다.
- **시연 데이터와 분리**
  - 이름, 보호자, 이메일, 반이 시연 Seed와 겹치지 않는다. 시연 학생 12명은 수정하지 않는다.
  - `--check`가 시연 학생 12명이 그대로인지, 벤치마크 반에 수강 등록되지 않았는지 확인한다.
- **다시 실행해도 안전하다**
  - 없는 학생과 수강만 만든다.
  - 업로드로 먼저 생긴 학생처럼 보호자 이메일이 비어 있으면 그 칸만 채운다.
  - 다른 이메일이 이미 들어 있으면 바꾸지 않고 NOTE로 알린다.

```powershell
# 3절과 같은 창(ACADEMY_DB_MODE, ACADEMY_DATABASE_URL 설정)에서
$env:ACADEMY_SEED_BENCHMARK = '1'
$env:ACADEMY_SEED_TARGET_HOST = '<3절에서 출력된 host 그대로>'
python scripts/seed_benchmark.py          # 등록 후 자동 검증
python scripts/seed_benchmark.py --check  # 읽기 전용 검증만
```

- 비밀번호 환경변수는 필요 없다. 감사 기록의 작업자는 시연 관리자다. 없으면 가장 오래된 활성 관리자가 된다.
- 담당 배정이 비어 있는 반은 `--check`가 NOTE로 알려 준다. 배정은 반 관리에서 한다.
- 참고: 시연 Seed(`seed_demo.py`)는 시연용이 아닌 반·학생이 있으면 실행을 거부한다. 그래서 벤치마크 반을 만든 뒤에는 `seed_demo.py --check`(읽기 전용)만 쓴다.

## 8. Render 환경변수와 주의사항

| 변수 | 값 | 비고 |
|---|---|---|
| `ACADEMY_DB_MODE` | `production` | |
| `ACADEMY_DATABASE_URL` | 2절의 Direct URL | **Secret**. `sslmode=require` 필수 |
| `ACADEMY_ENABLE_DB_APIS` | `1` | |
| `ACADEMY_COOKIE_SECURE` | `1` | 0이면 시작 실패 |
| `ACADEMY_CORS_ORIGINS` | `https://<Vercel 운영 도메인>` | 정확히 일치해야 한다 |
| `ACADEMY_EDGE_SECRET` / `ACADEMY_CLIENT_IP_HEADER` | 보안 가이드 2절 | 구성 A/A′ |
| `ACADEMY_API_DOCS` | 넣지 않음(0) | `/docs`는 404 |
| `ACADEMY_SESSION_TTL_MINUTES` / `_IDLE_MINUTES` | 480 / 60 | 기본값 |
| 넣지 않는다 | `ACADEMY_DB_TEST_MODE`, `ACADEMY_RUN_POSTGRES_INTEGRATION`, `ACADEMY_SEED_*`, `ACADEMY_BOOTSTRAP_*` | 앞의 두 개는 있으면 시작 실패 |

- **세션 서명용 Secret(`SESSION_SECRET` 같은 것)은 없다.** 토큰은 무작위로 만들고 DB에는 SHA-256 값만 저장한다.
- 쿠키 이름은 `ACADEMY_SESSION_COOKIE` / `ACADEMY_CSRF_COOKIE`(기본 `academy_session` / `academy_csrf`)다. CSRF 쿠키 이름은 바꾸지 않는다.
- 쿠키는 `HttpOnly`(세션만)·`Secure`·`SameSite=Lax`다. 그래서 Vercel `/api` Rewrite로 같은 출처를 유지해야 한다.
- Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT --no-proxy-headers --no-access-log`
  - 워커는 1개만 쓰고 인스턴스 자동 확장은 끈다.
  - Health Check는 `/api/health`다. DB에 접근하지 않는다.
- **재시작하면 메모리 상태가 초기화된다.** 로그인 시도 카운터와 비밀번호 재설정 코드가 사라진다. 코드는 다시 발급하면 된다.
- **Neon 휴면 뒤 첫 요청**(☁️ 무료 플랜은 유휴 시 compute가 정지된다)
  - 끊긴 연결은 `pool_pre_ping`이 다시 연결한다.
  - compute가 깨어나는 데 5초(`connect_timeout`)를 넘기면 그 요청은 503 `DATABASE_UNAVAILABLE`이다. 다시 시도하면 된다.
  - 프론트 기본 타임아웃은 10초다. Render 콜드 스타트와 겹치면 첫 요청이 실패할 수 있다. 시연 전에 `/api/health`와 로그인으로 미리 깨워 둔다.
- 로그
  - 접근 로그는 끈다(`--no-access-log`).
  - 앱 로그에는 경로만 남고, 예외는 유형과 SQLSTATE만 남는다.
  - ☁️ Render 플랫폼 로그에 쿼리 문자열이 남는지 확인한다.

## 9. 남은 확인 항목 (☁️)

| # | 항목 | 확인 시점 |
|---|---|---|
| N1 | `btree_gist`가 Neon에서 생성되는지 | 4절 Migration |
| N2 | Render → Neon Direct 연결(TLS·channel binding) | Render 첫 배포 로그, 로그인 |
| N3 | 휴면 뒤 첫 요청 지연이 5초 안인지 | 배포 후 5분 넘게 방치했다가 요청 |
| N4 | 무료 플랜 한도(저장 용량, compute 시간, 연결 수) | 콘솔 사용량 화면 |
| N5 | Pooled 연결을 쓸 경우 prepared statement 동작 | 쓰기로 할 때만 |
