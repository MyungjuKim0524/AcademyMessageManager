# Academy Message Manager

## 현재 제품 방향

현재 주 개발 경로는 **FastAPI + React + PostgreSQL 모듈형 모놀리스**다. 처음 만든 Java/Swing/JDBC
프로그램은 Import 업무 규칙과 회귀 계약을 옮겨 오기 위한 기준선으로만 쓰였고, **이 저장소에는
포함하지 않는다**(아래 [Java 레거시](#java-레거시-저장소-미포함) 참고).

```text
React → FastAPI Router → Service(업무·트랜잭션) → Repository(SQLAlchemy) → PostgreSQL
                         Authorization(서버 세션·CSRF·RBAC·담당 반 범위)
```

Phase 6A는 ADMIN의 반·학생·수강·최소 직원 배정과 TEACHER/ASSISTANT의 담당 반 학생
조회까지 구현한다. 쓰기 API는 ADMIN 세션과 CSRF가 모두 필요하며, 목록도 서버가 배정 기간과
역할로 범위를 제한한다. 교직원 조회 응답에는 보호자 이름·이메일을 포함하지 않는다.

- `POST /api/classrooms`, `POST /api/students`
- `POST /api/classrooms/{id}/enrollments`, `POST /api/classrooms/{id}/assignments`
- `GET /api/classrooms/{id}/students?limit=50&offset=0`
- React `/students`: 위 업무 흐름과 담당 반 학생 목록

DB 변경은 Alembic `003_phase6a_enrollment_integrity` 하나이며 학생·반 조합의 동시 중복을
DB UNIQUE 인덱스로 차단한다. 적용 전에 기존 중복을 읽기 전용으로 진단하며 개발 DB에
자동 적용하거나 데이터를 자동 정리하지 않는다. 관리자 계정이 없으면 비밀값을 파일이나
명령 기록에 넣지 말고 `scripts/bootstrap-admin.ps1`을 사용한다.

이후 Phase 6B~11에서 기능을 차례로 구현했고, 모두 완료됐다. 현재는 Phase 11-5(배포) 준비 단계다.
- Phase 6B: 직원·담당 반 배정
- Phase 7: 수업·출결·성적
- Phase 8: 템플릿·초안·검토·모의 발송
- Phase 9: 누락 탐지·처리 상태·실패 재시도
- Phase 10: 출결·성적 분석
- Phase 11: 통합·보안·정합성·성능 점검과 릴리스 준비

Kafka, Redis, MSA, Kubernetes, 실제 이메일/SMS 발송은 보류 또는 범위 밖이다.

전체 개발 이력과 현재 상태는 [Development History](docs/DEVELOPMENT_HISTORY.md)를 참고한다.
Phase 6A 세부 내용은 [Phase 6A 보고서](docs/phase6a-student-enrollment-vertical-slice.md)에 있다.

### D드라이브 개발 데이터 정책

프로젝트와 기존 Python 가상환경, Node 의존성 및 빌드 결과는 D드라이브에 유지한다. 테스트나
의존성 명령 전 아래 스크립트를 현재 PowerShell 세션에만 dot-source하면 pip/npm/Ruff/pytest,
coverage와 임시 파일이 Git 제외 경로인 `.dev-data` 아래에 저장된다. 사용자·시스템 전역
환경변수는 변경하지 않는다. 기존 정상 가상환경과 `node_modules`는 재설치하지 않는다.

```powershell
. .\scripts\use-d-drive-dev-env.ps1
```

Docker Desktop의 WSL 데이터 위치는 현재 `D:\DockerData\DockerDesktopWSL`로 설정되어 있다.
컨테이너·볼륨·VHDX는 검증 작업에서 이동·삭제·초기화하지 않는다.

## 현재 개발 비용·외부 연동 정책

이 저장소의 LearningOps 고도화는 개인 학습·취업 포트폴리오 목적으로 기존 로컬 환경과 무료
오픈소스만 사용한다. 유료 cloud/SaaS/API/DB를 생성하거나 배포하지 않으며 Docker Compose
로컬 환경까지만 다룬다. FastAPI 개발과 테스트에서는 실제 이메일·SMS를 발송하지 않고 Mock
adapter만 사용한다(`backend/app/modules/notifications/sender.py`).
Codex 모델 사용량과 계정 과금은 저장소로 통제할 수 없으므로 사용자가 직접 확인한다.

실제 학원 업무가 문자 중심인 점을 반영해, 보호자 휴대전화번호 기반 SMS/LMS 발송으로의 전환을
향후 검토 과제로 관리한다(미구현). 실제 발송 API 연동 전에는 외부 발송 I/O와 DB 트랜잭션 분리가
선행되어야 한다. 배경과 검토 범위는 [Development History — Future Roadmap](docs/DEVELOPMENT_HISTORY.md#8-future-roadmap)을 참고한다.

## 로컬 실행

요구 사항: Python 3.12 이상, Node.js(로컬 검증 24.x)와 npm, Docker Desktop(PostgreSQL 컨테이너).
백엔드 준비·설치·환경변수는 [backend/README.md](backend/README.md)와 `backend/.env.example`,
프론트엔드 환경변수는 `frontend/.env.example`을 참고한다.

```powershell
.\scripts\migrate-dev-db.ps1    # 개발 DB에 Alembic Migration 적용
.\scripts\bootstrap-admin.ps1   # 최초 관리자 생성(ACADEMY_BOOTSTRAP_EMAIL·PASSWORD를 현재 세션에만 설정)
.\scripts\start-fastapi.ps1     # FastAPI 127.0.0.1:8000
.\scripts\start-frontend.ps1    # React(Vite) 127.0.0.1:5173, /api는 FastAPI로 proxy
```

각 스크립트는 개발 DB 컨테이너(`academy-learningops-postgres-dev`, `127.0.0.1:55431`)의
라벨·포트를 확인한 뒤에만 실행되며, DB 비밀번호를 출력하지 않는다.

## 테스트

```powershell
. .\scripts\use-d-drive-dev-env.ps1

# 백엔드 단위 테스트·린트 (DB 불필요)
cd backend
.\.venv\Scripts\pytest.exe -m "not postgres"
.\.venv\Scripts\ruff.exe check .
cd ..

# 프론트엔드
cd frontend
npm run lint
npm test
npm run build
cd ..
```

위 단계를 한 번에 실행하려면 `.\scripts\verify-all.ps1`을 사용한다(Ruff → pytest → lint → Vitest → build, DB 불필요).

PostgreSQL 통합 테스트는 **격리 테스트 DB**(`academy-learningops-postgres-test`, `127.0.0.1:55432`,
라벨 `academy.environment=isolated-test`)에서만 실행된다. 일부 테스트가 테이블을 `TRUNCATE`하므로
다른 DB에는 실행하지 않는다. 스크립트가 컨테이너 라벨·포트·DB 이름·사용자를 확인하고, 하나라도
다르면 실행을 거부한다.

```powershell
$env:ACADEMY_TEST_DB_PASSWORD = '<로컬 테스트 DB 비밀번호>'   # 현재 세션에만
.\scripts\run-postgres-integration.ps1
Remove-Item Env:ACADEMY_TEST_DB_PASSWORD
```

## 배포

배포 실행 모드(`ACADEMY_DB_MODE=production`), 필수 환경변수, 실행 명령과 배포 후 점검 절차는
다음 문서를 따른다.

- [보안 배포 설정 가이드](docs/deployment/phase11_5_security_deployment_guide.md)
- [릴리스 준비도·배포 인계](docs/reviews/phase11_4_release_readiness.md)

## 샘플 데이터

`data/sample_students.csv`, `data/sample_students.xlsx`, `tests/fixtures/`, `sql/seed_postgresql.sql`의
인물·학교·이메일은 모두 테스트용 가상 데이터다. `example.invalid` 주소는 실제 메일이 발송되지 않는
예약 도메인이다. 실제 학생·보호자 정보는 저장소에 넣지 않는다.

## Java 레거시 (저장소 미포함)

이 프로젝트는 Java 17 · Swing · JDBC · Maven으로 만든 성적 안내 메시지 생성·발송 프로그램에서
시작했다. 업무 규칙과 회귀 계약을 FastAPI로 옮긴 뒤에는 기준선으로만 쓰였고, Java 소스(`src/`)와
빌드 설정(`pom.xml`)은 이 저장소에 포함하지 않는다(`.gitignore`). 따라서 Java 빌드·실행·테스트
절차도 이 문서에서 제외했다.

버전별 발전 과정(v1.0-legacy → v1.1.0 → v1.2.0 → FastAPI·React)과 항목별 비교(Before → Problem →
Decision → After → Validation → Trade-off), 웹에서 빠지거나 약해진 기능은
[Development History 2절](docs/DEVELOPMENT_HISTORY.md#2-architecture-evolution)과
[9절](docs/DEVELOPMENT_HISTORY.md#9-legacy--web-비교-개선-항목별-근거)에 정리했다.

Java 시절에서 이어져 지금도 쓰이는 파일만 남아 있다.

- `sql/schema_postgresql.sql`: Alembic 첫 Migration `001_java_schema_baseline`이 읽는 기준 스키마
- `tests/fixtures/contract/`: Python 계약 테스트(`backend/tests/test_contract_fixtures.py`)가 읽는 fixture
- `docs/`의 리팩토링·마이그레이션 기록(예: [백엔드 리팩토링 증거](docs/PORTFOLIO_BACKEND_REFACTORING_EVIDENCE.md),
  [Development History](docs/DEVELOPMENT_HISTORY.md)). 문서가 가리키는 Java 소스 경로는 이 저장소에 없다.

## 운영 전 개인정보 보호 확인

현재 프로젝트의 샘플 데이터는 모두 가상 정보다. 실제 운영 환경에서는 메시지 본문과 보호자 연락처에
대해 보존 기간, 접근 권한 및 삭제 절차를 별도로 적용해야 한다.
