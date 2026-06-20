# Academy Message Manager

Java Swing 기반 학원 성적 안내 메시지 자동 생성 및 이메일 발송 관리 프로그램입니다.

## 주요 기능

* `.xlsx` Excel 성적 데이터 불러오기
* CSV 성적 데이터 불러오기
* 필수 컬럼 및 값 검증
* JTable 데이터 미리보기
* Oracle DB 저장
* 분반, 학생, 수강 상태, 수업 회차, 성적 기록 관리
* 성적 기록의 `INSERT / UPDATE / SKIP` 판정 및 중복 저장 방지
* 정규 수업 / 내신 대비 메시지 자동 생성
* 예습, 주간 과제, 테스트 결과 전체 공백 컬럼 자동 제외
* DB 템플릿 기반 메시지 생성
* 템플릿 조회 및 수정
* 전체 학생 메시지 생성 및 학생별 내용 수정
* 이메일 발송 화면에서 개별 체크박스 또는 전체 선택/해제
* Gmail SMTP 기반 이메일 발송
* 퇴원 학생 기본 발송 제외
* 이메일 없음/형식 오류 학생 발송 제외
* 발송 성공/실패/제외 상태 관리 및 로그 조회
* 실패 건 재시도
* 발송 로그 CSV 저장
* 결석 학생 기반 보강 신청 관리
* 퇴원/휴원 학생 보강 대상 자동 제외
* 학생 관리 탭에서 이메일 및 수강 상태 수정
* 퇴원 처리 시 미완료 보강 신청 자동 취소

## 프로젝트 구조

```text
AcademyMessageManager
├── src/main/java/com/academy/message
│   ├── dao        # Oracle DB 접근
│   ├── model      # 데이터 모델
│   ├── service    # 파일 불러오기, 검증, 메시지 생성 등 주요 로직
│   ├── util       # 이메일 검증, CSV 저장 등 유틸리티
│   └── view       # Swing UI
├── src/main/resources
├── sql            # Oracle DB 스키마
├── data           # 샘플 입력 파일
├── pom.xml
└── README.md
```

## VS Code 실행 방법

1. VS Code에서 `AcademyMessageManager` 프로젝트 폴더를 엽니다.
2. Java Extension Pack이 없다면 설치합니다.
3. Maven이 없다면 Apache Maven을 설치하고 `mvn -version`으로 확인합니다.
4. 터미널에서 `mvn compile`을 실행해 의존성을 내려받습니다.
5. `src/main/java/com/academy/message/Main.java`를 열고 `Run`을 누릅니다.
6. 프로그램에서 `data/sample_students.xlsx` 또는 `data/sample_students.csv`를 선택해 테스트합니다.

## 터미널 실행

```powershell
mvn exec:java
```

## Oracle DB 연결 준비

1. SQL Developer에서 프로젝트용 Oracle 계정으로 접속합니다.
2. [sql/schema_oracle.sql](sql/schema_oracle.sql)을 실행해 프로젝트용 테이블을 생성합니다.
3. `src/main/resources/config.properties.example` 파일을 복사해 `config.properties`로 이름을 바꿉니다.
4. DB 접속 정보가 다르면 아래 값을 수정합니다.

```properties
db.url=jdbc:oracle:thin:@localhost:1521/testpdb
db.username=my_db_username
db.password=my_db_password
mail.smtp.host=smtp.gmail.com
mail.smtp.port=587
```

5. 프로그램에서 Excel/CSV를 불러온 뒤 `불러온 데이터 DB 반영`을 누릅니다.

메일 발송을 실제로 사용하려면 Gmail 2단계 인증과 앱 비밀번호가 필요합니다.
프로그램의 `메일 설정` 탭에서 Gmail 계정과 앱 비밀번호를 입력하고 마스터 암호로 암호화해 저장합니다.
암호화 파일은 사용자 홈 디렉터리 아래의 `AcademyMessageManagerData/mail_credentials.enc`에 저장되며 프로젝트에는 포함되지 않습니다.
마스터 암호는 저장되지 않으므로 잊으면 암호화 파일을 삭제하고 다시 설정해야 합니다.

## Excel / CSV 컬럼

```csv
분반명,수업유형,수업일자,시험회차,이름,학교명,수강상태,출석 여부,보호자명,보호자 이메일,예습 과제 등급,주간 과제 등급,test 결과
```

Excel/CSV 파일의 수업유형은 `정규`, `내신 대비` 중 하나로 입력합니다.
프로그램 화면에서도 동일한 한글 선택지를 사용합니다.

Excel/CSV 파일의 수강상태는 `재원`, `휴원`, `퇴원` 중 하나로 입력합니다.
프로그램의 학생 관리 화면에서도 동일한 한글 선택지를 사용합니다.

## 주요 화면

* `데이터 불러오기`: Excel/CSV 불러오기, 검증, Oracle DB 업데이트
* `메시지 생성`: 전체 메시지 생성 및 학생별 내용 수정
* `이메일 발송`: 최신 이메일 및 수강 상태 확인, 개별/전체 대상 선택, 선택 대상 이메일 발송
* `발송 내역`: 발송 로그 검색, 실패 건 재시도, CSV 저장
* `템플릿 설정`: 수업 유형 선택 시 DB 템플릿 자동 불러오기 및 저장
* `보강 관리`: 결석 학생 보강 신청, 완료, 취소
* `학생 관리`: 분반별 학생 조회, 이메일 및 수강 상태 수정
* `메일 설정`: 발송자 Gmail 계정과 앱 비밀번호 암호화 저장, Gmail 주소를 발신 주소로 사용

발송 결과는 화면에서 `발송 성공`, `발송 실패`, `발송 제외`로 관리되며, DB에서는 상황에 따라 `SENT`, `FAILED`, `SKIPPED` 상태값을 사용합니다.

## 보안 관련 주의사항

* 실제 DB 접속 정보가 들어간 `config.properties` 파일은 GitHub에 포함하지 않습니다.
* Gmail 계정, 앱 비밀번호, 암호화된 인증 파일은 GitHub에 포함하지 않습니다.
* `config.properties.example` 파일만 예시 설정 파일로 제공합니다.
* 샘플 데이터는 테스트용 더미 데이터만 사용합니다.
