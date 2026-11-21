# Phase 9 — 메시지 운영 현황·누락 탐지·실패 관리·안전한 수동 재시도 최종 보고서

작성일: 2026-11-20 · 계획: `docs/phase9-implementation-plan.md` · 진행: `docs/phase9-progress.md`

## 1. 목표 및 구현 범위
안내 대상 확인 → 처리 상태 집계 → 미처리·실패 탐지 → 직원의 안전한 조치(수동 재시도) → 결과·이력 확인.
모든 발송·재시도는 기존 **Mock Sender**로만 수행(실제 SMS·이메일·외부 API 없음). 자동 재시도·스케줄러·워커 없음.
구현: 안내 의무 판정, 처리 현황 집계 API, 미처리·실패 탐지(상태·원인·다음 조치), 실패 건 수동 재시도 API, React '메시지 운영' 화면 및 성적 안내 화면 연결.

## 2. Phase 8 재사용 기능
`parent_notification`(수업×수강×템플릿, 복합 FK, 활성 부분 UNIQUE)·상태 머신, `notification_send_attempt`(시도 원장, 멱등 키 UNIQUE, 메시지당 성공 1건 부분 UNIQUE), `NotificationService`의 행 잠금·멱등 처리·감사 로그·`source_changed`, `MockSender`, `eligible_on`(수업일 기준 수강 자격), `can_access_classroom` RBAC, 세션·CSRF, 공통 오류 형식, React 레이아웃·상태 태그·멱등 키 생성기.
**변경하지 않은 것**: 초안 생성·미리보기·템플릿 렌더링·검토·확정·기존 `mock-send` 계약(실패 건에 호출 시 `NOT_APPROVED` 유지 — Phase 8 테스트 그대로 통과), Import, Java 계약.

## 3. 메시지 안내 의무 정의 (계산형, 신규 테이블 없음)
의무 1건 = **(진행된 수업 1회차, 그날 수강 학생 1명)**. 메시지 종류는 현재 '수업별 성적 안내' 1종이므로 템플릿과 무관.
- 진행된 수업: 취소 아님 · 수업일 ≤ 오늘 · (상태 '완료' 또는 출결 기록 1건 이상)
- 그 수업의 안내 대상: `eligible_on(수업일)`(등록일~종료일, 날짜가 있는 휴원 이력) **또는** 그 수업 출결 기록이 있는 학생 — Phase 8 초안 생성 명단과 같은 규칙
- 계산형 근거: 날짜 기준 판정이라 이후 휴원·퇴원이 생겨도 **과거 결과가 바뀌지 않음**(테스트로 확인), 의무 레코드 소급 생성(추정) 불필요, (lesson_id, enrollment_id)로 메시지와 정확히 연결, 중복 의무가 구조적으로 불가능.

## 4. 누락·미처리 판정 정책
| 상태 | 조건(가장 진행된 활성 메시지 기준) | 다음 조치 |
|---|---|---|
| 초안 미생성 `MISSING` | 취소 아닌 메시지 없음 (참고: 보호자 이메일 없음 / 출결 미입력) | 초안 생성 |
| 검토·확정 대기 `IN_REVIEW` | 초안·검토 대기 | 검토·확정 |
| 모의 발송 대기 `READY_TO_SEND` | 확정됨 | 모의 발송 |
| 모의 발송 실패 `FAILED` | 모의 발송 실패 | 원인 확인·재시도 |
| 모의 발송 완료 `DONE` | 모의 발송 성공(성공 기록 존재) | 이력 조회 |
| 안내 대상 아님 `EXEMPT` | 수업 취소 / 진행 기록 없음(지난 '예정'·출결 없음) / 휴원·수강 대상 아님 | 없음 |
메시지가 없다는 이유만으로 누락 처리하지 않음: 비대상은 사유와 함께 별도 집계(`exempt`). 같은 (수업, 학생)에 템플릿별 메시지가 여럿이면 가장 진행된 1건으로 판정(성공 > 실패 > 확정 > 검토 대기 > 초안), 취소된 메시지는 의무를 충족하지 않음.

## 5. 처리 기한 정책
학원 정책 미확정 → **지연 판정 비활성**(`deadline_policy: "NOT_CONFIGURED"`, `overdue: null`, 화면에 "처리 기한 정책: 미설정"). 기한 초과는 처리 상태와 별도 속성으로 자리만 마련 — 정책 확정 시 추가(Phase 9.5 이후).

## 6. DB 스키마 및 Migration
**스키마 변경 없음** — 신규 Migration 없음(head `009_phase81_lesson_upload` 유지, `alembic check` 차이 없음). 필요한 인덱스는 기존 것 사용(`idx_parent_notification_lesson`, `uq_lesson_result`, `idx_notification_send_attempt_notification`).
코드만 변경: `MockSender`에 시연용 규칙 `mock-retry.invalid`(그 메시지의 **첫 시도만** `MOCK_TEMPORARY_FAILURE`, 이후 성공) 추가 — 실패→재시도 성공 흐름을 외부 발송 없이 재현. 기존 `mock-fail.invalid`(항상 거부) 유지.

## 7. 신규·변경 API
| 메서드 | 경로 | 권한 |
|---|---|---|
| GET | `/api/message-operations/summary?date_from&date_to` | 로그인 직원 — 볼 수 있는 반만 집계 |
| GET | `/api/message-operations/classrooms/{classroom_id}?date_from&date_to` | 반 접근 필요(403) |
| GET | `/api/message-operations/obligations?classroom_id&date_from&date_to&status&limit&offset` | 반 접근 필요, `total` 포함, `status=EXEMPT`로 비대상 조회 |
| GET | `/api/message-operations/obligations/{lesson_id}/{enrollment_id}` | 반 접근 필요, 판정 근거·메시지 전체(취소 포함)·시도 이력·재시도 가능 여부 |
| POST | `/api/notifications/{id}/retry-mock-send` (`Idempotency-Key`, CSRF) | 발송 권한(관리자·선생님·조교) + 반 접근 |
기간: 필수, 최대 93일(`DATE_RANGE_TOO_LONG`), 시작 ≤ 종료(`INVALID_DATE_RANGE`). 미래 수업은 의무가 아님.
별도 재시도 엔드포인트를 둔 이유: 기존 `mock-send` 계약(실패 건 거부)을 깨지 않고, 재시도에만 필요한 사전 검증(실패 건만·원본 변경 거부)을 명시적으로 적용하기 위함. 내부 발송 로직(잠금·멱등·원장·감사)은 공유.

## 8. 권한과 개인정보 보호
- 조회: 관리자 전체, 선생님·조교는 **유효 배정 반만**(summary는 다른 반을 집계하지 않음). 재시도: 기존 발송 권한 + 반 접근.
- 배정 해제 즉시 403, 비활성 계정은 세션 무효로 401, CSRF 없는 재시도 403, 로그인 없으면 401.
- IDOR/BOLA: 의무 상세는 수업의 반 접근을 먼저 검사(403) 후, 다른 반 수강 조합은 404(존재 노출 없음). 재시도는 메시지의 반 접근 재검사.
- 운영 API 응답에 보호자 이메일 없음(학생 이름·수업 정보만). 실패 사유는 저장된 안전 문구(주소·내부 오류 없음).

## 9. 실패 원인 분류
저장된 Mock Sender `error_code`만 사용(추정 금지): `MOCK_RECIPIENT_REJECTED` → 수신 대상 정보 오류, `MOCK_EMPTY_BODY` → 데이터 검증 실패, `MOCK_TEMPORARY_FAILURE` → 모의 발송기 일시 실패, 그 외 → 원인 불명. 상태·동시성 오류(`NOT_FAILED`, `ALREADY_MOCK_SENT`, `SOURCE_CHANGED`, `IDEMPOTENCY_KEY_REUSED`, `MOCK_SEND_CONFLICT`)는 요청 응답으로 안내.

## 10. 수동 재시도 정책
직원의 명시적 클릭(확인 창)으로만 실행. 사전 검증 순서: 권한·반 접근 → 메시지 행 잠금 → 같은 멱등 키면 저장된 결과 재반환(`replayed`)/다른 메시지에 쓴 키면 409 → 이미 성공이면 409 `ALREADY_MOCK_SENT` → 실패 상태가 아니면 409 `NOT_FAILED`(미확정·발송 대기 건은 기존 흐름 사용) → **원본 변경 시 409 `SOURCE_CHANGED`**(연락처·출결·성적 등이 바뀌었으면 확정된 본문을 다시 확정해야 하므로 취소 후 재생성) → 확정된 본문·수신 주소 그대로 모의 발송.

## 11. 상태 전이·이력 보존
`MOCK_FAILED → (재시도) → MOCK_SENT | MOCK_FAILED`. 시도마다 새 원장 행(이전 실패 행은 수정·삭제 없음), 본문·확정자·확정 시각 불변(테스트로 동일성 확인), 감사 `NOTIFICATION_MOCK_SEND`에 `from: MOCK_FAILED`, `retry: true`, `attempt_no`. 운영 상세에 메시지별 전체 시도 이력 표시.

## 12. 트랜잭션·멱등성·동시성
상태 변경·원장 행·감사 로그를 한 트랜잭션으로 커밋. 메시지 행 `FOR UPDATE` 잠금으로 동시 재시도를 직렬화 → 두 번째 요청은 성공 상태를 보고 409(테스트: 동시 2건 → [200, 409], 성공 행 1건). 멱등 키 UNIQUE + 메시지당 성공 부분 UNIQUE가 최종 방어선. 화면은 응답 전까지 같은 키를 재사용하고 버튼을 잠금(중복 클릭 방지).

## 13. React 운영 화면
메뉴 **'메시지 운영'**(`/message-operations`): 기간(기본 최근 14일) · 모의 발송 기준 안내 · 처리 기한 미설정 표시 → 현황 카드(안내 대상·미생성·검토 대기·발송 대기·실패·완료·완료율, 대상 0건은 "대상 없음") → 반별 표(안내 대상·완료·대기·실패·완료율·비대상, 행 클릭으로 반 선택) → 처리 목록(학생·수업일·상태 태그(아이콘+문구)·처리 시각·사유/참고·조치, 상태 필터, 50건 페이지).
조치 연결: 초안 생성 → 성적 안내 '누락·예외 생성'(수업 선택됨), 검토·확정/모의 발송/이력 → '검토·발송'(해당 메시지 열림), 실패 → **재시도**(확인 창). 성적 안내 검토 창의 실패 건에도 '모의 발송 재시도' 버튼(기존 "Phase 9에서 제공" 문구 대체).

## 14. PostgreSQL 조회·집계 방식
요청당 집합 쿼리 5개(수업, 수업×수강 명단+수업일 자격(`eligible_on(lesson.lesson_date)`)+출결 존재, 출결 있는 수업, 활성 메시지, 시도 원장) — 기간(≤93일)·접근 반으로 범위 제한, N+1 없음. 분류·합계는 애플리케이션에서 의무 단위로 1회 계산(의무당 1상태 → 합계 일치 보장). 별도 집계 테이블·캐시 없음. 규모가 커지면 SQL 조건부 집계로 이전 검토(Phase 9.5).

## 15. 테스트 명령과 실제 결과 (2026-11-20, 테스트 DB `academy_learningops_test`, head 009)
| 항목 | 명령 | 결과 |
|---|---|---|
| Ruff | `ruff check --no-cache app tests alembic scripts` | PASS |
| Alembic | `alembic current` / `alembic check` | 009 (head) / 차이 없음 |
| pytest 전체(PostgreSQL 통합 포함) | `pytest -q` (`ACADEMY_RUN_POSTGRES_INTEGRATION=1`) | **109 PASS / 0 fail / 0 error / 0 skip** |
| └ Phase 9 신규 | `tests/test_phase9_message_operations_integration.py` | 6 PASS (발송기 규칙 / 의무·비대상·과거 안정성·0건=null / 상태 합계·중복 없음·반별·스코프 / 재시도 성공·이력 보존·멱등·성공 건 차단·미확정 차단·키 재사용 / 원본 변경 거부·동시 재시도 / RBAC·IDOR·CSRF·배정 해제·비활성) |
| Java | `mvn -q -DrunPostgresIntegration=true test` | **48 PASS / 0 fail / 0 skip** |
| React 신규·관련 | `vitest run src/features/message-operations src/features/notifications` | 14 PASS (운영 화면 7, 성적 안내 7 — 재시도·연결 신규 1) |
| React 전체 | `npm test -- --run` | **54 PASS** (12 files) |
| TypeScript | `tsc -b` | PASS |
| Lint | `npx oxlint src` (프로젝트 lint 도구; ESLint는 미설치 — 신규 도입하지 않음) | PASS (경고 0) |
| Build | `npm run build` (`tsc -b && vite build`) | PASS (기존과 같은 500kB 초과 청크 경고만) |

## 16. 기존 기능 회귀 결과
pytest 전체 109(기존 103 + 신규 6), Java 48, Vitest 전체 54(기존 46 + 신규 8) — 기존 테스트 삭제·기대값 완화 없음. Phase 8 "실패 건 mock-send → NOT_APPROVED" 테스트를 포함해 그대로 통과.

## 17. Phase 9 Browser E2E 결과
**NOT RUN** — 이 작업 환경에는 브라우저 자동화 도구가 없음. 수동 검증 절차(관리자 비밀번호는 사용자가 직접 입력):
1. 서버 재기동(FastAPI 터미널 Ctrl+C 후 `.\scripts\start-fastapi.ps1`), 브라우저 Ctrl+F5.
2. 관리자 로그인 → **메시지 운영** → 기간 확인 → 반 선택 → 상태 '초안 미생성' 항목의 **초안 생성** → 성적 안내 '누락·예외 생성'(수업 선택됨)에서 초안 저장 → 검토·발송에서 **내용 확정** → **모의 발송** → 메시지 운영에서 새로고침, '완료'로 바뀌고 완료율이 오르는지.
3. 실패 시연: 학생·반 관리에서 가상 학생 보호자 이메일을 `가상@mock-retry.invalid`로 바꾸고 초안 생성·확정·모의 발송 → '모의 발송 실패(모의 발송기 일시 실패)' 확인 → 메시지 운영에서 **재시도** → '완료'로 바뀌는지, 검토 창 '모의 발송 시도'에 실패·성공 2줄이 모두 남는지.
4. 원본 변경 차단: `가상@mock-fail.invalid`로 실패시킨 뒤 이메일을 정상으로 고치고 재시도 → "원본이 바뀌어 재시도할 수 없습니다" 경고 확인.
5. 조교 계정: 담당 반만 보이는지, 재시도 가능 여부 확인.

## 18. 개발 DB Migration 적용 상태
신규 Migration 없음 → **승인·적용 대상 없음**. 개발 DB는 `009_phase81_lesson_upload` 그대로이며 이번 작업에서 쓰기 없음(읽기 전용 확인: 메시지 초안 1·모의 발송 성공 2, 시도 성공 2 — 작업 시작 때와 동일).

## 19. 미완료 기능과 제약
- 처리 기한(지연) 판정: 정책 미설정으로 비활성.
- 재시도는 1건씩(대량 재시도 없음), 자동 재시도 없음(요구사항).
- 목록의 '재시도' 버튼은 원본 변경 여부를 미리 표시하지 않음(목록 성능) — 서버가 거부하고 경고로 안내, 의무 상세 API는 `retry_blocked_reason` 제공.
- 메시지 종류 1종 전제(종류가 늘면 의무 키에 종류 추가 필요).
- Browser E2E 미실행(17절).

## 20. Phase 9.5 인계 사항
처리 기한 정책 설정 UI·지연 판정, 메인 대시보드·사이드바 재구성 시 '메시지 운영' 배치(현재 메뉴 1개 추가), 운영 화면 디자인 정비(현재 기능 중심 antd 카드·표), 메시지 종류 다중화 시 의무 모델 확장, 데이터 증가 시 SQL 조건부 집계로 이전 검토, 성적 안내 화면의 주소 파라미터 연결을 라우터 상태로 정리.

## 21. 최종 완료 판정
**조건부 완료** — 기능 구현 및 자동 검증(Python·PostgreSQL·Java·React·Build) 완료. 미완료: Phase 9 Browser E2E(도구 부재로 NOT RUN, 수동 절차 제공). 처리 기한 판정은 정책 미설정으로 의도적 비활성.
