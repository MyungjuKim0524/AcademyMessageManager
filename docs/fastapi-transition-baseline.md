# 기존 기능 보존 및 FastAPI 전환 준비 기준선

> 기록일: 2026-11-04 (Asia/Seoul)  
> 기준 경로: `D:\refactor\backend-architecture`  
> 범위: 기존 업무 로직과 DB를 변경하지 않고 현재 동작·테스트 근거와 FastAPI 전환 준비사항만 기록한다.

## 1. 결론

- Java 비DB 테스트는 **47개 중 42개 통과, PostgreSQL 통합 테스트 5개 skipped, 실패 0개**로 확인했다.
- React 테스트는 **5개 파일, 15개 테스트 모두 통과**했고 TypeScript/Vite 배포 빌드도 성공했다.
- Import Preview, Import Confirm의 서비스/API 경계, Import History, Message Preview는 위 자동 테스트로 현재 동작을 확인했다.
- 실제 PostgreSQL의 제약조건, rollback, atomic import, 동시 Idempotency-Key 처리는 **이번 실행에서 확인하지 못했다**. 전용 테스트 DB 자격 증명이 없고 해당 테스트가 테이블을 `TRUNCATE`하므로 운영 DB 오접속 위험을 피하기 위해 실행하지 않았다.
- FastAPI 첫 전환 API는 DB를 쓰지 않고 계약이 작은 `GET /api/health`, `POST /api/messages/preview`, `POST /api/imports/preview` 순서를 추천한다. DB 쓰기와 멱등성이 결합된 Confirm은 공통 fixture와 전용 PostgreSQL 검증을 마련한 뒤 전환한다.

## 2. 실행 환경과 검증 결과

### 2.1 실행한 명령

```powershell
$env:JAVA_HOME='D:\IntelliJ IDEA 2026.2.0.1\jbr'
mvn test

cd frontend
npm test
npm run build
```

패키지 설치나 버전 업데이트는 하지 않았다. 이미 존재하는 Maven/Node 의존성만 사용했다.

### 2.2 결과

| 검증 | 실제 결과 | 판정 |
|---|---|---|
| Java/JUnit 기본 suite | Tests run: 47, Failures: 0, Errors: 0, Skipped: 5; BUILD SUCCESS | 비DB 단위·서비스·HTTP API 테스트 통과 |
| PostgreSQL 통합 suite | 5개 모두 skipped | 미검증 |
| React/Vitest | 5 files passed, 15 tests passed | 통과 |
| React production build | 3,280 modules transformed, build 성공 | 통과 |

프론트 빌드에는 minified chunk 하나가 500kB를 넘는다는 경고가 있었다. 기능 보존 결과에는 영향이 없으며 이번 작업 범위에서 번들 구조나 패키지를 변경하지 않았다.

Java 테스트는 프로젝트의 target이 Java 17이지만 로컬에서 발견된 JBR 25로 실행했다. Java 17 CI에서도 별도 확인하는 것이 재현성 측면에서 필요하다.

## 3. 기능별 현재 동작과 테스트 근거

### 3.1 Import Preview

현재 동작:

- `POST /api/imports/preview`에 multipart `file`을 받는다.
- `.csv`, `.xlsx`만 허용하며 10MB, 5,000행, 64열, 셀 길이, 단일 XLSX 시트 정책을 적용한다.
- 서버 메모리에서 파싱·검증하며 DB에 저장하지 않는다.
- 각 행에 `rowNumber`, 최소 표시 데이터, `valid`, field error를 반환한다.
- 파일명을 저장 경로로 사용하지 않고 formula-like/HTML 입력을 실행하지 않는다.

코드 근거:

- `ImportPreviewHandler`
- `ImportPreviewService`
- `ImportPreviewRowValidator`
- `MultipartFormDataReader`
- React `ImportPreviewPage`, `validation.ts`

실행 근거:

- `ImportPreviewApiTest`: 4개 통과
- `ImportPreviewServiceTest`: 6개 통과
- `MultipartFormDataReaderTest`: 1개 통과
- `SampleImportTest`: CSV/XLSX 등가성 1개 통과
- React Import Preview/Confirm UI 및 파일 검증 관련 7개 테스트 통과

확인된 경계는 traversal 형태 파일명, 정확한 파일 크기 경계, 5,000/5,001행, 열 제한, malformed file/multipart, 잘못된 method, formula-like/HTML 값이다.

### 3.2 Import Confirm

현재 동작:

- `POST /api/imports/confirm`은 multipart `file`과 UUID `Idempotency-Key`를 요구한다.
- Preview JSON을 저장 근거로 받지 않고 업로드된 원본을 다시 파싱·검증한다.
- 유효하지 않은 key나 행은 repository 호출 전에 거부한다.
- repository 구현은 학생·반·수강·수업·수업결과를 INSERT/UPDATE/SKIP으로 판정하고 audit과 함께 한 transaction에서 저장하도록 작성되어 있다.

코드 근거:

- `ImportConfirmHandler`
- `ImportConfirmService.confirm`
- `JdbcImportConfirmRepository.confirm`
- `ImportConfirmRepository`

실행 근거:

- `ImportConfirmApiTest`: UUID key 성공과 missing/invalid key 거부 1개 통과
- `ImportConfirmServiceTest`: 원본 재파싱·개인정보 없는 audit 인자, invalid 요청의 repository 미호출 2개 통과
- React에서 유효한 Preview만 Confirm하고 저장 요약을 표시하는 테스트 통과

제한:

- 실제 DB commit/rollback과 INSERT/UPDATE/SKIP 결과는 이번 실행에서 검증되지 않았다.

### 3.3 Import History

현재 동작:

- `GET /api/imports?page=0&size=20`은 최신순 page를 반환한다. page는 0 이상, size는 1~100이다.
- `GET /api/imports/{id}`는 단건을 반환하며 잘못된 ID는 400, 없는 ID는 404다.
- 응답에는 상태·건수·처리 시각만 포함되고 파일명, file hash, request/idempotency key, 학생 개인정보는 포함되지 않는다.

코드 근거:

- `ImportHistoryHandler`
- `ImportHistoryService`
- `JdbcImportHistoryRepository`
- React `ImportHistoryPage`

실행 근거:

- `ImportHistoryApiTest`: 목록·상세·pagination/ID/404 안전 오류 테스트 통과
- `ImportHistoryServiceTest`: 기본 page/size, 상세, 잘못된 입력 테스트 2개 통과
- React History 빈 상태, 최소 상세, 오류 구분 테스트 3개 통과

제한:

- 실제 PostgreSQL의 `import_job` 조회 결과와 정렬은 이번 실행에서 검증되지 않았다.

### 3.4 Message Preview

현재 동작:

- `POST /api/messages/preview`는 학생/반/수업유형/수업일/출결과 선택적 등급·점수를 받는다.
- 선택 플래그가 켜지고 값이 존재하는 학습 항목만 메시지에 포함한다.
- unknown JSON, 필수값 누락, enum/점수 관계 오류, 잘못된 Content-Type/method/origin, 16KB 초과 요청을 거부한다.
- 응답은 생성 메시지만 반환하며 입력 개인정보를 추가로 반사하지 않는다.

코드 근거:

- `MessagePreviewHandler`
- `MessagePreviewValidator`
- `MessageGenerationService`
- `LearningMessageComposer`
- `TestScore`

실행 근거:

- `ApiServerTest`: health 포함 10개 HTTP 경계 테스트 통과
- `LearningMessageComposerTest`: 선택되고 비어 있지 않은 section만 조합하는 테스트 통과
- `TestScoreTest`: 파싱, 빈 값/만점, 잘못된 점수 3개 통과
- React Message Preview 성공·클라이언트 검증·API 실패 3개 통과

### 3.5 DB 데이터 검증 및 트랜잭션

코드에서 확인한 설계:

- PostgreSQL DDL은 FK, UNIQUE, CHECK로 학생 business key, 수강/수업/결과 중복, 상태, 점수 범위, import count를 제한한다.
- `JdbcImportConfirmRepository.confirm`과 기존 `AcademyImportDAO.importRows`는 명시적으로 transaction을 시작하고 실패 시 rollback하도록 작성되어 있다.
- Confirm 성공 audit과 업무 데이터 변경은 같은 connection에서 처리한다.
- `DataValidationService`는 DB 접근 전 business validation과 원본 행 번호 오류를 제공한다.

실행 근거:

- `DataValidationServiceTest` 1개 통과
- PostgreSQL 전용 `PostgreSqlDaoIntegrationTest` 5개는 skipped
- 따라서 DB 제약, FK 위반 rollback, 실제 atomicity를 구현 완료 근거로 주장하지 않는다.

실행하지 않은 이유:

- `DB_URL`, `DB_USER`, `DB_PASSWORD`가 모두 미설정이었다.
- 통합 테스트의 `@BeforeEach`는 관련 테이블을 `TRUNCATE`한다.
- 전용 테스트 DB임을 확인할 수 없으므로 제약조건상 실행하지 않았다.

### 3.6 Idempotency-Key

코드에서 확인한 설계:

- UUID 형식만 허용한다.
- `import_job.idempotency_key`에 unique index가 있다.
- 같은 key와 같은 file hash의 성공 요청은 기존 결과를 `replayed=true`로 반환한다.
- key 재사용 충돌과 동시 요청은 DB unique constraint/transaction으로 방어하도록 작성되어 있다.

실행 근거:

- API 형식 검증과 service delegation은 비DB 테스트로 통과했다.
- DB 단위의 원자성·재생·동시 요청 단일 저장은 `PostgreSqlDaoIntegrationTest.importConfirmIsAtomicAndIdempotent`와 `concurrentIdempotencyKeyPersistsOnlyOnce`에 정의되어 있으나 이번에는 skipped됐다.

판정:

- **요청 검증은 확인됨. 실제 DB 멱등성은 코드와 테스트가 존재하지만 이번 실행 근거는 없음.**

## 4. 기존 OpenAPI 계약 검토

현재 OpenAPI 3.1 계약은 다음 6개 operation을 정의한다.

| operationId | Method/Path | 주요 계약 |
|---|---|---|
| `getHealth` | `GET /api/health` | `{status: "UP"}` |
| `previewMessage` | `POST /api/messages/preview` | JSON → `{message}` |
| `previewImport` | `POST /api/imports/preview` | multipart file → row validation summary |
| `confirmImport` | `POST /api/imports/confirm` | UUID header + multipart file → persisted summary/replayed |
| `listImportHistory` | `GET /api/imports` | page/size → page response |
| `getImportHistory` | `GET /api/imports/{id}` | positive int64 ID → item |

유지해야 할 계약:

- camelCase JSON 필드명
- page 0 기반, size 기본 20/최대 100
- `Idempotency-Key` header와 UUID 형식
- multipart field 이름 `file`
- 오류 envelope `{code, message, fields}`와 기존 error code
- Preview/History의 개인정보 최소 응답
- Import Confirm 성공 시 `200`과 `replayed` 의미
- date는 `YYYY-MM-DD`, timestamp는 ISO-8601

보완이 필요한 부분:

1. 실제 공통 security wrapper는 모든 API에서 403/405/500을 반환할 수 있지만 operation별 OpenAPI response가 일부 빠져 있다.
2. `ImportPreviewResponse.rows[].data`는 실제 데이터보다 축약된 schema이므로 Java 응답과 React 사용 필드를 fixture로 고정해야 한다.
3. CORS와 요청 크기 정책은 설명 문서에는 있지만 machine-readable contract로는 충분하지 않다.
4. 인증 도입 전 계약이라 security scheme/401이 없다. 기존 API 전환과 인증 계약 변경은 별도 단계로 분리해야 한다.
5. OpenAPI와 구현을 자동 대조하는 테스트가 없다.

업무 동작을 바꾸지 않고 먼저 OpenAPI response 누락과 example을 보완하고, Java/Python 양쪽에 동일 contract test를 적용하는 것을 권장한다.

## 5. Java/Python 공통 테스트 데이터 목록

### 5.1 그대로 재사용할 파일

| 파일 | 공통 검증 목적 |
|---|---|
| `data/sample_students.csv` | 정상 CSV 파싱, 한글/코드 상태, 점수 변환 |
| `data/sample_students.xlsx` | 정상 XLSX 파싱과 CSV 결과 등가성 |
| `sql/schema_postgresql.sql` | 전용 테스트 DB baseline |
| `sql/seed_postgresql.sql` | 비식별 DB fixture |
| `sql/test_postgresql_constraints.sql` | FK/UNIQUE/CHECK 기대값 |

### 5.2 코드에서 공통 fixture 파일로 추출할 사례

기존 Java 테스트의 문자열/동적 생성 데이터를 별도 `tests/fixtures/contract/`에 JSON/CSV/binary fixture로 복사해 Java와 Python이 함께 읽도록 한다. 기존 테스트를 삭제하거나 이동하지 않는다.

| fixture 후보 | 기대 결과 |
|---|---|
| `message-preview/regular-full.json` | 모든 선택 section 포함, 200 |
| `message-preview/optional-blank.json` | 빈 section 제외, 200 |
| `message-preview/missing-required.json` | `VALIDATION_ERROR`, 400 |
| `message-preview/invalid-enum.json` | `VALIDATION_ERROR`, 400 |
| `message-preview/invalid-score.json` | correct > total 거부, 400 |
| `message-preview/unknown-field.json` | unknown JSON 거부, 400 |
| `imports/valid.csv` | 전행 valid, summary 일치 |
| `imports/mixed-valid-invalid.csv` | 원본 row number와 field errors 일치 |
| `imports/valid.xlsx` | CSV와 같은 domain 결과 |
| `imports/5000-rows.csv` | 허용 |
| `imports/5001-rows.csv` | `ROW_LIMIT_EXCEEDED`, 413 |
| `imports/64-columns.csv` | 허용 경계 |
| `imports/65-columns.csv` | 열 제한 오류 |
| `imports/formula-like.csv` | 실행하지 않고 invalid/text 처리 |
| `imports/html-value.csv` | HTML로 실행하지 않고 text 처리 |
| `imports/malformed.csv`, `malformed.xlsx` | 안전한 parse error |
| `imports/empty.csv`, `unsupported.txt`, `macro.xlsm` | file/type validation error |
| `imports/size-10mb.bin`, `size-over-10mb.bin` | 정확한 크기 경계 |
| `imports/traversal-filename.multipart` | 경로 traversal 영향 없음 |
| `idempotency/same-key-same-file.json` | 동일 결과, `replayed=true` |
| `idempotency/same-key-different-file.json` | 409 conflict |
| `idempotency/concurrent-same-key.json` | DB 저장 1회 |
| `history/empty-page.json` | 빈 items와 올바른 page metadata |
| `history/privacy-minimal-item.json` | 금지 필드 미포함 |
| `errors/*.json` | error code/status/envelope 고정 |

대용량 fixture는 저장소 용량을 늘리지 않도록 테스트에서 결정적으로 생성하되, Java/Python이 같은 생성 규칙과 SHA-256을 사용하도록 manifest를 둔다.

## 6. FastAPI 우선 전환 추천

### 1순위: `GET /api/health`

- DB·업무 규칙이 없고 배포/라우팅/공통 오류/보안 헤더를 검증하기 좋다.
- 단, 이것만 전환해서는 업무 호환성을 증명하지 못한다.

### 2순위: `POST /api/messages/preview`

- DB 쓰기가 없고 JSON 계약이 명확하다.
- Pydantic validation, camelCase alias, error envelope, domain parity를 검증하는 첫 업무 수직 기능으로 적합하다.
- `LearningMessageComposer`, `TestScore`, enum 변환을 Python으로 옮기고 golden response를 Java와 비교한다.

### 3순위: `POST /api/imports/preview`

- DB를 건드리지 않으면서 multipart, CSV/XLSX, 보안 한계값이라는 핵심 난도를 검증한다.
- Java/Python parser 차이가 크므로 공통 fixture가 선행되어야 한다.

### 4순위: Import History 읽기 API

- DB read-only라 write보다 위험이 낮다.
- 전용 테스트 DB와 SQLAlchemy session/migration baseline이 준비된 뒤 전환한다.

### 마지막: `POST /api/imports/confirm`

- transaction, business key, INSERT/UPDATE/SKIP, audit, idempotency와 동시성이 결합된 가장 위험한 write API다.
- 전용 PostgreSQL integration test에서 Java 기준 결과와 Python 결과가 일치한 뒤 전환한다.
- Java와 Python의 dual write는 금지하고 한 시점에 하나만 write owner로 둔다.

## 7. React API 호환성 유지 방안

1. 기존 Axios 호출 경로, method, query/header/multipart field를 변경하지 않는다.
2. Pydantic model에 alias를 사용해 `studentName`, `totalRows`, `importId` 같은 camelCase를 그대로 반환한다.
3. 기존 HTTP status와 `{code,message,fields}` error envelope를 유지한다. FastAPI 기본 422는 compatibility exception handler로 기존 400 의미에 맞춘다.
4. `Idempotency-Key`의 대소문자 비민감 HTTP header 의미와 UUID validation을 유지한다.
5. page는 0부터 시작하게 유지한다. FastAPI 내부 offset 계산 때문에 1-based로 바꾸지 않는다.
6. 날짜·timestamp serialization을 golden fixture로 고정한다.
7. OpenAPI에서 TypeScript client/type을 생성하거나 현재 수기 타입과 schema를 CI에서 대조한다.
8. `VITE_API_BASE_URL` 또는 reverse proxy로 backend만 Java/FastAPI 사이에서 바꾸고 React feature 코드는 유지한다.
9. endpoint 단위 shadow comparison 또는 contract test 후 proxy route를 전환한다.
10. 문제 발생 시 route를 Java로 되돌릴 수 있게 하며 DB migration은 additive하게 유지한다.

### 호환성 승인 기준

- Java와 Python이 공통 fixture에 대해 같은 status, JSON shape, error code를 반환한다.
- React 15개 테스트가 backend 선택과 무관하게 통과한다.
- 핵심 React→API E2E를 추가해 Preview 정상/오류, Confirm replay, History empty/detail을 검증한다.
- Confirm은 전용 PostgreSQL에서 rollback과 동시 멱등성까지 통과해야 전환 완료로 판정한다.

## 8. 다음 작업 제안

코드·DB를 변경하지 않는 다음 준비 작업은 다음 순서가 안전하다.

1. `tests/fixtures/contract/` manifest와 공통 fixture를 추가한다.
2. OpenAPI 누락 response/example만 보완하고 기존 동작 변경 여부를 review한다.
3. Java contract test가 fixture를 읽도록 병행 추가한다.
4. FastAPI skeleton에서 health와 Message Preview parity를 구현한다.
5. 별도의 PostgreSQL 테스트 DB를 명시적으로 준비하고, DB 이름 allowlist/운영 DB 차단 guard를 추가한 뒤 skipped 5개를 실행한다.

기존 파일 삭제, stage 통합, 대규모 이동은 이번 작업에서 수행하지 않았다. 필요하면 별도 migration 제안과 승인 후 진행한다.
