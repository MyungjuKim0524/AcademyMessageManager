# Engineering Retrospective — Decisions, Failures & Improvements

작성일: 2026-11-10

> 이 회고는 코드와 검증 결과에서 확인할 수 있는 엔지니어링 판단만 다룬다. 개발자의 감정,
> 개인적 동기, 당시 구두 의사결정은 확인할 수 없어 필요한 곳에 `개인 회고 보완 필요`로
> 표시한다. 작성 당시 `.git`이 없어 commit 단위 회고는 검증할 수 없었다. 2026-11-21 기준 저장소는 초기화됐지만 커밋은 아직 없다.
> Java 버전(v1.0~v1.2)과의 비교, 이후 Phase 11-4까지의 결과는 `DEVELOPMENT_HISTORY.md` 2·3·9절을 기준으로 한다.

## 1. Java에서 FastAPI로 전환한 기술적 의사결정

### Problem

Java Swing 프로그램에는 검증된 학원 업무 규칙이 존재하지만 웹 확장, API 기반 통합과 향후
분석 기능에는 제약이 있었다. 전면 재작성은 메시지 문구, 상태 변환, import 판정 규칙을
잃을 위험이 있었다.

### Decision

Java를 즉시 제거하지 않고 endpoint 단위로 FastAPI를 병행 구축했다. DB가 없는 Health와
Message Preview부터 시작하고 Import Preview, DB API 순으로 위험을 높였다.

### Implementation

- OpenAPI와 JSON field를 migration boundary로 사용
- Java/Python 공통 fixture 작성
- Java `LearningMessageComposer`, `TestScore`, validator의 순서를 Python에 이식
- React는 API base URL만 전환

### Verification

- Phase 1 계약 7/7, Phase 2 계약 27/27의 과거 실서버 비교 기록
- 2026-11-10 기본 Python 테스트 33 PASS
- Phase 4 성공 계약은 아직 `BLOCKED`

### Lessons Learned

기술 스택 변경의 핵심은 언어 변환이 아니라 관찰 가능한 계약을 먼저 고정하는 것이다.
완료 판정은 코드 존재보다 양쪽 구현의 성공·실패 결과 비교가 우선이다.

### 개발자 회고 — FastAPI를 선택한 이유 (2026-11-21 작성)

기존 Java Swing 애플리케이션의 웹 전환을 계획하면서, 처음에는 Spring Boot 기반 REST API를 고려했다. 그러나 프로젝트의 장기 확장 방향과 당시의 학습·개발 여건을 함께 판단해 FastAPI로 전환했다.

1. **Python 기반 AI 기능 확장 가능성**
   - 향후 학원 업무 자동화 시스템에 AI 기능을 추가할 가능성을 염두에 두었다.
   - Python 백엔드를 쓰면 관련 라이브러리와 개발 도구를 같은 언어 생태계에서 활용할 수 있다고 판단했다.
2. **프레임워크 학습 비용과 개발 일정의 균형**
   - Spring Boot를 단기간에 학습해 프로젝트에 적용하는 데 부담이 있을 것으로 예상했다.
   - 새 프레임워크 학습에 쓸 시간과, 웹서비스 핵심 기능의 구현·검증에 쓸 시간을 함께 고려했다.

**Trade-off**
- 기존 Java 구현을 직접 재사용하기 어려워졌다.
- API·인증·데이터 접근 계층을 Python으로 다시 구현하고 검증해야 했다.
- 따라서 FastAPI 선택이 개발 기간을 실제로 단축했다거나, Spring Boot보다 기술적으로 우수하다고 단정하지 않는다.

**결과**
- FastAPI 전환은 장기적인 Python 기반 AI 확장 방향과 당시의 학습·개발 제약을 함께 고려한 선택이었다.
- 현재 웹 버전의 주요 성과는 AI 기능 자체가 아니다. 기존 업무 로직의 웹서비스 전환과, 인증·권한·데이터 정합성·테스트 체계 구축이다.
- AI 기능은 아직 구현하지 않았다(범위·일정 미정, `DEVELOPMENT_HISTORY.md` 8절).

## 2. 개발 DB와 테스트 DB를 완전히 분리한 이유

### Problem

Java/Python PostgreSQL 통합 테스트에는 TRUNCATE, rollback, constraint violation, 동시성
시나리오가 있다. 잘못된 URL로 실행하면 개발 데이터를 훼손할 수 있다.

### Decision

논리적 DB명만 분리하지 않고 container, user, port, named volume, label까지 분리했다.

### Implementation

- dev: port 55431, `academy_dev`, 전용 volume, destructive forbidden
- test: port 55432, `academy_test`, 전용 volume, destructive allowed
- test mode 이중 switch와 database identity allowlist
- wrapper에서 service label과 접속 대상을 검증

### Verification

2026-11-10 두 컨테이너는 Healthy였고 서로 다른 DB명·계정·volume을 사용했다. 양쪽 schema와
Alembic revision은 같지만 개발 업무 데이터는 0행, 테스트 DB에는 합성 데이터 7행이었다.

### Lessons Learned

“테스트 DB를 사용한다”는 환경변수 이름만으로 보장되지 않는다. 파괴적 테스트는 실행 직전에
host, port, DB명, user, label을 함께 확인해야 한다.

## 3. API 계약을 유지하며 백엔드를 교체한 방식

### Problem

React를 보존하려면 HTTP status, camelCase field, 오류 envelope, 공백과 줄바꿈까지 같아야
한다. FastAPI 기본 422는 기존 Java 400과 충돌한다.

### Decision

framework 기본값보다 기존 공개 계약을 우선했다.

### Implementation

- compatibility exception handler로 400 오류 변환
- `{code, message, fields}` 구조 유지
- request size, content type, method, CORS guard
- 공통 fixture와 server-to-server comparison script

### Verification

Phase 1·2 비교는 완료됐지만 Phase 4 성공 경로 비교는 Java API DB runtime 문제로 미완료다.
따라서 Import Confirm 전체 호환 완료를 주장하지 않는다.

### Lessons Learned

API migration의 가장 위험한 차이는 type system보다 framework 기본 동작이다. validation과
transport 오류도 business response만큼 contract test가 필요하다.

## 4. 테스트 자동화와 데이터 무결성 관리

### Problem

Preview는 순수 계산이지만 Confirm은 여러 테이블과 audit를 함께 변경한다. 부분 성공이나
중복 재시도는 데이터 불일치를 만든다.

### Decision

파일 전체를 다시 검증하고 하나의 transaction으로 처리하며 UUID Idempotency-Key를 DB
unique constraint와 결합했다.

### Implementation

- parsing/validation은 transaction 전 수행
- `with session.begin()`으로 transaction owner 단일화
- `ON CONFLICT DO NOTHING RETURNING id`로 key claim
- 같은 key/hash는 replay, 다른 payload는 conflict
- 업무 데이터와 import audit를 함께 commit

### Verification

과거 실제 PostgreSQL 테스트에서 rollback과 동일 key concurrency가 통과한 기록이 있다.
다만 History projection과 secret 설정 변경 이후 현재 쓰기 통합 테스트는 재실행하지 않았다.

2026-11-10 현재 검증:

- Ruff PASS
- Python 33 PASS, PostgreSQL 10 SKIP
- Java 47 run, 42 PASS, PostgreSQL 5 SKIP
- React build PASS
- React Vitest 현재 실행은 정지해 중단

### Lessons Learned

통합 테스트는 많을수록 좋은 것이 아니라 대상 DB를 증명한 뒤에만 실행되어야 한다. 과거의
PASS와 현재 코드의 PASS도 구분해 기록해야 한다.

## 5. Docker 장애에서 원인을 단계적으로 좁힌 과정

### Problem

Docker Desktop은 Inference manager 초기화 중 종료됐고 이후 CLI도 Engine에 연결되지 않았다.
DB와 volume을 지키면서 runtime 문제인지 영구 데이터 손상인지 구분해야 했다.

### Decision

삭제보다 관찰을 우선했다. CLI, context, process, WSL, log, runtime socket, VHDX 순으로
계층을 분리했다.

### Implementation

- 전체 경로로 CLI 실행해 PATH 가설 제거
- named pipe 부재로 Engine 미기동 확인
- host log에서 `dockerInference` 제거 실패 확인
- VHDX 위치와 크기를 읽기 전용 확인
- 손상 runtime을 격리하고 공식 Desktop 실행
- 새 socket과 Engine 생성 후 container/volume/DB 검증

### Verification

Docker Client/Server 29.7.2, `desktop-linux`, WSL running, 두 PostgreSQL Healthy, 14개 table과
Alembic revision을 확인했다.

### Lessons Learned

직접 원인과 최초 근본 원인을 분리해야 한다. socket 제거 실패는 증명됐지만 왜 socket이
비정상이 됐는지는 확정하지 않았다. 불확실성을 남기는 것이 잘못된 단정이나 Factory Reset보다
안전하다.

## 6. 보안을 고려한 문제 해결 방식

### Problem

복구 과정은 관리자 권한, 자격 증명, volume 삭제 같은 위험을 쉽게 확대할 수 있다.

### Decision

최소 권한, 최소 출력, 승인 기반 destructive action 원칙을 적용했다.

### Implementation

- secret environment 전체를 출력하지 않음
- container inspect에서 password를 조회하지 않음
- 외부 script/download 미사용
- Factory Reset, volume prune, WSL unregister 금지
- 읽기 전용 SQL transaction 사용
- cache만 기간 filter와 기본 prune 정책으로 정리

### Verification

이미지·volume·container 수, DB명, table 수, Alembic revision이 정리 전후 유지됐다. BuildKit
cache만 약 59MB 감소했다.

### Lessons Learned

복구 속도보다 변경 범위와 rollback 가능성을 관리하는 능력이 운영 안정성에 직접 연결된다.

## 7. 기능 구현에서 운영 안정성 중심 사고로의 확장

### Problem

API가 정상 응답하는 것만으로는 운영 준비가 되지 않는다. DB 격리, secret, idempotency,
resource limit, 장애 복구와 저장 공간 관리가 필요하다.

### Decision

Definition of Done에 transaction, rollback, security boundary, test isolation, 문서화와 실제
환경 검증을 포함했다.

### Implementation

- DB API 기본 disabled
- loopback/mode/identity allowlist
- request ID와 generic error response
- Docker healthcheck와 named volume
- Alembic baseline과 destructive downgrade gate
- Docker recovery 후 DB read-only validation

### Verification

구현 여부와 운영 공개 가능성을 분리해 평가했다. History/Confirm 코드는 존재하지만 인증이
없어 운영 공개 불가로 문서화했다.

### Lessons Learned

“구현 완료”와 “운영 가능”은 다른 상태다. 보안 경계와 현재 검증 수준을 상태 모델처럼
명확히 표현해야 한다.

## 8. 다음 개발 단계에서 개선할 사항

> 2026-11-10 시점의 계획이다. 이후 인증·RBAC(P1), PostgreSQL 통합 테스트 재실행, React 테스트 재검증은 Phase 5~11에서 완료됐다.
> 현재 상태와 남은 과제는 `DEVELOPMENT_HISTORY.md` 7·8절을 따른다.

### P0 — 현재 기능의 검증 부채 해소

1. 격리 테스트 DB 승인 후 Python/Java PostgreSQL 통합 테스트 재실행
2. Java/Python Phase 4 성공 계약 비교 완료
3. React Vitest 정지 원인 진단과 현재 15개 test 재검증

### P1 — 인증과 권한

1. 사용자, Role, 담당 반 scope schema 확정
2. ADMIN/TEACHER/ASSISTANT authorization matrix 작성
3. local gate를 인증 dependency와 object-level check로 교체
4. audit actor와 권한 거부 test 추가

### P2 — 이벤트와 분석

1. Kafka 도입 전 transaction outbox 필요성 검토
2. Import 완료, 과제/성적/출결 변화 이벤트 정의
3. dashboard 지표의 source-of-truth와 권한별 집계 범위 설계

### P3 — 운영 엔지니어링

1. CI에서 unit/contract/integration test 단계 분리
2. PostgreSQL backup 및 restore drill
3. Docker cache/image 소유권 inventory
4. structured log, metric, alert와 retention 정책

## 9. 기존 기능 이식 누락 — 보강 관리와 Feature Parity (2026-11-21 작성)

### Problem

Java 버전(v1.0~v1.2)의 보강 관리 기능은 FastAPI·React 웹 버전으로 이식되지 않았다.
- Java에 있던 것: 화면의 보강 신청·완료·취소(상태 규칙에는 승인 포함), 재원생만 신청, 상태별 보호자 안내 문구
- 웹에 있는 것: `makeup_request` 테이블 모델과, 결석일 때 넣는 고정 문장 하나(`DEVELOPMENT_HISTORY.md` 9.9절)

### Cause (개발자 회고)

- 처음부터 의도적으로 제외한 기능이 아니다. 기존 기능의 이식 범위를 충분히 확인하지 못해 생긴 **누락**이다.
- 코드 구조 개선과 데이터 검증·정합성 확보에 예상보다 많은 시간을 쓰면서, 이 기능까지 구현할 여력이 부족했다.

### Decision

- 현재 릴리스에는 추가하지 않는다.
- 기존 업무 흐름의 안정화와 배포를 마친 뒤, 실제 필요성과 구현 비용을 검토해 개발 여부를 정한다(`DEVELOPMENT_HISTORY.md` 8절).

### Lessons Learned

- 레거시 마이그레이션에서는 아키텍처 전환과 기술적 품질 개선만큼, 기존 기능의 이식 여부를 추적하는 **Feature Parity 검증**이 중요하다.
- 다음 마이그레이션에서는 착수 단계부터 체크리스트를 관리한다. 기존 기능 목록과 신규 구현 상태를 짝지어 기능 누락을 막는다.
- 이번 프로젝트의 사후 대응표는 `DEVELOPMENT_HISTORY.md` 9.0·9.9절이다.

## 최종 회고 요약

이 프로젝트에서 확인되는 핵심 역량은 기존 규칙을 보존하는 점진적 migration, 계약 기반
테스트, DB transaction과 idempotency, 파괴적 테스트 격리, 데이터 우선 장애 복구다. 반면
인증/RBAC, Phase 4 최종 계약 검증, 현재 DB integration 재실행과 CI/CD는 아직 완료되지
않았다. 이 경계를 숨기지 않는 것이 다음 단계의 가장 중요한 출발점이다.

**개인 회고 보완 필요(일부 작성):** 기술 선택의 이유(1절)와, 다음 프로젝트에서 처음부터 다르게 할 선택(9절, Feature Parity 체크리스트)은 개발자 본인이 작성했다. 가장 어려웠던 판단과 예상과 달랐던 점은 아직 비어 있다.

> 위 요약은 2026-11-10 기준이다. 이후 인증/RBAC, PostgreSQL 통합 재실행, 동시성·보안 점검은 완료됐다. CI/CD와 실제 클라우드 배포는 아직 남아 있다(`DEVELOPMENT_HISTORY.md` 7절).
