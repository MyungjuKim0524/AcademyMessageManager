# Academy LearningOps Phase 4 — Secure Import Database API Migration

작성일: 2026-11-09  
판정: **구현 완료, 최종 DB/계약 재검증 BLOCKED — Phase 4 전체 완료로 판정하지 않음**

## 1. 구현 요약

기존 Java의 Import History 목록·상세와 Import Confirm을 FastAPI로 이식했다.

- `GET /api/imports`
- `GET /api/imports/{id}`
- `POST /api/imports/confirm`

History는 DB pagination, `started_at DESC, id DESC` 안정 정렬, 필요한 audit 컬럼만 조회하고
원본 파일명·hash·Idempotency-Key·request ID를 반환하지 않는다. Confirm은 Preview 응답을
신뢰하지 않고 업로드 파일을 다시 파싱·검증하며, 업무 데이터와 import audit를 하나의
SQLAlchemy transaction으로 저장한다.

DB API는 인증/RBAC가 없는 상태이므로 기본 비활성화된다. 명시적 활성화, loopback bind,
development/test DB allowlist가 모두 일치해야 접근할 수 있다. 이 local gate는 인증을
대체하지 않으며 Phase 5에서 실제 RBAC 검사로 교체해야 한다.

2026-11-08 독립 PostgreSQL 테스트 DB에서 Phase 3 테스트 5개와 신규 Phase 4 테스트
5개, 총 10개가 실제 통과했다. 이후 History 조회를 필요한 컬럼 projection으로 개선하고
Secret 고정값을 제거했다. 2026-11-09 최종 재검증 시 Docker Desktop 자체가 stale inference
socket 오류로 시작되지 않아, 이 마지막 변경 상태의 PostgreSQL 테스트와 Phase 4 성공
계약 비교는 재실행하지 못했다. 따라서 전체 Phase 4는 완료로 판정하지 않는다.

## 2. 변경 파일

### API와 보안

- `backend/app/security.py`: DB API local-only gate 및 Phase 5 권한 경계
- `backend/app/config.py`: API host와 DB API enable 설정
- `backend/app/middleware.py`: History/Confirm method, multipart, 크기 제한, request ID
- `backend/app/main.py`: Confirm multipart 오류 호환 처리
- `backend/app/modules/imports/router.py`: History/Confirm endpoint
- `backend/app/modules/imports/schemas.py`: History/Confirm camelCase 응답

### Service와 Repository

- `backend/app/modules/imports/history.py`: History service/repository
- `backend/app/modules/imports/confirm.py`: 재검증, transaction, 멱등성, 저장/audit
- `backend/app/modules/imports/service.py`: Preview와 Confirm이 공유하는 parser 진입점

### 테스트·도구·설정

- `backend/tests/test_api.py`: 기본 비활성화, 외부 bind 차단, 오류 redaction/session 정리
- `backend/tests/test_secure_import_integration.py`: 실제 PostgreSQL History/Confirm 테스트
- `backend/scripts/compare_secure_import_contract.py`: 순차 단독 write-owner 계약 비교
- `compose.postgres-test.yml`: DB 비밀번호를 필수 환경변수로 변경
- `scripts/run-postgres-integration.ps1`: test 비밀번호 필수 환경변수 및 URL encoding
- `backend/.env.example`: 실제 Secret이 없는 placeholder
- `backend/README.md`: DB API 활성화 제한과 실행법

Java 업무 코드, React 소스, 기존 DDL과 OpenAPI 문서는 변경하지 않았다.

## 3. Phase 4A — Import History

### 계약

- page 기본값 0, size 기본값 20
- page 0 이상, size 1~100
- 중복/알 수 없는 query parameter 거부
- 잘못된 숫자와 SQL injection 형태 입력을 400으로 거부
- 양의 정수 ID만 허용, 미존재 ID는 404
- `started_at DESC, id DESC`, DB LIMIT/OFFSET
- 전체 count와 `totalPages` 계산
- 조회 응답은 audit 집계와 timestamp만 포함

### 계층

`Router → ImportHistoryService → ImportHistoryRepository → Session → PostgreSQL`

Router에는 SQL이 없고 Repository의 정렬·필터는 SQLAlchemy expression 또는 고정 SQL만
사용한다. 외부 입력은 SQL 문자열·ORDER BY·테이블 이름에 결합되지 않는다.

### 검증 상태

| 항목 | 상태 | 근거 |
|---|---|---|
| 빈 목록, 목록/상세, pagination | VERIFIED | 2026-11-08 실제 PostgreSQL pytest |
| 잘못된 page/size/ID, 404 | VERIFIED | 실제 PostgreSQL pytest 및 비DB API 테스트 |
| 개인정보 최소 응답 | VERIFIED | 금지 필드 집합 assertion |
| SQL injection 형태 입력 | VERIFIED | `page=0 OR 1=1` 400 |
| DB 오류 redaction | VERIFIED | 제어된 SQLAlchemy 오류가 일반 `DATABASE_ERROR`로 변환 |
| Session 정리 | VERIFIED | dependency override의 finally 실행 assertion |
| 기본 비활성화/외부 bind 차단 | VERIFIED | 404 `DB_API_DISABLED` 테스트 |
| 필요한 컬럼 projection의 실제 PG 재실행 | NOT VERIFIED | projection 개선 후 Docker 시작 실패 |
| 대량 데이터 성능·EXPLAIN | NOT VERIFIED | 최종 DB 환경 불가, 최적화 효과 주장 안 함 |

Phase 4A 구현에서 차단 수준의 코드 결함은 발견되지 않았지만 최신 projection 변경의 실제
DB 재실행이 필요하다.

## 4. Phase 4B — Import Confirm

### 보존한 규칙

- UUID `Idempotency-Key` 필수
- 원본 CSV/XLSX 재업로드 및 Preview parser/validator 재사용
- 10 MiB, 5,000행, 64열, 셀 5,000자 제한
- 학생 `name + school_name`, 반 `name + class_type`
- 수업 `classroom + lesson_date + exam_round`
- 결과 `lesson + enrollment`
- INSERT/UPDATE/SKIP의 Java ordinal 우선순위 보존
- 학생 보호자 정보, enrollment 상태, lesson result 변경 감지
- 원본 파일명 대신 `redacted-upload`, SHA-256은 DB 내부 audit에만 사용
- `import_job`, 업무 데이터, `import_row`를 동일 transaction으로 저장

### Transaction과 멱등성

파일 파싱·검증은 transaction 전에 수행한다. Repository가 `with session.begin():`으로
transaction을 단독 소유하고 Router나 하위 helper는 commit하지 않는다.

`import_job.idempotency_key` UNIQUE index와
`INSERT ... ON CONFLICT DO NOTHING RETURNING id`로 claim한다.

- 동일 key + 동일 hash/행 수 + SUCCESS: 기존 summary, `replayed=true`
- 동일 key + 다른 hash/행 수: 409 `IMPORT_CONFLICT`
- 처리 중/미완료 key: 409 `IMPORT_ALREADY_PROCESSED`
- 동일 key 동시 요청: PostgreSQL unique/transaction 대기 후 하나만 저장

### 검증 상태

| 항목 | 상태 | 근거 |
|---|---|---|
| 정상 Confirm, audit, History 연결 | VERIFIED | 2026-11-08 실제 PostgreSQL pytest |
| 잘못된/누락 key | VERIFIED | 실제 API 테스트 |
| 오류 행 재검증 거부 | VERIFIED | `IMPORT_VALIDATION_FAILED` |
| 동일 key replay | VERIFIED | 같은 import ID/summary, replay flag |
| 동일 key + 다른 파일 | VERIFIED | 409 conflict |
| 동일 key 동시 요청 | VERIFIED | 2 요청, import_job 1건 |
| 중간 persistence 실패 rollback | VERIFIED | 제어된 failure 후 업무/audit 0건 |
| DB 제약 및 Java 원자성 | VERIFIED | Phase 3 Java PostgreSQL 5/5 |
| DB 연결 실패 오류 비노출 | VERIFIED | 제어된 오류 redaction; 실제 network 단절은 미실행 |
| Commit/Audit 전용 장애 주입 | NOT VERIFIED | 별도 commit/audit fault injector 미구현 |
| 여러 서로 다른 Confirm 동시 실행 | NOT VERIFIED | 실제 PostgreSQL 시나리오 미실행 |
| 최종 코드의 실제 PostgreSQL 재실행 | BLOCKED | Docker Desktop 엔진 시작 실패 |

## 5. Java/Python 계약 비교

Phase 1 Message Preview 7/7, Phase 2 Import Preview 27/27은 2026-11-09 실서버에서 다시
통과했다.

Phase 4 도구는 Java 실행 → DB 초기화 → Python 실행 순으로 하나의 backend만 write owner가
되도록 구현했다. 비교 대상은 Confirm, replay, History 목록/상세, pagination과 오류이다.
독립 실행의 timestamp 실제 값만 명시적으로 비본질적 차이로 분류하며 필드 존재와 null
구조는 비교한다.

첫 실행 결과:

- 입력 오류 5개: Java/Python 일치
- Python Confirm/History: 200 정상
- Java `mvn exec:java` DB API: `DATABASE_ERROR` 500
- 동일 환경변수의 Java `PostgreSqlDaoIntegrationTest`: 5/5 PASS

따라서 Java 업무/DB 테스트가 아니라 Maven in-process API 실행의 DB 환경 전달 문제로
분류했다. 별도 JVM classpath 실행으로 재검증하려 했으나 이후 Docker Desktop 엔진이
시작되지 않아 성공 비교를 완료하지 못했다.

Phase 4 성공 계약 판정: **BLOCKED**. 불일치를 정상화하거나 숨기지 않았다.

## 6. 보안 위협 및 대응

| 위협 | 상태 | 대응/근거 |
|---|---|---|
| Broken Authentication / Function Authorization | VERIFIED(임시 제한) | 기본 disabled + loopback + DB allowlist. 실제 인증은 미구현 |
| BOLA | NOT VERIFIED | 사용자/담당 반 개념이 없어 Phase 5 RBAC 필요 |
| SQL Injection | VERIFIED | bound parameter, 고정 정렬, 비정상 query 테스트 |
| Mass Assignment | VERIFIED | multipart file/key만 수신, 내부 PK/status/count/time 서버 계산 |
| Resource Consumption | VERIFIED | Preview와 같은 파일/행/열/셀/multipart 제한 |
| Security Misconfiguration | VERIFIED | 외부 bind에서 DB API 404, test mode 이중 switch |
| Sensitive Data Exposure | VERIFIED | History 금지 필드, DB 오류/SQL/stack trace redaction |
| Unsafe Error Handling | VERIFIED | 호환 오류 envelope, generic 500, no-store/보안 header |
| Transaction partial write | VERIFIED | 실제 PG rollback 테스트 |
| Idempotency race | VERIFIED | 실제 PG 동시 동일 key 테스트 |
| Runtime DB least privilege | NOT VERIFIED | 계정 분리는 됐으나 schema owner/runtime role 분리는 후속 |

`authorization_boundary()`가 Phase 5 교체 지점이다. 이 함수가 local gate만 수행하므로
운영 공개 승인을 의미하지 않는다.

## 7. Secret 및 의존성 검토

- Compose·PowerShell·`.env.example`의 고정 DB 비밀번호 제거: VERIFIED
- 실제 비밀번호는 `ACADEMY_DEV_DB_PASSWORD`, `ACADEMY_TEST_DB_PASSWORD`에서만 수신
- URL용 비밀번호는 wrapper에서 encoding하고 출력하지 않음
- `.env`, key/certificate, credentials 파일은 `.gitignore` 대상
- 대표 AWS key/private key/이전 고정 password 패턴 scan: 결과 0

`pip-audit 2.10.1` 실행 결과 애플리케이션 패키지가 아니라 가상환경 도구
`pip 25.0.1`에서 중복 포함 12개 advisory가 탐지됐다. 프로젝트 runtime dependency에서
별도 취약 패키지는 보고되지 않았다. 불필요한 패키지 업데이트 금지 원칙 때문에 pip를
임의 업데이트하지 않았다. `pip-audit` 자체는 검사 도구로 가상환경에만 설치했고
`pyproject.toml` 의존성에는 추가하지 않았다.

## 8. 성능 검토

History query는 DB count + 제한된 column projection의 page query 2개이며 N+1이 없다.
정렬은 `(started_at DESC, id DESC)`이고 기존 `idx_import_job_started_at`을 활용할 수 있다.
동률 안정 정렬을 위한 id가 복합 index에는 포함되지 않으므로 대량 데이터 EXPLAIN 결과에
따라 `(started_at DESC, id DESC)` index를 검토한다. 측정 없이 migration은 추가하지 않았다.

Confirm은 파일 검증을 transaction 밖에서 수행하고 DB transaction 시간을 줄였다. 행마다
최대 다섯 entity 조회/변경과 audit 1회를 수행한다. 5,000행 성능 측정과 batch 최적화는
NOT VERIFIED이며 무결성 검증을 제거하지 않는다.

## 9. 테스트 결과

| 실행 | 결과 | 시점/비고 |
|---|---:|---|
| Ruff | PASS | 최종 코드, 2026-11-09 |
| Python 비DB pytest | 33 PASS | 최종 코드 |
| Python 기본 pytest | 33 PASS, 10 SKIP | DB 명시 실행 기본 비활성화 |
| Python PostgreSQL | 10 PASS | 2026-11-08, projection/Secret 최종 변경 전 |
| Java Maven | 42 PASS, 5 SKIP | 2026-11-09 Docker 불가 |
| Java PostgreSQL | 5 PASS | 2026-11-08 및 DB 사용 가능 시 재확인 |
| React Vitest | 15 PASS | 2026-11-09 |
| React production build | PASS | 기존 500 kB chunk 경고 |
| Phase 1 계약 | 7/7 PASS | 2026-11-09 |
| Phase 2 계약 | 27/27 PASS | 2026-11-09 |
| Phase 4 오류 계약 | PASS | 5개 입력 오류 일치 |
| Phase 4 성공 계약 | BLOCKED | Java API DB 500 후 Docker 엔진 시작 실패 |
| FastAPI OpenAPI 경로 | PASS | History/Confirm/multipart 확인 |
| pip-audit | FAIL(tooling) | pip 25.0.1 advisory, app package 별도 탐지 없음 |

FastAPI TestClient의 기존 Starlette deprecation warning과 React jsdom pseudo-element 안내는
기능 실패가 아니다.

2026-11-09 최종 인계 직전 재실행에서는 Ruff를 `--no-cache`로 다시 실행해 통과했다.
pytest는 테스트 수집 후 첫 TestClient 요청에서 정지했으며, `faulthandler` 스택은
애플리케이션 진입 전 Windows `asyncio.windows_events._make_self_pipe()`의 내부
`socket.accept()` 대기를 가리켰다. 이 실행은 중단했으며 PASS로 기록하지 않았다. 직전의
동일 코드 33 PASS 결과는 보존하되, Windows 재시작 후 재실행해야 한다.

## 10. Docker 차단 원인

Docker Desktop UI에서 다음 오류를 직접 확인했다.

`starting services: initializing Inference manager ... remove .../Docker/run/dockerInference: The file cannot be accessed by the system`

해당 경로는 0-byte reparse point였다. 데이터 volume을 보호하기 위해 factory reset은 하지
않았다. 같은 폴더의 백업 이름으로 이동하는 복구도 OS가 access denied하여 실패했다.
Windows 재시작 또는 Docker 공식 진단 후 재시도가 필요하다. volume 삭제 명령은 실행하지
않았다.

같은 시점에 Python TestClient용 asyncio 내부 socketpair 생성도 멈췄으므로 Docker만의
애플리케이션 설정 문제가 아니라 Windows 로컬 소켓 계층 이상 가능성이 높다. 코드 변경으로
우회하지 않고 재시작 후 재검증하는 것이 안전하다.

## 11. 남은 위험과 기술 부채

1. Docker 복구 후 최종 코드의 PostgreSQL 10개 이상 테스트 재실행
2. Java API를 별도 JVM으로 기동하여 Phase 4 성공 계약 비교 완료
3. History 대량 합성 데이터 EXPLAIN/latency 측정
4. Commit 실패, audit 실패, 여러 상이한 파일 동시 요청의 제어된 장애 테스트
5. schema owner와 runtime 최소권한 role 분리
6. Phase 5 사용자 인증, ADMIN/TEACHER/ASSISTANT RBAC와 담당 반 scope
7. TestClient deprecation 및 pip 도구 advisory를 별도 dependency maintenance 작업으로 처리

## 12. Phase 5 착수 판단

RBAC 경계와 DB API 기본 차단은 구현되어 Phase 5 설계·인증 작업은 시작할 수 있다.
그러나 Phase 4를 완료 처리하거나 DB API를 운영 공개해서는 안 된다. Docker 복구 후 최종
PostgreSQL/계약 검증을 먼저 완료하고, Phase 5 인증이 붙기 전까지 local-only gate를
유지해야 한다.

## 13. 재검증 명령

실제 Secret 값은 shell 환경변수에만 설정한다.

```powershell
cd D:\refactor\backend-architecture
$env:ACADEMY_DEV_DB_PASSWORD = '<local development secret>'
$env:ACADEMY_TEST_DB_PASSWORD = '<different local test secret>'
docker compose -f compose.postgres-test.yml up -d --wait
$env:JAVA_HOME = '<Java 17+ JDK directory>'
.\scripts\run-postgres-integration.ps1
```

두 서버를 테스트 DB에 연결한 후:

```powershell
cd backend
python scripts\compare_secure_import_contract.py `
  --java-base-url http://127.0.0.1:8080 `
  --python-base-url http://127.0.0.1:8000
```
