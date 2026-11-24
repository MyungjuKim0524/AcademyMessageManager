# 트러블슈팅·기술 검증 기록 인덱스

## 1. 엔지니어링 검증 보고서

설계·보안·정합성·성능 문제를 찾고 고친 기록이다. 상세 내용과 수정 전후 결과는 각 보고서에 있다.

| 기술적 문제 | 관련 기술 | 상세 보고서 | 구현 및 검증 코드 |
|---|---|---|---|
| Java 메시지 생성·DB 접근의 책임 분리(v1.1.0) | 도메인 타입, Port 인터페이스, 생성자 DI | [리팩터링 증거 문제 1~4](../archive/java-v1/PORTFOLIO_BACKEND_REFACTORING_EVIDENCE.md#4-문제-2--메시지-생성-규칙이-db-조회와-결합되어-있었다) · [자동 검증](../archive/java-v1/PORTFOLIO_BACKEND_REFACTORING_EVIDENCE.md#10-자동-검증-증거)(CSV 수식 주입 방어 포함) · [02-backend-architecture-refactoring](../refactoring/02-backend-architecture-refactoring.md) | 태그 [`v1.1.0`](https://github.com/MyungjuKim0524/AcademyMessageManager/tree/v1.1.0)의 Java 코드(현재 브랜치에는 없음) |
| 확정 메시지가 원본(출결·성적) 변경 뒤에도 발송됨(H1) | 원본 해시, 발송 전 재검사 | [phase10_5_c1_results](../reviews/phase10_5_c1_results.md#h1-확정-메시지가-원본-변경-후에도-첫-모의-발송됨) | `backend/app/modules/notifications/service.py` |
| 발송 원본 검사와 출결·성적 저장의 경쟁 상태(INT-01 TOCTOU) 외 3건 | 트랜잭션, 행 잠금 순서, advisory lock, 동시성 회귀 테스트 | [phase11_3_integrity_audit](../reviews/phase11_3_integrity_audit.md) · [phase11_3_integrity_remediation](../reviews/phase11_3_integrity_remediation.md#9-재현-테스트와-수정-전후-비교)(신규 23건, 전체 회귀 204건) | `backend/app/modules/notifications/service.py`, `backend/app/modules/lesson_upload/service.py`, `backend/tests/test_phase113_concurrency_integration.py` |
| 반 단위 출결 분석 SQL이 느림 | CTE `MATERIALIZED`, EXPLAIN ANALYZE | [phase10-learning-analytics 14절](../archive/phases/phase10-learning-analytics.md#14-성능-테스트-db-합성-데이터에서-실측-끝나면-rollback)(369.8 → 45.9 ms) · [EXPLAIN 원본](../archive/phases/phase10-explain-measurement.txt) | `backend/app/modules/analytics/repository.py` |
| 일괄 처리 쿼리 증폭, DB 장애 시 500 응답 | 쿼리 수 측정, 예외 분류(503·409) | [phase11_4_a_performance_results](../reviews/phase11_4_a_performance_results.md#4-수정-전후-측정-결과동일-시드규모) | `backend/app/db/session.py`, `backend/app/main.py` |
| 동시 요청으로 로그인 시도 제한 우회 | 원자적 한도 예약, 프록시 뒤 클라이언트 식별 | [phase11_2_security_audit](../reviews/phase11_2_security_audit.md) · [phase11_2_b2_results](../reviews/phase11_2_b2_results.md) · [phase11_2_b2_followup_results](../reviews/phase11_2_b2_followup_results.md#1-검증-결과)(병렬 30건 중 429: 0 → 25) | `backend/app/modules/auth/service.py`, `backend/tests/test_phase112b2_login_integration.py` |
| 통합 테스트 실행기가 PowerShell 5.1에서 테스트 DB 검사를 건너뜀(Fail-open) | 테스트 DB 격리, 실행 전 정체 확인 | [phase11_0_test_guard_fix](../reviews/phase11_0_test_guard_fix.md) | `scripts/run-postgres-integration.ps1` |

그 밖의 점검: [보안 감사 SEC-01~11](../reviews/phase11_2_security_audit.md#9-발견-문제와-근거) · [실행 모드·계정 보안](../reviews/phase11_4_b_runtime_account_results.md) · [아키텍처 리뷰](../reviews/phase10_5_architecture_review.md) · [릴리스 준비도](../reviews/phase11_4_release_readiness.md) · 전체 목록은 [reviews/](../reviews/)

## 2. 개발 환경 장애 기록

개발 중 실제로 겪은 장애의 원인 분석과 해결 과정이다. 문서마다 현상 → 원인 → 조치 → 검증 순서로 적었다.

| 문서 | 날짜 | 현상 | 원인과 조치 |
|---|---|---|---|
| [Phase 5 인증 초기 화면 오류](phase5-auth-initial-load-incident.md) | 2026-11-12 | 앱을 처음 열면 로그인 전에 `GET /api/auth/me`가 500 `INTERNAL_ERROR` | DB 의존성이 세션 쿠키 검사보다 먼저 실행됨. 쿠키 검사를 앞으로 옮겨 401로 응답하고, DB 미설정은 503으로 분류. Vite 프록시가 Java 서버를 가리키던 실행 구성도 바로잡음 |
| [Docker Desktop 장애 원인 분석](DOCKER_TROUBLESHOOTING.md) | 2026-11-10 | Docker Desktop이 시작 직후 종료되어 PostgreSQL 컨테이너를 쓸 수 없음 | Inference manager용 Unix socket 자리에 손상된 Windows Reparse Point가 남아 있었음. 초기화·재설치 없이 해당 항목만 정리해 복구 |
| [Docker Desktop 안전 복구 보고서](docker-desktop-safe-recovery.md) | 2026-11-15 | 같은 유형의 시작 실패가 재발 | 원인 가설 5개 비교. 남은 socket을 격리하자 다른 socket에서 같은 오류가 나, 원인을 4.86.0의 비정상 종료 후 socket 미제거 결함으로 좁힘. 공식 배포본으로 업데이트해 복구하고 기존 컨테이너·볼륨·DB 데이터 보존을 검증 |

공통 원칙: 데이터를 지우는 조치(Factory Reset, 볼륨 삭제, WSL 등록 해제)는 하지 않았고, 비밀번호·토큰 같은 민감 정보는 조회하거나 출력하지 않았다.
