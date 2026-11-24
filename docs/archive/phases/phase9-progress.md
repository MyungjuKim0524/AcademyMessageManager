# Phase 9 진행 상황

| Stage | 상태 | 내용 |
|---|---|---|
| 1 기반 확인·설계 | 완료 (2026-11-20) | `docs/archive/phases/phase9-implementation-plan.md`. DB head 009 확인(개발·테스트). 결론: 안내 의무 계산형(Migration 없음), 기존 `mock-send` 계약 유지 + 재시도 전용 동작 |
| 2 안내 의무·누락 판정 | 완료 | `app/modules/message_operations/{repository,service}.py` — 진행된 수업 × 수업일 수강 대상(+출결 기록), 비대상 사유(취소·미진행·휴원/대상 아님), 미생성 참고 사유(보호자 이메일 없음·출결 미입력) |
| 3 현황·집계 API | 완료 | `GET /api/message-operations/{summary, classrooms/{id}, obligations, obligations/{lesson_id}/{enrollment_id}}`, 의무당 1상태·합계 일치·완료율(대상 0건 = null) |
| 4 미처리·실패 탐지 | 완료 | 상태 MISSING/IN_REVIEW/READY_TO_SEND/FAILED/DONE/EXEMPT, 실패 원인(저장된 error_code 기준), 다음 조치. 처리 기한: 정책 미설정 → 비활성 |
| 5 수동 재시도 | 완료 | `POST /api/notifications/{id}/retry-mock-send` (Idempotency-Key, CSRF). 실패 건만, 원본 변경 시 거부, 행 잠금 직렬화, 새 시도 행(실패 이력 보존), 감사 `retry: true`. `MockSender` `mock-retry.invalid` 규칙 |
| 6 React 운영 화면 | 완료 | `features/message-operations/*`(신규), 메뉴 '메시지 운영', 성적 안내 화면 주소 파라미터 연결(`?classroom&tab&lesson&notification`), 검토 창 '모의 발송 재시도' |
| 7 통합 테스트·보고 | 조건부 완료 | 자동 검증 전부 PASS, Browser E2E **NOT RUN**(도구 없음, 수동 절차는 최종 보고서 17절). 보고서 `docs/archive/phases/phase9-message-operations.md` |

| 항목 | 내용 |
|---|---|
| 변경 파일(백엔드) | `app/modules/message_operations/*`(신규), `app/modules/notifications/{service,router,repository,sender}.py`, `app/main.py`, `tests/test_phase9_message_operations_integration.py`(신규 6) |
| 변경 파일(프론트) | `features/message-operations/{api.ts,MessageOperationsPage.tsx,MessageOperationsPage.test.tsx}`(신규), `features/notifications/{api.ts,NotificationsPage.tsx,ReviewTab.tsx,ComposeTab.tsx,NotificationsPage.test.tsx}`, `app/router.tsx`, `layout/AppLayout.tsx` |
| 테스트(최종) | Ruff PASS, `alembic check` 차이 없음, pytest **109 PASS / 0 skip**, Java **48 PASS / 0 skip**, Vitest **54 PASS**(12 files), tsc·oxlint·build PASS, Browser E2E NOT RUN |
| 차단 사항 | 없음 |
| DB Migration 승인 | 해당 없음(스키마 변경 없음). 개발 DB 009 그대로, 쓰기 없음(읽기 전용 확인) |
| 다음 작업 | 사용자 수동 브라우저 확인(선택) → Phase 9.5 |
