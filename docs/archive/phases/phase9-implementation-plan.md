# Phase 9 구현 계획 — 메시지 운영 현황·누락 탐지·실패 관리·안전한 수동 재시도

작성일: 2026-11-20 · 진행: `docs/archive/phases/phase9-progress.md` · 최종 보고: `docs/archive/phases/phase9-message-operations.md`
출발점: Phase 8/8.1 완료(브라우저 확인 포함). DB head `009_phase81_lesson_upload`(개발·테스트 DB 모두, 2026-11-20 읽기 전용 확인).

## 1. 기존 Phase 8 재사용 구조 (조사 결과)

| 질문 | 답 (근거 코드) |
|---|---|
| 메시지와 수업·학생 관계 | `parent_notification(lesson_id, enrollment_id, classroom_id, template_id)` — 복합 FK로 같은 반의 수업·수강만 허용. 활성 메시지 부분 UNIQUE `(lesson, enrollment, template) WHERE status<>'CANCELLED'` (`tables.py`) |
| 모의 발송 성공·실패 구분 | 메시지 `status`: `APPROVED → MOCK_SENT | MOCK_FAILED`. 시도 원장 `notification_send_attempt.result`: `MOCK_SUCCESS | MOCK_FAILURE`(+`error_code` 필수) |
| 메시지 상태만으로 현황 계산 가능? | **메시지가 있는 학생**은 가능(상태가 시도 결과와 같은 트랜잭션에서 갱신됨). **메시지가 없는 학생**은 별도 판정 필요 → 안내 의무 모델(§3) |
| 복수 발송 시도 저장 | 시도마다 1행(`idempotency_key` UNIQUE), 메시지당 성공 1건 부분 UNIQUE. 실패 행은 수정·삭제 경로 없음(RESTRICT) |
| 승인·발송 API를 재시도에 재사용? | `mock_send`는 `APPROVED`만 허용하고 Phase 8 테스트가 "`MOCK_FAILED`에 mock-send → `NOT_APPROVED`"를 계약으로 고정("retry is Phase 9"). → **기존 계약 유지 + 재시도 전용 동작 추가**, 발송 내부 로직(잠금·멱등·원장·감사)은 공유 |
| RBAC 적용 | `can_access_classroom`(관리자 전체, 그 외 유효 배정 반만) + 세션·CSRF 의존성 그대로 |
| 화면 연결 | 성적 안내(`/notifications`)의 '누락·예외 생성'·'검토·발송' 탭으로 이동(반·수업·메시지 지정) |

재사용: `eligible_on`(수업일 기준 수강 자격, 휴원 이력·퇴원일 반영), `NotificationService`의 잠금·멱등·감사·`source_changed`, `MockSender`, `mask_email`, 공통 오류 형식, React 레이아웃·`StatusTag`·`newRequestKey`.

## 2. 신규 구현 기능
1. 안내 의무 판정(계산형) + 비대상 사유
2. 운영 현황 집계(전체·반별) 및 학생·수업별 상세 목록, 의무 1건 상세
3. 상태 분류·실패 원인 분류·다음 조치 판정
4. 모의 발송 실패 건 수동 재시도 `POST /api/notifications/{id}/retry-mock-send`
5. React '메시지 운영' 화면(현황 카드·반별 표·처리 목록·재시도·성적 안내 화면 연결)

## 3. 메시지 안내 의무 모델 — **계산형(신규 테이블 없음)**

**의무 1건 = (수업 1회차, 수강 1건)**. 메시지 종류는 현재 "수업별 성적 안내" 1종(템플릿은 문구 선택일 뿐) → 의무는 템플릿과 무관하게 (수업, 수강)당 1건.

판정 (수업일 = `lesson.lesson_date`):
- **진행된 수업**만: `status <> 'CANCELLED'` AND `lesson_date <= 오늘` AND (`status = 'COMPLETED'` OR 출결 기록 1건 이상)
- 그 수업의 **안내 대상 학생**: 같은 반 수강 중 `eligible_on(수업일)` (휴원 기간·퇴원일·등록일 반영) **또는** 그 수업 출결 기록이 있는 학생 — Phase 8 초안 생성 명단과 동일 규칙

비대상(의무 없음, 사유와 함께 별도 표시 — 수강 기간(등록일~종료일) 안의 학생만):
| 사유 | 조건 |
|---|---|
| `LESSON_CANCELLED` 수업 취소 | 수업 상태 취소 |
| `LESSON_NOT_HELD` 진행 기록 없음 | 지난 '예정' 수업인데 출결이 하나도 없음 |
| `NOT_ELIGIBLE` 휴원·수강 대상 아님 | 수업일에 휴원 중, 종료일 없는 퇴원 등 `eligible_on` 거짓 + 출결 기록 없음 |

계산형을 택한 이유: (1) `eligible_on`이 날짜가 있는 휴원 이력·종료일로 판정하므로 **과거 시점 재현이 안정적**(현재 상태값이 아니라 기간 기준), (2) 의무 레코드를 과거에 소급 생성하는 추정이 필요 없음(§4.4), (3) 메시지와 (lesson_id, enrollment_id)로 정확히 연결, (4) 중복 의무가 구조적으로 불가능(키가 (수업, 수강) 쌍), (5) 조회 기간 제한(최대 93일)으로 집계량이 작음. **Migration 없음** → 개발 DB 승인 대상 없음. 필요한 인덱스(`idx_parent_notification_lesson`, `uq_lesson_result`, `idx_lesson_result_lesson`)는 이미 존재.

## 4. 상태 분류 정책

의무 1건은 **정확히 하나**의 처리 상태(활성 메시지 = 취소 아닌 메시지, 여러 개면 가장 진행된 것: 성공 > 실패 > 확정 > 검토 대기 > 초안):

| 처리 상태 | 조건 | 다음 조치 |
|---|---|---|
| `MISSING` 초안 미생성 | 활성 메시지 없음 | 초안 생성('누락·예외 생성'). 참고 사유: 보호자 이메일 없음 / 출결 미입력 |
| `IN_REVIEW` 검토·확정 대기 | `DRAFT`, `READY_FOR_REVIEW` | 검토·내용 확정 |
| `READY_TO_SEND` 모의 발송 대기 | `APPROVED` (성공 기록 없음) | 모의 발송 |
| `FAILED` 모의 발송 실패 | `MOCK_FAILED` | 원인 확인·수동 재시도(원본 변경 시 취소 후 재생성) |
| `DONE` 처리 완료 | `MOCK_SENT` (성공 기록 존재) | 이력 조회 |
| (비대상) `EXEMPT` | §3 비대상 | 조치 없음 |

완료율 = `DONE 수 / 유효 의무 수 × 100` (소수 첫째 자리). 유효 의무가 0건이면 **`null`("대상 없음")** — 0%로 표시하지 않음. 발송 시도 수가 아니라 의무 단위로 집계하므로 여러 시도·여러 메시지가 중복 집계되지 않음. 상태별 합계 = 유효 의무 수(테스트로 검증).

**처리 기한(지연)**: 학원 정책 미확정 → **비활성**(`deadline_policy: "NOT_CONFIGURED"`, 지연 판정 없음). 미처리 상태와 기한 초과는 별개 속성으로 남겨 두고 정책 확정 시 추가(Phase 9.5 이후).

실패 원인 분류(기존 `error_code` 재사용, 추정 금지): `MOCK_RECIPIENT_REJECTED` → 수신 대상 정보 오류, `MOCK_EMPTY_BODY` → 데이터 검증 실패, `MOCK_TEMPORARY_FAILURE`(신규, §9) → Mock Sender 일시 실패, 그 외 → 원인 불명. 화면에는 저장된 안전한 메시지(주소 없음)만 표시.

## 5. API

| 메서드 | 경로 | 내용 |
|---|---|---|
| GET | `/api/message-operations/summary?date_from&date_to` | 전체 합계 + 접근 가능한 반별 합계(대상·상태별·비대상·완료율) |
| GET | `/api/message-operations/classrooms/{classroom_id}?date_from&date_to` | 한 반 합계(권한 없으면 403) |
| GET | `/api/message-operations/obligations?classroom_id&date_from&date_to&status&limit&offset` | 학생·수업별 처리 목록(비대상은 `status=EXEMPT`로 조회), `total` 포함 |
| GET | `/api/message-operations/obligations/{lesson_id}/{enrollment_id}` | 의무 1건 상세: 판정 근거, 활성·취소 메시지 목록, 발송 시도 이력 |
| POST | `/api/notifications/{id}/retry-mock-send` (CSRF, `Idempotency-Key`) | 실패 건 수동 재시도(§9) |

기간: 필수, 최대 93일, `date_from <= date_to`. 의무 상세의 경로 키 `(lesson_id, enrollment_id)`는 계산형 의무의 자연 키.

## 6. 데이터 모델 및 Migration
- 스키마 변경 **없음**(신규 테이블·컬럼·인덱스 없음). 재시도는 기존 `notification_send_attempt`에 새 행 추가.
- `MockSender`에 시연용 결정적 규칙 1개 추가(코드만): 수신 도메인 `mock-retry.invalid`는 **그 메시지의 첫 시도만** `MOCK_TEMPORARY_FAILURE`로 실패, 이후 성공 — "실패 → 재시도 성공" 흐름을 외부 발송 없이 재현하기 위함. 기존 `mock-fail.invalid`(항상 실패) 유지.

## 7. React 화면
메뉴 **'메시지 운영'**(`/message-operations`, 모든 직원 — 서버가 담당 반으로 제한):
1. 기간(기본 최근 14일) + "모의 발송 기준 — 실제 전송 없음" + "처리 기한 정책 미설정" 안내
2. 현황 카드: 안내 대상·미생성·검토 대기·발송 대기·실패·완료·완료율
3. 반별 표(반·안내 대상·완료·대기·실패·완료율), 행 선택 → 4
4. 처리 목록(학생·수업일·상태 태그(아이콘+문구)·처리 시각·실패 사유/참고·조치), 상태 필터
5. 조치: 초안 생성/검토/모의 발송/이력 → 성적 안내 화면으로 이동(`?classroom=&tab=&lesson=&notification=`), 실패 → **재시도**(확인 → 멱등 키, 중복 클릭 방지)
성적 안내 화면: 주소 파라미터로 반·탭·수업·메시지를 열도록 최소 확장, 검토 창의 실패 건에 '모의 발송 재시도' 버튼(기존 "Phase 9에서 제공" 문구 대체).

## 8. 권한 및 보안
- 조회: 인증 + 반 접근(`can_access_classroom`) — 관리자 전체, 선생님·조교는 유효 배정 반만. 반을 지정하지 않는 summary는 접근 가능한 반만 집계(타 반 미포함).
- 재시도: 기존 발송 권한(`APPROVERS` = 관리자·선생님·조교, Phase 8 정책) + 반 접근 + CSRF. 배정 해제 즉시 403, 비활성 계정은 세션 무효(기존).
- IDOR/BOLA: 의무 상세·재시도 모두 대상 반 접근 재검사, 다른 반 수업·수강 조합은 404(존재 노출 없음).
- 개인정보: 목록·상세에 보호자 이메일 미포함(메시지 상세의 마스킹 규칙 유지), 실패 사유는 저장된 안전 문구만.

## 9. 동시성·멱등성 (수동 재시도)
사전 검증 순서: 반 접근·권한 → 메시지 행 잠금(`FOR UPDATE`) → 같은 멱등 키 재요청이면 저장된 결과 그대로 반환(`replayed`) / 다른 메시지에 쓴 키면 409 → `MOCK_SENT`면 409 `ALREADY_MOCK_SENT` → `MOCK_FAILED`가 아니면 409 `NOT_FAILED`(승인 전·발송 대기 건은 기존 모의 발송 사용) → 원본 변경(`source_changed`: 수업·출결·성적·연락처가 바뀜)이면 409 `SOURCE_CHANGED`(재확정 필요 → 취소 후 재생성) → 승인 본문·수신 주소 그대로 `MockSender` 호출 → 새 시도 행 + 상태 갱신 + 감사(`NOTIFICATION_MOCK_SEND`, `retry: true`)를 한 트랜잭션으로 커밋.
- 중복 클릭·동시 재시도: 행 잠금으로 직렬화 → 두 번째는 상태가 바뀐 것을 보고 409(성공 후) 또는 새 실패 행. 성공 부분 UNIQUE가 최후 방어선.
- 이전 실패 행은 수정·삭제하지 않음(새 행 추가만).

## 10. 테스트 계획
- PostgreSQL 통합(테스트 DB): 의무/비대상(휴원·등록 전·퇴원·취소·미진행), 상태 분류·합계 일치·완료율(0건=null), 여러 시도·여러 메시지 중복 없음, 재시도(정상·성공 건 차단·미확정 차단·원본 변경 차단·키 재사용·다른 메시지 키·동시 재시도·실패 이력 보존·실패→성공), 권한(관리자·담당 선생님·조교·미배정·배정 해제·비활성·타 반 IDOR·CSRF).
- Sender 단위 테스트. React(Vitest): 현황·반별·목록·필터·재시도·빈/오류 화면·화면 연결. tsc·oxlint·build.
- 회귀: pytest 전체, Java Maven, Vitest 전체.
- Browser E2E: 실행 환경에 브라우저 자동화 도구가 없으면 `NOT RUN` + 수동 절차.

## 11. 주요 위험
| 위험 | 대응 |
|---|---|
| '예정'으로 남은 지난 수업을 의무로 오판 | 진행 판정(완료 또는 출결 존재), 미진행은 비대상 사유로 노출 |
| 같은 (수업, 학생)에 템플릿별 메시지 여러 개 | 가장 진행된 1건으로 판정, 상세에서 전부 표시 |
| 정책 미확정 지연 판정 | 비활성으로 명시 |
| 재시도 시 바뀐 연락처로 보내야 하는 경우 | 원본 변경이면 재시도 거부 → 재생성(재확정) 유도 |
| 운영 시작 전 과거 수업이 대량 '미생성'으로 표시 | 조회 기간 필수·최대 93일, 기본 14일 |

## 12. Phase 9.5 연계
처리 기한 정책 설정, 메인 대시보드·사이드바 재구성 시 '메시지 운영' 위치 재배치, 메시지 종류 다중화 시 의무 모델에 종류 축 추가, 대량 재시도(현재 1건씩), 집계를 SQL 집계로 옮길지(데이터 규모 증가 시) 검토.
