# 작업 기록 보관

웹 전환 단계(Phase 1~11)별 기록과 Java 시절 문서를 보관한다.
- 여기 있는 단계는 **모두 완료된 작업**이다. 문서 안의 "다음 작업", "진행 중", "승인 대기" 같은 표현은 작성 시점의 상태다.
- 작성 시점의 기록이라 현재 코드와 다를 수 있다. 현재 상태는 [Development History](../DEVELOPMENT_HISTORY.md)와 [README](../../README.md)를 기준으로 본다.

## phases/: 웹 전환 단계별 기록

### 최종 보고서 (구현 내용·설계 근거·검증 결과)

| 단계 | 주제 | 문서 |
|---|---|---|
| 기준선 | FastAPI 전환 전 기능·테스트 기준선 | [fastapi-transition-baseline](phases/fastapi-transition-baseline.md) |
| Phase 1~4 | FastAPI 이전, 가져오기 미리보기, PostgreSQL 인프라, 안전한 가져오기 확정 | [1](phases/phase1-fastapi-migration.md) · [2](phases/phase2-import-preview-migration.md) · [3](phases/phase3-postgresql-infrastructure.md) · [4](phases/phase4-secure-import-migration.md) |
| Phase 5 | 직원 인증·권한(RBAC) | [phase5-auth-rbac-implementation](phases/phase5-auth-rbac-implementation.md) |
| Phase 6 | 학생·수강, 직원·담당 반, 이벤트·분석 설계(보류된 설계 포함) | [6a](phases/phase6a-student-enrollment-vertical-slice.md) · [6a 검증](phases/phase6a-verification-and-hardening.md) · [6b](phases/phase6b-staff-classroom-management.md) · [이벤트 설계](phases/phase6-event-architecture-design.md) · [분석 설계](phases/phase6-learning-analytics-design.md) |
| Phase 7 | 수업·출결·성적, 안정화 | [기능](phases/phase7-lessons-attendance-grades.md) · [7.1 안정화](phases/phase7-1-stabilization.md) |
| Phase 8 | 학부모 안내 메시지, 주간 엑셀 업로드 | [메시지](phases/phase8-parent-notification-workflow.md) · [8.1 엑셀](phases/phase8-1-excel-upload.md) |
| Phase 9 | 메시지 처리 현황, UX 구조 개선, 구 가져오기 제거 | [메시지 운영](phases/phase9-message-operations.md) · [9.5 UX](phases/phase9-5-ux-architecture-improvement.md) · [9.6 업무 동선](phases/phase9-6-ux-workflow-report.md) |
| Phase 10 | 출결·성적 분석(SQL 성능 측정 14절) | [phase10-learning-analytics](phases/phase10-learning-analytics.md) |
| Phase 11 | 일괄 검토, 업로드 시간대, 학생·반 관리, 분석·직원·대시보드 | [일괄 검토](phases/phase11-batch-review.md) · [시간대](phases/phase11-upload-time-slots.md) · [학생·반](phases/phase11-class-student-management.md) · [분석·직원·대시보드](phases/phase11-analytics-staff-dashboard.md) |

Phase 10.5 이후의 아키텍처·보안·정합성·성능·릴리스 검증 결과는 [reviews/](../reviews/)에 있다.

### 계획·진단·진행·인계 기록

단계를 시작할 때의 분석·계획과 진행 중 기록이다. 최종 보고서에 없는 내용(기존 구조 재사용 판단, 단계별 실행 테스트 수치, 사용자 정책 결정, Migration 백업 기록)이 있어 함께 보관한다.

| 단계 | 계획·진단 | 진행 | 기타 |
|---|---|---|---|
| Phase 7 | [구현 계획](phases/phase7-implementation-plan.md) | [진행](phases/phase7-progress.md) | |
| Phase 8 | [구현 계획](phases/phase8-implementation-plan.md) | [진행](phases/phase8-progress.md) | [8.1 작업 인계 프롬프트](phases/phase8-1-handoff.md)(AI 에이전트용, `reviews/phase10_5_improvement_plan.md`가 인용) |
| Phase 9 | [구현 계획](phases/phase9-implementation-plan.md) | [진행](phases/phase9-progress.md) | |
| Phase 9.5 | [개선 전 진단](phases/phase9-5-assessment.md) | [진행](phases/phase9-5-progress.md) | |
| Phase 9.6 | [분석·계획](phases/phase9-6-ux-workflow-plan.md) | (보고서에 포함) | |
| Phase 10 | [구현 계획](phases/phase10-implementation-plan.md) | [진행](phases/phase10-progress.md) | |
| Phase 10.5 | [개선 계획](../reviews/phase10_5_improvement_plan.md)(reviews) | [진행](phases/phase10-5-progress.md) | |

### 수동 점검표와 측정 원본

- 수동 점검표: [9.5 UI](phases/phase9-5-manual-ui-checklist.md) · [10](phases/phase10-manual-test-checklist.md) · [11 업무 시나리오](phases/phase11-manual-scenario-checklist.md)
- 측정 원본: [Phase 10 EXPLAIN ANALYZE 출력](phases/phase10-explain-measurement.txt)(최종 쿼리 기준. 최초 구현과의 비교표는 [phase10-learning-analytics 14절](phases/phase10-learning-analytics.md#14-성능-테스트-db-합성-데이터에서-실측-끝나면-rollback))

분석 지표 정의는 현재도 유효한 명세라서 [analytics/phase10-metric-definitions.md](../analytics/phase10-metric-definitions.md)에 따로 둔다.

## java-v1/: Java 데스크톱 시절 문서

| 문서 | 내용 |
|---|---|
| [BACKEND_REQUIREMENTS](java-v1/BACKEND_REQUIREMENTS.md) | Java 버전의 백엔드 업무 요구사항(보강 관리 포함) |
| [PORTFOLIO_BACKEND_REFACTORING_EVIDENCE](java-v1/PORTFOLIO_BACKEND_REFACTORING_EVIDENCE.md) | Refactoring 1(v1.1.0)의 문제와 코드 증거 |
| [IMPORT_CONFIRM](java-v1/IMPORT_CONFIRM.md) | 삭제된 구 가져오기 확정 API(`/api/imports/confirm`) |
