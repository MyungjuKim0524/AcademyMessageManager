# Phase 10.5-C-1 — 결과: 메시지 원본 정합성(H1) · 학생 목록 절단(M3)

작업일: 2026-11-20 · 근거 문서: `phase10_5_architecture_review.md`, `phase10_5_improvement_plan.md` · 범위 밖(수정 안 함): M4, B-2

## 0. 보고서와 현재 코드의 차이
- H1 위치: 보고서의 `notifications/service.py:594-600/619/424`는 Phase 10.5-B(M2 주석 추가) 이후 +2줄 이동(수정 전 `mock_send` 596, 재시도 검사 621, `check_source` 424). 진단 내용은 그대로 일치.
- M3: 보고서대로 프론트 `learningops/api.ts`의 `students()`가 limit 없이 호출(백엔드 기본 50). 백엔드 응답은 `items/limit/offset`(전체 건수 없음), 정렬은 `Student.id`(`learningops/repository.py:138-146`) — 보고서에 없던 사실로, 클라이언트 연속 조회가 안전한 근거.
- H1 원본 범위(보고서 보강): 원본 지문(`notifications/engine.py:185-191`)은 **출결·수신 주소·수업 상태는 항상**, 성적은 템플릿이 `{성적요약}`을 쓸 때만 포함 → 성적 변경은 성적을 보여 주는 메시지만 오래된 것으로 판정(의도된 동작, 테스트로 고정).

## 1. 원인과 수정 요약
### H1 확정 메시지가 원본 변경 후에도 첫 모의 발송됨
- **원인**: 원본 변경 검사가 재시도 경로에만 있었고, 상세 응답은 DRAFT·검토 대기에서만 `source_changed`를 계산 → 확정 후에는 경고도 차단도 없었음.
- **수정**:
  - `NotificationService._reject_changed_source(row, action)` 신설 — 기존 `source_changed()`를 그대로 사용하는 **단일 검사**. `mock_send`(첫 발송)와 `retry_mock_send`(재시도)가 같은 함수를 호출. 실패 시 409 `SOURCE_CHANGED`(기존 오류 코드, 재시도 문구는 기존과 동일).
  - 검사 위치: 메시지 행 잠금(`FOR UPDATE`) + 멱등 키 재요청 판정 + 상태 확인 **뒤**, 시도 행·상태 변경 **앞** → 거부 시 발송 시도·상태·감사 기록이 남지 않음(롤백). 같은 키 재요청은 기존처럼 저장된 결과를 반환(멱등성 유지).
  - 상세 응답: `check_source`를 `EDITABLE | SENDABLE`(DRAFT·검토 대기·확정·발송 실패)로 확장 — 경고 대상 상태 = 진행을 거부하는 상태.
  - 화면(`ReviewTab.tsx`): 확정·실패 상태에서 원본 변경 시 "확정 후 … 모의 발송할 수 없으니 취소하고 다시 생성" 경고, '모의 발송'·'모의 발송 재시도' 버튼 비활성. 초안·검토 대기의 기존 문구는 유지.
### M3 반별 학생 목록 50명 절단
- **원인**: `students()`가 limit을 보내지 않아 백엔드 기본 50건만 수신, 페이지 UI 없음.
- **수정**: 기존 계약(`limit≤100`, `offset`)으로 **짧은 페이지가 올 때까지 이어 받기**. limit을 키워 숨기지 않음. 중복(조회 중 수강 추가로 행이 밀린 경우)은 `enrollment_id`로 1회만 유지, 어느 페이지든 실패하면 전체 실패(부분 목록을 조용히 보여 주지 않음), 100페이지(1만 명) 안전 상한 초과 시 `STUDENT_LIST_TOO_LONG` 오류. 호출 화면(학생·반 관리 반별 목록, 성적 분석 학생 선택)은 변경 없음 — 기존 로딩·오류·빈 목록 처리 그대로.

## 2. 변경 파일과 주요 함수
| 파일 | 변경 |
|---|---|
| `backend/app/modules/notifications/service.py` | `SENDABLE` 상수, `_reject_changed_source()` 신설, `mock_send()`에 호출 추가, `retry_mock_send()` 중복 검사를 같은 함수로 대체, `_detail()`의 `check_source` 범위 |
| `frontend/src/features/notifications/ReviewTab.tsx` | 상태별 경고 문구, 발송·재시도 버튼 `disabled={detail.source_changed}` |
| `frontend/src/features/learningops/api.ts` | `students()` 페이지 연속 조회, `STUDENT_PAGE_SIZE` |
| 테스트 | 아래 4절 |
API·DB·다른 모듈·라우터 변경 없음.

## 3. 기존 코드 재사용
`source_changed()`(원본 지문 재계산), `_abort()`(롤백 후 오류), `_locked_for_send()`(행 잠금·멱등 판정), 기존 오류 코드 `SOURCE_CHANGED`, 기존 화면 경고 컴포넌트·버튼. 학생 목록은 기존 API 계약과 기존 `apiClient`, 기존 오류 타입(`ApiClientError`).

## 4. 추가·수정한 테스트
| 파일 | 테스트 | 시나리오(지시서 번호) |
|---|---|---|
| `backend/tests/test_phase8_notifications_integration.py` | `test_confirmed_message_is_not_sent_after_its_attendance_changed` | (2) 확정 후 출결 변경 → 409, (5) 시도 0·발송 감사 0·상태 APPROVED 유지, (6) 상세 `source_changed: true` |
| 〃 | `test_confirmed_message_is_not_sent_after_a_score_it_shows_changed` | (3) 성적 변경: `{성적요약}` 템플릿 메시지 409 / 출결만 쓰는 템플릿 메시지는 정상 발송(1), 같은 키 재요청은 원본 변경 후에도 `replayed` 반환(멱등성) |
| 〃 | `test_failed_message_shows_the_change_and_retry_stays_blocked` | (4) 재시도 차단 유지, 실패 상태 상세 경고, 시도 기록은 원래 실패 1건뿐 |
| 기존 `test_mock_send_is_idempotent_and_never_touches_the_network` | 변경 없음 | (1) 원본 그대로인 확정 메시지 정상 첫 발송 |
| `backend/tests/test_phase6a_learningops_integration.py` | `test_class_student_pages_cover_large_classes_without_gaps_or_overlap` | 실제 API·PostgreSQL에서 151명: 100/51/0 페이지, 경계 중복·누락 없음, id 순 정렬, 다른 반 403(권한 범위), 비관리자 응답에 연락처 없음, 기본 50·최대 100 계약 유지 |
| `frontend/src/features/learningops/api.test.ts`(신규) | 0·1·50·51·99·100·101·250명, 경계 중복 제거, 중간 페이지 실패 시 전체 실패 | M3 회귀 |
| `frontend/src/features/notifications/NotificationsPage.test.tsx` | 확정+원본 변경 경고·발송 버튼 비활성, 실패+원본 변경 재시도 비활성 | (6) 화면 |
**수정 전 코드로 실패 확인**: 백업한 수정 전 `notifications/service.py`로 잠시 바꿔 실행 → 신규 백엔드 3건 FAIL, 기존 11건 PASS; 수정본 복원 후 해시 동일 확인 → 14건 PASS.
기존 테스트 기대값 변경: 없음.

## 5. 실제 실행한 테스트 (2026-11-20)
| 명령 | 결과 |
|---|---|
| `ruff check app tests alembic scripts` | PASS |
| `pytest -m "not postgres"` | 39 PASS |
| `pytest -m postgres` 전체(격리 테스트 DB `academy_learningops_test`@127.0.0.1:55432, 컨테이너 라벨 `isolated-test`·`destructive-tests=allowed`·DB 이름·사용자 확인 후) | **74 PASS** (기존 70 + 신규 4). 통합 테스트 픽스처가 이 테스트 DB 테이블을 비우고 가상 데이터를 넣음(기존 테스트와 같은 방식). 개발 DB·볼륨·다른 컨테이너 접근 없음 |
| `tsc -b` | PASS (1차 실행에서 신규 테스트 파일 mock 타입 오류 1건 → 테스트 타입만 수정) |
| `oxlint src` | PASS |
| Vitest 전체 | **14 files / 95 PASS** (기존 83 + 신규 12: 학생 목록 10, 검토 화면 2) |
| `npm run build` | PASS (기존 500kB 청크 경고만) |
| Java(mvn) | 미실행 — Java·공유 API 변경 없음 |
| 브라우저 E2E | **미실행** — 자동화 도구 없음. 수동 확인: (a) 확정 메시지 원본 변경 시 경고·발송 버튼 비활성, (b) 51명 이상 반의 학생 목록 |

## 6. 남은 위험과 Phase 11 이관
- **원본 행 잠금 없음(Phase 11-3 검토)**: 원본 검사는 메시지 행 잠금 아래에서 하지만 출결·성적·연락처 행은 잠그지 않는다. 검사와 커밋 사이(수 ms)에 다른 요청이 원본을 커밋하면, 발송은 검사 시점 데이터와 일치하는 본문으로 성공하고 그 뒤 원본이 바뀐 상태가 된다(READ COMMITTED). 원본 조회가 LEFT JOIN이라 `FOR SHARE`를 그대로 붙일 수 없어 트랜잭션 구조 변경이 필요 → 임의 구현하지 않음. 현재는 모의 발송이며, 발송 후 원본 변경은 이력과 처리 현황에서 확인 가능.
- 학생 목록 연속 조회 중 수강 추가·종료가 동시에 일어나면 한 번의 조회 결과가 그 순간과 1명 차이 날 수 있음(중복은 제거, 누락은 새로고침으로 해소). 반 인원 규모에서 허용.
- 메시지 처리 현황 목록의 '모의 발송 대기' 행은 원본 변경 여부를 미리 표시하지 않음(조치 시 검토 화면에서 경고·차단). 필요 시 Phase 11 UX.

## 7. API·DB 스키마 호환성
- API: 경로·요청·응답 필드 변경 없음. `mock-send`가 원본 변경 시 기존 오류 코드 `SOURCE_CHANGED`(409)를 새로 반환할 수 있음(재시도·확정과 같은 계약). 상세의 `source_changed` 필드는 기존 필드 — 확정·실패 상태에서도 실제 값을 반환.
- 학생 목록: 기존 `limit/offset` 계약 그대로(기본 50·최대 100 테스트로 확인).
- DB: 스키마·Migration 변경 없음.
- 백업: `D:\Temp\…\scratchpad\backup-c1`(수정 전 프론트 소스·백엔드 테스트), 수정 전 서비스는 `backup-b3-m2`.
