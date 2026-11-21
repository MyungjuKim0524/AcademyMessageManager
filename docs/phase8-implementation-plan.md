# Phase 8 구현 계획 — 학부모 안내 메시지 생성·검토·승인·모의 발송

작성일: 2026-11-18 (Stage 1 산출물)

## 1. 선행 상태 확인 (설명이 아닌 실제 검증)

| 항목 | 확인 결과 |
|---|---|
| Phase 7.1 | `docs/phase7-1-stabilization.md` 판정 **완료**, Migration `007_phase71_sessions_pauses` 테스트 DB·개발 DB 모두 head |
| 기존 메시지 데이터(개발 DB) | `message_template` 0, `message_draft` 0, `delivery_job` 0 |
| Git | CLI 없음 — 사용자 지시대로 설치·초기화하지 않음 |

## 2. 기존 메시지 기능 분석

| 기능 | 위치 | 성격 | Phase 8 판단 |
|---|---|---|---|
| 메시지 미리보기 API | `POST /api/messages/preview`, `app/domain.py` | 요청값만으로 문장 생성(DB 미사용), Java와 계약 fixture 공유 | **변경하지 않음**(하위 호환). 문장 규칙(`_pre`, `_weekly`, 테스트·보강 문장)만 재사용 |
| 템플릿 치환 규칙 | Java `LearningMessageComposer`, Python `compose_message` | `{학생명}` 형식 한글 변수, 단순 문자열 치환, 빈 줄 정리 | **같은 `{변수}` 문법 채택**(직원에게 익숙, 규칙 일관) + 화이트리스트 검증 추가 |
| `message_template` | Java `TemplateDAO` 관리 | 수업 유형(REGULAR/EXAM_PREP)당 **1개만** 허용(UNIQUE) | 재사용 불가: 여러 템플릿·버전·활성 관리 불가, Java 화면이 덮어씀 |
| `message_draft` | Java `SendLogDAO` | `lesson_result_id NOT NULL` → **출결 기록이 있어야만** 생성 가능. 상태 DRAFT/READY/CANCELLED | 재사용 불가: 출결 미입력 학생 표현 불가, 승인·모의 발송 상태 없음 |
| `delivery_job`/`delivery_attempt` | Java `SendLogDAO`, `EmailSendService`(SMTP) | **실제 이메일 발송 로그**. Java 발송 이력 화면이 전 행을 SUCCESS/FAILED로 표시 | 재사용하면 **모의 발송이 Java 화면에서 실제 발송처럼 보임** → 사용 금지 |
| 학생·보호자 | `student.parent_name`, `student.parent_email` | 보호자 연락처 **1개**(이메일) | 수신자 = `parent_email` 단일. 없으면 생성 불가 |
| 수업·출결·성적 | Phase 7/7.1 `academics` 모듈 | 행 없음=미입력, EXCUSED, 휴원 기준일 판정(`eligible_on`), 교시 | 그대로 재사용 |
| 감사 로그 | `audit_log` | actor·event·target·request_id·JSON, 같은 트랜잭션 기록 | 재사용(상태 변경 이력) |
| 권한 | `can_access_classroom`, `require_csrf` | 오늘 유효한 배정 + 역할 일치 | 재사용 |

결론: Java 테이블은 건드리지 않고, Phase 8 전용 테이블 3개를 새로 만든다(Java와 무관한 이름).

## 3. 데이터 모델 (Migration `008_phase8_notifications`, 추가형)

### 3-1. `notification_template`
`id`, `name VARCHAR(100) UNIQUE`, `body TEXT (1~2000자, 공백만 불가)`, `is_active`, `version`(트리거로 증가),
`created_by_staff_user_id`(SET NULL), timestamps. 기본 템플릿 1개를 Migration에서 삽입(새 테이블 데이터만).

### 3-2. `parent_notification` (메시지 1건 = 학생 1명 × 수업 1회 × 템플릿 1개)
- 연결: `classroom_id`, `lesson_id`, `enrollment_id`(학생은 수강을 통해), `template_id`, `template_version`
- 복합 FK `(lesson_id, classroom_id) → lesson`, `(enrollment_id, classroom_id) → enrollment` → 다른 반 조합 불가(DB 보장)
- **스냅샷**: `body`(생성·수정된 확정 본문), `recipient_email`(생성 시점 보호자 이메일), `source_hash`(생성에 쓴 원천 데이터 지문)
- `status`: `DRAFT | READY_FOR_REVIEW | APPROVED | MOCK_SENT | MOCK_FAILED | CANCELLED`
- `created_by`, `updated_by`, `approved_by`, `approved_at`, `version`(낙관적 잠금), timestamps
- CHECK: 승인 이후 상태(APPROVED/MOCK_*)는 `approved_at` 필수
- 중복 방지: 부분 UNIQUE `(lesson_id, enrollment_id, template_id) WHERE status <> 'CANCELLED'`
- 인덱스: `(classroom_id, status)`, `(lesson_id)`

### 3-3. `notification_send_attempt`
`notification_id`(RESTRICT), `idempotency_key UUID UNIQUE`, `channel = 'MOCK'`(CHECK),
`result IN ('MOCK_SUCCESS','MOCK_FAILURE')`, `error_code`/`error_message`(실패 시 필수), `requested_by`, `attempted_at`.
부분 UNIQUE `(notification_id) WHERE result = 'MOCK_SUCCESS'` → **성공은 메시지당 최대 1회(DB 보장)**.

### 3-4. 변경 이력
상태 전이·본문 수정은 `audit_log`(`target_type = 'PARENT_NOTIFICATION'`)에 같은 트랜잭션으로 기록. 본문 원문은 감사 로그에 복제하지 않고
길이·변경 여부만 기록(개인정보 최소화). 발송 시도는 `notification_send_attempt`가 원장.

## 4. 템플릿 엔진

- 문법: `{변수명}` 단순 치환(기존 Java/Python 규칙). 표현식·속성 접근·함수 호출 없음.
- 검증: 화이트리스트 외 변수, 짝이 맞지 않는 중괄호, 빈 템플릿, 2000자 초과 → 저장 거부.
- 렌더링 후: 3줄 이상 빈 줄 정리(기존 규칙), 결과가 비거나 2000자 초과면 생성 불가.
- 출력은 평문. React가 텍스트로 렌더링(HTML 미해석).

| 변수 | 값 | 누락 시 |
|---|---|---|
| `{학생명}` `{분반명}` `{수업일자}` | 학생 이름, 반 이름, 수업일 | 항상 존재 |
| `{교시}` | "2교시" (1교시는 빈 값) | 빈 값 |
| `{시험회차}` | `exam_round` | 빈 값 |
| `{수업주제}` | `lesson.topic` | **생성 차단**(주제 미입력) |
| `{출결}` | 출석/지각/결석/인정결석 | **생성 차단**(출결 미입력 ≠ 결석) |
| `{보강메시지}` | 결석 시 기존 보강 문장, 그 외 빈 값 | 출결 미입력이면 **차단** |
| `{성적요약}` | 이 수업에 연결된 평가: "단원 평가 18/20점", 미응시는 "미응시" | 연결 평가 없음 → 빈 값 + 경고 / 결과 미입력 → **차단**(≠ 0점) |
| `{예습메시지}` `{주간메시지}` `{테스트메시지}` | 기존 Import 등급·정답 수(기존 문장 재사용) | 빈 값(기존 규칙) |

공통 차단: 취소된 수업, 수업일 기준 수강 대상 아님(휴원·기간 밖)이면서 출결 기록도 없음, 보호자 이메일 없음, 비활성 템플릿.
차단된 학생은 **저장되지 않고 사유가 표시**된다 → DB의 초안은 항상 필수 데이터가 갖춰진 상태.

## 5. 상태 머신

```
DRAFT ──submit──▶ READY_FOR_REVIEW ──approve──▶ APPROVED ──mock-send──▶ MOCK_SENT
  ▲  └──────────────approve───────────────────▶   │  └──(실패)──▶ MOCK_FAILED
  └───────────────revoke(승인 취소)────────────────┘
DRAFT / READY_FOR_REVIEW / APPROVED / MOCK_FAILED ──cancel──▶ CANCELLED
```
- 본문 수정은 DRAFT·READY_FOR_REVIEW에서만. 승인 후 수정하려면 **승인 취소 → DRAFT → 수정 → 재승인**.
- 승인 시 원천 데이터 지문을 다시 계산해 생성 이후 출결·성적·주제가 바뀌었으면 409 `SOURCE_CHANGED`(취소 후 재생성 안내).
- MOCK_SENT는 종결. MOCK_FAILED의 재시도는 Phase 9 범위(이번에는 취소만 허용).
- 모든 전이: `version` 일치 + 행 잠금(`FOR UPDATE`) + 서버 측 허용 전이 검사.

## 6. 권한

> **변경(2026-11-18, 사용자 결정)**: 실제 발송은 조교가 한다. 조교도 내용 확정(승인)·확정 취소·모의 발송·취소를 할 수 있다.
> 화면 용어는 "승인" 대신 "내용 확정". 아래 표는 초기 설계이며 최종 정책은 최종 보고서 §10을 따른다.

| 작업 | ADMIN | 배정 TEACHER | 배정 ASSISTANT |
|---|---|---|---|
| 템플릿 조회 | O | O(활성만) | O(활성만) |
| 템플릿 등록·수정·활성 관리 | O | X | X |
| 미리보기·초안 생성·본문 수정·검토 요청 | O | O | O |
| 승인·승인 취소 | O | O | **X** |
| 모의 발송 | O | O | **X** |
| 취소 | O | O | DRAFT·READY만 |

- ASSISTANT 승인 제한 근거: 최소 권한 원칙 + Phase 7의 성적 권한 정책(ASSISTANT는 기록 보조).
- TEACHER의 자기 초안 승인 허용: 소규모 학원 단일 승인 단계(다단계 결재 미도입). 승인자·시각은 기록.
- 모든 메시지 API는 메시지의 반을 기준으로 `can_access_classroom` 검사 → 배정 해제 즉시 차단, 비활성 직원 401.

## 7. API (신규 모듈 `app/modules/notifications`)

| Method | Path |
|---|---|
| GET | `/api/notification-templates`, `/api/notification-templates/variables` |
| POST/PATCH | `/api/notification-templates`, `/api/notification-templates/{id}` (ADMIN) |
| POST | `/api/notification-templates/validate` (본문 검증 + 가상 예시 렌더링, ADMIN) |
| POST | `/api/lessons/{lesson_id}/notifications/preview` (DB 쓰기 없음) |
| POST | `/api/lessons/{lesson_id}/notifications` (초안 일괄 저장) |
| GET | `/api/notifications?classroom_id=&lesson_id=&status=` |
| GET | `/api/notifications/{id}` (본문·상태·원천 변경 여부·발송 시도·이력) |
| PATCH | `/api/notifications/{id}` (본문 수정, `version`) |
| POST | `/api/notifications/{id}/submit` · `/approve` · `/revoke` · `/cancel` (`version`) |
| POST | `/api/notifications/{id}/mock-send` (헤더 `Idempotency-Key` 필수) |

일괄 요청 최대 100명. 일괄 저장: 차단 학생·이미 초안이 있는 학생은 사유와 함께 건너뛰고, 저장 가능한 학생은 한 트랜잭션으로 저장.
동시 요청으로 UNIQUE 충돌 시 전체 롤백 후 409(재요청하면 기존 초안을 건너뜀 → 멱등).

## 8. Mock Sender

- `MockSender.send(recipient) -> MockResult` 인터페이스(실제 네트워크 호출 없음).
- 결정적 실패 규칙: 수신 도메인이 `mock-fail.invalid`(RFC 2606 예약 도메인)이면 `MOCK_RECIPIENT_REJECTED` 실패. UI에 실패 조작 기능 없음.
- 처리: 메시지 행 `FOR UPDATE` → 같은 `Idempotency-Key` 시도가 있으면 **이전 결과 재반환** →
  APPROVED가 아니면 409(이미 성공이면 `ALREADY_MOCK_SENT`) → 시도 기록 + 상태 변경 + 감사 로그를 한 트랜잭션으로 커밋.
- 표기: 화면·API 모두 "모의 발송 성공/실패 — 실제 전송 없음". `SENT`/`DELIVERED` 용어 미사용.

## 9. 위험과 대응

| 위험 | 대응 |
|---|---|
| Java 발송 이력과 혼동 | Java 테이블 미사용, 별도 테이블·용어 |
| 미입력 데이터로 잘못된 안내 | 변수별 차단 규칙, 초안은 완전한 데이터만 |
| 생성 후 원천 수정 | 본문 스냅샷 보존 + 승인 시 지문 비교 |
| 중복 초안·중복 발송 | 부분 UNIQUE 2개, Idempotency-Key UNIQUE, 행 잠금 |
| 개인정보 노출 | 감사 로그에 본문 미기록, 목록에서 이메일 마스킹, 오류 응답에 수신자 미포함 |
| 템플릿 수정이 과거 메시지 변경 | 본문 스냅샷 + 템플릿 버전 기록 |
| UTC/KST 날짜 | 이번 단계 DB 트리거에 날짜 계산 없음 |

## 10. 테스트 계획

- 단위: 템플릿 파서(화이트리스트·중괄호·길이·특수문자), 렌더러(누락 규칙), Mock Sender.
- PostgreSQL 통합: 미리보기 DB 무변경, 권한(비담당·IDOR·ASSISTANT 승인·배정 해제·비활성), 차단 규칙(미입력·취소·휴원·연락처),
  일괄 저장 멱등성, 상태 전이·잘못된 전이, 승인 후 수정 차단, 원천 변경 감지, 동시 승인·동시 발송, Idempotency 재요청,
  실패 기록, 제약(FK·UNIQUE·CHECK), 템플릿 수정 후 기존 메시지 보존, 다운그레이드.
- 회귀: pytest 전체, Java(PostgreSQL), Vitest·lint·tsc·build.

## 11. Phase 9 연계

메시지별 학생·반·수업, 상태, 생성자·승인자·시각, 시도별 시각·결과·오류 코드·Idempotency-Key가 남는다.
**메시지가 없다는 사실만으로 미발송을 판단하지 않는다** — 발송 의무 대상·기준 시점은 Phase 9에서 별도 정의한다.
