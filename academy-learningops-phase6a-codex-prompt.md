# Academy LearningOps — MVP 방향 재정의 및 Phase 6A 첫 Vertical Slice

## 역할과 목표
당신은 FastAPI, PostgreSQL, SQLAlchemy, Alembic, React, REST API, 보안, 테스트에 능숙한 시니어 백엔드 개발자다. 목적은 기술 과시가 아닌 학원 직원의 실제 업무 누락 예방, 데이터 무결성, 정확한 교육 현황, 메시지 처리 추적을 제공하는 모듈형 모놀리스(Modular Monolith) 시스템으로 기존 Academy LearningOps를 발전시키는 것이다.

**이번 작업 순서:** (1) 현재 코드·보고서 검증 → (2) Docker/DB/인증 상태 확인 → (3) README·아키텍처·로드맵을 실제 상태에 맞게 수정 → (4) Phase 6A 첫 수직 업무 흐름 구현 → (5) 회귀/보안/통합 테스트 → (6) 결과 문서화.

## 제품 범위와 최종 업무 흐름
1. ADMIN이 학생·반·수강을 관리하고 담당 교사/조교를 배정한다.
2. TEACHER는 담당 반의 수업별 출결·성적을 기록하고 학습 현황(출석률·성적 추이)을 조회한다.
3. 시스템은 수업 데이터와 DB 템플릿으로 학부모 안내 메시지 초안을 생성한다.
4. 직원이 검토·수정·확정한 뒤 모의 발송(Mock Sender)으로 처리 상태를 검증한다.
5. 관리자는 반별 입력 누락·검토 대기·처리 대기·완료·부분 실패·실패·제외를 확인하고 후속 조치한다.
6. 모든 단계에서 인증, RBAC, 담당 반 단위 접근 제어, 데이터 무결성, 처리 이력을 보장한다.

학생 로그인, 학생용 대시보드, Kafka, Redis, MSA, Kubernetes, 복잡한 AI 분석, 실제 이메일·SMS 전송, 유료 클라우드·API는 이번 MVP 범위에서 제외한다. Kafka/분석 관련 기존 문서는 삭제하지 말고 ‘보류된 설계’로 분류한다. 기존 Java 업무 규칙과 회귀 테스트는 Python 기능 동등성 확인용으로 보존한다.

## A. 현재 구현과 안전한 환경 확인
실제 저장소를 탐색해 루트/백엔드 README, Phase 1~5 보고서, Phase 6 설계, OpenAPI, FastAPI/React/Java 코드, SQL DDL, Alembic, 테스트 스크립트 등을 확인한다. 문서와 코드가 다르면 실증된 구현을 기준으로 차이를 보고한다.

마지막 보고에 의하면 Docker Desktop Linux Engine은 중지 상태였고, 개발·테스트 DB Alembic revision은 `002_staff_auth_rbac`, 관리자 ACTIVE 계정 생성은 확인되지 않았다. 현재 상태는 새로 검증하고 이전 결과를 그대로 현재 상태라고 단정하지 않는다.

- Docker 및 컨테이너 상태, DB 이름/계정/포트/라벨 확인. 개발 DB `academy_learningops_dev` / `127.0.0.1:55431`, 테스트 DB `academy_learningops_test` / `127.0.0.1:55432`이며 별도 볼륨이다.
- 기존 `academy-postgres` 컨테이너는 소유가 확인되지 않았으므로 접근·수정하지 않는다.
- 개발 DB의 ACTIVE ADMIN 수, Alembic revision, FastAPI preflight, `/api/auth/me` 미인증 401을 안전하게 확인한다.
- 관리자가 없으면 비밀번호를 임의 생성하지 말고 사용자가 로컬에서 안전하게 부트스트랩할 명령을 안내한다. 기존 관리자 계정 삭제·재생성·비밀번호 초기화는 금지한다.
- 환경이나 사용자 인증정보 문제로 실제 브라우저 E2E가 불가능하면 BLOCKED로 표기한다. 보안 검사를 우회하지 않는다.
- 진단 중 개인정보·DB 비밀번호·해시·세션/CSRF 토큰을 터미널/로그/보고서에 노출하지 않는다.

## B. 실제 코드와 제품 목표에 맞게 문서 수정
- README에 현재 FastAPI + React + PostgreSQL 아키텍처, 실제 구현/미구현 상태, 직원 업무 흐름, 로컬 실행법, 보안 규칙, 테스트 명령, 단계별 로드맵을 정확히 반영한다.
- Java/Spring Boot 중심의 오래된 계획은 레거시 역사로 구분하고 현재 개발 방향으로 잘못 읽히지 않도록 정리한다.
- Modular Monolith: Router(HTTP), Service(업무/트랜잭션), Repository(DB), Schema(Pydantic), Authorization(인증·권한); 기존 구조 재사용 우선, 무리한 전면 리팩터링 금지.
- 기존 보고서 및 ADR 보존. 새 문서는 중복 생성하지 말고 현재 문서 구조와 일치시킨다.
- 향후 단계 재정의:
  * Phase 6A: 학생·반·수강 관리 첫 Vertical Slice
  * Phase 6B: ADMIN 전용 직원·반 배정 관리 확장
  * Phase 7: 수업·출결·성적 기록
  * Phase 8: DB 템플릿·메시지 초안·검토·모의 처리
  * Phase 9: 반별 메시지 처리 상태·입력 누락 탐지·실패 원인·재처리
  * Phase 10: 출석률·성적 추이 시각화(PostgreSQL 집계 + React 차트)
  * Phase 11: 통합 테스트, 성능·장애 검증, 로컬 Docker 실행, ERD/OpenAPI/포트폴리오 문서화
- 메시지 상태(입력 누락/검토 대기/처리 대기/완료/부분 실패/실패/제외)는 우선 설계 문서에서 정의한다. 수업 종료 여부, 처리 대상, 업무 기한 등의 근거 없이 단지 발송 기록이 없다는 이유로 누락 판정 금지. 단계마다 DB enum/컬럼을 미리 추가하지 않는다. 모의 발송 완료를 실제 이메일 수신 완료로 표현하지 않는다. UI에는 색상뿐 아니라 상태명·건수도 사용한다.

## C. 이번 구현 범위 — Phase 6A 첫 Vertical Slice
완성할 실제 사용자 시나리오:
1. ADMIN 로그인
2. ADMIN이 반 등록
3. ADMIN이 학생 등록
4. ADMIN이 학생을 반에 수강 등록
5. ADMIN이 TEACHER를 해당 반에 배정(기존 배정 기능이 없다면 이 시나리오에 필요한 최소 기능만 구현)
6. TEACHER 로그인 후 담당 반 학생 목록 조회
7. 다른 반/다른 학생의 비허가 데이터 접근 차단
8. 동일 학생·반 중복 수강 요청 및 동시 요청에서 데이터 무결성 유지

### 구현 전 분석
- 기존 `student`, `classroom`, `enrollment`, `staff_user`, `classroom_staff_assignment`의 PK/FK/UNIQUE/index/상태 규칙을 검토한다.
- 기존 Java Import Confirm 및 등록/퇴원/휴원 업무 규칙과 계약을 조사하고 Python과 충돌하지 않게 한다.
- 동명이인·학생 업무 키 충돌 가능성을 조사하되 임의의 식별자/UNIQUE 변경은 하지 않는다. 변경 필요성·기존 Import에 대한 영향·마이그레이션 방안을 문서화한다.
- 요구 시나리오에 필요한 API 경로/HTTP 메서드는 현재 OpenAPI 명명 규칙에 맞춰 최소한으로 선정한다. 무관한 대규모 CRUD API 생성 금지.

### 구현 규칙
- FastAPI Router → Service → Repository/SQLAlchemy 계층과 Pydantic request/response 검증.
- 올바른 HTTP Status와 기존 오류 응답 형식 유지(400/401/403/404/409 등).
- DB 트랜잭션 경계 명확화, 중복 등록은 사전 SELECT만이 아니라 DB UNIQUE/경쟁조건 처리로 보장.
- 서버 세션, CSRF, ADMIN/TEACHER/ASSISTANT RBAC 및 담당 반 객체 단위 인가를 그대로 적용한다. 요청의 역할/사용자 ID를 신뢰하지 않는다. 목록 API 역시 DB 조회 범위를 제한한다.
- 학생이 여러 반에 등록된 경우 교사·조교에게 허용할 개인정보 범위를 설계하고 테스트한다.
- React에서 반·학생 등록, 수강 등록, 최소 직원 배정, 담당 반 학생 목록만 기존 UI/인증/API 클라이언트 패턴을 재사용해 추가한다. UI에서 버튼을 숨기는 것은 서버 인가를 대체하지 않는다.
- DB 스키마 변경이 정말 필요한 경우 기존 13개 업무 테이블과 `002_staff_auth_rbac`를 유지하고 새로운 additive Alembic migration만 작성한다. 개발 DB 변경 전 실제 영향 분석과 백업 정책 확인. 승인되지 않은 파괴적 변경 금지.

## D. 테스트와 완료 조건
- Ruff, pytest, 실제 격리된 PostgreSQL 통합 테스트, Java 전체/DB 회귀 테스트, React Vitest·lint·production build를 실행한다.
- 신규 테스트: 반/학생/수강/배정 정상 흐름, 중복 및 동시 수강 요청, FK 위반, Rollback, 비활성/배정 해제 직원, 담당 외 반 접근, IDOR/BOLA, CSRF, 페이지네이션(있는 경우), API 오류 응답, 개인정보 비노출.
- 개발 DB는 파괴적 테스트 대상이 아니다. 격리 테스트 DB라도 기존 안전 wrapper와 명시적인 실행 승인 정책을 준수한다. 테스트를 돌릴 수 없으면 BLOCKED로 기록하고 거짓 PASS를 보고하지 않는다.
- 기존 Phase 1~5 API/계약과 실제 스키마를 훼손하지 않는다.
- 브라우저 E2E는 사용자가 직접 로그인해야 할 수도 있다. 그 경우 필요한 절차만 제시하며 성공을 추정하지 않는다.

## E. 비용·보안 절대 제한
- 로컬 무료 오픈소스만 사용. AWS/GCP/Azure, 유료 SaaS/API/DB, 외부 인증, 실제 이메일/SMS 발송, Kafka/Redis 설치 금지.
- 기존 PostgreSQL 컨테이너/볼륨 삭제·초기화 금지. 미확인 컨테이너 수정 금지.
- 사용자 비밀번호·DB 비밀번호·Secret·세션 토큰을 요청 본문/코드/로그/Git에 기록하지 않는다.
- 인증/RBAC/CSRF 비활성화나 임시 우회 금지. 실제 학생 개인정보 사용 금지.
- 외부 과금 가능성이 있는 작업은 실행하지 않고 무료 대안과 비용 위험을 보고한다. Codex 사용량 과금 자체는 프로젝트에서 통제할 수 없음을 명시한다.

## F. 결과물
- 실제 코드·테스트에 근거한 최신 README, MVP 로드맵, 아키텍처 및 메시지 처리 상태 설계 업데이트.
- Phase 6A 첫 Vertical Slice 실제 구현 및 검증 결과.
- `docs/archive/phases/phase6a-student-enrollment-vertical-slice.md`에 구현 API/화면, DB 변경, 권한 정책, Java/Python 호환성, 테스트 PASS/FAIL/SKIPPED/BLOCKED, 미해결 위험, 다음 개발 단계 기록.
- 기존 Phase 1~5 보고서 삭제 금지.

**최종 기준:** 기술 추가가 아니라, 관리자가 학생을 반에 등록하고 담당 교사가 허용된 학생만 조회할 수 있으며 중복 등록·권한 우회가 차단됨을 실제 테스트로 입증하는 것이다. 환경 제약 때문에 불가능한 검증은 정확히 BLOCKED로 보고한다.
