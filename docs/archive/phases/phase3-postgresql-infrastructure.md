# Academy LearningOps Phase 3 — PostgreSQL Infrastructure

작성일: 2026-11-08  
작업 범위: 독립 PostgreSQL 개발·테스트 환경, SQLAlchemy 2.x, Alembic 기준선 및 실제 DB 통합 테스트

## 1. 결과 요약

PostgreSQL 17.6 기반의 독립 개발·테스트 환경을 각각 구축하고 기존 Java DDL 13개
테이블을 두 DB 모두에 Alembic 기준선으로 재현했다. FastAPI에는 동기 SQLAlchemy Session
계층과 13개 ORM 모델을 추가했다. 기존 Health, Message Preview, Import Preview는 DB
설정 없이 계속 동작한다.

실제 전용 컨테이너에서 Python PostgreSQL 테스트 5개와 기존 Java PostgreSQL 테스트
5개를 모두 실행했다. Java 전체 결과는 47 passed, 0 skipped였다. 실제 스키마와 ORM
metadata의 Alembic 비교 결과는 두 환경 모두 빈 diff(`[]`)였다. 새 프로젝트 전용 개발
DB는 최초 생성했으며, 기존의 미식별 `academy-postgres` 컨테이너와 volume은 변경하지
않았다.

사전 문서 중 `docs/academy-learningops-assessment.md`는 저장소에 존재하지 않아 확인하지
못했다. 나머지 Phase 1·2 문서, OpenAPI, Java DDL·DAO·테스트를 기준으로 구현했다.

## 2. 변경 파일

### 테스트 인프라

- `compose.postgres-test.yml`: PostgreSQL 17.6 Alpine 개발·테스트 서비스, 각각의
  DB/user/volume, health check, `127.0.0.1:55431/55432` 제한 binding과 안전 label
- `scripts/run-postgres-integration.ps1`: container label, port binding, DB명·사용자,
  JAVA_HOME을 검증한 후에만 Python/Java 파괴적 테스트 실행
- `backend/.env.example`: 개발 기본값과 테스트 override 예시
- `backend/README.md`: 기동·중지, transaction 정책, Alembic 기준선 절차

### FastAPI DB 계층

- `backend/app/config.py`: 선택적 `ACADEMY_DATABASE_URL`
- `backend/app/db/base.py`: SQLAlchemy Declarative Base
- `backend/app/db/safety.py`: 복수 조건 DB allowlist와 fail-closed 검사
- `backend/app/db/session.py`: Engine pool, Session factory, FastAPI `get_db()`
- `backend/app/db/schema.py`: 접속 서버 식별 및 13개 테이블 검증
- `backend/app/db/models/tables.py`: 기존 13개 테이블 ORM metadata
- `backend/app/db/models/__init__.py`

### Alembic

- `backend/alembic.ini`
- `backend/alembic/env.py`
- `backend/alembic/script.py.mako`
- `backend/alembic/versions/001_java_schema_baseline.py`

### 테스트와 의존성

- `backend/tests/test_db_safety.py`
- `backend/tests/test_postgres_integration.py`
- `backend/pyproject.toml`

기존 Java 업무 코드, Java 테스트 기대값, React 소스, API 계약, PostgreSQL 기존 DDL은
수정하지 않았다.

## 3. 추가 의존성

| 패키지 | 버전 | 선정 이유 |
|---|---:|---|
| SQLAlchemy | 2.1.8 | 동기 Engine/Session과 명시적 transaction 경계 |
| Alembic | 1.20.1 | 향후 버전별 PostgreSQL schema 관리 |
| psycopg[binary] | 3.3.8 | Psycopg 3 PostgreSQL driver, 로컬 설치 재현성 |

이번 단계에는 async driver, SQLAlchemy async API, testcontainers, Redis, Kafka를 추가하지
않았다. 버전은 구현일의 PyPI 공개 버전을 확인해 고정했다.

## 4. 기존 DB 구조 분석

정본은 `sql/schema_postgresql.sql`이며 13개 테이블은 다음과 같다.

`student`, `classroom`, `enrollment`, `lesson`, `lesson_result`, `makeup_request`,
`message_template`, `message_draft`, `delivery_job`, `delivery_attempt`, `import_job`,
`import_row`, `import_error`.

확인된 DB 기능:

- 모든 테이블의 PK와 도메인 관계 FK
- 상태값·날짜·점수·집계 수치 CHECK 제약
- 학생 `(name, COALESCE(school_name, ''))` business-key unique expression index
- 시험 회차 NULL 여부를 분리하는 `lesson` partial unique index 2개
- `import_job.idempotency_key` unique index
- message/import/delivery 관련 unique 제약과 cascade/restrict/set-null 정책
- timestamp 및 상태 기본값
- 9개 테이블의 `updated_at` trigger와 `set_updated_at()` 함수

`sql/migrations/002_import_confirm.sql`은 student duplicate preflight, Import Confirm audit
열, 집계 CHECK, idempotency unique index를 추가하는 기존 migration이다. 현재 정본 DDL에는
해당 변경이 이미 반영되어 있다.

## 5. DB 오접속 방지

Python DB 연결은 다음 조건을 모두 만족하지 않으면 `UnsafeDatabaseError`로 중단된다.

1. `ACADEMY_DB_MODE`가 `development` 또는 `test`
2. development는 DB/user/port가 `academy_learningops_dev`/`academy_dev`/`55431`
3. test는 DB/user/port가 `academy_learningops_test`/`academy_test`/`55432`
4. host가 `127.0.0.1`이고 PostgreSQL URL일 것
5. test 모드는 추가로 `ACADEMY_DB_TEST_MODE=1`

allowlist 값은 환경변수로 완화할 수 없도록 코드에 고정했다. 개발 container에는
`academy.destructive-tests=forbidden`, 테스트 container에는 `allowed` label을 사용한다.

통합 실행 스크립트는 추가로 Docker container의
`academy.environment=isolated-test`, `academy.destructive-tests=allowed` label,
loopback port binding, 실제 `current_database()`와 `current_user`를 검사한다. Docker
엔진이 꺼진 상태에서 실행한 실패 경로도 확인했으며 DB 작업 전에 거부됐다.

Java 통합 테스트는 각 테스트 전에 12개 테이블을 `TRUNCATE ... RESTART IDENTITY CASCADE`
한다. 따라서 검증 스크립트 외부에서 임의의 `DB_URL`로 실행하면 안 된다. 이번 실제 실행은
위 container identity를 확인한 뒤에만 수행했다.

Compose의 일반 종료는 `stop`이며 volume을 삭제하지 않는다. `down -v` 같은 파괴적 명령은
일반 절차에 포함하지 않았다.

## 6. SQLAlchemy Session과 transaction 정책

구조는 `Router → Application Service → Repository → Session → PostgreSQL`이다.

- Engine은 lazy singleton이며 `pool_pre_ping`, pool size 5, overflow 5를 사용한다.
- `get_db()`는 요청마다 독립 Session을 만들고 항상 닫는다.
- 예외 발생 시 `get_db()`가 rollback한다.
- 정상 쓰기 transaction과 commit은 Application Service가
  `with session.begin():`으로 한 번만 소유한다.
- Router와 Repository는 commit하지 않는다.
- 기존 Phase 1·2 router에는 DB dependency를 연결하지 않았다.
- SQL echo는 비활성화하여 URL과 SQL parameter의 민감정보 노출을 피했다.

Phase 3에는 실제 CRUD API나 전체 Repository를 만들지 않았다.

## 7. ORM 및 스키마 호환성

13개 ORM model은 기존 테이블·컬럼명, PostgreSQL 타입, nullability, server default, FK
delete 정책, CHECK/UNIQUE/index를 반영한다. 초기 비교에서 `import_job.file_hash`와
`import_row.row_hash`가 ORM `VARCHAR(64)`로 표현된 차이를 발견했고 정본 DDL과 같은
`CHAR(64)`로 수정했다.

수정 후 실제 PostgreSQL schema와 metadata를 `compare_metadata`로 비교한 결과는 `[]`로,
예상하지 않은 Create/Drop/Alter가 없다. Trigger는 SQLAlchemy metadata 비교 대상이 아니므로
PostgreSQL catalog에서 9개 이름을 별도로 검증했다. 두 partial unique index의 WHERE 절도
catalog에서 확인했다.

학생 business key의 동명이인 충돌 가능성은 기존 정책을 그대로 보존했다. 향후 학생 식별
모델을 개선할 때 데이터 migration과 중복 해소 정책이 선행되어야 한다.

## 8. Alembic 기준선 관리

revision은 `001_java_schema_baseline`이다. 빈 개발·테스트 DB의 upgrade는 검토된 기존
`sql/schema_postgresql.sql`을 그대로 실행하므로 Java DDL이 단일 정본이다. 적용 후
`alembic_version`과 13개 테이블, 제약·index·trigger를 확인했다. `upgrade head` 재실행도
성공했다.

이미 기존 테이블이 있는 DB에는 upgrade를 바로 실행하지 않는다.

1. 안전한 읽기 전용 환경에서 schema/metadata diff가 없는지 확인한다.
2. 13개 테이블, trigger, partial index와 Import Confirm 열을 검증한다.
3. 검증 결과를 승인한 경우에만 `alembic stamp 001_java_schema_baseline`을 수동 검토한다.

미식별 기존 DB와 운영 DB에는 upgrade나 stamp를 실행하지 않았다. 이번에 새로 만든 빈
`academy_learningops_dev`에는 기준선 upgrade를 실행했다. 기준선 revision이 저장소 루트의
정본 DDL 경로에 의존한다는 점은 배포 패키징 시 고려해야 한다. 별도 migration artifact로
배포할 경우 DDL을 함께 포함해야 한다.

## 8.1 최초 구축 결과

Docker 조사에서 기존 `academy-postgres`(PostgreSQL 16, host 5432, 익명 volume)를
발견했지만 프로젝트 identity label이 없어 조회 외에는 변경하지 않았다.

새로 구축한 환경:

| 용도 | Container | DB / User | Host port | Volume | 상태 |
|---|---|---|---:|---|---|
| 개발 | `academy-learningops-postgres-dev` | `academy_learningops_dev` / `academy_dev` | 55431 | `academy_learningops_postgres_dev_data` | 기준선 적용 |
| 테스트 | `academy-learningops-postgres-test` | `academy_learningops_test` / `academy_test` | 55432 | `academy_learningops_postgres_test_data` | 기준선 적용 |

개발 DB에서 FastAPI의 `create_db_engine()`으로 실제 연결해 PostgreSQL 17.6, 현재 DB/user,
13개 업무 테이블과 Alembic head를 확인했다. catalog 집계는 FK 14개, 명시적 UNIQUE
constraint 6개, 업무 index 52개, trigger 9개였다. ORM 비교 결과는 `[]`였다. 테스트 DB는
동일 기준선에 Python/Java 통합 테스트를 수행했다. 최종 확인 시 개발 DB의 `student`와
`import_job`은 모두 0건으로 테스트 데이터가 유입되지 않았다. DDL 자체 수정은 필요하지
않았다.

## 9. 실제 테스트 결과

### Python

| 검증 | 결과 | 세부 결과 |
|---|---:|---|
| Ruff | PASS | 오류 0 |
| 기본 pytest | PASS | 30 passed, PostgreSQL 5 intentionally skipped |
| PostgreSQL pytest | PASS | 5 passed |
| DB 연결/잘못된 자격 증명 | PASS | 정상 identity 및 안전 실패 |
| Student CRUD/rollback | PASS | 합성 데이터만 사용 |
| FK/CHECK/UNIQUE/NULL/partial unique | PASS | 실제 PostgreSQL 제약 확인 |
| Session 격리/실패 복구 | PASS | 독립 Session 및 rollback 후 정상 처리 |
| Alembic/13 tables/trigger | PASS | revision, 재실행, catalog 검증 |
| ORM schema diff | PASS | `[]` |

기본 pytest의 5개 skip은 의도된 안전 기본값이다. DB 테스트는
`ACADEMY_RUN_POSTGRES_INTEGRATION=1` 및 모든 allowlist 조건이 있을 때만 실행된다.

### Java

`PostgreSqlDaoIntegrationTest` 실제 실행 결과:

| 테스트 | 결과 | 검증 내용 |
|---|---:|---|
| `actualPostgreSqlSupportsImportMessageMakeupAndDeliveryHistory` | PASS | CSV/XLSX import와 message/makeup/delivery 저장 |
| `actualPostgreSqlEnforcesForeignKeysAndRollsBackTransactions` | PASS | FK 및 rollback |
| `importConfirmIsAtomicAndIdempotent` | PASS | 원자성, replay, 실패 rollback, history |
| `studentBusinessKeyAndImportCountsAreEnforced` | PASS | expression unique와 집계 CHECK |
| `concurrentIdempotencyKeyPersistsOnlyOnce` | PASS | 동시 동일 key 단일 저장 |

Java 전체: 47 passed, 0 failed, 0 errors, 0 skipped.

### 기존 API·프론트엔드

| 검증 | 결과 |
|---|---:|
| Message Preview Java/Python 계약 | 7/7 PASS |
| Import Preview Java/Python 계약 | 27/27 PASS |
| React Vitest | 5 files, 15 tests PASS |
| React production build | PASS |

React 테스트에는 jsdom pseudo-element 안내가 있었고 build에는 기존 500 kB 초과 chunk
경고가 있다. 기능 실패는 아니다. Python에는 기존 Starlette TestClient deprecation 경고가
남아 있으며 불필요한 패키지 update는 하지 않았다.

## 10. 실행 명령

```powershell
cd D:\refactor\backend-architecture
docker compose -f compose.postgres-test.yml up -d --wait
$env:JAVA_HOME = '<Java 17+ JDK directory>'
.\scripts\run-postgres-integration.ps1
docker compose -f compose.postgres-test.yml stop
```

기본 비DB 검증:

```powershell
cd D:\refactor\backend-architecture\backend
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\pytest.exe -q
```

## 11. 해결된 문제와 남은 문제

해결:

- Java PostgreSQL 통합 테스트 5개가 실제 DB에서 검증됨
- 테스트 DB와 개발·운영 DB의 연결 설정 및 volume 분리
- 기본 비활성화와 복수 identity 검증
- SQLAlchemy Engine/Session/rollback infrastructure
- 13개 ORM metadata 및 기존 DDL 호환성 확인
- Alembic 기준선과 재현 가능한 빈 DB 초기화

남음:

- Java 테스트 자체에는 allowlist가 없으므로 반드시 wrapper를 사용해야 한다.
- Alembic baseline은 정본 DDL 파일과 함께 배포되어야 한다.
- Session pool의 실제 운영 부하/장시간 장애 복구는 아직 검증하지 않았다.
- 기존 DB stamp 절차는 운영·개발 DB 안전 원칙에 따라 실제 실행하지 않았다.
- Import Confirm/History의 Python Repository와 API는 아직 없다.
- 브라우저 수동 E2E는 수행하지 않았다.

## 12. Phase 4 착수 판단

독립 DB, transaction, idempotency 동시성, schema 기준선이 실제 PostgreSQL에서 검증되어
Import Confirm의 Python 이식을 시작할 기술적 기반은 마련됐다. Phase 4는 공통 Confirm
fixture와 Repository transaction 테스트부터 시작할 수 있다.

단, 운영 전환 가능 상태를 의미하지는 않는다. Python Confirm 구현 후 Java/Python 결과,
동시 idempotency, rollback, audit history를 동일 테스트 DB에서 다시 비교해야 한다.
