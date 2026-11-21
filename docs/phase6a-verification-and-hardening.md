# Phase 6A 최종 검증 업데이트 (2026-11-16 KST)

## 최종 판정

Phase 6A의 **PostgreSQL 백엔드 구현과 보안 검증은 PASS**다. 테스트 DB와 개발 DB 모두
Migration 003이 적용됐고, 실제 PostgreSQL 통합 테스트 16개 및 Java PostgreSQL 테스트 5개가
통과했다. 다만 개발 DB에 ACTIVE ADMIN이 없어 실제 개발 DB 브라우저 로그인 E2E는
**BLOCKED**다. 따라서 전체 Phase 6A는 엄격한 완료 기준상 **조건부 완료 / 브라우저 E2E 미완료**로
판정한다. 아래의 과거 BLOCKED 기록은 Docker 복구 전 상태이며 이 최종 업데이트가 우선한다.

## Docker 및 DB 최종 상태

| 항목 | 결과 |
|---|---|
| Docker Desktop | PASS, 4.99.0 build 245822 |
| Docker Engine | PASS, 29.9.3 running |
| 개발 PostgreSQL | PASS, healthy, `127.0.0.1:55431` |
| 테스트 PostgreSQL | PASS, healthy, `127.0.0.1:55432` |
| 개발 DB revision | `003_phase6a_enrollment_integrity (head)` |
| 테스트 DB revision | `003_phase6a_enrollment_integrity (head)` |
| 개발 DB ACTIVE ADMIN | 0명 |
| 테스트 종료 후 ACTIVE ADMIN | 0명 |
| 중복 수강 조합 | 양쪽 DB 0건 |

기존 볼륨 `academy_learningops_postgres_dev_data`와
`academy_learningops_postgres_test_data`를 그대로 사용했다. 미확인 `academy-postgres`는 변경하지
않았다.

## Migration 003 검증 및 적용

Migration 003은 `enrollment(student_id, classroom_id)`에
`uq_enrollment_student_classroom` UNIQUE 인덱스만 추가한다. 기존 PK, 학생/반 FK,
status/date CHECK 및 `(student_id,classroom_id,enrolled_at)` UNIQUE와 호환된다. Import Confirm은
기존 수강을 학생·반으로 먼저 조회해 status를 갱신하므로 현재 재수강 이력 모델을 사용하지 않는
정책과 일치한다.

- 테스트 DB 사전 중복 조회: 0건
- 테스트 DB 적용: PASS
- 재실행: PASS/no-op
- Alembic drift: PASS, `No new upgrade operations detected`
- 개발 DB 사전 중복 조회: 0건
- 개발 DB 적용: 사용자 승인 후 PASS
- 개발 DB 적용 전후 학생/반/수강/직원/Import Job: `0|0|0|0|0`로 동일
- 개발 DB 생성 인덱스: 실제 PostgreSQL catalog에서 확인

개발 DB 백업:

`data/backups/academy_learningops_dev_before_003_20261115.dump`

- PostgreSQL 17.6 custom format, TOC 193개
- 크기: 71,466 bytes
- SHA-256: `09473FC7B2ABBEA983CC1886FCBEECED8CC3A3F3CE8B44DA731B1A3940586E6F`
- 복구 방법: 빈 격리 DB에서 `pg_restore`로 사전 연습 후 필요 시 복원한다. 기존 개발 DB에
  즉시 덮어쓰지 않는다.

## 실제 PostgreSQL 통합·보안 검증

Python postgres marker 16개: **16 PASS**.

- 합성 ADMIN 로그인, 반·학생 생성, 수강 및 TEACHER 배정
- TEACHER 담당 반 학생 목록과 변경 후 DB 조회
- 동시 동일 수강 요청 결과 201/409, DB row 1개
- DB UNIQUE, FK, CHECK, 잘못된 status 차단
- 트랜잭션 중간 실패 rollback 및 이후 session 정상 사용
- 미인증, CSRF 없음, 비활성 계정, role header 조작 차단
- 미담당 반 IDOR/BOLA 차단 및 배정 해제 후 차단
- 응답에서 보호자 개인정보 최소화
- Message Preview, Import Preview/Confirm/History, Auth 회귀
- Import Confirm 원자성·idempotency·동시 요청 회귀

이는 TestClient만의 단위 테스트가 아니라 `academy_learningops_test` PostgreSQL에 실제로 연결해
TRUNCATE/transaction/concurrency/constraint를 검증한 API 기반 E2E다. 테스트 DB의
`isolated-test|destructive-tests=allowed` 라벨과 DB identity를 확인한 뒤에만 실행했다.

## 전체 회귀 결과

| 검증 | 결과 |
|---|---|
| Ruff | PASS |
| Python 비DB pytest | 35 PASS |
| Python PostgreSQL pytest | 16 PASS |
| Alembic 재실행 | PASS/no-op |
| Alembic metadata drift | PASS |
| Java Maven 기본 | 47개 중 42 PASS, DB 5 SKIPPED |
| Java Maven PostgreSQL 활성화 | 47 PASS, 0 skipped |
| React Vitest | 7 files / 20 PASS |
| React lint | PASS |
| React production build | PASS, 3,286 modules |
| API 기반 인증·업무 E2E | PASS, 테스트 DB 합성 계정 |
| 개발 DB 실제 브라우저 E2E | BLOCKED, ACTIVE ADMIN 없음 |

Vitest의 jsdom pseudo-element 메시지와 Vite의 500KB chunk 경고는 비치명적이며 exit code는 0이다.
Starlette TestClient의 `httpx` 사용 deprecation warning도 남아 있으나 이번 단계에서 패키지
업데이트는 하지 않았다.

## 수정 파일과 이유

- `backend/scripts/auth_preflight.py`: Migration 003 적용 후에도 이전 revision 002를 정확히
  요구해 FastAPI 시작을 차단하던 검사를 실제 head `003_phase6a_enrollment_integrity`로
  갱신했다. 실제 개발 DB preflight와 Python 비DB 35개를 재검증했다.
- `backend/tests/test_postgres_integration.py`: schema reproducibility 테스트의 예상 Alembic
  revision을 오래된 `002_staff_auth_rbac`에서 실제 head인
  `003_phase6a_enrollment_integrity`로 변경했다. 제품 코드나 API 계약은 변경하지 않았다.
- `docs/phase6a-verification-and-hardening.md`: 실제 검증 결과를 추가했다.

Git 실행 파일이 PATH 및 확인한 표준 경로에 없어 `git status`는 BLOCKED였다. 따라서 기존 파일을
전면 덮어쓰지 않고 위 두 파일만 최소 수정했다.

## 인증 및 브라우저 E2E

테스트 DB에서는 합성 ADMIN/TEACHER/비활성 계정을 fixture가 생성하고 테스트 종료 시 정리한다.
관리자 로그인부터 반·학생·수강·배정·교사 조회·타 반 차단·로그아웃/세션 차단까지 API 레벨로
검증됐다. React 컴포넌트 테스트도 PASS했다.

개발 DB에는 ACTIVE ADMIN이 0명이므로 실제 브라우저 `/students` 시나리오는 실행하지 않았다.
임의 비밀번호나 계정을 만들지 않았다. 사용자가 직접 선택한 강한 비밀번호를 현재 PowerShell
세션에만 넣고 `scripts/bootstrap-admin.ps1`의 대화형 절차로 부트스트랩한 뒤 브라우저 수동 검증을
수행해야 한다. 비밀번호는 명령행 인자, 로그, 문서에 기록하지 않아야 한다.

## 데이터·저장 공간 보호

- 개발 DB 초기화/TRUNCATE: 미실행
- 기존 데이터 자동 삭제·병합: 미실행
- 기존 Volume/VHDX 이동·삭제: 미실행
- Factory Reset/prune: 미실행
- 모든 Python/npm/Ruff/pytest 임시·캐시: 프로젝트 `.dev-data`의 D드라이브 경로 사용
- DB 백업 및 보고서: D드라이브 사용
- C드라이브 시스템·사용자 파일: 삭제하지 않음

## 다음 단계 권장

1. 사용자 관리 비밀번호로 개발 ADMIN을 공식 스크립트로 부트스트랩한다.
2. FastAPI와 React를 개발 DB에 연결해 `/students` 브라우저 E2E를 수동 또는 자동화로 실행한다.
3. 이 마지막 BLOCKED 항목이 PASS하면 Phase 6A를 **완전 완료**로 전환한다.
4. 그 전까지 Phase 6B 착수는 가능하지만, 릴리스 게이트에서는 Phase 6A 브라우저 E2E 미완료를
   명시적으로 유지한다.

# Phase 6A Verification and Hardening

검증일: 2026-11-15 KST

## 1. 결론

Phase 6A 기능은 **구현 완료 상태**이지만 **실제 PostgreSQL 검증 완료 상태는 아니다**.
Python 비DB 회귀, Java 비DB 회귀, React 테스트·lint·build는 PASS했다. Docker Desktop의
Inference/Secrets 부가 서비스 초기화 오류로 Linux Engine이 시작되지 않아 Migration 003,
PostgreSQL 통합·동시성·RBAC, 개발 환경 E2E는 BLOCKED다. 미실행 항목을 PASS로 간주하지 않았다.

## 2. 사전 환경 상태와 복구 시도

- 프로젝트: `D:\refactor\backend-architecture`
- Python: 기존 `backend\.venv` 재사용
- Docker 데이터: `D:\DockerData\DockerDesktopWSL`에 보존
- Docker Desktop: 설치됨, 시작 전 Engine 중지
- Git: 실행 파일이 PATH에 없어 `git status` 확인 BLOCKED
- Java: PATH와 `JAVA_HOME`은 비어 있었으나 기존 IntelliJ JBR 25.0.3과 `javac` 발견
- Maven: 3.9.16, D드라이브 설치
- DB credential 환경변수: 설정되지 않음

Docker Desktop을 비파괴적으로 시작했으나 다음 순서로 실패했다.

1. `Docker/run/dockerInference` stale 0바이트 IPC reparse point 오류
2. 오류 프로세스 종료 후 해당 endpoint 하나만 제거
3. `docker-secrets-engine/engine.sock` stale 0바이트 IPC 오류
4. 오류 프로세스 종료 후 해당 endpoint 하나만 제거
5. 재시작 시 `dockerInference` 오류가 다시 생성됨

설정 파일에는 `EnableDockerAI: true`가 있으며 오류 서비스와 일치한다. 이 기능은 PostgreSQL
검증에 필요하지 않지만 저장소 밖 Docker Desktop 설정 변경은 사용자 명시 승인 없이 수행하지
않았다. `Reset to factory defaults`, WSL 이전, 볼륨 삭제, 컨테이너 재생성은 실행하지 않았다.
마지막 오류 후 Docker 프로세스만 종료해 안정된 상태로 두었다.

Java는 전역 설정 없이 현재 테스트 프로세스에서만 다음 기존 JBR을 `JAVA_HOME`으로 사용했다.

```text
D:\IntelliJ IDEA 2026.2.0.1\jbr
```

## 3. PostgreSQL 연결 확인

| 대상 | 결과 | 근거 |
|---|---|---|
| 개발 DB `127.0.0.1:55431/academy_learningops_dev` | BLOCKED | Docker Engine 시작 실패 |
| 테스트 DB `127.0.0.1:55432/academy_learningops_test` | BLOCKED | Docker Engine 시작 실패 |
| 컨테이너 라벨/포트/health | BLOCKED | Docker API 사용 불가 |
| DB identity/current user | BLOCKED | DB 연결 불가 |
| ACTIVE ADMIN 수 | BLOCKED | 개발 DB 읽기 불가 |
| FastAPI auth preflight | BLOCKED | DB 연결 불가 |
| `/api/auth/me` 미인증 401 실서버 확인 | BLOCKED | DB 기반 서버 기동 불가 |

소유권이 확인되지 않은 `academy-postgres`에는 접근하거나 변경하지 않았다. DB credential을 출력,
파일 저장 또는 보고서에 기록하지 않았다.

## 4. Migration 003 안전성 분석

`003_phase6a_enrollment_integrity`는 `enrollment(student_id, classroom_id)`에 unique index
`uq_enrollment_student_classroom` 하나를 추가한다. DROP/UPDATE/DELETE나 데이터 정리 DDL은 없다.
기존 PK/FK/check와 `uq_enrollment(student_id,classroom_id,enrolled_at)`는 유지된다.

적용 전 필수 읽기 전용 진단은 다음과 같다.

```sql
SELECT student_id, classroom_id, COUNT(*)
FROM enrollment
GROUP BY student_id, classroom_id
HAVING COUNT(*) > 1;
```

결과가 있으면 index 생성이 실패하며 기존 행을 자동 병합·삭제하지 않는다. Java와 Python Import
Confirm은 학생·반의 최신 enrollment를 조회하여 재사용/상태 변경하므로 새 제약의 현재 업무 의도와
일치한다. 다만 역사적 재등록을 별도 행으로 보존해야 한다면 적용 전에 기간 모델을 재설계해야 한다.

| 검증 | 결과 |
|---|---|
| DDL 정적 검토 | PASS |
| 개발 DB revision/중복 읽기 | BLOCKED |
| 테스트 DB 적용 | BLOCKED |
| 적용 후 revision | BLOCKED |
| ORM metadata diff | BLOCKED |
| 재실행 동작 | BLOCKED |

개발 DB에는 Migration 003을 적용하지 않았다. 개발 DB 적용은 중복 0건, 현재 revision, 백업 상태,
테스트 DB PASS를 먼저 보고한 뒤 사용자의 별도 명시 승인 하에서만 가능하다.

## 5. 실행한 테스트

| 영역 | 명령/범위 | 결과 |
|---|---|---|
| Ruff | `ruff check --no-cache backend` | PASS |
| Python 비DB | `pytest -q -m "not postgres"` | 35 PASS |
| Python PostgreSQL | postgres marker 16개 | BLOCKED |
| Java 전체 기본 | `mvn test` | 47개 중 42 PASS, PostgreSQL 5 SKIPPED |
| Java PostgreSQL | `-DrunPostgresIntegration=true` | BLOCKED |
| React Vitest | 기존 suite | 7 files / 20 PASS |
| React lint | `oxlint src` | PASS |
| React production build | TypeScript + Vite | PASS, 3,286 modules |
| 브라우저 E2E | `/students` 관리자/교사 흐름 | BLOCKED |

Vite의 500KB 초과 chunk warning과 jsdom의 pseudo-element 경고는 있었지만 exit code는 0이었다.
패키지를 설치·업데이트하지 않았다.

## 6. 실DB 검증 상태

다음은 테스트 코드에 존재하지만 이번 실행에서 실제 PostgreSQL로 입증되지 않았다.

- ADMIN 반·학생·수강·TEACHER 배정 정상 흐름
- DB 저장 후 재조회
- 동일 학생·반 중복과 실제 unique 제약
- 동시 요청의 201/409 및 단일 행 보장
- FK/check 위반, 중간 실패, rollback 후 세션 복구
- ADMIN/TEACHER/ASSISTANT, 비활성 계정, 배정 해제
- 다른 반 IDOR/BOLA, role header 조작, CSRF
- 개인정보 최소 응답
- Message/Import/Auth 실제 DB 회귀 및 Import Confirm 호환성

따라서 중복·FK·rollback·동시성·RBAC 항목은 모두 **BLOCKED**이며 PASS가 아니다.

## 7. 발견 오류와 최소 수정

프로젝트 D드라이브 환경 스크립트가 pytest에 존재하지 않는 `--cache-dir` 옵션을 전달하여 실행이
실패했다. 원인은 pytest cache 설정 문법 오류였다. `scripts/use-d-drive-dev-env.ps1`을
`-o cache_dir=<D 경로>`로 최소 수정했으며, 같은 D cache 설정으로 Python 35개가 PASS했다.

Docker 오류 복구를 위해 프로젝트 코드나 DB를 변경하지 않았다. Docker AI 설정 변경 시도는
승인 정책에 의해 실행 전에 거부되었으며 실제 설정 파일은 변경되지 않았다.

## 8. React 업무 흐름

컴포넌트 자동 테스트 20개, lint, production build는 PASS했다. 그러나 개발 DB와 로그인 가능한
계정을 확인할 수 없어 실제 브라우저의 ADMIN 생성·수강·배정·로그아웃 및 TEACHER 담당 반 조회는
BLOCKED다. 자동 테스트 PASS를 업무 E2E 성공으로 표현하지 않는다.

## 9. 수정 파일

- `scripts/use-d-drive-dev-env.ps1`: 올바른 pytest D드라이브 cache 옵션
- `docs/phase6a-verification-and-hardening.md`: 본 검증 보고서

그 외 Phase 6A 구현 코드는 이번 검증 단계에서 수정하지 않았다.

## 10. 데이터·볼륨 보호

- 개발 DB 초기화/쓰기: 없음
- 테스트 DB TRUNCATE: 미실행
- Migration 적용: 없음
- 컨테이너/볼륨 삭제 또는 재생성: 없음
- Docker factory reset: 미실행
- WSL/VHDX 이동·수정: 없음
- 관리자 생성/삭제/비밀번호 변경: 없음
- 실제 개인정보/메일/SMS/유료 서비스: 사용 안 함
- 제거 항목: Docker가 오류 종료 후 남긴 0바이트 IPC endpoint 2개만 제거

## 11. 남은 위험과 다음 단계 착수 판정

Phase 6B 착수는 **보류**한다. Phase 6A 실DB 완료 기준을 충족하지 못했다.

다음 재개 조건은 Docker Desktop의 불필요한 AI 부가 기능을 끄는 설정 변경에 대한 사용자 명시
승인 또는 사용자의 직접 조치다. 승인 후 Docker를 재시작하여 라벨/포트/volume/health를 읽기
전용 확인하고, 개발 DB revision·중복·ACTIVE ADMIN을 읽기 전용 조회한다. 그 다음에만 안전 wrapper로
테스트 DB migration 및 Python/Java PostgreSQL suite를 실행한다. 테스트 DB PASS 후에도 개발 DB
Migration 003 적용은 별도 명시 승인이 필요하다.
