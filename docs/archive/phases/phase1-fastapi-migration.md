# Academy LearningOps Phase 1 — FastAPI 기반 및 Message Preview 전환

> 완료일: 2026-11-04 (Asia/Seoul)  
> 작업 경로: `D:\refactor\backend-architecture`  
> 변경 범위: 신규 `backend/`, 공통 계약 fixture, 본 문서, Python 생성물용 `.gitignore` 항목. Java·React·PostgreSQL 소스/스키마/데이터는 변경하지 않았다.

## 1. 결과

FastAPI 기반에서 다음 API를 구현했다.

- `GET /api/health`
- `POST /api/messages/preview`

Message Preview는 Java의 `MessagePreviewValidator`, `MessageGenerationService` 기본 템플릿 fallback, `LearningMessageComposer`, `TestScore`의 API 관련 규칙과 enum 변환을 Python으로 이식했다. camelCase 요청, 상태 코드, `{code,message,fields}` 오류, 16KB 제한, CORS, Request ID, 보안 헤더, 줄바꿈 정리와 개인정보 최소 응답을 유지한다.

Java/Python 실제 서버에 공통 fixture 7건을 전송한 결과 상태 코드, JSON 본문과 `Content-Type`이 모두 일치했다.

## 2. 사전 분석 결과

요청된 문서의 실제 존재 여부는 다음과 같았다.

| 문서 | 결과 |
|---|---|
| `docs/academy-learningops-assessment.md` | `D:\refactor` 아래에서 찾지 못함 |
| `docs/archive/phases/fastapi-transition-baseline.md` | 확인 및 반영 |
| `docs/api/openapi.yaml` | 확인 및 반영 |

누락된 assessment의 내용을 추정하지 않고 baseline, OpenAPI, 실제 Java 소스를 기준으로 구현했다.

분석한 핵심 Java 구현:

- `api/handler/MessagePreviewHandler.java`
- `api/validation/MessagePreviewValidator.java`
- `service/MessageGenerationService.java`
- `domain/LearningMessageComposer.java`
- `domain/TestScore.java`
- `domain/ClassType.java`, `AttendanceStatus.java`, `AchievementGrade.java`
- `dao/TemplateDAO.java`
- `api/ApiRoutes.java`, `security/*`, `json/*`

## 3. 추가 파일

```text
backend/
├─ app/
│  ├─ config.py       환경변수 설정
│  ├─ domain.py       enum, validation, 기본 템플릿, message composition
│  ├─ errors.py       호환 오류 모델
│  ├─ main.py         FastAPI와 두 endpoint
│  ├─ middleware.py   크기 제한, CORS, Request ID, 보안 헤더, 로깅
│  └─ models.py       Pydantic v2 요청/응답
├─ scripts/
│  └─ compare_contract.py
├─ tests/
│  ├─ test_api.py
│  ├─ test_contract_fixtures.py
│  └─ test_domain.py
├─ .env.example
├─ pyproject.toml
└─ README.md

tests/fixtures/contract/
└─ message-preview-cases.json
```

의존성은 FastAPI, Pydantic v2, Uvicorn과 테스트용 pytest, HTTPX, Ruff만 사용했다. SQLAlchemy, Kafka, Redis는 추가하지 않았다.

## 4. 공통 계약 fixture

`tests/fixtures/contract/message-preview-cases.json`에 다음 7건을 구성했다.

1. 정상 메시지 생성
2. 선택 항목이 비어 있는 요청
3. 필수값 누락
4. 잘못된 enum
5. `correctCount > totalCount`
6. 허용하지 않는 JSON 필드
7. 잘못된 Content-Type

각 fixture에는 요청 Content-Type/JSON과 예상 status/JSON 전체를 기록했다. 성공 메시지는 공백과 줄바꿈을 포함한 전체 문자열을 고정한다. `compare_contract.py`는 같은 fixture를 실행 중인 Java/Python 서버에 보내 다음을 동시에 비교한다.

- HTTP status
- JSON 구조와 문자열 전체
- `Content-Type`
- fixture의 예상 결과

## 5. 구현된 호환 동작

### Health

- `200 {"status":"UP"}`
- `Content-Type: application/json; charset=UTF-8`
- `X-Request-Id`, `X-Content-Type-Options: nosniff`, `Cache-Control: no-store`, CSP, Referrer-Policy

### Message Preview

- 기존 camelCase 필드 유지
- 필수 문자열, 최대 길이, ISO 날짜, enum, 점수 쌍/범위 검증
- `REGULAR`/`EXAM_PREP`와 기존 한글 alias 지원
- `PRESENT`/`ABSENT`/`LATE`와 기존 한글 alias 지원
- include flag 누락 시 Java처럼 `true`
- 선택되지 않았거나 빈 학습 항목 제거
- 연속된 3개 이상 줄바꿈을 2개로 축소하고 양끝 trim
- 응답은 `message` 하나만 포함
- unknown JSON과 JSON 타입 불일치는 `400 INVALID_JSON`
- 업무 validation은 `400 VALIDATION_ERROR`
- 잘못된 Content-Type은 415, body 16KB 초과는 413
- 허용되지 않은 Origin은 403, 잘못된 method는 405

FastAPI의 기본 422에 의존하지 않고 기존 Java 400 계약으로 변환했다.

## 6. 발견한 계약 차이와 처리

### 6.1 FieldError OpenAPI 불일치

OpenAPI의 `FieldError`는 `field`, `code`, `message`를 required로 선언한다. 그러나 실제 Java `FieldErrorResponse`는 `field`, `message`만 반환한다.

이번 목표는 기존 동작 보존이므로 Python은 실제 Java 응답인 `{field,message}`를 따른다. OpenAPI 수정은 Java/React 계약 변경 검토가 필요한 별도 작업으로 남긴다.

### 6.2 Content-Type 차이

첫 실서버 비교에서 FastAPI 기본값은 `application/json`, Java는 `application/json; charset=UTF-8`이었다. Python middleware가 Java와 동일한 값을 명시하도록 수정했고 재비교 7건이 모두 통과했다.

### 6.3 DB 사용자 정의 템플릿

Java `MessageGenerationService`는 DB에서 활성 템플릿 조회를 먼저 시도하고 실패하면 `TemplateDAO`의 기본 템플릿을 사용한다. Phase 1 Python에는 DB 의존성을 넣지 않았으므로 **Java 기본 fallback 템플릿과 동일한 동작만 이식했다.**

이번 실제 비교는 DB 환경변수가 없는 Java 서버의 fallback 경로를 기준으로 통과했다. 운영 DB에 사용자 정의 활성 템플릿이 있다면 Python 결과는 달라질 수 있다. 정책을 임의 변경하지 않았으며, 이 차이는 다음 중 하나를 결정하기 전까지 남는다.

- 템플릿 조회 전용 repository를 다음 DB 단계에서 구현
- 템플릿을 환경/배포 설정으로 동기화
- Message Preview 계약을 기본 템플릿 전용으로 명시

운영 전에는 실제 사용 방식을 확인해 결정해야 한다.

### 6.4 테스트 라이브러리 경고

pytest는 모두 통과했지만 FastAPI 0.162.0의 `TestClient`가 HTTPX 사용 방식에 대한 `StarletteDeprecationWarning` 1건을 출력했다. 요청 조건에 HTTPX가 포함되어 현재 조합을 유지했으며, 기능 실패는 아니다. 불필요한 패키지 변경을 피하기 위해 이번 단계에서 대체 라이브러리로 전환하지 않았다.

## 7. 실제 검증 결과

### Python

| 명령 | 결과 |
|---|---|
| `.venv\Scripts\ruff.exe check .` | All checks passed |
| `.venv\Scripts\pytest.exe` | 14 passed, 1 deprecation warning |
| FastAPI 생성 OpenAPI 검사 | Message Preview `requestBody` schema 존재 확인 |

Python 테스트 구성:

- domain 단위 테스트 3개
- FastAPI API/transport 테스트 4개
- 공통 fixture parameterized 테스트 7개

### Java/Python 실제 계약 비교

`compare_contract.py` 최종 결과:

```text
regular-full: PASS
optional-empty: PASS
missing-required: PASS
invalid-enum: PASS
invalid-score: PASS
unknown-field: PASS
wrong-content-type: PASS
```

두 서버는 비교 후 종료했다. DB 환경변수는 설정하지 않았다.

### 기존 Java

`mvn test` 최종 결과:

- Tests run: 47
- Failures: 0
- Errors: 0
- Skipped: 5
- BUILD SUCCESS

Skipped 5건은 `PostgreSqlDaoIntegrationTest`다. 테스트가 DB 테이블을 `TRUNCATE`하며 전용 테스트 DB 설정이 없으므로 운영 DB 금지 조건에 따라 실행하지 않았다. 이번 Phase 1 endpoint는 DB를 쓰지 않는다.

Java는 프로젝트 compiler target이 17이지만 로컬에서 이용 가능한 JBR 25로 실행했다. Java 17 CI 재현은 별도 확인이 필요하다.

### 기존 React

- Vitest: 5 files, 15 tests passed
- TypeScript/Vite production build: 성공, 3,280 modules transformed
- 기존 경고: 500kB 초과 chunk 1개

React 소스는 변경하지 않았다.

## 8. 실행 방법

상세 명령은 `backend/README.md`에 기록했다. 요약:

```powershell
cd D:\refactor\backend-architecture\backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
ruff check .
pytest
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

React의 기존 Axios client는 `VITE_API_BASE_URL`을 이미 지원하므로 프론트 소스 수정 없이 Python backend를 선택할 수 있다.

## 9. 배포와 롤백

Phase 1은 DB 변경이 없어 DB rollback이 필요하지 않다.

- 전환: reverse proxy 또는 `VITE_API_BASE_URL`을 Python 8000 endpoint로 지정
- rollback: 같은 설정을 Java 8080 endpoint로 복원
- 승인 조건: 공통 fixture, Python test, 기존 Java/React test가 모두 통과해야 함
- 운영 전 조건: 사용자 정의 DB 템플릿 사용 여부 확인

## 10. 다음 단계: Import Preview 고려사항

Import Preview 전환 전에 다음을 선행한다.

1. CSV/XLSX 정상·혼합 오류·5,000/5,001행·64/65열 fixture를 Java/Python 공통 형식으로 고정한다.
2. 10MB 경계, 빈 파일, `.xlsm`, malformed ZIP/XLSX, 다중 sheet, formula-like/HTML 값 결과를 비교한다.
3. Java의 원본 row number, field error 순서, 한글/코드 enum 변환을 그대로 보존한다.
4. 업로드 전체를 무제한 메모리에 읽지 않고 streaming size limit을 먼저 적용한다.
5. 파일명은 경로로 사용하지 않고 로그에 학생 원문·파일 내용을 남기지 않는다.
6. Import Preview는 계속 DB write 없이 구현한다.
7. Python parser와 Apache POI/Java CSV 처리 차이를 공통 fixture 실서버 비교로 확인한다.
8. Confirm, History, SQLAlchemy, DB migration은 Import Preview 범위에 섞지 않는다.

## 11. 남은 위험

- 운영 DB 사용자 정의 템플릿과 Python 기본 템플릿의 차이
- OpenAPI `FieldError.code`와 실제 Java 응답의 불일치
- TestClient deprecation warning
- Java 17이 아닌 JBR 25에서만 이번 회귀 테스트를 실행한 점
- Git metadata가 이 디렉터리에 없어 `git diff/status`로 변경 범위를 검증할 수 없는 점

위 항목은 숨기지 않고 다음 단계의 입력으로 유지한다.
