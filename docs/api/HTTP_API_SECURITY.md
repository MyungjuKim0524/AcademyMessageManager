# Local HTTP API Security Model

## Scope

이 API는 React/Vue 개발 서버와 현재 Java 애플리케이션을 연결하는 localhost 전용 어댑터다. 실제 이메일 발송, 인증, 외부 네트워크 공개는 이번 범위에 포함하지 않는다.

## Protected assets

- 학생 식별 정보와 학습·출결 정보
- 생성된 학습 안내 메시지
- DB 및 SMTP credential
- 내부 SQL, 예외 및 로컬 파일 경로

## Trust boundaries and controls

| 위협 | 경계 | 적용 통제 |
|---|---|---|
| 외부 네트워크 노출 | 소켓 | `127.0.0.1` 고정 바인딩 |
| 임의 웹사이트의 API 호출 | 브라우저 Origin | 고정 CORS allowlist, 불일치 시 403 |
| 과도한 요청으로 인한 메모리 소비 | HTTP body | JSON 16KB, Import 파일 10MB 및 multipart 여유분 제한, 초과 시 413 |
| 악성 또는 비정상 스프레드시트 | Import parser | 확장자·MIME·시그니처 확인, 5,000행·64열·단일 시트·ZIP Bomb 제한 |
| 경로 조작 파일명 | multipart filename | 경로 구성요소를 제거하고 파일 시스템 경로로 사용하지 않음 |
| 잘못된 JSON 및 예상하지 못한 필드 | JSON 역직렬화 | 엄격한 Jackson 역직렬화, 400 |
| 비정상 업무 값 | DTO 경계 | 길이·날짜·enum·점수 관계 검증 |
| 내부 구현 정보 노출 | 오류 응답 | 안정적인 오류 코드와 일반화된 메시지 |
| 개인정보 로그 유출 | 운영 로그 | method, endpoint, status, duration, requestId, errorCode만 기록 |
| 캐시를 통한 메시지 잔존 | HTTP response | `Cache-Control: no-store` |
| MIME 추론 | HTTP response | `X-Content-Type-Options: nosniff` |
| SQL Injection | 계층 경계 | Handler에 SQL 없음, 기존 DAO의 PreparedStatement 유지 |
| 비밀값 Git 유입 | 저장소 | 환경변수 사용 및 secret 파일 `.gitignore` 제외 |

## Deliberately deferred

localhost MVP에서는 OAuth2, JWT, Redis, API Gateway, WAF 및 복잡한 Rate Limit을 도입하지 않는다. `ApiRoutes`의 공통 요청 래퍼가 이후 endpoint/IP/사용자 기준 제한을 추가할 확장 지점이다. 외부 공개 전에는 인증·인가, TLS, Rate Limit, 감사 정책과 개인정보 보존 정책을 별도로 설계해야 한다.

현재 multipart 처리는 Java `HttpServer`용 제한적 어댑터다. Spring Boot 전환 시 프레임워크의 검증된 multipart 처리기로 교체하되, 현재 파일 크기·개수·형식 정책과 회귀 테스트는 유지한다.

## Verification checklist

- [x] `127.0.0.1`에만 바인딩
- [x] wildcard 또는 Origin 반사 방식 CORS 미사용
- [x] 가상 테스트 데이터만 사용
- [x] 개인정보·메시지·credential 미로깅
- [x] DB/SMTP 비밀값 미하드코딩
- [x] `.env`, 로컬 설정, 키 파일 Git 제외
- [x] Handler에 동적 SQL 없음
- [x] 오류 응답에서 SQL·stack trace·로컬 경로 비노출
- [x] JSON 16KB 및 Import 파일 10MB 요청 제한
- [x] 4,999/5,000/5,001행, 63/64/65열 및 파일 크기 경계 테스트
- [x] HTTP Method 및 JSON Content-Type 검증
- [x] 길이·enum·점수 관계 검증
- [x] `Cache-Control: no-store`, `nosniff` 적용
- [x] Health 응답을 `{ "status": "UP" }`로 제한
- [x] 실제 이메일 발송 endpoint 미제공
