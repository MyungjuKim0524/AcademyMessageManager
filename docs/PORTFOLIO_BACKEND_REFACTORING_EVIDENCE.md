# 학원 메시지 관리 시스템 백엔드 리팩토링 증거 문서

## 1. 프로젝트 개요

이 프로젝트는 CSV/XLSX로 전달받은 학원 수업 데이터를 검증하고 Oracle DB에 반영한 뒤, 학생별 학습 안내 메시지를 생성하여 보호자에게 이메일로 발송하는 Java 17 기반 데스크톱 애플리케이션이다.

초기 버전은 실제 업무 흐름을 끝까지 수행할 수 있었지만, 비즈니스 규칙이 문자열 비교와 DAO 내부에 분산되어 있었다. 따라서 기능을 추가하거나 정책을 변경할 때 영향 범위를 예측하기 어렵고, DB 없이 핵심 규칙을 검증하기도 어려웠다.

이번 작업의 목표는 프론트엔드를 다시 만드는 것이 아니라 다음 두 가지를 증명하는 것이었다.

1. 동작을 유지하면서 비즈니스 요구사항이 코드에서 직접 읽히도록 만든다.
2. 핵심 규칙을 외부 기술과 분리하여 테스트와 확장이 가능한 백엔드 구조를 만든다.

---

## 2. 개선 결과 요약

| 증거 항목 | 초기 코드 | 리팩토링 후 | 의미 |
|---|---:|---:|---|
| 운영 Java 소스 | 30개 | 44개 | 역할별 도메인·포트·유스케이스 분리 |
| 테스트 Java 소스 | 0개 | 5개 | 자동 회귀 검증 기반 확보 |
| 자동 테스트 | 0개 | 10개 | 도메인 규칙, 입력 검증, CSV 수식 주입 방어 확인 |
| 명시적 도메인 타입 | 0개 | 9개 | 문자열에 숨은 업무 개념을 코드화 |
| 외부 의존 포트 | 0개 | 3개 | DB 구현과 핵심 서비스 결합 완화 |
| 개인 PC 고정 경로 | 1개 | 0개 | 실행 환경 이식성 개선 |
| 전체 빌드 | 기준 코드 컴파일 가능 | `mvn clean verify` 성공 | 소스·테스트·JAR 패키징 확인 |

수치가 많아졌다는 사실 자체가 개선을 의미하지는 않는다. 여기서 파일 증가는 각 파일이 하나의 업무 개념 또는 기술 경계를 표현하도록 책임을 분리한 결과다. 효과는 아래 문제별 코드 증거와 테스트로 판단했다.

---

## 3. 문제 1 — 업무 상태가 문자열 비교에 숨어 있었다

### 문제

초기 코드는 `"ACTIVE"`, `"WITHDRAWN"`, `"결석"`, `"COMPLETED"` 같은 문자열을 여러 서비스와 DAO에서 직접 비교했다.

```java
if ("COMPLETED".equals(status)) {
    return "결석한 수업 내용은 보강 수업을 통해 보완하였습니다.";
}
if ("REQUESTED".equals(status) || "APPROVED".equals(status)) {
    return "결석한 수업 내용은 신청한 보강 수업에서 보완할 예정입니다.";
}
```

이 구조에서는 다음 문제가 생긴다.

- 허용 가능한 상태의 전체 목록을 한 곳에서 확인할 수 없다.
- 오타도 컴파일에 성공한다.
- “재원생만 보강 신청 가능” 같은 정책과 단순 표시용 문자열을 구분하기 어렵다.
- 새로운 상태를 추가하면 관련 문자열 비교 위치를 모두 찾아야 한다.

### 해결

수업 유형, 수강 상태, 출석, 성취도, 보강 상태, 발송 상태를 enum으로 만들고 업무 의미를 해당 타입에 배치했다.

```java
public enum EnrollmentStatus {
    ACTIVE("재원"), PAUSED("휴원"), WITHDRAWN("퇴원");

    public boolean canRequestMakeup() {
        return this == ACTIVE;
    }
}
```

```java
public boolean canTransitionTo(MakeupStatus target) {
    return switch (this) {
        case REQUESTED -> target == APPROVED || target == COMPLETED || target == CANCELED;
        case APPROVED -> target == COMPLETED || target == CANCELED;
        case COMPLETED, CANCELED -> false;
    };
}
```

### 선택 근거

DB 값과 Swing 화면의 기존 문자열 계약을 한 번에 변경하면 리팩토링 범위가 프론트엔드와 스키마까지 커진다. 따라서 외부 계약은 유지하고 내부 판단만 타입으로 전환했다. 이는 위험을 낮추는 **점진적 리팩토링** 선택이다.

enum을 선택한 이유는 상태 집합이 작고 닫혀 있으며, 각 상태에 행동을 부여할 수 있기 때문이다. 별도 설정 테이블이나 범용 상태 머신은 현재 규모에서 복잡도만 증가시키므로 도입하지 않았다.

### 코드 증거

- `src/main/java/com/academy/message/domain/EnrollmentStatus.java`
- `src/main/java/com/academy/message/domain/MakeupStatus.java`
- `src/main/java/com/academy/message/domain/AttendanceStatus.java`
- `src/main/java/com/academy/message/domain/SendStatus.java`
- `src/test/java/com/academy/message/domain/DomainStatusTest.java`

### 검증

- 한글 표시값과 영문 코드가 같은 enum으로 변환되는지 확인했다.
- 휴원·퇴원 학생이 보강 자격을 얻지 못하는지 확인했다.
- 완료·취소 상태가 종료 상태인지 확인했다.
- 정의되지 않은 성취도 `D`가 거부되는지 확인했다.

---

## 4. 문제 2 — 메시지 생성 규칙이 DB 조회와 결합되어 있었다

### 문제

초기 `MessageGenerationService`는 한 클래스에서 다음 책임을 모두 수행했다.

- DB 템플릿 조회
- DB 보강 상태 조회
- 예습/주간 성취도 문구 결정
- 테스트 결과 문구 생성
- 템플릿 치환
- 빈 줄 정리
- DB 오류 시 대체 처리

따라서 메시지 한 문장을 검증하려 해도 실제 DAO 객체가 생성되고 DB 접근 가능성을 고려해야 했다. 메시지 정책 변경과 인프라 장애 대응도 같은 메서드 안에 섞여 있었다.

### 해결

순수 비즈니스 계산을 `LearningMessageComposer`와 `MakeupGuidancePolicy`로 분리했다.

```java
String result = composer.compose(
    template,
    row,
    new MessageSections(true, true, true),
    MakeupStatus.REQUESTED
);
```

DB가 필요한 값은 `TemplateProvider`, `MakeupStatusProvider` 포트를 통해 받아오고, 기본 생성자는 기존 DAO를 연결하여 화면 호환성을 유지했다.

```java
public MessageGenerationService(
        TemplateProvider templateProvider,
        MakeupStatusProvider makeupStatusProvider,
        LearningMessageComposer composer) {
    this.templateProvider = templateProvider;
    this.makeupStatusProvider = makeupStatusProvider;
    this.composer = composer;
}
```

### 선택 근거

메시지 조합은 파일·DB·SMTP와 무관한 결정적 계산이다. 이 로직을 순수 객체로 만들면 다음 이점이 있다.

- Oracle 없이 밀리초 단위의 단위 테스트가 가능하다.
- 템플릿 저장 위치가 DB에서 API로 바뀌어도 메시지 정책은 변경하지 않는다.
- 테스트에서 포트를 가짜 구현으로 교체할 수 있다.
- 업무 문구와 장애 대체 전략의 변경 이유를 분리할 수 있다.

Spring 같은 DI 프레임워크를 추가하지 않고 생성자 주입을 선택했다. 현재 애플리케이션은 단일 JVM의 작은 Swing 프로그램이므로 프레임워크 도입 비용보다 Java 생성자만으로 명시적인 의존 관계를 유지하는 편이 합리적이다.

### 코드 증거

- `src/main/java/com/academy/message/domain/LearningMessageComposer.java`
- `src/main/java/com/academy/message/domain/MakeupGuidancePolicy.java`
- `src/main/java/com/academy/message/port/TemplateProvider.java`
- `src/main/java/com/academy/message/port/MakeupStatusProvider.java`
- `src/main/java/com/academy/message/service/MessageGenerationService.java`
- `src/test/java/com/academy/message/domain/LearningMessageComposerTest.java`

### 검증

DB 없이 다음 결과를 자동 검증했다.

- 선택된 항목만 메시지에 포함된다.
- 값이 없는 주간 과제 영역은 남지 않는다.
- 결석 및 보강 신청 상태에 예정 안내가 생성된다.
- 출석 학생에게 보강 문구가 생성되지 않는다.

---

## 5. 문제 3 — DAO가 연결 구현을 직접 생성했다

### 문제

초기 DAO는 모두 다음 형태로 `DBConnection`을 직접 생성했다.

```java
private final DBConnection dbConnection = new DBConnection();
```

이 방식은 DAO와 연결 생성 정책을 강하게 결합한다. 테스트용 연결, 트랜잭션 범위 공유, 다른 데이터베이스 또는 커넥션 풀로 전환하려면 DAO 내부를 수정해야 한다.

### 해결

최소 계약인 `ConnectionProvider`를 만들고 모든 DAO가 생성자로 이를 받게 했다.

```java
@FunctionalInterface
public interface ConnectionProvider {
    Connection getConnection() throws SQLException;
}
```

```java
public AcademyImportDAO() {
    this(new DBConnection());
}

public AcademyImportDAO(ConnectionProvider connectionProvider) {
    this.connectionProvider = connectionProvider;
}
```

### 선택 근거

Repository 전체를 새로 설계하면 SQL과 화면 호출부를 동시에 크게 바꾸게 된다. Backend Architecture Refactoring에서는 현재 JDBC DAO를 유지하면서 가장 변화 가능성이 높은 **연결 생성 책임**부터 포트로 분리했다.

이 선택은 완성형 아키텍처를 한 번에 강요하기보다, 실제 위험을 낮추면서 이후 통합 테스트와 커넥션 풀 도입을 가능하게 만드는 단계적 개선이다.

### 코드 증거

- `src/main/java/com/academy/message/port/ConnectionProvider.java`
- `src/main/java/com/academy/message/dao/AcademyImportDAO.java`
- `src/main/java/com/academy/message/dao/EnrollmentDAO.java`
- `src/main/java/com/academy/message/dao/MakeupDAO.java`
- `src/main/java/com/academy/message/dao/SendLogDAO.java`
- `src/main/java/com/academy/message/dao/TemplateDAO.java`

---

## 6. 문제 4 — 파일 입력과 비즈니스 검증의 사용 절차가 UI에 노출되어 있었다

### 문제

초기 화면은 파일을 읽은 뒤 별도로 검증 서비스를 호출했다.

```java
importedRows = importService.importFile(file);
List<String> errors = validationService.validate(importedRows);
```

화면 또는 다른 진입점이 검증 호출을 빠뜨리면 유효하지 않은 데이터가 다음 단계로 전달될 수 있다. 또한 “파일을 불러와 검증 결과를 보여준다”는 하나의 사용자 행동이 코드에서는 두 개의 개별 기술 호출로 표현됐다.

### 해결

`AcademyDataImportService.loadAndValidate()` 유스케이스와 불변 결과 타입 `ImportBatch`를 만들었다.

```java
ImportBatch batch = academyDataImportService.loadAndValidate(file);
importedRows = batch.rows();
List<String> errors = batch.validationErrors();
```

### 선택 근거

DB 반영까지 자동으로 묶지 않은 이유는 운영자가 미리보기와 오류를 확인한 후 명시적으로 승인해야 하기 때문이다. 즉, 자동화 속도보다 **사람의 승인 지점**을 보존하는 것이 이 업무에 적합하다.

파일 읽기와 검증은 되돌리기 쉬운 읽기 작업이므로 하나로 묶고, DB 변경은 별도의 확인 단계로 유지했다. 이는 프로젝트 운영 원칙의 “되돌리기 어려운 데이터 변경에는 명시적 승인”을 코드 흐름에 반영한 것이다.

### 코드 증거

- `src/main/java/com/academy/message/service/AcademyDataImportService.java`
- `src/main/java/com/academy/message/service/ImportBatch.java`
- `src/main/java/com/academy/message/view/MainFrame.java`
- `src/test/java/com/academy/message/service/DataValidationServiceTest.java`

---

## 7. 문제 5 — 보강 상태를 임의로 변경할 수 있었다

### 문제

초기 코드는 전달받은 문자열로 곧바로 상태를 수정했다.

```java
UPDATE makeup_request SET status = ? WHERE makeup_id = ?
```

이 경우 완료된 보강이 다시 신청 상태로 돌아가거나, 두 운영자가 같은 데이터를 수정했을 때 마지막 저장이 앞선 변경을 덮어쓸 수 있다.

### 해결

도메인에서 허용 상태 전이를 정의하고, DAO는 현재 상태를 확인한 후 이전 상태까지 `WHERE` 조건에 포함한다.

```java
UPDATE makeup_request
SET status = ?
WHERE makeup_id = ? AND status = ?
```

수정 행이 1건이 아니면 다른 사용자의 변경 가능성을 알리는 오류를 발생시킨다.

### 선택 근거

현재 시스템은 별도 버전 컬럼이 없으므로 스키마 변경 없이 적용할 수 있는 낙관적 동시성 검사를 선택했다. 장기적으로 여러 필드를 동시에 수정한다면 `version` 컬럼을 추가하는 방식이 더 적합하지만, 상태 한 필드 변경에는 기존 상태 비교가 가장 작은 안전장치다.

### 코드 증거

- `src/main/java/com/academy/message/domain/MakeupStatus.java`
- `src/main/java/com/academy/message/dao/MakeupDAO.java`
- `src/test/java/com/academy/message/domain/MakeupGuidancePolicyTest.java`

---

## 8. 문제 6 — 실행 환경과 비밀정보 경계가 불명확했다

### 문제

초기 메일 자격증명 저장 위치에는 특정 드라이브와 개인 식별 문자열이 포함되어 있었다.

```java
Path.of("D:\\AcademyMessageManagerData", "user_mail_credentials.enc");
```

또한 DB 설정은 클래스패스의 `config.properties` 파일만 사용해 운영 환경에서 비밀값을 외부 주입하기 어려웠다.

### 해결

- 메일 데이터 위치는 `ACADEMY_DATA_DIR` 환경변수를 우선 사용한다.
- 환경변수가 없으면 사용자 홈의 `.academy-message-manager`를 사용한다.
- DB 연결 정보는 `ACADEMY_DB_URL`, `ACADEMY_DB_USERNAME`, `ACADEMY_DB_PASSWORD` 환경변수를 파일보다 우선한다.
- `config.properties.example`에는 값이 아닌 설정 방법만 기록한다.
- 메일 전송 전 수신 주소·제목·본문을 검증한다.

### 선택 근거

환경변수는 소스 저장소와 운영 비밀값을 분리하며, 로컬·CI·운영 환경에서 동일한 바이너리를 사용할 수 있게 한다. 동시에 기존 사용자를 위해 설정 파일 fallback을 유지했다.

메일 자격증명은 기존 AES-GCM 및 PBKDF2 암호화 방식을 유지했다. 검증된 보안 메커니즘을 이유 없이 다시 작성하는 것보다, 실제 문제였던 경로 결합을 제거하는 것이 이번 범위에서 더 안전하다고 판단했다.

### 코드 증거

- `src/main/java/com/academy/message/dao/DBConnection.java`
- `src/main/java/com/academy/message/service/MailCredentialStore.java`
- `src/main/java/com/academy/message/service/EmailSendService.java`
- `src/main/resources/config.properties.example`

---

## 9. 최종 아키텍처와 선택 이유

```text
[Swing UI]
     ↓ 사용자 행동 전달
[service / use case]
     ↓ 업무 흐름 조정
[domain]
     ↓ 순수한 상태·정책·메시지 계산
[port]
     ↓ 외부 기능의 최소 계약
[dao / mail / file adapter]
     ↓
[Oracle / SMTP / CSV·XLSX]
```

이 구조는 전면적인 클린 아키텍처 재작성보다 현재 시스템에 맞춘 점진적 구조다.

- `domain`: 변경 이유가 업무 정책일 때 수정한다.
- `service`: 사용자 작업 순서가 바뀔 때 수정한다.
- `port`: 외부 기술에 필요한 최소 계약을 정의한다.
- `dao`: Oracle SQL 또는 결과 매핑이 바뀔 때 수정한다.
- `view`: 사용자 입력과 결과 표시를 담당하며 새 업무 규칙을 두지 않는다.

Spring Boot로 전환하지 않은 이유는 이번 목표가 웹 서버 전환이 아니라 기존 Swing 제품의 백엔드 품질 개선이었기 때문이다. 프레임워크 교체 없이도 의존성 역전, 테스트 가능성, 설정 외부화를 먼저 확보하면 이후 웹/API 전환 시 재사용할 핵심 코드가 남는다.

---

## 10. 자동 검증 증거

실행 명령:

```powershell
mvn clean verify
```

검증 결과:

```text
Tests run: 10, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

검증한 범위:

- 수업 유형의 한글/영문 코드 변환
- 수강 상태별 보강 신청 자격
- 잘못된 성취도 거부
- 출석/결석 및 보강 상태별 안내 문구
- 보강 종료 상태의 전이 차단
- 메시지 선택 영역과 빈 영역 처리
- 입력 오류에 원본 행 번호 포함
- Maven 컴파일, 테스트 컴파일, JAR 패키징

테스트를 추가한 이유는 리팩토링이 “코드가 더 보기 좋아졌다”는 주장에 그치지 않고, 핵심 동작을 자동으로 재현할 수 있어야 하기 때문이다.

---

## 11. 의도적으로 남긴 한계

이번 결과가 모든 문제를 해결했다는 의미는 아니다. 다음 항목은 환경 또는 범위를 이유로 남겼다.

- 실제 Oracle 테스트 인스턴스가 없어 DAO 통합 테스트는 수행하지 않았다.
- 실제 Gmail 자격증명이 없어 SMTP 실발송 테스트는 수행하지 않았다.
- `ImportRow`는 아직 파일 입력 DTO와 도메인 모델 역할을 함께 수행한다.
- 일부 화면 이벤트에는 DB 조회와 발송 절차가 남아 있어 추가 application service 분리가 가능하다.
- 보강 동시성은 기존 상태 비교 방식이며 범용 버전 관리 컬럼은 없다.

이 한계를 문서화한 이유는 미검증 영역을 성공으로 포장하지 않고, 다음 개선의 우선순위를 명확하게 하기 위해서다.

---

## 12. 포트폴리오 요약 문구

> Java Swing과 Oracle로 구현된 학원 메시지 관리 시스템에서 문자열과 DAO에 분산된 수강·출결·보강·발송 규칙을 명시적 도메인 타입과 정책 객체로 재구성했습니다. 메시지 생성과 DB 조회를 포트로 분리하고 모든 DAO에 연결 제공자를 주입하여 테스트 및 인프라 교체 가능성을 확보했습니다. 또한 사용자 승인 전에는 DB를 변경하지 않는 유스케이스 경계, 환경변수 기반 비밀정보 관리, 보강 상태 전이 및 낙관적 동시성 검사를 적용했습니다. JUnit 테스트 10개와 `mvn clean verify`로 핵심 정책, 입력 검증, CSV 수식 주입 방어, 전체 패키징을 검증했습니다.

## 13. 면접 설명용 핵심 질문과 답변

### 왜 enum을 사용했는가?

상태 집합이 작고 닫혀 있으며 상태별 행동이 존재했기 때문이다. 문자열 오타를 컴파일 단계에서 막고, 허용 전이를 한 파일에서 확인할 수 있다.

### 왜 Spring을 도입하지 않았는가?

현재 목표는 웹 전환이 아니라 기존 애플리케이션의 백엔드 결합을 낮추는 것이었다. 생성자 주입만으로 필요한 의존성 역전을 달성할 수 있어 프레임워크 비용을 추가하지 않았다.

### 왜 DB 저장까지 하나의 import 유스케이스로 묶지 않았는가?

DB 반영은 되돌리기 어려운 작업이므로 운영자가 미리보기와 오류를 확인한 후 승인해야 한다. 읽기·검증과 쓰기 사이의 사람 승인 지점을 보존했다.

### 왜 Repository 전체를 새로 만들지 않고 ConnectionProvider부터 분리했는가?

화면과 SQL을 동시에 대규모로 변경하는 위험을 피하면서 테스트 연결과 커넥션 풀 전환 가능성을 먼저 확보하기 위해서다. 현재 규모에 맞는 점진적 개선을 선택했다.

### 무엇을 실제로 검증하지 못했는가?

Oracle 통합 동작과 Gmail 실발송은 외부 실행 환경 및 자격증명이 없어 검증하지 못했다. 대신 순수 도메인 규칙, 입력 검증, 전체 컴파일과 패키징은 자동화했다.
