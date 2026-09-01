# Backend Architecture Refactoring: 백엔드 아키텍처 개선

이 문서는 전체 **Refactoring 1** 범위 중 백엔드 의존성과 기술 경계를 정리한 작업을 설명합니다.

## 구조

```text
Swing UI (기존 유지)
    ↓
service  ── 유스케이스 조정, 파일·메일 처리
    ↓
domain   ── 순수 비즈니스 타입과 정책
    ↓
port     ── DB 등 외부 구현의 인터페이스
    ↓
dao      ── Oracle JDBC 어댑터
```

## 적용한 원칙

- 도메인 정책은 DB 없이 단위 테스트할 수 있게 분리했다.
- 서비스는 `TemplateProvider`, `MakeupStatusProvider`에 의존하며 DAO 구현을 생성자에서 교체할 수 있다.
- 모든 DAO는 `ConnectionProvider`를 주입받아 연결 생성과 SQL 책임을 분리했다.
- `AcademyDataImportService`가 파일 읽기와 검증을 하나의 유스케이스로 표현한다.
- DB 설정은 파일보다 환경변수를 우선한다.
- 개인 PC의 고정 경로를 제거하고 `ACADEMY_DATA_DIR` 또는 사용자 데이터 폴더를 사용한다.
- 메일 주소·제목·본문을 전송 전에 검증한다.
- 보강 상태 변경 시 현재 상태와 허용 전이를 확인하고 동시 변경을 감지한다.

## 의존 방향 규칙

- `domain`은 DAO, Swing, Jakarta Mail, Apache POI를 참조하지 않는다.
- `service`는 도메인 정책을 조합하고 외부 구현은 port를 통해 사용한다.
- `dao`는 SQL과 결과 매핑만 담당한다.
- UI에서 새 비즈니스 규칙을 추가하지 않는다.

## 다음 수직 기능에서 권장할 작업

1. 화면의 DB 반영·메일 발송 절차도 application use case로 이동한다.
2. Oracle Testcontainers 또는 전용 테스트 스키마로 DAO 통합 테스트를 추가한다.
3. `ImportRow`를 파일 입력 DTO와 도메인 모델로 분리한다.
4. 운영 메일은 SMTP 직접 연결 대신 재시도·속도 제한을 제공하는 발송 어댑터를 검토한다.
