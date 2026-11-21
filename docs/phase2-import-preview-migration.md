# Academy LearningOps Phase 2 — Import Preview FastAPI 마이그레이션

작성일: 2026-11-06  
작업 범위: `POST /api/imports/preview`의 읽기 전용 FastAPI 이식

## 1. 결과 요약

Import Preview를 기존 Java 계약과 동일한 FastAPI API로 이식했다. CSV와 XLSX를
메모리에서 파싱·검증하며 PostgreSQL에는 연결하거나 기록하지 않는다. 기존 Java,
React, DB 스키마는 변경하지 않았다. Java와 Python 서버에 동일한 요청을 보낸 계약
비교 27개 시나리오는 모두 상태 코드와 JSON 본문이 일치했다.

`docs/academy-learningops-assessment.md`는 작업 디렉터리에서 찾을 수 없어 이번 단계의
근거로 사용할 수 없었다. 대신 `docs/fastapi-transition-baseline.md`,
`docs/api/openapi.yaml`, Java 구현·테스트와 Phase 1 결과를 확인했다.

## 2. 기존 Java 동작 분석

### 요청과 전송 계층

- 라우팅과 응답: `src/main/java/com/academy/message/api/handler/ImportPreviewHandler.java`
- multipart 파싱: `src/main/java/com/academy/message/api/multipart/MultipartFormDataReader.java`
- 요청은 `multipart/form-data`이고 파일 필드명은 `file`이다.
- 파일 크기 제한은 10 MiB, multipart 전체 요청 제한은 10 MiB + 64 KiB이다.
- 확장자는 `.csv`, `.xlsx`만 지원한다. 확장자별 Content-Type 또는
  `application/octet-stream`만 허용한다.
- 파일명은 basename으로 정규화하여 경로 탐색 문자열을 제거한다.

### 파싱과 검증

핵심 구현은
`src/main/java/com/academy/message/service/ImportPreviewService.java#preview`와
`ImportPreviewRowValidator.java#validate`이다.

- 필수 열: 학급명, 수업유형, 수업일자, 시험회차, 이름, 학교명, 등록상태,
  출석 여부, 보호자명, 보호자 이메일, 예습 과제 등급, 주간 과제 등급,
  `test 결과`
- 별칭: `분반명` → `학급명`, `수강상태` → `등록상태`
- CSV: 엄격한 UTF-8, UTF-8 BOM 허용, 인용 쉼표·인용 줄바꿈 지원, NUL 거부
- XLSX: ZIP/XLSX 구조 확인, 정확히 한 시트만 허용, 날짜 셀을 ISO 날짜로 변환
- 데이터 최대 5,000행, 최대 64열, 셀 문자열 최대 5,000자
- `=`, `+`, `-`, `@`로 시작하는 값은 제거하지 않고
  `FORMULA_LIKE_VALUE` 행 오류로 표시한다.
- HTML 모양 문자열은 실행하지 않고 일반 텍스트로 취급한다.
- 날짜·enum·점수 등 행 객체 생성 실패는 `INVALID_VALUE`, 도메인 검증 실패는
  `VALIDATION_ERROR`로 반환한다.
- 응답의 학생 데이터는 `studentName`, `className`만 포함해 개인정보 노출을
  최소화한다.

Preview에는 INSERT/UPDATE/SKIP 판정이나 트랜잭션이 없다. 이 로직은 Confirm의
책임이며 Phase 2 범위에서 제외했다.

## 3. FastAPI 구현

구현은 `backend/app/modules/imports/`에 한정했다.

- `router.py#import_preview`: multipart 수신, 안전한 파일명, 정확한 10 MiB 제한
- `service.py#preview_import`: 파일 유형 판별, 파서 선택, summary 계산
- `parsers/csv_parser.py#parse_csv`: Java와 같은 CSV 레코드 처리
- `parsers/xlsx_parser.py#parse_xlsx`: 단일 시트 XLSX 처리와 ZIP 압축비 검사
- `parsers/common.py`: 헤더 별칭, 열·셀 제한, 수식형 값 검사
- `validators.py#validate_row`: Java `ImportPreviewRowValidator`와 동일한 행 검증
- `schemas.py`: camelCase 응답 모델
- `middleware.py`: Import Preview의 Content-Type, multipart boundary, 요청 크기,
  Request ID와 구조화 로그 처리

FastAPI의 기본 multipart/validation 오류가 Java 오류 계약과 다르므로 예외 처리를
통해 `{code, message, fields}` 형식과 400/413/415 상태를 유지했다.

새 런타임 의존성은 필요한 범위로 제한했다.

- `openpyxl==3.1.5`: XLSX 읽기
- `python-multipart==0.0.33`: FastAPI multipart 처리

SQLAlchemy, Kafka, Redis는 추가하지 않았다.

## 4. 공통 계약 데이터와 비교

정적 fixture는 `tests/fixtures/contract/import-preview/`, 목록과 기대값은
`tests/fixtures/contract/import-preview-cases.json`에 있다.

포함 사례:

- 정상 CSV/XLSX와 두 형식의 결과 동등성
- 정상·오류 행 혼합
- 잘못된 enum, 날짜, 점수
- 필수 헤더 누락과 잘못된 CSV
- 수식형 문자열과 HTML 모양 텍스트
- 지원하지 않는 확장자와 파일 Content-Type
- 경로가 포함된 파일명
- 5,000/5,001행, 64/65열, 10 MiB/10 MiB+1 byte 경계
- 잘못된 UTF-8, NUL CSV, 손상 XLSX, 다중 시트 XLSX
- 잘못된 multipart boundary, HTTP method, 요청 Content-Type

`backend/scripts/compare_import_preview_contract.py`가 정적 fixture와 큰 경계
fixture를 생성하여 Java(8080)와 Python(8000)의 상태 코드와 JSON을 비교한다.
2026-11-06 실행 결과 27/27 PASS였으며 발견된 계약 차이는 없다.

## 5. 테스트 결과

| 검증 | 결과 | 비고 |
|---|---:|---|
| `ruff check .` | PASS | 오류 0 |
| Python `pytest -q` | PASS | 22 passed |
| Java/Python 계약 비교 | PASS | 27/27 시나리오 |
| FastAPI 생성 OpenAPI 확인 | PASS | multipart 요청 및 200 응답 스키마 확인 |
| Java `mvn test` | PASS | 47 run, 0 failure/error, 5 skipped |
| React `npm test -- --run` | PASS | 5 files, 15 tests |
| React `npm run build` | PASS | production build 성공 |

Python 테스트에는 FastAPI TestClient 내부의 `httpx` 사용에 관한 Starlette
deprecation 경고 1건이 있다. 기능 실패는 아니며 현재 고정 의존성을 불필요하게
올리지 않기 위해 Phase 2에서는 변경하지 않았다.

Java에서 skipped된 5개는 `PostgreSqlDaoIntegrationTest`이다. 테스트용 PostgreSQL
환경변수가 없고 운영 DB 테스트가 금지되어 실행하지 않았다. 따라서 DB 데이터
검증·트랜잭션에 관한 새로운 통합 성공을 주장하지 않는다.

React 테스트 중 jsdom의 pseudo-element `getComputedStyle` 미구현 안내가 출력됐지만
테스트는 통과했다. 빌드에는 500 kB 초과 chunk 경고가 있으며 기존 프론트엔드
번들 구성 문제로, 이번 백엔드 마이그레이션 범위에서는 변경하지 않았다.

브라우저를 통한 수동 E2E와 운영 DB 테스트는 수행하지 않았다. 대신 React가 사용하는
동일한 `FormData`/응답 구조를 서버 계약 비교와 기존 컴포넌트 테스트로 검증했다.

## 6. OpenAPI 및 React 호환성

기존 `docs/api/openapi.yaml`의 `/api/imports/preview` 계약과 FastAPI 생성 스키마는
multipart `file` 요청 및 `ImportPreviewResponse` 구조에서 일치한다. 기존 문서는
변경하지 않았다.

React의 `frontend/src/features/import-preview/api.ts#previewImport`는 기존처럼
`FormData`의 `file`로 전송하고, `types.ts`의 summary/rows 구조를 그대로 받는다.
프론트엔드 코드를 수정하지 않고 실행 환경의
`VITE_API_BASE_URL=http://127.0.0.1:8000`만 사용하면 FastAPI로 전환할 수 있다.
점진 전환 시 reverse proxy에서 `/api/imports/preview`만 Python으로 라우팅하고
Confirm·History는 계속 Java로 보내는 방식도 가능하다.

## 7. 보안·운영 고려사항

- 파일과 multipart 요청 크기를 스트리밍 읽기 단계에서 제한한다.
- CSV는 UTF-8만 허용하고 NUL을 거부한다.
- XLSX는 ZIP 구조, 압축비, 단일 시트를 검사한다.
- 파일명은 저장에 사용하지 않으며 경로 요소를 제거한다.
- 업로드 파일이나 행의 개인정보를 로그에 남기지 않는다.
- Preview는 메모리 처리만 하므로 재시작·실패 시 DB 롤백 대상이 없다.
- 현재 구조는 최대 허용 파일을 메모리에 올린다. 동시 대용량 요청이 증가하면
  proxy 동시성 제한과 메모리 모니터링이 필요하다.

## 8. 실행 방법

```powershell
cd D:\refactor\backend-architecture\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
ruff check .
pytest -q
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

두 서버를 실행한 계약 비교:

```powershell
python scripts\compare_import_preview_contract.py `
  --java-base-url http://127.0.0.1:8080 `
  --python-base-url http://127.0.0.1:8000
```

롤백은 reverse proxy 또는 `VITE_API_BASE_URL`을 Java 서버로 되돌리는 것으로
가능하다. DB 변경이 없으므로 데이터 롤백은 필요 없다.

## 9. 다음 단계: Import Confirm 전환 고려사항

Confirm은 Preview보다 위험도가 높으므로 별도 수직 기능으로 진행해야 한다.

1. 현재 Java `ImportConfirmService`의 재파싱·재검증 규칙을 공통 fixture로 고정한다.
2. `Idempotency-Key` 형식, 요청 hash, 같은 키/같은 요청 재응답과 같은 키/다른 요청
   충돌 계약을 먼저 비교한다.
3. INSERT/UPDATE/SKIP 판정과 저장 순서를 테스트 DB에서만 검증한다.
4. 전체 batch의 원자성과 실패 시 rollback을 PostgreSQL 통합 테스트로 확인한다.
5. 동시 요청에서 idempotency unique constraint와 transaction 격리 동작을 확인한다.
6. 운영 DB를 사용하지 않고 전용 disposable DB와 마이그레이션/롤백 절차를 마련한
   뒤에만 트래픽을 전환한다.

우선순위는 계약 fixture → 테스트 DB/트랜잭션 기반 → Confirm API → Java/Python
동시 비교 → 제한적 라우팅 전환 순이다. History는 Confirm이 만든 audit 레코드 계약이
안정된 뒤 이식하는 것이 의존성상 안전하다.
