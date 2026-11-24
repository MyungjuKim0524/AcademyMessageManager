# 트러블슈팅 기록

개발 중 실제로 겪은 장애의 원인 분석과 해결 과정이다. 문서마다 현상 → 원인 → 조치 → 검증 순서로 적었다.

| 문서 | 날짜 | 현상 | 원인과 조치 |
|---|---|---|---|
| [Phase 5 인증 초기 화면 오류](phase5-auth-initial-load-incident.md) | 2026-11-12 | 앱을 처음 열면 로그인 전에 `GET /api/auth/me`가 500 `INTERNAL_ERROR` | DB 의존성이 세션 쿠키 검사보다 먼저 실행됨. 쿠키 검사를 앞으로 옮겨 401로 응답하고, DB 미설정은 503으로 분류. Vite 프록시가 Java 서버를 가리키던 실행 구성도 바로잡음 |
| [Docker Desktop 장애 원인 분석](DOCKER_TROUBLESHOOTING.md) | 2026-11-10 | Docker Desktop이 시작 직후 종료되어 PostgreSQL 컨테이너를 쓸 수 없음 | Inference manager용 Unix socket 자리에 손상된 Windows Reparse Point가 남아 있었음. 초기화·재설치 없이 해당 항목만 정리해 복구 |
| [Docker Desktop 안전 복구 보고서](docker-desktop-safe-recovery.md) | 2026-11-15 | 위 장애의 복구 절차 | 원인 가설 5개 비교, 단계별 복구, 기존 컨테이너·볼륨·DB 데이터 보존 검증 |

공통 원칙: 데이터를 지우는 조치(Factory Reset, 볼륨 삭제, WSL 등록 해제)는 하지 않았고, 비밀번호·토큰 같은 민감 정보는 조회하거나 출력하지 않았다.

보안·정합성·성능 점검에서 찾은 결함과 수정 결과는 [reviews/](../reviews/)에 있다.
