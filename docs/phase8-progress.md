# Phase 8 진행 상황

| 항목 | 내용 |
|---|---|
| 현재 Stage | **Phase 8 완료 (2026-11-20)** — 사용자 브라우저 확인 1~8 완료 후 요청 3건 반영, 다음은 Phase 9. 보고서: `docs/phase8-parent-notification-workflow.md`(Phase 8), `docs/phase8-1-excel-upload.md`(Phase 8.1) |
| 완료(8) | 1 분석·설계, 2 Migration 008, 3 템플릿 엔진, 4 미리보기·초안, 5 검토·확정, 6 Mock Sender, 7 React, 8 회귀·보고 |
| 완료(8.1) | Migration 009, 엑셀 반 블록 파서, 업로드 미리보기·확정 API, 수업유형별 기본 템플릿 지정, `{성적요약}` "N/M", 가져오기 `session_no=1` 수정, 출결 화면 기본값, 업로드 화면·탭 정리, 회귀 |
| 정책 변경 | 2026-11-18: 조교가 내용 확정·모의 발송 직접 수행, "승인" → "내용 확정". 2026-11-19: 메시지 생성 경로를 엑셀 업로드로 통일(수동 생성은 '누락·예외 생성'), 출결 불일치 시 앱 값 유지·초안 미생성, 성적 문구에서 "점" 제거 |
| 수정 파일(8.1 백엔드) | `alembic/versions/009_phase81_lesson_upload.py`(신규), `app/db/models/tables.py`, `app/main.py`, `app/modules/lesson_upload/*`(신규), `app/modules/notifications/{schemas,service,engine}.py`, `app/modules/imports/confirm.py`, `app/modules/learningops/*`(전체 학생 API), `app/modules/academics/*`(학습 현황·칸 수정·오늘 수업 시작·권한), `tests/test_phase81_*.py`(신규 3), `tests/test_phase6a_learningops_integration.py`, `tests/test_phase7_academics_integration.py`(조교 권한 기대값), `tests/test_secure_import_integration.py`, `tests/test_postgres_integration.py`·`tests/test_phase7_schema_integrity.py`(head 009), `tests/test_phase8_*`(문구) |
| 수정 파일(8.1 프론트) | `features/notifications/{uploadApi.ts,UploadTab.tsx}`(신규), `NotificationsPage.tsx`, `ComposeTab.tsx`, `TemplatesTab.tsx`, `api.ts`, `features/classwork/{ProgressTab.tsx,scoreRules.ts}`(신규), `ClassworkPage.tsx`, `AttendanceTab.tsx`, `GradesTab.tsx`(평가 관리), `StudentRecordsDrawer.tsx`, `common.tsx`, `api.ts`, `features/learningops/{AllStudentsCard.tsx,StudentPicker.tsx,status.ts}`(신규), `LearningOpsPage.tsx`, `api.ts`, `features/auth/LoginPage.tsx`, `pages/NotFoundPage.tsx`, `layout/AppLayout.tsx`, `app/router.tsx`, 테스트 `ClassworkPage.test.tsx`·`NotificationsPage.test.tsx`·`LearningOpsPage.test.tsx` |
| 테스트(8.1 본 구현) | pytest **97 PASS / 0 skip**, Ruff PASS, `alembic check` 차이 없음, Java **48 PASS / 0 skip**, Vitest **39 PASS**(11 files), oxlint·tsc·build PASS — 테스트 DB head 009 |
| 추가 개선(8.1-1) | 2026-11-19: 로그인 후 첫 화면 `/notifications` 수정, `GET /api/students`(관리자) + '전체 학생'·'반별 학생' 탭, 수강 등록 학생 이름 검색 선택 — pytest **98 PASS**, Vitest **41 PASS** |
| 추가 개선(8.1-2) | 2026-11-19: 업로드 결과 초안 미생성 빨간 팝업, 수업·출결·성적 탭 재구성(출결 기본 · 학습 현황 · 수업 · 평가 관리), 칸 단위 출결·과제 등급·점수 수정 + 과제·성적 변경 확인 팝업 — pytest **100 PASS**, Vitest **45 PASS** |
| 정책 변경(2) | 2026-11-19: 조교에게 과제 등급·점수 기록·수정과 평가 등록·수정 허용 (`GRADE_WRITERS`·`ASSESSMENT_WRITERS` += ASSISTANT). 수업 등록·수정·취소는 관리자·선생님 유지 |
| 추가 개선(8.1-3) | 2026-11-19: 출결 탭 "오늘 수업 시작"(조교 포함, 멱등 생성) — pytest **102 PASS**, Vitest **46 PASS**, Java **48 PASS / 0 skip**(Docker 재기동 후), build PASS |
| 브라우저 확인 | 2026-11-20 사용자 직접 확인 1~8 완료(전체 학생·수강 등록, 반 배정, 오늘 수업 시작, 학습 현황 수정·확인 팝업, 평가 관리, 업로드 빨간 팝업, 검토·모의 발송) |
| 최종 반영(8.1-4) | 2026-11-20: ① 엑셀 신규 학생 학교 자동 배정(내신 대비 반 이름에서 추출, 정규반은 비움) ② 학습 현황 일 단위 표(학생·예습 과제·주간 과제·시험 종목별 열) ③ 메뉴 '학부모 안내' → '성적 안내'. 사용자 요청으로 브라우저 확인 없이 Phase 9 진행. 변경 영역 자동 테스트만 실행: pytest 업로드·파서 8 PASS, Vitest classwork 11 PASS, Ruff·tsc·oxlint PASS (전체 회귀 미실행) |
| 차단 사항 | 없음 |
| 다음 작업 | Phase 9 시작. Phase 9 첫 회귀 때 전체 pytest·Vitest·Java·build를 한 번 실행해 8.1-4 반영분까지 확인 권장 |
| Migration 승인 | 008·009 개발 DB **적용됨**. 009는 2026-11-19 승인 후 적용, 백업 `.dev-data\backups\academy_learningops_dev-pre009-20261119-022839.dump`, 사후 검증 통과. 8.1-1 ~ 8.1-4는 DB 변경 없음 |
