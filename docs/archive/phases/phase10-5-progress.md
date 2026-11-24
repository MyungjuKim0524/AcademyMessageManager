# Phase 10.5 진행 상황

계획: `docs/reviews/phase10_5_improvement_plan.md` · 리뷰: `docs/reviews/phase10_5_architecture_review.md`

| 작업 | 상태 | 내용 |
|---|---|---|
| B-3 엑셀 재업로드 변경값 안내 (H2, 사용자 결정 2026-11-20 "규칙 유지 + 미리보기 안내") | 완료 (2026-11-20) | 아래 |
| M2 보호자 이메일 상세 노출 (사용자 재확인 2026-11-20 "현행 유지") | 완료 | 코드 주석만 정책과 일치 |
| A-1 확정 메시지 원본 변경 시 발송 차단 (H1) | 완료 (C-1) | `docs/reviews/phase10_5_c1_results.md` |
| B-1 학생 목록 50명 절단 (M3) | 완료 (C-1) | 〃 |
| B-2 진행된 수업 규칙 단일화 | 완료 (C-2) | `docs/reviews/phase10_5_c2_results.md` |
| M4 레거시 메시지 미리보기 의존성 | 일부 정리 (C-2) — 엔진→레거시 의존 제거, 레거시 API·화면은 유지(Phase 11 제거 후보) | 〃 |

## B-3 변경 내용
- 저장 규칙은 그대로(엑셀이 점수·과제 등급의 출처, 출결은 앱 기록 우선).
- 점수 저장 규칙을 함수 하나(`planned_scores`)로 모아 미리보기와 확정이 같은 규칙을 쓰게 함(규칙 중복 없음).
- 미리보기 응답에 **필드 추가만**: 행별 `app_changes`(항목·앱 값·엑셀 값 — 엑셀 값이 있고 앱 값과 다른 점수·예습/주간 등급, 결석·인정결석 학생의 빈칸이 앱 점수를 미응시로 바꾸는 경우 포함), 반 블록별 `max_score_changes`.
- 만점을 이미 입력된 점수보다 낮게 바꾸는 머리글은 **미리보기에서 오류로 막음**(확정 불가, 사유 표시). 그 사이 다른 사용자가 점수를 넣어 DB가 거부하면 "동시에 저장" 대신 `MAX_SCORE_BELOW_EXISTING` 안내.
- 감사: `UPLOAD_ROW_APPLIED.details.changed`에 바뀐 항목의 이전→이후, `LESSON_UPLOAD_APPLIED.details.max_score_changes`에 만점 변경(앱 정정 감사와 같은 수준의 정보).
- 화면: 바뀌는 값이 있는 행은 '확인 필요'로 분류, 행에 "어휘: 앱 9 → 엑셀 8", 반 블록에 만점 변경 경고, 세부 줄과 확정 확인창에 건수.
- M2: `learningops/router.py`, `notifications/service.py` 주석을 2026-11-18 결정(목록 마스킹, 상세는 확정·발송 담당 직원에게 전체 주소)과 일치시킴. 동작 변경 없음.

## 변경 파일 (Git 없음 — 백업 `D:\Temp\…\scratchpad\backup-b3-m2`)
- 백엔드: `app/modules/lesson_upload/{service,schemas}.py`, `app/modules/learningops/router.py`(주석), `app/modules/notifications/service.py`(주석), `tests/test_phase81_lesson_upload_integration.py`(+1 테스트)
- 프론트: `src/features/notifications/{uploadApi.ts,UploadTab.tsx,NotificationsPage.test.tsx}`(+1 테스트)

## 테스트 (2026-11-20 실제 실행)
| 명령 | 결과 |
|---|---|
| ruff | PASS |
| pytest 단위 | 39 PASS |
| pytest PostgreSQL(격리 테스트 DB) | 70 PASS (신규 1: 앱 정정 → 재업로드 미리보기 `app_changes`·감사 이전→이후·결석 빈칸→미응시·만점 낮춤 차단·만점 올림 표시) |
| tsc · oxlint | PASS |
| Vitest notifications | 18 PASS (신규 1) |
| Vitest 전체 | 13 files / 83 PASS |
| build | PASS (기존 500kB 청크 경고만) |
| 브라우저 | NOT RUN (자동화 도구 없음) |

API 계약: 미리보기 응답에 선택 필드 2개 추가(기존 필드·확정 요청·DB 스키마 불변).
