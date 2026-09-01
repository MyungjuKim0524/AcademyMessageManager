# Academy Message Manager

Java Swing 기반 학원 성적 안내 메시지 자동 생성 및 발송 관리 프로그램입니다.

현재 저장소는 기존 Swing/Oracle 기반 기능을 유지하면서 내부 구조와 테스트 가능성을 개선한 **Refactoring 1 (v1.1.0)** 결과물입니다. PostgreSQL, Spring Boot, REST API, React 전환은 향후 단계로 분리했습니다.

백엔드는 비즈니스 규칙(`domain`), 유스케이스(`service`), 외부 의존성 경계(`port`), Oracle 구현(`dao`)으로 구성됩니다. 세부 리팩토링 과정은 [백엔드 요구사항](docs/BACKEND_REQUIREMENTS.md), [Business Rule Refactoring](docs/refactoring/01-business-readable-refactoring.md), [Backend Architecture Refactoring](docs/refactoring/02-backend-architecture-refactoring.md)에서 확인할 수 있습니다.

문제 정의, 개선 과정, 코드 및 테스트 근거는 [백엔드 리팩토링 증거 문서](docs/PORTFOLIO_BACKEND_REFACTORING_EVIDENCE.md)에 정리했습니다.

## Architecture

```text
Before
Swing UI
  ↓
Service / Business Rules / SQL
  ↓
Oracle / SMTP

After Refactoring 1
Swing UI
  ↓
Service / Use Case
  ↓
Domain
  ↓
Port
  ↓
DAO / Oracle / SMTP
```

### Key Improvements

- 문자열로 분산되어 있던 상태값과 업무 규칙을 Domain 타입 및 정책으로 분리
- 화면과 유스케이스의 책임 분리
- Port 인터페이스를 통한 외부 의존성 경계 명확화
- 생성자 기반 Dependency Injection 적용
- Domain 및 Validation 단위 테스트 추가
- 환경 설정과 자격증명 관리 구조 개선
- 기존 Java 17, Swing, Maven, Oracle JDBC, Jakarta Mail 기반 기능 유지

## Security Improvements

- DB 및 메일 자격증명을 로컬 설정/암호화 파일로 분리하고 Git 추적 대상에서 제외
- CSV Export 시 `=`, `+`, `-`, `@` 시작값에 대한 Formula Injection 방어
- 외부 연동 실패 시 상세 예외는 내부 로그에 기록하고 사용자 화면에는 일반화된 오류 메시지 표시
- 샘플 데이터는 `example.invalid`를 포함한 가상 정보만 사용

## Key Features

- `.xlsx` / CSV 성적 데이터 Import
- 필수 컬럼 및 입력값 검증
- JTable 기반 데이터 미리보기
- Oracle DB 저장
- 분반, 학생, 수강 상태, 수업 회차, 성적 기록 관리
- `INSERT / UPDATE / SKIP` 기반 중복 저장 방지
- 정규 수업 / 내신 대비 메시지 자동 생성
- 예습, 주간 과제, 테스트 결과 전체 공백 컬럼 자동 제외
- DB 템플릿 기반 메시지 생성 및 수정
- 전체 학생 메시지 생성 및 학생별 내용 수정
- 개별/전체 대상 선택 기반 이메일 발송
- Gmail SMTP 기반 이메일 발송
- 퇴원 학생 기본 발송 제외
- 이메일 누락/형식 오류 대상 발송 제외
- 발송 성공/실패/제외 로그 저장 및 조회
- 실패 건 재시도
- 발송 로그 CSV Export
- 결석 학생 기반 보강 신청 관리
- 퇴원/휴원 학생 보강 대상 자동 제외
- 학생 이메일 및 수강 상태 수정
- 퇴원 처리 시 미완료 보강 신청 자동 취소

## Getting Started

### VS Code

1. 저장소를 clone한 뒤 VS Code에서 프로젝트 루트를 엽니다.
2. Java Extension Pack을 설치합니다.
3. Maven 설치 여부를 `mvn -version`으로 확인합니다.
4. 다음 명령으로 의존성을 내려받고 프로젝트를 컴파일합니다.

```powershell
mvn compile
```

5. `src/main/java/com/academy/message/Main.java`를 실행합니다.
6. `data/sample_students.xlsx` 또는 `data/sample_students.csv`를 사용해 동작을 확인합니다.

### Terminal

```powershell
mvn exec:java
```

## Oracle Database Setup

1. SQL Developer에서 프로젝트용 Oracle 계정으로 접속합니다.
2. [sql/schema_oracle.sql](sql/schema_oracle.sql)을 실행해 필요한 테이블을 생성합니다.
3. `src/main/resources/config.properties.example`을 복사해 `config.properties`를 생성합니다.
4. 환경에 맞게 DB 접속 정보를 설정합니다.

```properties
db.url=jdbc:oracle:thin:@localhost:1521/testpdb
db.username=YOUR_DB_USERNAME
db.password=YOUR_DB_PASSWORD
mail.smtp.host=smtp.gmail.com
mail.smtp.port=587
```

5. 프로그램에서 Excel/CSV 데이터를 불러온 뒤 `DB 업데이트 실행`을 수행합니다.

메일 발송 기능은 Gmail 2단계 인증과 앱 비밀번호를 사용합니다. 발송 계정과 앱 비밀번호는 프로그램의 `메일 설정` 탭에서 입력하며, 마스터 암호를 기반으로 암호화해 저장합니다.

암호화 파일은 `ACADEMY_DATA_DIR` 환경변수로 지정한 경로에 저장되며, 환경변수가 없는 경우 사용자 홈의 `.academy-message-manager` 디렉터리를 사용합니다. 마스터 암호 자체는 저장하지 않습니다.

## Input Data Format

`data/sample_students.csv`와 `data/sample_students.xlsx`에는 테스트용 가상 데이터만 포함되어 있습니다. `example.invalid`는 실제 메일 발송이 발생하지 않는 예약 도메인입니다.

```csv
분반명,수업유형,수업일자,시험회차,이름,학교명,수강상태,출석 여부,보호자명,보호자 이메일,예습 과제 등급,주간 과제 등급,test 결과
```

- 수업유형: `정규`, `내신 대비` / 기존 `REGULAR`, `EXAM_PREP` 호환
- 수강상태: `재원`, `휴원`, `퇴원` / 기존 `ACTIVE`, `PAUSED`, `WITHDRAWN` 호환

## Main Screens

- `데이터 불러오기`: Excel/CSV Import, Validation, Oracle DB Update
- `메시지 생성`: 전체 메시지 생성 및 학생별 내용 수정
- `이메일 발송`: 최신 이메일/수강 상태 확인, 개별·전체 대상 선택, 이메일 발송
- `발송 내역`: 발송 로그 조회, 실패 건 재시도, CSV Export
- `템플릿 설정`: 수업 유형별 DB 템플릿 조회 및 수정
- `보강 관리`: 결석 학생 보강 신청, 완료, 취소
- `학생 관리`: 분반별 학생 조회, 이메일 및 수강 상태 수정
- `메일 설정`: Gmail 계정 및 앱 비밀번호 암호화 저장

발송 상태는 화면에서 `발송 성공`, `발송 실패`, `발송 제외`로 표시하며, DB에는 각각 `SENT`, `FAILED`, `SKIPPED`로 저장합니다.

## Roadmap

1. **Database Redesign**
   - 프로젝트 전용 PostgreSQL 스키마 재설계
   - ERD, PK/FK, 제약조건, 인덱스, Migration/Rollback 설계

2. **Backend Modernization**
   - Spring Boot 기반 백엔드 전환
   - REST API, Validation, Exception Handling, Transaction, Repository 구조 적용

3. **Web Migration**
   - Swing UI 제거
   - React 기반 Web UI 전환

4. **Production Readiness**
   - Docker
   - CI/CD
   - 보안 강화
   - Cloud Deployment

위 항목은 향후 계획이며 Refactoring 1 범위에는 포함되지 않습니다.

## Testing

JDK 17 이상과 Maven 환경에서 다음 명령을 실행합니다.

```powershell
mvn test
```

현재 단위 테스트는 다음 영역을 검증합니다.

- Domain 상태 변환
- 보강 자격 및 상태 전이
- 메시지 구성
- 입력 데이터 Validation
- CSV Formula Injection 방어

Oracle DAO는 실제 Oracle 테스트 환경이 필요한 통합 검증 대상으로 분리합니다.

## Privacy Considerations

현재 저장소의 샘플 데이터는 모두 가상 정보입니다.

실제 운영 환경에서는 발송 로그에 포함될 수 있는 보호자 이메일과 메시지 내용에 대해 별도의 **보존 기간, 접근 권한, 삭제 절차, 백업 정책**이 필요합니다
