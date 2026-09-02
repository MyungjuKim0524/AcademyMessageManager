# Academy Message Manager

Java Swing 기반 성적 안내 메시지 자동 생성 및 발송 관리 프로그램입니다.

이 저장소는 **Refactoring 1 (버전 1.1.0)** 이후 **PostgreSQL Database Redesign을 완료한 결과물**입니다. Swing/JDBC 구조는 유지하며 Spring Boot, REST API, React 전환은 아직 구현하지 않았습니다.

백엔드는 비즈니스 규칙(`domain`), 유스케이스(`service`), 외부 경계(`port`), PostgreSQL JDBC 구현(`dao`)으로 분리되어 있습니다. 리팩토링 근거는 [백엔드 요구사항](docs/BACKEND_REQUIREMENTS.md), [Business Rule Refactoring](docs/refactoring/01-business-readable-refactoring.md), [Backend Architecture Refactoring](docs/refactoring/02-backend-architecture-refactoring.md)을 참고하세요. 두 문서는 모두 Refactoring 1 안의 세부 작업입니다.

포트폴리오 제출용 문제 해결 과정과 코드·테스트 증거는 [백엔드 리팩토링 증거 문서](docs/PORTFOLIO_BACKEND_REFACTORING_EVIDENCE.md)에 정리되어 있습니다.

## 아키텍처 변화

```text
Before: Swing 화면 → 서비스/업무 규칙/SQL 혼재 → Oracle·SMTP

After : Swing 화면 → service → domain
                         ↓
                        port
                         ↓
                   dao / PostgreSQL·SMTP
```

핵심 개선 사항은 도메인·유스케이스 분리, DAO 연결 제공자 주입, PostgreSQL 전용 관계 모델, import audit, 발송 시도 이력입니다. Java 17, Swing, Maven, JDBC, Jakarta Mail 구성은 유지하며 `test 결과` 입력은 내부에서 `correct_count/total_count`로 변환합니다.

## 보안 개선

- DB/메일 비밀값을 로컬 설정 및 암호화 파일로 분리하고 Git 추적에서 제외
- CSV 내보내기 시 `=`, `+`, `-`, `@` 시작값의 수식 주입 방어
- 외부 연동 실패의 상세 예외는 내부 로그에 기록하고 사용자에게는 일반화된 메시지 표시
- 샘플 데이터는 `example.invalid`를 포함한 가상 정보만 사용

## 현재 구현된 범위

- `.xlsx` Excel 성적 데이터 불러오기
- CSV 성적 데이터 불러오기
- 필수 컬럼 및 값 검증
- JTable 데이터 미리보기
- PostgreSQL DB 저장
- 분반, 학생, 수강 상태, 수업 회차, 성적 기록 관리
- `INSERT / UPDATE / SKIP` 기반 중복 저장 방지
- 정규 수업 / 내신 대비 메시지 자동 생성
- 예습, 주간 과제, 테스트 결과 전체 공백 컬럼 자동 제외
- DB 템플릿 기반 메시지 생성
- 템플릿 조회 및 수정
- 전체 학생 메시지 생성 및 학생별 내용 수정
- 이메일 발송 화면에서 개별 체크박스 또는 전체 선택/해제
- Gmail SMTP 기반 이메일 발송
- 퇴원 학생 기본 발송 제외
- 이메일 없음/형식 오류 학생 발송 제외
- 발송 성공/실패/제외 로그 저장 및 조회
- 실패 건 재시도
- 발송 로그 CSV 저장
- 결석 학생 기반 보강 신청 관리
- 퇴원/휴원 학생 보강 대상 자동 제외
- 학생 관리 탭에서 이메일 및 수강 상태 수정
- 퇴원 처리 시 미완료 보강 신청 자동 취소

## VS Code 실행 방법

1. 이 저장소를 클론한 뒤 VS Code에서 저장소 루트 폴더를 엽니다.
2. Java Extension Pack이 없다면 설치합니다.
3. Maven이 없다면 Apache Maven을 설치하고 `mvn -version`으로 확인합니다.
4. 터미널에서 `mvn compile`을 실행해 의존성을 내려받습니다.
5. `src/main/java/com/academy/message/Main.java`를 열고 `Run`을 누릅니다.
6. 프로그램에서 `data/sample_students.xlsx` 또는 `data/sample_students.csv`를 선택해 테스트합니다.

## 터미널 실행

```powershell
mvn exec:java
```

## PostgreSQL DB 연결 준비

1. PostgreSQL에 `academy_message_manager` 테스트 DB와 전용 사용자를 준비합니다.
2. [sql/schema_postgresql.sql](sql/schema_postgresql.sql)을 실행해 테이블을 생성합니다.
3. 선택적으로 [sql/seed_postgresql.sql](sql/seed_postgresql.sql)을 실행해 비식별 샘플 데이터를 추가합니다.
4. `src/main/resources/config.properties.example` 파일을 복사해 `config.properties`로 이름을 바꿉니다.
5. DB 접속 정보가 다르면 아래 값을 수정하거나 `DB_URL`, `DB_USER`, `DB_PASSWORD` 환경변수를 설정합니다.

```properties
db.url=jdbc:postgresql://localhost:5432/academy_message_manager
db.username=YOUR_DB_USERNAME
db.password=YOUR_DB_PASSWORD
mail.smtp.host=smtp.gmail.com
mail.smtp.port=587
```

6. 프로그램에서 Excel/CSV를 불러온 뒤 `DB 업데이트 실행`을 누릅니다.

최종 ERD는 `PostgreSQL ERD v1.2.drawio`이며, `makeup_request.target_lesson_id`를 nullable FK로 두어 보강 요청 생성 후 대상 수업을 배정할 수 있습니다. DDL과 ERD 모두 `target_lesson_id → lesson(id)` 및 조회용 인덱스를 반영합니다.

메일 발송을 실제로 사용하려면 Gmail 2단계 인증과 앱 비밀번호가 필요합니다.
프로그램의 `메일 설정` 탭에서 계정과 앱 비밀번호를 입력하고 마스터 암호로 암호화해 저장합니다.
암호화 파일은 `ACADEMY_DATA_DIR` 환경변수로 지정한 폴더에 저장됩니다. 환경변수가 없으면 사용자 홈의 `.academy-message-manager` 폴더를 사용하며 제출 프로젝트에는 포함되지 않습니다.
마스터 암호는 저장되지 않으므로 잊으면 암호화 파일을 삭제하고 다시 설정해야 합니다.

## Excel / CSV 컬럼

`data/sample_students.csv`와 `data/sample_students.xlsx`의 인물·학교·이메일은 모두 테스트용 가상 데이터입니다. `example.invalid` 주소는 실제 메일이 발송되지 않는 예약 도메인입니다.

```csv
분반명,수업유형,수업일자,시험회차,이름,학교명,수강상태,출석 여부,보호자명,보호자 이메일,예습 과제 등급,주간 과제 등급,test 결과
```

수업유형은 `정규`, `내신 대비`로 입력할 수 있으며, 기존 `REGULAR`, `EXAM_PREP` 값도 호환됩니다.
수강상태는 `재원`, `휴원`, `퇴원`으로 입력할 수 있으며, 기존 `ACTIVE`, `PAUSED`, `WITHDRAWN` 값도 호환됩니다.

## 주요 화면

- `데이터 불러오기`: Excel/CSV 불러오기, 검증, PostgreSQL DB 업데이트 및 import audit 기록
- `메시지 생성`: 전체 메시지 생성 및 학생별 내용 수정
- `이메일 발송`: 최신 이메일 및 수강 상태 확인, 개별/전체 대상 선택, 선택 대상 이메일 발송
- `발송 내역`: 발송 로그 검색, 실패 건 재시도, CSV 저장
- `템플릿 설정`: 수업 유형 선택 시 DB 템플릿 자동 불러오기 및 저장
- `보강 관리`: 결석 학생 보강 신청, 완료, 취소
- `학생 관리`: 분반별 학생 조회, 이메일 및 수강 상태 수정
- `메일 설정`: 발송자 Gmail 계정과 앱 비밀번호 암호화 저장, Gmail 주소를 발신 주소로 사용

발송 상태는 화면에서 `발송 성공`, `발송 실패`, `발송 제외`로 표시되며 DB에는 각각 `SENT`, `FAILED`, `SKIPPED`로 저장됩니다.

## 향후 로드맵

1. **Backend Modernization**: Spring Boot와 REST API 도입
2. **Web Frontend**: React 기반 사용자 화면 전환
3. **Production Readiness**: Docker, CI/CD, 보안 강화, 클라우드 배포

위 항목은 향후 계획이며 Refactoring 1 완료 범위에는 포함되지 않습니다.

## 테스트

JDK 17 이상과 Maven 환경에서 다음 명령을 실행합니다.

```powershell
mvn test
```

단위 테스트는 도메인 상태 변환, 보강 자격·상태 전이, 점수 파싱·검증·표현, 메시지 구성, 입력 데이터 검증, CSV 수식 주입 방어를 확인합니다.

실제 PostgreSQL DAO 통합 테스트는 DB 접속 환경변수와 실행 플래그를 설정한 뒤 수행합니다. 테스트는 스키마가 적용된 전용 테스트 DB의 관련 테이블을 `TRUNCATE`하므로 운영 DB에는 실행하지 마세요.

```powershell
$env:DB_URL = "jdbc:postgresql://localhost:5432/academy_message_manager"
$env:DB_USER = "YOUR_DB_USERNAME"
$env:DB_PASSWORD = "YOUR_DB_PASSWORD"
$env:RUN_POSTGRES_INTEGRATION = "true"
mvn -Dtest=PostgreSqlDaoIntegrationTest test
```

이 통합 테스트는 CSV/XLSX import, 학생·분반·수강·수업·성적 CRUD, DB 템플릿 메시지 생성, nullable `target_lesson_id` 보강 처리, 발송 이력·시도 저장, FK 위반 거부 및 트랜잭션 롤백을 실제 PostgreSQL에서 확인합니다. `RUN_POSTGRES_INTEGRATION`이 없으면 공개 저장소의 기본 `mvn test`에서는 안전하게 건너뜁니다.

## 운영 전 개인정보 보호 확인

현재 프로젝트의 샘플 데이터는 모두 가상 정보입니다. 실제 운영 환경에서는 발송 로그에 포함되는 보호자 이메일과 메시지 내용에 대해 보존 기간, 접근 권한 및 삭제 절차를 별도로 적용해야 합니다.
