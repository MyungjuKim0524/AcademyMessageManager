# Academy LearningOps — Development History & Architecture

작성일: 2026-11-10 · **최종 갱신: 2026-11-25 (11-5 클라우드 배포·배포 후 점검 반영)**  
근거 기준:
- 현재 저장소의 소스·설정·Alembic 마이그레이션, `docs/` Phase 보고서와 `docs/reviews/` 결과 문서
- 기존 Java 저장소(GitHub `AcademyMessageManager`)의 태그 `v1.0-legacy`·`v1.1.0`·`v1.2.0`. 태그 시점의 코드를 직접 읽어 확인했고, 릴리스 설명만으로 구현을 단정하지 않았다.

> 이 문서는 검증된 사실, 기존 보고서의 과거 결과, 향후 제안을 구분한다.
> - **Java 버전**: 기존 저장소의 커밋·태그로 순서와 날짜를 확인할 수 있다(2절).
> - **웹 버전(Phase 1~11)**: v2.0.0 이전 작업(Phase 1~11-4)은 커밋 하나(`ca15e62`, 태그 `v2.0.0`, 2026-11-21)로 올라가 있어, 그 안의 날짜와 순서는 각 Phase 보고서의 작성일을 근거로 한다. 그 이후 변경은 `main`의 커밋 이력으로 확인할 수 있다.

## 1. Project Overview

### 프로젝트 배경

Academy LearningOps는 Java Swing 기반 학원 업무 자동화 프로그램을 React와 FastAPI 기반
웹서비스로 전환한 프로젝트다.
- 기존 Java 프로그램(v1.0~v1.2)은 단일 사용자 데스크톱 앱이다. 화면은 탭 8개였다: 데이터 불러오기, 메시지 생성, 이메일 발송, 발송 내역, 템플릿 설정, 보강 관리, 학생 관리, 메일 설정(`MainFrame.java`).
  - DB: v1.0·v1.1은 Oracle, v1.2부터 PostgreSQL
  - 이메일 발송: Jakarta Mail로 Gmail SMTP에 접속하는 방식(Gmail API가 아니다)

전환 초기(Phase 1~4)에는 기존 업무 규칙과 HTTP 계약을 보존하기 위해 API별로 Java와 Python을
비교하며 옮겼다. 인증·권한이 들어간 Phase 5 이후에는 FastAPI + React + PostgreSQL 모듈형
모놀리스가 주 개발 경로가 되었다.

Java 코드는 이 저장소에 포함하지 않는다(`.gitignore`의 `/src/`, `/pom.xml`).
- v1.0~v1.2는 기존 저장소의 태그로 확인할 수 있다.
- v1.2 이후 추가한 Java REST 어댑터 단계(2절)는 GitHub 어느 저장소에도 올라가 있지 않다.

버전별 비교와 개선 근거는 2절과 [9절](#9-legacy--web-비교-개선-항목별-근거)에 있다.

### 자동화 목표와 현재 웹 기능

| 기능 | 현재 FastAPI 상태 | 주요 근거 |
|---|---|---|
| Health, Message Preview(Java 계약 유지) | 구현 | `backend/app/main.py`, `backend/app/domain.py` |
| 직원 로그인·세션·CSRF·역할(ADMIN/TEACHER/ASSISTANT)·담당 반 범위 | 구현 | `backend/app/modules/auth/` |
| 직원 계정·담당 반 배정 관리(관리자), 반·학생·수강 관리 | 구현 | `backend/app/modules/learningops/` |
| 수업·출결·과제 등급·평가·성적·휴원/복귀 | 구현 | `backend/app/modules/academics/` |
| 학원 주간 엑셀 업로드(시간대 시트 선택, 미리보기 → 확정) | 구현 | `backend/app/modules/lesson_upload/` |
| 학부모 안내 메시지 생성·검토·확정·**모의 발송**·실패 재시도·반 단위 일괄 처리 | 구현(발송은 `MockSender`) | `backend/app/modules/notifications/` |
| 메시지 처리 현황·누락 탐지 | 구현 | `backend/app/modules/message_operations/` |
| 출결·성적 분석, 관심 필요 학생, 학생 학습 리포트, 대시보드 할 일 | 구현 | `backend/app/modules/analytics/` |
| 구 CSV/XLSX 가져오기(`/api/imports*`) | **제거**(Phase 9.6, 사용자 승인) | `docs/archive/phases/phase9-6-ux-workflow-report.md` |
| 실제 이메일·SMS 발송 | 미구현(모의 발송만). Java 버전의 Gmail SMTP 실발송은 이식하지 않음 | 8절 향후 검토 과제 |
| 보강 신청 관리(Java v1.x: 화면에서 신청·완료·취소, 상태 규칙에는 승인 포함, 상태별 안내 문구) | **미이식**. `makeup_request` 테이블 모델만 있고 API·화면이 없다. 메시지는 결석일 때 고정 문장 하나만 넣는다 | `backend/app/modules/notifications/engine.py`(`MAKEUP_SENTENCE`), 9.9절 |
| 발송 이력 전용 화면(`/deliveries`) | 미구현(Coming Soon 화면) | `frontend/src/app/router.tsx` |
| Kafka 이벤트 | 미구현(보류) | 의존성·코드 없음. 보류 결정은 `docs/archive/phases/phase6-event-architecture-design.md` |
| AI 기능 | 미구현(향후 검토, 범위 미정) | 8절, `docs/ENGINEERING_RETROSPECTIVE.md` 1절 |

React 메뉴(`frontend/src/layout/AppLayout.tsx`):
- 대시보드
- 학생·반 관리(관리자) / 담당 반 학생
- 수업·출결·성적
- 출결·성적 분석
- 엑셀 기반 성적 안내 메시지 생성(탭: 엑셀 업로드·검토·발송·누락·예외 생성·메시지 처리 현황·템플릿)
- 직원·담당 반 배정(관리자)

### 기술 스택

- Legacy(Java, 이 저장소 미포함): Java 17, Swing, Maven, JDBC(Oracle `ojdbc11` → v1.2에서 PostgreSQL 드라이버 추가), Apache POI, Jakarta Mail
- Web frontend: React 19, TypeScript 6, Vite 8, Ant Design 6, TanStack React Query 5, Axios 1.20, React Router 8, oxlint
- Backend: Python 3.12+, FastAPI 0.162, Pydantic 2.14, SQLAlchemy 2.1, Psycopg 3.3, Alembic 1.20, Uvicorn 0.54, argon2-cffi(Argon2), openpyxl + defusedxml(엑셀)
- Database: PostgreSQL 17.6
- Quality: pytest 9, HTTPX, Ruff, Vitest 5, Testing Library, JUnit 5(레거시), pip-audit·npm audit(수동 실행)
- Infrastructure: Docker Desktop, Docker Compose, WSL2

버전 근거:
- 웹: `backend/pyproject.toml`, `frontend/package.json`, `compose.postgres-test.yml`
- Java: 기존 저장소 태그의 `pom.xml`

## 2. Architecture Evolution

### Java 릴리스별 발전 과정 (기존 저장소 태그 기준)

아래 수치는 각 태그의 파일을 `git ls-tree`/`git show`로 직접 센 값이다. 경로는 기존 저장소 기준이다.

| 버전 | 날짜 | 구조 | DB·접근 | 발송 | 테스트 |
|---|---|---|---|---|---|
| `v1.0-legacy` | 2026-08-21 | Swing 단일 창 `view/MainFrame.java`(1,065줄)가 DAO·Service 9개를 직접 생성한다. 발송 반복문, 퇴원 제외, 이메일 형식 검사도 화면 안에 있다. 운영 Java 소스 30개 | Oracle(`sql/schema_oracle.sql`, 테이블 8개), JDBC DAO 6개. DB 접속 정보는 `config.properties` 파일에서만 읽는다. 일괄 반영은 DAO 안에서 `setAutoCommit(false)`·`commit`·`rollback` | `EmailSendService`: Jakarta Mail SMTP(`mail.smtp.*`, `Transport.send`). Gmail 앱 비밀번호는 `MailCredentialStore`가 AES-GCM + PBKDF2(210,000회)로 암호화해 보관한다. 결과는 `send_log`(`READY/SENT/FAILED/SKIPPED`) | **0개** |
| `v1.1.0` (Refactoring 1, PR #1) | 2026-09-01 | `domain` 패키지(상태 enum 6개, `LearningMessageComposer`, `MakeupGuidancePolicy`, `MessageSections`)와 `port`(`ConnectionProvider` 등 3개) 추가. `AcademyDataImportService`로 파일 읽기·검증을 하나의 유스케이스로 묶음. 화면의 발송 반복문은 그대로 | Oracle 유지. `DBConnection`이 환경변수를 파일보다 우선 | 변경 없음 | 5개 파일, `@Test` 10개(도메인·검증·CSV 수식 주입) |
| `v1.2.0` (PostgreSQL Redesign) | 2026-09-03 | `TestScore`, `ImportHashUtil`(파일 SHA-256) 추가. `MainFrame`은 1,077줄로 발송 반복문이 여전히 화면에 있다 | PostgreSQL 스키마(`sql/schema_postgresql.sql`, 테이블 13개, `CHECK` 22줄, 외래키 14개), 시드·제약 검증 SQL, ERD v1.2. `send_log`를 `message_draft → delivery_job → delivery_attempt`로 분리하고 `import_job/row/error` 감사 테이블을 둠. `pom.xml`에는 Oracle·PostgreSQL 드라이버가 함께 있음 | 변경 없음(SMTP). 발송 관련 UNIQUE는 `(delivery_job_id, attempt_no)`뿐이고, 멱등 키나 메시지당 성공 1회 제약은 없다 | 9개 파일, `@Test` 17개. DB 통합 테스트 2개는 `RUN_POSTGRES_INTEGRATION=true`일 때만 실행 |
| (태그 없음) Java REST 어댑터 단계 | ~2026-11-04 | Java `HttpServer` 기반 `api` 패키지 21개(`ApiServer`, `ApiRoutes`, `CorsPolicy`, `RequestSizeLimiter`, `SecurityHeaders`, multipart 리더). Import Preview·Confirm·History 서비스·JDBC 저장소 13개. React 화면이 이 API를 썼다 | v1.2 스키마 + Import 확정 멱등 키 | 변경 없음 | Java 47개 중 42 PASS, 5 SKIP(PostgreSQL). React 5파일 15개 PASS(`docs/archive/phases/fastapi-transition-baseline.md`) |

- v1.0의 문제와 v1.1의 개선 목표는 그 시점의 문서에 남아 있다. 이 저장소의 사본은 기존 저장소 `v1.2.0`의 문서와 같다.
  - `docs/archive/java-v1/PORTFOLIO_BACKEND_REFACTORING_EVIDENCE.md`(문제 6개와 코드 증거)
  - `docs/refactoring/01-business-readable-refactoring.md`
  - `docs/refactoring/02-backend-architecture-refactoring.md`
  - `docs/archive/java-v1/BACKEND_REQUIREMENTS.md`
- v1.1 문서(`02-…` "다음 수직 기능에서 권장할 작업")가 다음 과제로 남긴 네 가지와 이후 경과
  1. 화면의 DB 반영·메일 발송 절차를 use case로 이동: **Java에서는 v1.2까지 이뤄지지 않았다**(`MainFrame`의 `sendEmail` 호출 2곳). 웹 전환에서 서비스 계층으로 옮겨졌다(9.2절).
  2. DAO 통합 테스트: v1.2의 `PostgreSqlDaoIntegrationTest`(Oracle Testcontainers가 아니라 전용 PostgreSQL 테스트 DB)
  3. `ImportRow`를 입력 DTO와 도메인 모델로 분리: Java에서는 확인되지 않았다. 웹에서는 업로드 파서(`lesson_upload/workbook.py`)와 저장 모델이 분리되어 있다.
  4. 재시도·속도 제한이 있는 발송 어댑터: **미구현**. 웹은 모의 발송만 한다(9.7절).
- Oracle → PostgreSQL 전환 문서(`docs/database/oracle-to-postgresql-migration.md`)는 ETL 계획을 담고 있다. 다만 실제 Oracle 데이터를 옮긴 실행 기록은 확인되지 않는다. 검증 기록은 새 스키마·시드 적용과 DAO 통합 테스트까지다.

### FastAPI 전환 의사결정

1. 공통 fixture로 JSON·상태 코드·오류 구조를 고정하고, DB가 없는 API(Preview)부터 이식했다(Phase 1~2).
2. DB API는 SQLAlchemy Session과 PostgreSQL 트랜잭션으로 옮기고, 개발·테스트 DB를 물리적으로 분리했다(Phase 3~4).
3. 인증 도입(Phase 5) 후에는 신규 업무 기능을 FastAPI 모듈로만 구현했다. Router → Service → Repository 계층, 서버 측 세션·CSRF·RBAC·담당 반 범위 검사를 쓴다.
4. 외부 발송 채널 연동보다 인증·인가, 데이터 정합성, 트랜잭션·동시성, 유지보수성을 우선했다. 메시지 발송은 `MockSender`로 업무 흐름을 끝까지 구현했다(Phase 8~9).
5. 업무 흐름 밖이 된 구 CSV/XLSX 가져오기는 FastAPI·React에서 제거했다. 학원 주간 엑셀 업로드가 이를 대체한다(Phase 8.1, 9.6).

### 현재 데이터 흐름

```text
React (Axios, withCredentials + X-CSRF-Token)
  → (개발) Vite 프록시 /api → FastAPI(127.0.0.1)
  → CompatibilityMiddleware: Origin 허용 목록, 본문 크기 제한, 보안 헤더, 요청 ID,
                             미처리 예외의 정제 로그(예외 문구 미기록)
  → Router 의존성: 실행 모드 게이트 → 세션 인증 → CSRF → 역할
  → Service: 업무 규칙, 담당 반 검사, 트랜잭션·행 잠금, 감사 기록
  → Repository (SQLAlchemy 2.1)
  → PostgreSQL 17.6 (FK·CHECK·UNIQUE·EXCLUDE·트리거)
```

FastAPI 모듈: `auth`, `learningops`, `academics`, `lesson_upload`, `notifications`,
`message_operations`, `analytics`. 모듈 간 순환 의존은 없다(Phase 10.5-A 리뷰).

Java 경로(Swing / Java HttpServer → service → port → JDBC → PostgreSQL)는 이 저장소에 포함하지 않는다.
- Java 시절 산출물 중 지금도 쓰이는 것은 두 가지다.
  - `sql/schema_postgresql.sql`: Alembic `001_java_schema_baseline`이 읽는 기준 스키마
  - `tests/fixtures/contract/`: Python 계약 테스트
- Java 실발송 기록용 테이블 4개(`message_template`, `message_draft`, `delivery_job`, `delivery_attempt`)는 스키마에 남아 있지만, 웹 서비스는 쓰지 않는다(4절).

## 3. Development Timeline

각 항목의 상세와 검증 결과는 괄호 안 문서에 있다.

### Phase 1 — FastAPI 기반과 Message Preview (2026-11-04)
- `GET /api/health`, `POST /api/messages/preview`를 Java 응답 계약 그대로 이식했다.
- `{code, message, fields}` 오류 형식, 요청 ID·CORS·크기 제한·보안 헤더. Java/Python 공통 fixture 7/7 일치.
- (`docs/archive/phases/phase1-fastapi-migration.md`)

### Phase 2 — Import Preview (2026-11-06)
- CSV/XLSX를 DB 저장 없이 파싱·검증했다(10MiB, 5,000행, 64열). 계약 27/27 일치.
- 이 모듈은 Phase 9.6에서 제거되었다.
- (`docs/archive/phases/phase2-import-preview-migration.md`)

### Phase 3 — PostgreSQL Infrastructure (2026-11-08)
- 개발 DB(`academy_learningops_dev`, 55431)와 테스트 DB(`academy_learningops_test`, 55432)를 컨테이너·계정·볼륨·라벨로 분리했다.
- DB URL 허용 목록, Alembic `001_java_schema_baseline`.
- (`docs/archive/phases/phase3-postgresql-infrastructure.md`)

### Phase 4 — Secure Import History/Confirm (2026-11-09)
- Import Confirm의 단일 트랜잭션, UUID 멱등 키, 감사 기록 동시 저장.
- 이 기능도 Phase 9.6에서 제거되었다.
- (`docs/archive/phases/phase4-secure-import-migration.md`)

### Phase 5 — 인증·RBAC (2026-11-12)
- 로그인/로그아웃/`me`, ADMIN·TEACHER·ASSISTANT 직원 계정.
- Argon2id, 서버 측 불투명 세션(해시 저장), HttpOnly·SameSite 쿠키, 세션 결합 이중 제출 CSRF.
- (`docs/archive/phases/phase5-auth-rbac-implementation.md`, `docs/decisions/0001-local-session-authentication.md`)

### Phase 6A·6B — 학생·반·수강, 직원·담당 반 배정 (2026-11-15 ~ 11-17)
- `learningops` 모듈: 관리자의 반·학생·수강 등록, 담당 반 학생 조회.
- 직원 생성·활성/비활성(세션 폐기), 담당 반 배정·해제.
- 학생·반 중복 수강과 열린 배정 중복을 DB UNIQUE로 차단(003, 004), 직원 표시 이름(005).
- (`docs/archive/phases/phase6a-*.md`, `docs/archive/phases/phase6b-staff-classroom-management.md`)

### Phase 7·7.1 — 수업·출결·성적, 안정화 (2026-11-18)
- 수업 회차, 출결, 평가·성적.
- 담당 반 권한, DB 제약, 트리거 기반 버전(동시 수정 감지), 변경 감사(006).
- 같은 날 복수 교시, 날짜가 있는 휴원 이력(기간 중복 EXCLUDE), 인정결석(007).
- (`docs/archive/phases/phase7-lessons-attendance-grades.md`, `docs/archive/phases/phase7-1-stabilization.md`)

### Phase 8·8.1 — 학부모 안내 메시지, 엑셀 업로드 (2026-11-18 ~ 11-19)
- 템플릿 → 초안 → 검토 → 확정 → **모의 발송** → 이력.
- 메시지 행 잠금·버전, 멱등 키, 메시지당 성공 1회 부분 UNIQUE(008).
- 학원 주간 엑셀(시트 = 시간대, 반 블록)을 업로드하면 반별 출결·등급·점수가 저장되고, 수업 유형별 기본 템플릿으로 초안을 만든다(009).
- (`docs/archive/phases/phase8-parent-notification-workflow.md`, `docs/archive/phases/phase8-1-excel-upload.md`)

### Phase 9·9.5·9.6 — 메시지 운영, UI/UX (2026-11-20)
- 처리 현황 집계, 미처리·실패 탐지, 실패 건 수동 재시도(같은 멱등 규칙).
- 업무 중심 메뉴·화면 정리(프론트엔드 전용).
- 구 CSV/XLSX 가져오기 제거, `import_*` 테이블 삭제(010, 데이터가 있으면 거부).
- (`docs/archive/phases/phase9-message-operations.md`, `docs/archive/phases/phase9-5-ux-architecture-improvement.md`, `docs/archive/phases/phase9-6-ux-workflow-report.md`)

### Phase 10·10.5 — 교육 데이터 분석, 아키텍처 리뷰 (2026-11-20)
- 반별·학생별 출결 통계, 성적 분석, 지표 정의 문서.
- 아키텍처 리뷰 결과 수정:
  - 확정 메시지도 원본이 바뀌면 발송 차단(H1)
  - 반 학생 목록 절단(M3), 레거시 의존(M4), '진행된 수업' 규칙 공통화(B-2)
- (`docs/archive/phases/phase10-learning-analytics.md`, `docs/reviews/phase10_5_*.md`)

### Phase 11 — 통합·업무 개선·보안·정합성·릴리스 준비·배포 (2026-11-20 ~ 11-24, 2026-11-24 배포 완료)
- **11-0**: 통합 테스트 스크립트의 컨테이너 라벨·포트 검사 결함 수정(PS 5.1에서 검사를 건너뛰던 문제). (`docs/reviews/phase11_0_test_guard_fix.md`)
- **업무 개선**(사용자 요청):
  - 반 단위 일괄 검토·확정·모의 발송(`docs/archive/phases/phase11-batch-review.md`)
  - 업로드 시간대(시트) 선택·변경 없는 행 생략(`docs/archive/phases/phase11-upload-time-slots.md`)
  - 학생·반 관리 재구성(`docs/archive/phases/phase11-class-student-management.md`)
  - 성적 분석 재설계, 직원 삭제 B안(011), 대시보드 할 일(`docs/archive/phases/phase11-analytics-staff-dashboard.md`)
- **11-2 보안**: 감사(`docs/reviews/phase11_2_security_audit.md`) 후 다음을 수정했다.
  - SEC-01: 업로드 '신규'가 다른 반 기존 학생을 재사용하던 문제
  - SEC-02: 관리자 변경 감사 누락
  - SEC-03: 로그인 제한의 프록시 식별·동시 요청 우회·계정 잠금 완화
  - SEC-06: XLSX 자원 고갈
  - SEC-07: 예외 로그의 개인정보
  - SEC-08·09: 문서 비공개·HSTS 설정
  - SEC-11: 의존성 검사·패치
  - (`docs/reviews/phase11_2_b1_results.md`, `phase11_2_b2_results.md`, `phase11_2_b2_followup_results.md`)
  - 배포 설정 확정본: `docs/deployment/phase11_5_security_deployment_guide.md`
- **11-3 정합성**: 트랜잭션·동시성 감사 후 4건을 수정했다(`docs/reviews/phase11_3_integrity_audit.md`, `phase11_3_integrity_remediation.md`).
  - INT-01: 발송 원본 TOCTOU → 원본 행 고정 순서 잠금
  - INT-02: 평가 조회 `populate_existing`
  - INT-03: 취소 수업에 평가 연결
  - INT-04: 엑셀 확정 이중 제출 → 반별 advisory lock + 재분석
- **11-4-A 성능·예외 처리**(`docs/reviews/phase11_4_a_performance_results.md`)
  - 일괄 처리 쿼리 증폭 제거, 진도표 단일 조회, 업로드 본문 선형 버퍼링
  - DB 연결 `connect_timeout=5`
  - DB 장애 → 503 `DATABASE_UNAVAILABLE`, 잠금 충돌 → 409 `TRANSACTION_CONFLICT`
- **11-4-B 실행 모드·계정 보안**(`docs/reviews/phase11_4_b_runtime_account_results.md`, 스키마 변경 없음)
  - SEC-04: `ACADEMY_DB_MODE=production`과 시작 시 설정 검증
  - SEC-05: 서버 기준 유휴 세션 만료(기본 60분)
  - SEC-10: 비밀번호 변경, 관리자 발급 일회용 재설정 코드
- **11-4-C 회귀·릴리스 준비**(`docs/reviews/phase11_4_release_readiness.md`)
  - 기존 Vitest 실패 1건 원인 해결(antd 체크박스 등록 타이밍, 테스트 수정)
  - 모의 발송 문구 정정, 배포 준비도 점검
  - 판정: 로컬 READY / 배포 CONDITIONALLY READY
- **11-5 Step 1 업로드 전 점검**(2026-11-21)
  - 비밀정보·개인정보 검사
  - `.gitignore` 보완: DB 덤프 패턴, Java `/src/`·`/pom.xml`·`/scripts/start-backend.ps1` 제외
  - README·`backend/README.md`에서 Java 빌드 설명 정리
  - `scripts/run-postgres-integration.ps1`·`scripts/verify-all.ps1`에서 Maven 단계 제거
  - GitHub 업로드는 아직 하지 않았다.
- **개발 DB Migration 011 적용**(2026-11-21)
  - 원인: `scripts/start-fastapi.ps1`의 사전 점검이 "head 011 미적용(현재 010)"으로 실행을 막았다. 011은 그동안 테스트 DB에만 적용되어 있었다.
  - 처리: 백업(`data/backups/academy_learningops_dev_before_011_20261121.dump`, Git 제외)을 만든 뒤 `scripts/migrate-dev-db.ps1`로 개발 DB에만 적용했다.
  - 확인: revision 011, 직원 데이터 변화 없음, 사전 점검 통과
- **화면 문구·배치 조정**(2026-11-21, 사용자 요청, 프론트엔드 전용)
  - 보호자 이메일 수정 버튼·링크·열 제목·창 제목을 "메일 주소 변경"으로 통일했다. 대상 화면은 전체 학생, 반별 학생, 메시지 처리 현황, 누락·예외 생성이다.
  - 반별 학생 표: "메일 주소 변경" 열을 "휴원 관리" 앞으로 옮겼다.
  - 직원 목록 계정 관리 버튼 순서: 이름 수정 → 재설정 코드 → 비활성화 → 삭제
  - 출결 분석: "기록 완료율"을 "출결 입력 완료율"로, 보조 문구를 "입력 n / 대상 m"으로 바꿨다. 계산식(`record_rate`)은 그대로다.

- **v2.0.0 업로드 후 문서 정비**(2026-11-21~22)
  - v2.0.0: 커밋 `ca15e62`와 태그 `v2.0.0`을 GitHub `main`에 일반 Push했다(기존 이력·태그 보존).
  - ERD: 코드에서 자동 생성하는 `docs/database/ERD.md`를 추가했다(`backend/scripts/generate_erd.py`). 이전 ERD는 Java v1.2 기록으로 표시했다.
  - Migration 절차 보완: 001이 루트의 `sql/`을 읽는다는 점, 007의 `btree_gist` 확장 권한을 배포 가이드 4절과 릴리스 준비도 5·7절에 추가했다.
  - README 재구성: 소개·기능·아키텍처·버전 이력 중심으로 바꿨다. 로컬 환경·테스트·개발 정책은 `docs/DEVELOPMENT_GUIDE.md`로 옮겼다.
- **반 일괄 처리 결석생 선택 규칙**(2026-11-23, 사용자 요청, 프론트엔드 전용)
  - 배경: 결석·인정결석 학생도 설계대로 초안이 만들어지는데, 전체 선택으로 함께 확정·발송될 수 있었다.
  - 전체 선택은 결석·인정결석 메시지를 빼고 선택하고, 확정 확인창에 포함된 결석·인정결석 건수를 표시한다. 직접 체크하면 지금처럼 확정·발송할 수 있다.
  - 초안 생성·확정·발송 규칙, API, DB는 바꾸지 않았다(`docs/archive/phases/phase11-batch-review.md` 동작 2).
- **11-5 클라우드 배포**(2026-11-24, 사용자 수행)
  - 서비스: https://academy-message-manager.vercel.app — Vercel(React) · Render(FastAPI) · Neon(PostgreSQL). 운영 DB에는 시연용 가상 데이터만 있다.
  - 배포 후 점검(2026-11-25 확인, `docs/reviews/phase11_4_release_readiness.md` 12절, 배포 가이드 6·8절):
    - 확인: Render 기동·환경변수(R1), Neon 연결(R2, Direct connection), 워커·인스턴스 1개(R4), 세션 쿠키 속성, API 문서 비공개(Render 주소의 `/openapi.json`·`/docs` 404, `ACADEMY_API_DOCS` 없음), 진단 엔드포인트 꺼짐
    - 로그인 제한(R3): **구성 A′**(비밀 헤더 없음, `cf-connecting-ip`)로 운영한다. Render 환경변수로 확인했고, 진단 엔드포인트 실측(`source`, `CF-Connecting-IP` 도착)은 하지 않았다. Vercel 송신 주소 단위로 묶이는 위험(배포 가이드 3절)은 가상 데이터 전용 시연 서비스이고 재시작으로 즉시 해제되므로 수용했다.
    - 생략·미확인: 플랫폼 로그의 쿼리 문자열(R5)은 가상 데이터만 있어 생략, 무료 플랜 유휴 정지(R6)는 측정하지 않았다.
  - 발견: 없는 경로의 404 응답 본문이 `INTERNAL_ERROR`("요청 처리 중 오류가 발생했습니다.")다(`backend/app/main.py`의 `http_error_handler`). 상태 코드는 404라 노출은 없다.
  - 수정(2026-11-25): 404는 `NOT_FOUND`("요청한 기능을 사용할 수 없습니다.")로 응답한다(`http_error_handler`). 회귀 테스트 `backend/tests/test_api.py::test_unknown_path_is_a_plain_not_found`.

## 4. Database Architecture

### 스키마

업무 테이블 20개(+ `alembic_version`). 모델은 `backend/app/db/models/tables.py`, 기대 목록은
`backend/app/db/schema.py`(`EXPECTED_TABLES`)에 있다.

- **현재 ERD**: [`docs/database/ERD.md`](database/ERD.md)
  - Mermaid 형식이며, `backend/scripts/generate_erd.py`가 모델에서 자동 생성한다.
  - Migration 뒤에 다시 실행하고, `--check`로 최신 여부를 확인한다.
- **이전 ERD**: `docs/database/`의 `AMM_PostgreSQL_ERD_v1.3.*`, `PostgreSQL ERD v1.2.drawio`, `import-audit-erd.md`는 Java v1.2 시절(13개 테이블) 기록이다.
  - 웹 버전에서 추가된 10개 테이블이 빠져 있다.
  - Migration 010으로 삭제된 `import_*` 3개가 들어 있다.

- 학습: `student`, `classroom`, `enrollment`, `enrollment_pause`, `lesson`, `lesson_result`, `assessment`, `assessment_result`, `makeup_request`
- 직원·보안: `staff_user`, `classroom_staff_assignment`, `auth_session`, `audit_log`
- 학부모 안내(FastAPI): `notification_template`, `parent_notification`, `notification_send_attempt`
- Java 레거시 메시지: `message_template`, `message_draft`, `delivery_job`, `delivery_attempt`(Java 실제 발송 기록 전용. FastAPI 모의 발송과 섞지 않음)

### Migration 이력

`001_java_schema_baseline` → `002_staff_auth_rbac` → `003_phase6a_enrollment_integrity` →
`004_phase6b_assignment_integrity` → `005_staff_display_name` → `006_phase7_lessons_grades` →
`007_phase71_sessions_pauses` → `008_phase8_notifications` → `009_phase81_lesson_upload` →
`010_drop_legacy_import_tables` → `011_staff_deleted_status`(단일 선형 체인)

- 테스트 DB는 head(011)이고, `alembic check` 결과 모델과 차이 없음(2026-11-20, Phase 11-3-A).
- 개발 DB에는 자동으로 적용하지 않는다. 적용은 `scripts/migrate-dev-db.ps1`로 하며, 사전 백업을 권장한다.
  - 2026-11-21 기준 개발 DB도 head(011)다. 읽기 전용으로 확인했고, 3·9.3절에 경위가 있다.
- 실행 전 사전 점검: `scripts/start-fastapi.ps1`은 `backend/scripts/auth_preflight.py`로 세 가지를 확인한 뒤에만 서버를 시작한다.
  - DB·사용자 정체
  - revision이 코드의 head와 같은지
  - 활성 관리자가 있는지
  - 그래서 개발 DB에 Migration을 적용하지 않으면 실행이 멈춘다.

### 격리 전략

| 보호 장치 | 개발 DB | 테스트 DB |
|---|---|---|
| 전용 컨테이너 | `academy-learningops-postgres-dev` | `academy-learningops-postgres-test` |
| 전용 사용자 | `academy_dev` | `academy_test` |
| 전용 볼륨 | Yes | Yes |
| 전용 port | 55431 | 55432 |
| destructive label | forbidden | allowed |
| 앱 측 URL 허용 목록 | `db/safety.py` | `db/safety.py` + test mode 이중 스위치 |

- 통합 테스트 실행기(`scripts/run-postgres-integration.ps1`)는 라벨·포트·DB 이름·사용자를 모두 확인한 뒤에만 실행한다(11-0에서 수정).
- 기존 통합 테스트는 테스트 DB를 TRUNCATE한다. Phase 11-3-B의 신규 동시성 테스트는 초기화 없이 접두사 데이터를 쓴다.

### 트랜잭션·동시성 원칙

- 요청마다 Session 하나, 서비스가 commit·rollback을 책임진다. 업무 변경과 `audit_log`는 같은 commit으로 저장된다.
- 동시 수정 방지는 다음 수단을 함께 쓴다.
  - `version`(UPDATE마다 트리거로 +1) 비교와 행 잠금(`FOR UPDATE`/`FOR SHARE`)
  - 중복은 UNIQUE·부분 UNIQUE·EXCLUDE 제약이 최종 차단
- 메시지 발송은 메시지 행 잠금 → 원본 행(반·수업·연결 평가·수강·학생) 고정 순서 잠금 → 원본 검사 → 발송·기록·감사 commit 순서다(Phase 11-3-B).
- 엑셀 확정은 반별 트랜잭션 advisory lock 후 다시 분석해 반영한다.
- 기본 격리 수준은 READ COMMITTED다.

## 5. Security & Reliability

| 항목 | 구현 상태 | 근거/한계 |
|---|---|---|
| 직원 인증·세션 | 구현 | Argon2id, 해시 저장 세션, 로그아웃·비활성화·삭제 시 세션 폐기, 8시간 절대 만료 |
| CSRF·CORS | 구현 | 세션 결합 이중 제출, Origin 허용 목록 |
| RBAC·담당 반(BOLA) | 구현 | 역할 + 담당 반 배정 기간을 요청마다 재검사, 반 안에서만 ID 해석 |
| 로그인 시도 제한 | 구현 | 주소+계정 5, 주소 20, 계정 20(15분). 원자적 예약, 알려진 주소 예외, 프록시 출처 설정. 프로세스 메모리 저장(워커 1 전제) |
| 감사 기록 | 구현 | 업무·인증·관리자 변경. 업무 변경과 원자적, 개인정보 원문 미기록 |
| 입력·파일 검증 | 구현 | Pydantic, 업로드 10MB·5,000행·64열, ZIP 항목 수·해제 총량·순회 행 상한, defusedxml |
| 로그 개인정보 | 구현 | 미처리 예외는 유형·SQLSTATE·요청 ID만 기록, SQL 파라미터 숨김 |
| API 문서·HSTS | 설정 제어 | `ACADEMY_API_DOCS`(기본 꺼짐), `ACADEMY_HSTS_MAX_AGE`(기본 0) |
| 데이터 정합성·동시성 | 구현 | 4절. Phase 11-3 감사·수정 |
| 의존성 취약점 | 수동 검사 | pip-audit(PyPI·OSV) 0건, npm audit 0건(2026-11-20 패치 후). CI 자동화는 미구현 |
| 운영 실행 모드 | 구현(11-4-B), **클라우드 미검증** | `ACADEMY_DB_MODE=production`. 시작 시 설정을 검증하고, 위반하면 시작을 거부한다(설정 이름만 보고). development/test는 기존처럼 루프백·고정 DB만 허용 |
| 유휴 세션 만료, 비밀번호 변경·재설정 | 구현(11-4-B) | 유휴 60분(서버 판정, 최대 약 1분 일찍 만료 가능), 비밀번호 변경, 관리자 발급 일회용 재설정 코드(메모리 저장 → 워커 1 전제) |
| 실제 외부 발송 | 미구현 | 모의 발송만. 연동 전 트랜잭션 분리 필요(INT-I1, 8절) |

## 6. Test & Quality Assurance

### 테스트 구조

- Python 단위: 도메인·템플릿 엔진·워크북 파서·설정·DB 안전장치·주소 식별·업로드 한도·로그 정제
- Python 통합(격리 PostgreSQL): 인증·RBAC·직원·학생·수업·출결·성적·업로드·메시지·운영·분석·스키마·마이그레이션 왕복, Phase 11 보안·동시성 회귀
- React: Vitest/Testing Library 화면 상호작용 테스트
- Java(레거시): JUnit 5, 계약 fixture

### 최근 실행 결과

| 명령 | 결과 | 시점 |
|---|---|---|
| `ruff check .` | PASS | 2026-11-25 (`verify-all.ps1`, 404 응답 수정 후 한 번 더) |
| `pytest -m "not postgres"` | 166 실행 · 166 PASS | 2026-11-25 (404 응답 수정 후) |
| `pytest -m postgres`(격리 테스트 DB, 전체) | 141 PASS, 0 FAIL, 0 SKIP | 2026-11-21 (11-4-B 최종 백엔드 변경 후, 사용자 승인 하 전체 회귀) |
| `pytest -m postgres`(비파괴: 11-3 동시성·11-4-A·11-4-B) | 36 PASS | 2026-11-21 (11-4-C) |
| `vitest run`(전체) | 15 파일 · 114 실행 · 114 PASS / 0 FAIL | 2026-11-25 (`verify-all.ps1`) |
| `tsc -b`, `oxlint`, `npm run build` | PASS | 2026-11-25 (`verify-all.ps1`) |
| `pip-audit`, `npm audit` | 알려진 취약점 0 | 2026-11-20 (Phase 11-2-B-2) |
| `mvn test`(Java) | 48 PASS(마지막 기록) | Phase 9 — 이후 미재실행. Java는 이 저장소에 없다 |

- 11-2부터 실패하던 Vitest 1건("uploads only the chosen time slot…")은 11-4-C에서 원인을 해결했다. 제품 결함이 아니라 antd `Checkbox.Group`의 값 등록 타이밍 문제였고, 테스트를 고쳤다.
- 11-4-C 이후의 화면 문구 변경(3절 "화면 문구·배치 조정")은 먼저 영향받는 폴더만 실행했다(learningops·staff·message-operations 37, notifications·analytics 31, 모두 PASS). 이어서 전체 Vitest를 다시 실행해 113/113 PASS를 확인했다.
- 표의 수치는 **실행해서 통과한 테스트 수**이며 커버리지(코드 실행 비율)가 아니다. 커버리지는 측정하지 않았다(9.8절).

## 7. Current Project Status

### 완료

- 직원 인증·세션·CSRF·RBAC·담당 반 범위, 직원·배정 관리
- 반·학생·수강, 수업·출결·과제 등급·평가·성적·휴원/복귀
- 학원 주간 엑셀 업로드(시간대 선택, 변경 없는 행 생략, 재업로드 시 바뀌는 값 미리 보기)
- 학부모 안내 메시지 생성·검토·확정·모의 발송·재시도·반 일괄 처리, 처리 현황·누락 탐지
- 출결·성적 분석, 관심 필요 학생, 학생 학습 리포트, 대시보드 할 일
- Phase 11-2 보안 수정(SEC-01·02·03·06·07·08·09·11), Phase 11-3 정합성 수정(INT-01~04)
- Phase 11-4: 성능·예외 처리(A), 운영 실행 모드(SEC-04)·유휴 만료(SEC-05)·비밀번호 변경·재설정(SEC-10)(B), 회귀·릴리스 준비(C)
- 배포 보안 설정 가이드 확정본, GitHub 업로드 전 점검(11-5 Step 1), v2.0.0 GitHub 업로드(2026-11-21)
- 클라우드 배포(2026-11-24): Vercel · Render · Neon. 배포 후 점검 결과는 3절 Phase 11 "11-5 클라우드 배포"
- 개발 DB를 head(011)로 갱신(2026-11-21, 백업 후)

### 부분 완료 또는 검증 필요

- 배포 후 점검 중 미확인: 로그인 제한 구성 A′의 진단 엔드포인트 실측(R3, 환경변수로만 확인), 무료 플랜 유휴 정지 측정(R6). R5는 가상 데이터 전용이라 생략(`docs/reviews/phase11_4_release_readiness.md` 12절).
- Java 레거시: 이 저장소에 포함하지 않는다. Migration 010(`import_*` 삭제) 이후 Java 테스트를 다시 실행한 기록은 없다.
- 빈 PostgreSQL 17 일회용 DB에서 001→011 전체 재구성 검증 완료(2026-11-23, Phase 11-5-B). `011_staff_deleted_status` head, `btree_gist`, FK·UNIQUE·CHECK·Trigger와 Seed 멱등성·부분 복구를 확인했다.
- 개발 DB 불변조건 점검: 미실행(사용자 보류). revision은 2026-11-21에 확인했다.
- Phase 11 업무 시나리오 수동 점검표(`docs/archive/phases/phase11-manual-scenario-checklist.md`): 실행 결과는 이 문서에서 확인하지 않았다.
- API 계약 문서(10.5 M5): Java 시절 문서 3개(`docs/api/openapi-java-v1-legacy.yaml`(옛 `openapi.yaml`), `docs/api/HTTP_API_SECURITY.md`, `docs/archive/java-v1/IMPORT_CONFIRM.md`)에 "이전 기록" 표시를 붙였다(2026-11-24). 현재 API 명세는 `backend/scripts/generate_openapi.py`가 FastAPI 앱에서 생성하는 `docs/api/openapi.json`과 엔드포인트 요약 `docs/api/README.md`다(2026-11-25, 82개). 레거시 미리보기 API(`/api/messages/preview`) 유지 여부(M4)는 아직 결정하지 않았다.

### 미완료

- 보강 신청 관리의 웹 이식(Java v1.x 기능 누락, 9.9절). 배포 후 검토한다.
- AI 기능(향후 검토, 범위 미정)
- 실제 발송 채널과 발송 트랜잭션 분리(INT-I1), 발송 이력 전용 화면
- CI/CD, 운영 모니터링, 백업·복구 자동화
- Kafka 이벤트(보류)

## 8. Future Roadmap

순서와 단계는 기존 보고서의 인계 사항을 따른다. 아직 정하지 않은 항목은 "미정"으로 둔다.

| 단계 | 작업 | 근거 |
|---|---|---|
| ~~Phase 11-4~~ 완료 | 운영 실행 모드(SEC-04), 유휴 만료(SEC-05), 비밀번호 변경·재설정(SEC-10), 기존 React 실패 테스트 수정 | `phase11_4_b_runtime_account_results.md`, `phase11_4_release_readiness.md` |
| ~~Phase 11-5~~ 배포 완료(2026-11-24) | GitHub 업로드(2026-11-21), 사용자가 직접 수행한 배포(Neon + Render + Vercel)와 배포 직후 점검(미확인 항목은 7절). **남은 것**: CI에 pip-audit·npm audit 추가 | `deployment/phase11_5_security_deployment_guide.md`, `deployment/phase11_5_a_neon_guide.md`, `phase11_4_release_readiness.md` 7~11절 |
| 배포 이후 | 보강 신청 관리 웹 이식 여부 결정. 현재 릴리스에는 넣지 않고, 업무 안정화·배포 후 필요성과 구현 비용을 검토한다 | 9.9절, `ENGINEERING_RETROSPECTIVE.md` 9절 |
| 미정(범위·일정 미정) | **AI 기능 추가 검토**. FastAPI(Python)를 고른 이유 중 하나로, 학원 업무 자동화에 AI 기능을 더하는 방향이다. 구체 기능·데이터·개인정보 처리 방식은 정해지지 않았고, 현재 코드에 AI 기능은 없다 | `ENGINEERING_RETROSPECTIVE.md` 1절 |
| 미정 | 개발 DB 불변조건 읽기 전용 점검(승인 시). 빈 DB 001→011 재구성은 Phase 11-5-B에서 완료 | `phase11_3_integrity_remediation.md` 12~13절 |
| 결정됨 | Java 레거시는 저장소에 포함하지 않음(2026-11-21). 기존 Java 저장소 태그가 이력의 근거 | 2·9절 |
| 미정 | 실제 발송 도입 시 INT-I1(외부 I/O·트랜잭션 분리) | 아래 향후 검토 과제 |

### 향후 검토 과제 — 보호자 휴대전화 기반 SMS/LMS 발송 체계 (2026-11-20 추가)

> **상태: 계획, 미구현.** 진행 중인 Phase 11(통합·보안·정합성 검증)과 별개인 후속 고도화 방향이다.
> 발송 공급자, 비용, DB 변경 규모, 일정, Phase 번호는 정해지지 않았다.

**배경 (확인된 사실)**

- **Java Swing 버전**은 실제 이메일을 발송했다.
  - 방식: Jakarta Mail로 Gmail SMTP(STARTTLS)에 접속하고, Gmail 계정과 앱 비밀번호를 마스터 암호로 암호화해 저장한다.
  - 발송 결과는 `SENT`/`FAILED`/`SKIPPED` 로그로 남기고, 실패 건 재시도를 지원한다(기존 저장소 `v1.2.0`의 `src/main/java/com/academy/message/service/EmailSendService.java`, `dao/SendLogDAO.java`).
  - 실제 학원 업무는 문자(SMS/MMS) 중심이었지만, 당시 무료로 사용할 수 있는 이메일 방식을 채택했다.
- **FastAPI 웹서비스**는 메시지 생성 → 검토 → 확정 → 모의 발송 → 실패·재시도·이력 관리까지의 업무 로직을 구현했다.
  - 발송은 프로세스 내부의 `MockSender`가 대신하며 네트워크로 나가는 발송은 없다.
  - Gmail 실발송은 웹서비스로 이식하지 않았다.
  - 마이그레이션에서는 외부 발송 채널 연동보다 인증·인가, 데이터 정합성, 트랜잭션·동시성, 유지보수성을 우선했다(Phase 8~11 보고서).
- 웹서비스 전환 후 실제 업무 요구사항을 다시 평가하면서, 전화번호 기반 문자 발송을 후속 고도화 방향으로 정했다.

**전환 시 고려할 현재 코드 상태 (2026-11-20 확인)**

- 수신 대상은 이메일 주소다: `student.parent_email`, 메시지별 스냅샷 `parent_notification.recipient_email`. 목록 화면은 주소를 마스킹한다.
- 보호자 연락처의 입력 경로:
  - 현재 FastAPI 주간 엑셀 업로드는 연락처 열을 읽지 않는다. 연락처는 학생 등록과 보호자 연락처 수정 API(`PATCH /api/students/{id}/contact`)로 관리한다. 이 API를 여는 화면 버튼의 이름은 "메일 주소 변경"이다.
  - Java 레거시 Excel/CSV 가져오기에는 `보호자 이메일` 열이 있다.
- 발송 채널 추상화는 **구현되어 있지 않다.** `NotificationService`가 `MockSender`를 직접 생성한다. 발송 시도 기록의 `channel`은 DB CHECK 제약으로 `'MOCK'`만 허용한다.
- Mock 발송의 실패 재현 규칙은 이메일 도메인 기준이다(`mock-fail.invalid`, `mock-retry.invalid`).
- 재사용을 검토할 기존 구조:
  - 상태 전이(DRAFT → READY_FOR_REVIEW → APPROVED → MOCK_SENT/MOCK_FAILED, CANCELLED)
  - 메시지 행 잠금과 버전 검사
  - `Idempotency-Key` UNIQUE, 메시지당 발송 성공 1회 부분 UNIQUE
  - 원본 변경 시 확정·발송 차단(`source_hash`, Phase 11-3-B의 원본 행 잠금)
  - 업무 변경과 같은 트랜잭션의 감사 기록

**향후 검토 범위**

1. 보호자 연락처를 이메일 중심에서 휴대전화번호 중심으로 전환
2. 전화번호 입력·형식 검증과 개인정보 보호 정책 정비(목록 마스킹, 로그·감사 기록의 원문 미기록)
3. 보호자 연락처를 받는 입력 경로(엑셀/CSV 업로드 포함) 결정과 처리 변경
4. 메시지 수신 대상과 발송 이력을 전화번호 기반으로 관리
5. Mock Sender를 SMS/LMS 모의 발송 방식으로 변경(본문 길이에 따른 SMS/LMS 구분 포함)
6. 필요하면 실제 SMS API 연동. README의 현재 비용·외부 연동 정책(유료 API 미사용)과 맞물리므로, 연동 여부 자체가 별도 결정 사항이다
7. 실제 발송 시 외부 I/O와 DB 트랜잭션 분리(아래 선행 과제)
8. 발송 결과 처리, 실패 재시도, 중복 발송 방지 재검증
9. 기존 확정·상태 전이·멱등성 구조를 최대한 재사용

MMS는 이미지 등 멀티미디어 발송 요구사항이 확인될 때만 추가로 검토한다.

**필수 선행 과제 — INT-I1: 외부 발송 I/O와 DB 트랜잭션 분리**

- 현재 발송(`NotificationService._deliver`) 흐름:
  1. DB 트랜잭션과 메시지·원본 행 잠금 안에서 `MockSender.send()`를 호출한다.
  2. 상태·발송 시도·감사를 기록한다.
  3. 한 번에 commit한다.
- Mock은 프로세스 내부 함수라서, 롤백되면 아무것도 나가지 않은 것과 같다.
- 실제 SMS API는 외부 I/O라서 **DB 롤백으로 발송을 취소할 수 없다.**
  - 발송 성공 뒤 commit이 실패하면, 기록 없이 발송된 상태가 되고 재시도 때 중복 발송될 수 있다.
  - 외부 호출 시간만큼 잠금이 유지되어 같은 수업의 출결·성적 저장이 기다린다.
  - 근거: `docs/reviews/phase11_3_integrity_audit.md` INT-I1·4.5절, `docs/reviews/phase11_3_integrity_remediation.md` 4.5절.
- 실제 연동 **전에** 다음을 설계하고 검증한다.
  - 발송 결정(원본 검사 포함)과 외부 호출의 트랜잭션 분리. 구체 방식(예: 발송 요청을 먼저 기록해 commit한 뒤 트랜잭션 밖에서 호출)은 설계 단계에서 정한다
  - 발송 요청과 결과의 영속적 관리. 요청 중·결과 미확인 같은 상태가 필요하면 상태 CHECK 변경 등 스키마 변경이 따르므로 별도 승인 대상이다
  - 멱등성: 공급자의 중복 방지 수단 확인, 기존 `Idempotency-Key`·성공 1회 제약과의 연결
  - 실패·타임아웃·재시도 정책: 타임아웃 후 결과를 알 수 없는 건의 처리, 재시도 조건, 수동 재시도 유지 여부
  - 원본 정합성의 보장 범위: 발송 결정 시점까지 보장하고, 그 뒤 원본이 바뀐 경우를 어떻게 안내할지 정한다

**정해지지 않은 것**: 발송 공급자, 비용, DB 변경 규모, 구현 일정, Phase 번호, MMS 필요 여부.

## 9. Legacy → Web 비교: 개선 항목별 근거

각 항목은 같은 형식으로 정리했다.

| 칸 | 내용 |
|---|---|
| Before | Java 버전의 실제 코드 |
| Problem | 코드나 당시 문서로 확인된 제약 |
| Decision | 기존 문서에 기록된 선택 근거 |
| After | 현재 파일·모듈 |
| Validation | 실제 실행한 테스트 |
| Trade-off | 얻은 것과 새로 생긴 비용 |

작성 원칙:
- 재현하지 않은 문제는 **(추정)**, 근거 문서가 없는 결정 이유는 **(기록 없음)**으로 표시한다.
  - FastAPI 선택 이유와 보강 관리 누락 원인은 2026-11-21 개발자 회고(`docs/ENGINEERING_RETROSPECTIVE.md` 1·9절)로 채웠다. 현재 "(기록 없음)" 항목은 없다.
- Java 경로는 기존 저장소 태그 기준이다.
- 웹 버전 테스트 수치는 **실행해서 통과한 테스트 수**다. 백엔드 DB 없는 테스트 166, PostgreSQL 통합 141, Vitest 15파일 114다(실행일은 9.8절 표). 정의된 개수·실행 결과·커버리지를 어떻게 구분했는지는 9.8절에 있다.

### 9.0 구현 대응표

| Java (v1.x) | 웹 (현재) | 관계 |
|---|---|---|
| `view/MainFrame.java`(화면 + 발송 절차) | `frontend/src/features/*` 화면 + `backend/app/modules/*/router.py`·`service.py` | 화면과 업무 절차 분리 |
| `domain/LearningMessageComposer`, `MessageSections`, `TestScore` | `backend/app/domain.py`(Message Preview 계약), `modules/notifications/engine.py`(템플릿 렌더링) | 규칙 이식, Phase 1 계약 fixture로 비교 |
| `service/MessageGenerationService` + `dao/TemplateDAO` | `modules/notifications/service.py`(초안 생성) + `notification_template` | 재설계(검토·확정 단계 추가) |
| `service/EmailSendService`(Jakarta Mail SMTP) | `modules/notifications/sender.py`(`MockSender`) | **실발송 → 모의 발송으로 축소** |
| `dao/SendLogDAO`(`send_log`) | `parent_notification` + `notification_send_attempt` | 재설계(시도 원장, 멱등 키) |
| `service/SpreadsheetImportService`·`XlsxImportService`·`CsvImportService`, `DataValidationService`, `dao/AcademyImportDAO` | `modules/lesson_upload/workbook.py`·`service.py`, `app/uploads.py` | 입력 형식 자체가 바뀜(9.6) |
| `dao/EnrollmentDAO` 등 | `modules/learningops`, `modules/academics` | 재설계 |
| `dao/MakeupDAO`, `domain/MakeupStatus`, `MakeupGuidancePolicy` | 없음(`engine.py`의 고정 결석 문장만) | **미이식**(9.9) |
| `dao/DBConnection` → `port/ConnectionProvider` | `app/db/session.py`, `app/db/safety.py`, `alembic/` | 교체 |
| `service/MailCredentialStore`(AES-GCM) | 없음(외부 발송 없음) | 해당 없음 |
| 없음 | `modules/auth`(직원 인증·RBAC), `modules/analytics`, `modules/message_operations` | 웹에서 새로 생김 |

### 9.1 실행 구조: 단일 사용자 데스크톱 → 다중 사용자 웹

- **Before**: `Main.java` → Swing `MainFrame`. 한 PC에서 한 사람이 쓰고, DB 접속 정보를 가진 사람이 곧 사용자다.
- **Problem**:
  - 화면 클래스가 1,065줄(v1.0)이고 업무 절차를 직접 수행한다(9.2).
  - 여러 직원(관리자·선생님·조교)이 역할에 맞게 나눠 쓰는 구조가 없다(9.5).
  - 당시 문서가 "웹 확장, API 기반 통합, 분석 기능에 제약"을 기록했다(`docs/ENGINEERING_RETROSPECTIVE.md` 1절).
- **Decision**:
  - 기록된 결정은 "Java를 즉시 제거하지 않고 endpoint 단위로 FastAPI를 병행 구축"이다(같은 문서). 계약을 고정한 뒤 DB 없는 API부터 옮겼다.
  - FastAPI를 고른 이유는 개발자 회고에 있다(`docs/ENGINEERING_RETROSPECTIVE.md` 1절, 2026-11-21 작성).
    - 처음에는 Spring Boot REST API를 고려했다.
    - 두 가지를 함께 판단해 FastAPI로 정했다: 향후 **Python 기반 AI 기능 확장 가능성**, 그리고 Spring Boot를 단기간에 학습하는 부담과 핵심 기능 구현·검증 일정 사이의 균형.
    - FastAPI가 개발 기간을 실제로 단축했다거나 Spring Boot보다 우수하다고 단정하지 않는다.
    - AI 기능은 아직 구현하지 않았다(8절).
- **After**:
  - React(Vite) → FastAPI(`backend/app/main.py`) → PostgreSQL
  - 배포용 실행 모드 `ACADEMY_DB_MODE=production`과 시작 시 설정 검증(`app/config.py::production_problems`, Phase 11-4-B)
  - 배포 절차: `docs/deployment/phase11_5_security_deployment_guide.md`
- **Validation**:
  - 계약 비교: Phase 1 7/7, Phase 2 27/27
  - production 모드 기동·거부 subprocess 테스트(11-4-B)
  - `npm run build` PASS
  - 클라우드 배포 완료(2026-11-24, Vercel · Render · Neon). 배포 후 점검 결과는 3절 Phase 11
- **Trade-off**:
  - 언어를 바꾸면서 Java 구현을 직접 재사용할 수 없어, API·인증·데이터 접근 계층을 Python으로 다시 구현하고 검증해야 했다(9.0 대응표).
  - 여러 사용자가 브라우저로 접근할 수 있게 된 대신, 데스크톱에는 없던 일이 생겼다.
  - 세션·CSRF·CORS·프록시 설정
  - 로그인 제한·재설정 코드의 메모리 저장 때문에 **워커 1개**로 운영해야 함
  - 배포 환경 점검 절차

### 9.2 계층과 책임: 화면 중심 → 계층 분리

- **Before**:
  - v1.0은 `MainFrame`이 DAO·Service 객체 9개를 직접 만든다. 발송 반복문, 퇴원 제외(`isWithdrawn`), 이메일 형식 검사가 화면에 있다.
  - v1.1에서 `domain`(9개)과 `port`(3개)를 추가해 규칙을 분리했다. 그래도 v1.2의 `MainFrame`(1,077줄)은 여전히 `sendEmail`을 두 곳에서 직접 호출한다.
- **Problem**:
  - 업무 상태가 문자열 비교에 숨어 있었고, 메시지 규칙이 DB 조회와 결합되어 있었다(`docs/archive/java-v1/PORTFOLIO_BACKEND_REFACTORING_EVIDENCE.md` 문제 1~4).
  - v1.1 문서가 "화면의 DB 반영·메일 발송 절차를 use case로 이동"을 다음 과제로 남겼다(`docs/refactoring/02-backend-architecture-refactoring.md`).
- **Decision**: Router → Service → Repository. 업무 규칙·트랜잭션·권한 검사는 서비스가 맡고, 라우터는 입력·응답만 다룬다(`docs/archive/phases/phase9-5-ux-architecture-improvement.md`, Phase 10.5 리뷰).
- **After**:
  - 모듈 7개: `auth`, `learningops`, `academics`, `lesson_upload`, `notifications`, `message_operations`, `analytics`
  - 발송 결정(퇴원·이메일·원본 변경 검사)은 `notifications/service.py`에 있다.
  - 모듈 간 순환 의존은 없다(Phase 10.5-A 리뷰).
- **Validation**: Phase 10.5 아키텍처 리뷰(`docs/reviews/phase10_5_architecture_review.md`). 레거시 비공개 함수 의존을 제거했다(10.5-C2).
- **Trade-off**:
  - v1.1의 도메인 타입(Java enum)을 그대로 옮기지 않았다. 웹은 DB CHECK 제약과 Pydantic 리터럴로 상태를 표현한다.
  - 구 미리보기 API용 레거시 모듈(`app/domain.py`)이 공개 계약 때문에 아직 남아 있다(10.5 M4).

### 9.3 데이터베이스: Oracle → PostgreSQL 재설계 → Alembic 관리

- **Before**:
  - v1.0·v1.1: Oracle `sql/schema_oracle.sql`. 테이블 8개, 발송 기록은 `send_log` 한 테이블.
  - v1.2: PostgreSQL `sql/schema_postgresql.sql`. 테이블 13개, 발송 기록을 draft → job → attempt로 분리, import 감사 테이블 추가.
- **Problem**: 학습용 Oracle에 다른 테이블이 섞여 있었다. 점수가 `'13/39'` 문자열이었다(`docs/database/oracle-to-postgresql-migration.md` 1·3절).
- **Decision**:
  - 스키마 복제가 아니라 검증된 데이터만 옮기는 ETL로 계획했다.
  - 점수는 `correct_count`/`total_count` 정수로 분리했다(같은 문서).
  - 웹 전환 후에는 v1.2 DDL을 Alembic 기준선(`001_java_schema_baseline`)으로 삼고, 이후 변경은 모두 Migration으로 관리했다.
- **After**: 업무 테이블 20개, Migration 001→011 단일 선형 체인(4절).
- **Validation**:
  - v1.2: `PostgreSqlDaoIntegrationTest` 2건(환경변수로 켜야 실행)
  - 웹: 스키마·제약 통합 테스트와 Migration 왕복 테스트(일부 구간)가 PostgreSQL 141건에 포함
  - 테스트 DB에서 `alembic check` 차이 없음(11-3-A)
  - 빈 PostgreSQL 17 일회용 DB에서 001→011 전체 재구성 검증(2026-11-23, Phase 11-5-B, 7절 기록. 별도 결과 보고서는 없음)
- **Trade-off**:
  - 실제 Oracle 데이터를 옮긴 실행 기록은 **확인되지 않는다**.
  - Java 전용 메시지 테이블 4개가 스키마에 남아 있지만 웹은 쓰지 않는다.
  - 개발 DB는 자동 적용하지 않는 원칙이라, 적용이 늦어질 수 있다. 실제로 011이 늦게 적용됐다(2026-11-21, 4절).

### 9.4 DB 접근: JDBC 수동 트랜잭션 → SQLAlchemy Session

- **Before**:
  - DAO마다 `Connection`을 열고 일괄 반영 때만 `setAutoCommit(false)`·`commit`·`rollback`을 직접 호출한다(`AcademyImportDAO`, `EnrollmentDAO`).
  - v1.0은 접속 정보를 `config.properties` 파일에서만 읽었고, v1.1부터 환경변수를 우선한다.
- **Problem**: 트랜잭션 경계가 DAO 안에 흩어져 있다. v1.1 문서는 "DAO가 연결 구현을 직접 생성"하는 문제를 `ConnectionProvider`로 완화했다(PORTFOLIO 문제 3).
- **Decision**: 요청마다 Session 하나, 서비스가 commit·rollback을 맡는다. 업무 변경과 감사 기록은 같은 commit으로 저장한다(Phase 3·4 문서, 4절).
- **After**:
  - `app/db/session.py`: `get_db`, `pool_pre_ping`, `connect_timeout=5`, `hide_parameters=True`
  - `app/db/safety.py`: 모드별 DB 대상 허용 목록, production은 TLS 필수
- **Validation**:
  - DB 장애 시 503 `DATABASE_UNAVAILABLE`, 잠금 충돌 시 409 `TRANSACTION_CONFLICT`(11-4-A, 실제 연결 실패 테스트 포함)
  - 쿼리 수 감소의 실측 수치는 `docs/reviews/phase11_4_a_performance_results.md` 4절에 있다.
- **Trade-off**: ORM 추상화가 추가됐다. 동시성 정확도는 ORM 기본값만으로 확보되지 않아, 행 잠금·`populate_existing`·advisory lock을 직접 설계해야 했다(9.8).

### 9.5 인증·권한·보안

- **Before**:
  - 세 버전 모두 직원 로그인·역할 코드가 **없다**. 검색에 걸린 인증 코드는 SMTP 인증(`Authenticator`)뿐이다.
  - 비밀정보 보호는 두 가지였다. DB 접속 정보를 파일·환경변수로 분리했고, Gmail 앱 비밀번호는 `MailCredentialStore`가 AES-GCM + PBKDF2(210,000회)로 암호화했다.
- **Problem**: 단일 사용자 데스크톱에서는 필요 없었던 직원별 접근 통제가 웹에서는 필수다. 담당하지 않은 반의 학생·보호자 정보에 접근하는 것을 막아야 한다.
- **Decision**: 외부 IdP 없이 로컬 세션 인증을 쓴다(`docs/decisions/0001-local-session-authentication.md`). 역할 + 담당 반 범위를 요청마다 서버가 다시 검사한다.
- **After**:
  - `modules/auth`: Argon2 해시, 해시로만 저장하는 불투명 세션, HttpOnly·SameSite 쿠키, 세션에 묶인 CSRF 토큰, 로그인 시도 제한(주소+계정 5, 주소 20, 계정 20 / 15분)
  - 유휴 만료 60분, 절대 만료 8시간, 비밀번호 변경과 관리자 발급 일회용 재설정 코드(11-4-B)
  - `require_admin`, `require_classroom_access`, 감사 기록
- **Validation**:
  - 인증·RBAC·CSRF PostgreSQL 회귀가 141건에 포함
  - Phase 11-2 보안 감사·수정(SEC-01~11), 11-4-B 신규 34건(단위 24 + PostgreSQL 10)
- **Trade-off**: 로그인 카운터와 재설정 코드가 프로세스 메모리에 있다. 그래서 워커는 1개여야 하고, 재시작하면 초기화된다. 화면의 메뉴 숨김은 편의 기능일 뿐이고, 권한은 서버가 판정한다.

### 9.6 Excel/CSV 입력과 데이터 검증

- **Before**:
  - Java는 표준 열(분반명·수업유형·수업일자·…·보호자 이메일·`test 결과`) CSV/XLSX를 Apache POI로 읽는다.
  - `DataValidationService`로 검증하고, `AcademyImportDAO`로 한 트랜잭션에 반영한다.
  - v1.2에서 파일 SHA-256(`ImportHashUtil`)과 `import_job/row/error` 감사가 추가됐다.
- **Problem**: v1.1 문서가 "파일 입력과 비즈니스 검증의 사용 절차가 UI에 노출"을 지적했다(PORTFOLIO 문제 4).
- **Decision**:
  - 1차: Java 계약 그대로 Import Preview·Confirm을 옮겼다(Phase 2·4: 단일 트랜잭션, UUID 멱등 키).
  - 2차: 학원이 실제로 쓰는 **주간 엑셀**(시트 = 시간대, 반 블록) 업로드로 대체하고, 구 가져오기는 제거했다(Phase 8.1, 9.6, 사용자 승인).
- **After**:
  - `modules/lesson_upload`: 미리보기 → 확정, 시간대(시트) 선택, 변경 없는 행 생략
  - 반별 `pg_advisory_xact_lock` 후 다시 분석(INT-04)
  - `app/uploads.py`: 10MiB·5,000행·64열, ZIP 항목 수·해제 총량 제한, defusedxml(SEC-06)
- **Validation**: 업로드 통합 테스트, SEC-01(다른 반 학생 재사용 차단)·SEC-06·INT-04 회귀가 PostgreSQL 141건에 포함
- **Trade-off**:
  - 입력 형식이 바뀌어 Java의 표준 CSV는 더 이상 받지 않는다.
  - 주간 엑셀에는 연락처 열이 없어서, **보호자 이메일은 업로드로 들어오지 않는다**. 학생 화면의 "메일 주소 변경"으로 따로 입력해야 한다.

### 9.7 메시지 생성·확정·발송과 멱등성

발송 방식은 다음 네 가지를 구분해야 한다.

| 구분 | 상태 | 근거 |
|---|---|---|
| Java v1.x 실제 발송 | **Jakarta Mail SMTP(Gmail)**. Gmail API가 아니다. 발송 대상을 고르고 확인 창을 거친 뒤, 화면 처리 중에 동기 호출로 발송한다 | `EmailSendService.java`(`Transport.send`), `MainFrame.java` |
| 현재 웹 발송 | **`MockSender`만 있다.** 네트워크로 나가는 발송은 없다. 시도 기록의 `channel`은 CHECK로 `'MOCK'`만 허용한다 | `notifications/sender.py`, `db/models/tables.py`(`chk_notification_send_attempt_channel`) |
| 향후 계획 | 보호자 휴대전화 기반 SMS/LMS. 공급자·비용·일정은 미정 | 8절 |
| SMS 도입 전 필수 과제 | **INT-I1**: 지금은 외부 발송 I/O가 DB 트랜잭션·행 잠금 안에서 호출된다. 분리하지 않으면 실발송 후 commit이 실패할 때 기록 없는 발송과 재시도 시 이중 발송이 생길 수 있다 | `docs/reviews/phase11_3_integrity_audit.md` |

- **Before**:
  - 발송 결과는 `send_log`(Oracle, `READY/SENT/FAILED/SKIPPED`)에 남고, 실패 건을 운영자가 골라 재시도한다.
  - v1.2 스키마에도 발송 관련 UNIQUE는 `(delivery_job_id, attempt_no)`뿐이다. 멱등 키나 메시지당 성공 1회 제약이 없다.
  - 그래서 같은 학생에게 두 번 발송하는 것을 DB가 막지 않는다. **(추정: 코드 관찰. 재현하지 않음)**
- **Problem**:
  - 학생별 메시지를 수정·저장하고 발송 전 확인 창을 거치지만, "검토 완료·확정" 같은 **저장되는 상태(누가 언제 확정했는지)**는 없다. 그래서 여러 직원이 나눠 검토하거나 확정한 메시지만 발송하도록 막을 수 없다.
  - 생성 뒤 출결·성적이 바뀌어도 이미 만든 본문으로 발송된다. 웹에서는 이 문제를 H1으로 재현·수정했다(Phase 10.5).
- **Decision**:
  - 발송 채널 연동보다 상태 전이·검토·멱등성·정합성을 먼저 구현했다(3절 Phase 8~9, 2절 "FastAPI 전환 의사결정" 4번).
  - 실발송은 이식하지 않았다(8절).
- **After**:
  - 상태: `DRAFT → READY_FOR_REVIEW → APPROVED → MOCK_SENT/MOCK_FAILED`
  - 멱등성: `Idempotency-Key` UNIQUE(`uq_notification_send_attempt_key`), 메시지당 성공 1회 부분 UNIQUE(`uq_notification_send_attempt_success`)
  - 원본이 바뀌면 확정·발송 차단(`source_hash`), 발송 전 원본 행을 고정 순서로 잠금(INT-01)
  - 반 단위 일괄 검토·확정·모의 발송
- **Validation**: 메시지·운영·동시성 통합 테스트(PostgreSQL 141건에 포함). 동시 확정·발송·재시도 경합은 `backend/tests/test_phase113_concurrency_integration.py` 15건.
- **Trade-off**:
  - **실제 발송 능력은 Java보다 줄었다**. 웹은 학부모에게 아무것도 보내지 않는다.
  - 실발송을 도입하려면 INT-I1(아웃박스 등)과 채널 추상화가 먼저 필요하다. 지금은 `NotificationService`가 `MockSender`를 직접 생성한다.

### 9.8 테스트·동시성 검증 체계

- **Before**: 아래 수치는 서로 다른 종류다. **커버리지(코드 몇 %를 실행했는지)는 어느 버전에서도 측정하지 않았다.**

  | 버전 | 정의된 테스트 | 실행 결과 기록 | 근거 |
  |---|---|---|---|
  | v1.0 | **0**(`src/test` 폴더가 없음) | 해당 없음 | 태그 `v1.0-legacy`의 파일 목록 |
  | v1.1 | **10**(`@Test` 메서드 10개, 파일 5개) | **Tests run 10, Failures 0, Errors 0, Skipped 0**(`mvn clean verify`) | 태그 `v1.1.0` 코드, `docs/archive/java-v1/PORTFOLIO_BACKEND_REFACTORING_EVIDENCE.md` 10절 |
  | v1.2 | **17**(`@Test` 메서드 17개, 파일 9개) | **미확인**(실행 결과 기록을 찾지 못함). 그중 DB 통합 2개는 `RUN_POSTGRES_INTEGRATION=true`일 때만 실행되므로, 기본 `mvn test`에서는 15개가 실행 대상이다(코드 기준 추정) | 태그 `v1.2.0` 코드 |
  | Java REST 어댑터 단계 | — | Java 47 실행(42 PASS / 5 SKIP), React 15 PASS(2026-11-04) | `docs/archive/phases/fastapi-transition-baseline.md` |

  - Java 테스트에는 파라미터·반복 테스트(`@ParameterizedTest` 등)가 없다. 그래서 `@Test` 1개가 실행 1건이다.
  - 동시성 테스트는 없었다. 보강 상태의 동시 변경 감지는 코드로 추가됐다(PORTFOLIO 문제 5).
- **Problem**: 동시 확정·이중 제출·원본 변경 경합은 단위 테스트로 드러나지 않는다. 파괴적 통합 테스트가 잘못된 DB를 비울 위험도 있었다(11-0에서 실제 검사 결함 발견).
- **Decision**:
  - 개발·테스트 DB를 컨테이너·계정·포트·볼륨·라벨까지 분리했다(Phase 3, `ENGINEERING_RETROSPECTIVE.md` 2절).
  - 실행기는 실행 직전에 정체를 확인한다(11-0).
  - 동시성 회귀는 초기화 없이 접두사 데이터를 쓴다(11-3-B).
- **After**:
  - pytest 단위·PostgreSQL 통합, Vitest/Testing Library
  - `scripts/run-postgres-integration.ps1`(격리 확인), `scripts/verify-all.ps1`(DB 없이 Ruff → pytest → lint → Vitest → build)
- **Validation**: 웹 버전 수치는 모두 **실행해서 통과한 테스트 수**다. 커버리지는 측정하지 않았다(`pytest-cov`·Vitest coverage 미설치).

  | 수치 | 의미 | 최근 실행 |
  |---|---|---|
  | **166** | 백엔드 DB 없는 테스트(`pytest -m "not postgres"`) 166개 실행, 166 PASS | 2026-11-25 |
  | **141** | 백엔드 PostgreSQL 통합 테스트(`pytest -m postgres`, 격리 테스트 DB) 141개 실행, 141 PASS / 0 FAIL / 0 SKIP | 2026-11-21, 11-4-B 최종 백엔드 변경 뒤 전체 회귀. 이후 앱 코드 변경은 404 응답 처리(2026-11-25, DB와 무관한 라우팅 오류 처리기)뿐이고 PostgreSQL 테스트는 재실행하지 않았다. 개수 141은 2026-11-25에도 같다 |
  | **114** | 프론트엔드 Vitest 테스트 114개(15개 파일) 실행, 114 PASS | 2026-11-25, 6절 표 참고 |

  - pytest 수치는 **테스트 항목** 기준이다. 테스트 함수 229개 중 `@pytest.mark.parametrize`(18곳)로 펼쳐진 경우를 각각 1개로 센다. 백엔드 합계는 307개(= 166 + 141)다(2026-11-25 기준).
  - 그래서 Java의 `@Test` 개수와 셈의 단위가 같지 않다. 버전 간 숫자를 직접 비교해 "몇 배 늘었다"고 말하지 않는다.
- **Trade-off**:
  - 브라우저 E2E 자동화는 없다(수동 체크리스트).
  - CI는 미구성이다.
  - 전체 Vitest는 약 7~10분 걸린다.

### 9.9 웹에서 빠지거나 약해진 것

- **보강 신청 관리 미이식**: Java v1.x의 기능이 웹에는 없다.
  - Java에 있던 것: 화면의 보강 신청·완료·취소(상태 규칙에는 신청 → 승인 → 완료/취소 포함, 승인 버튼은 없음), 재원생만 신청, 퇴원 시 미완료 보강 취소, 상태별 보호자 안내 문구(`MakeupDAO`, `MakeupGuidancePolicy`, `docs/archive/java-v1/BACKEND_REQUIREMENTS.md`)
  - 웹에 있는 것: `makeup_request` 테이블 모델과, 결석일 때 넣는 고정 문장 하나(`engine.py`의 `MAKEUP_SENTENCE`)뿐이다.
  - **원인(개발자 회고, `docs/ENGINEERING_RETROSPECTIVE.md` 9절)**:
    - 의도적으로 제외한 것이 아니다. 기존 기능의 이식 범위를 충분히 확인하지 못해 생긴 **누락**이다.
    - 코드 구조 개선과 데이터 검증·정합성 확보에 예상보다 많은 시간을 쓰면서, 이 기능까지 구현할 여력이 부족했다.
  - **결정**: 현재 릴리스에는 추가하지 않는다. 업무 흐름 안정화와 배포 뒤 필요성과 구현 비용을 검토해 정한다(8절).
  - **교훈**: 레거시 마이그레이션에는 Feature Parity 검증이 필요하다. 다음에는 착수 단계부터 기존 기능 목록과 신규 구현 상태를 짝지은 체크리스트를 관리한다. 9.0 대응표가 이번 프로젝트의 사후 체크리스트다.
- **실제 이메일 발송 미이식**(9.7)
- **발송 로그 CSV 저장**: Java에는 있었다(`CsvExportUtil`, 수식 주입 방어 포함). 웹 화면에서는 대응 기능을 찾지 못했다.
- **표준 CSV 가져오기 제거**(9.6): 업로드로 보호자 이메일을 받을 수 없다.

## 근거와 한계

- 주요 근거: `README.md`, `backend/README.md`, `docs/archive/phases/phase*-*.md`, `docs/reviews/*.md`, `docs/deployment/*.md`, 실제 소스·설정·마이그레이션
- Java 이력: 기존 저장소 태그 `v1.0-legacy`·`v1.1.0`·`v1.2.0`의 코드를 `git show`/`git ls-tree`로 직접 확인했다(2·9절). 태그 이후의 Java REST 어댑터 단계는 로컬 사본과 `docs/archive/phases/fastapi-transition-baseline.md`가 근거다.
- 웹 버전의 Git 이력: v2.0.0 이전 작업은 커밋 하나(`ca15e62`, 2026-11-21)라서 Phase 순서와 날짜는 보고서 작성일을 근거로 한다. 그 이후 변경은 커밋 이력으로 확인할 수 있다.
- 테스트 결과: 6절 표의 시점에 실제로 실행한 결과다.
- 개발 DB: 2026-11-21 Migration 011을 적용할 때 읽기 전용 세션으로 revision·제약·직원 수만 조회했다.
- 개발자의 개인적 동기나 감정: 문서에 창작하지 않음
