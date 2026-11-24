# 작업 기록 보관

개발 단계별 계획·진행·점검표와 Java 시절 문서를 보관한다. 작성 시점의 기록이라 현재 코드와 다를 수 있다.
현재 상태와 단계별 요약은 [Development History](../DEVELOPMENT_HISTORY.md)를 먼저 본다.

## phases/: 웹 전환 단계별 작업 기록

| 단계 | 주제 | 주요 문서 |
|---|---|---|
| 기준선 | FastAPI 전환 전 기능·테스트 기준선 | [fastapi-transition-baseline](phases/fastapi-transition-baseline.md) |
| Phase 1~4 | FastAPI 이전, 가져오기 미리보기, PostgreSQL 인프라, 안전한 가져오기 확정 | [1](phases/phase1-fastapi-migration.md) · [2](phases/phase2-import-preview-migration.md) · [3](phases/phase3-postgresql-infrastructure.md) · [4](phases/phase4-secure-import-migration.md) |
| Phase 5 | 직원 인증·권한(RBAC) | [phase5-auth-rbac-implementation](phases/phase5-auth-rbac-implementation.md) |
| Phase 6 | 학생·수강, 직원·담당 반, 이벤트·분석 설계 | [6a](phases/phase6a-student-enrollment-vertical-slice.md) · [6a 검증](phases/phase6a-verification-and-hardening.md) · [6b](phases/phase6b-staff-classroom-management.md) · [이벤트 설계](phases/phase6-event-architecture-design.md) · [분석 설계](phases/phase6-learning-analytics-design.md) |
| Phase 7 | 수업·출결·성적 | [기능](phases/phase7-lessons-attendance-grades.md) · [계획](phases/phase7-implementation-plan.md) · [진행](phases/phase7-progress.md) · [안정화](phases/phase7-1-stabilization.md) |
| Phase 8 | 학부모 안내 메시지, 주간 엑셀 업로드 | [메시지](phases/phase8-parent-notification-workflow.md) · [엑셀](phases/phase8-1-excel-upload.md) · [인계](phases/phase8-1-handoff.md) · [계획](phases/phase8-implementation-plan.md) · [진행](phases/phase8-progress.md) |
| Phase 9 | 메시지 처리 현황, UX 구조 개선 | [메시지 운영](phases/phase9-message-operations.md) · [9.5 평가](phases/phase9-5-assessment.md) · [9.5 UX](phases/phase9-5-ux-architecture-improvement.md) · [9.5 진행](phases/phase9-5-progress.md) · [9.6 계획](phases/phase9-6-ux-workflow-plan.md) · [9.6 보고](phases/phase9-6-ux-workflow-report.md) · [계획](phases/phase9-implementation-plan.md) · [진행](phases/phase9-progress.md) |
| Phase 10 | 출결·성적 분석 | [기능](phases/phase10-learning-analytics.md) · [계획](phases/phase10-implementation-plan.md) · [진행](phases/phase10-progress.md) · [10.5 진행](phases/phase10-5-progress.md) · [EXPLAIN 측정](phases/phase10-explain-measurement.txt) |
| Phase 11 | 일괄 검토, 업로드 시간대, 학생·반 관리, 분석·대시보드 | [일괄 검토](phases/phase11-batch-review.md) · [시간대](phases/phase11-upload-time-slots.md) · [학생·반](phases/phase11-class-student-management.md) · [분석·직원·대시보드](phases/phase11-analytics-staff-dashboard.md) |

수동 점검표: [9.5 UI](phases/phase9-5-manual-ui-checklist.md) · [10](phases/phase10-manual-test-checklist.md) · [11 업무 시나리오](phases/phase11-manual-scenario-checklist.md)

분석 지표 정의는 현재도 유효한 명세라서 [analytics/phase10-metric-definitions.md](../analytics/phase10-metric-definitions.md)에 따로 둔다.

## java-v1/: Java 데스크톱 시절 문서

| 문서 | 내용 |
|---|---|
| [BACKEND_REQUIREMENTS](java-v1/BACKEND_REQUIREMENTS.md) | Java 버전의 백엔드 업무 요구사항(보강 관리 포함) |
| [PORTFOLIO_BACKEND_REFACTORING_EVIDENCE](java-v1/PORTFOLIO_BACKEND_REFACTORING_EVIDENCE.md) | Refactoring 1(v1.1.0)의 문제와 코드 증거 |
| [IMPORT_CONFIRM](java-v1/IMPORT_CONFIRM.md) | 삭제된 구 가져오기 확정 API(`/api/imports/confirm`) |
