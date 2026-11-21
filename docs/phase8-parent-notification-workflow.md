# Phase 8 — 학부모 안내 메시지 생성·검토·승인·모의 발송 최종 보고서

작성일: 2026-11-18 · 설계: `docs/phase8-implementation-plan.md` · 진행: `docs/phase8-progress.md`

## 1. 목표 및 구현 범위

수업·출결·성적 데이터로 학부모 안내 초안을 자동 생성하고, 직원 검토·수정 → 승인 → **모의 발송** → 이력 확인까지
하나의 흐름으로 제공한다. 실제 SMS·이메일·외부 API·LLM·스케줄러·재시도·대시보드는 구현하지 않았다(Phase 9 이후).

## 2. 기존 메시지 기능 분석

| 기존 기능 | 판단 |
|---|---|
| `POST /api/messages/preview` (`app/domain.py`) | 계약 변경 없음(Java fixture 공유). 문장 규칙(예습·주간·테스트·보강)과 빈 줄 정리 규칙을 재사용 |
| Java `{학생명}` 치환 규칙 | 같은 `{변수}` 문법 채택 |
| `message_template` | 수업 유형당 1개 UNIQUE, Java가 관리 → 재사용 불가 |
| `message_draft` | `lesson_result_id NOT NULL` → 출결 미입력 학생 표현 불가 → 재사용 불가 |
| `delivery_job`/`delivery_attempt` | Java **실제 SMTP 발송 로그**(`EmailSendService`), Java 화면이 전 행을 발송 이력으로 표시 → 모의 발송을 섞으면 실제 발송으로 오인 → 사용 금지 |
| `student.parent_email` | 보호자 연락처 1개 → 수신자 단일 정책 |
| Phase 7/7.1 수업·출결·성적, `eligible_on` | 그대로 재사용 |
| `audit_log`, 권한 의존성 | 재사용 |

## 3. 재사용 vs 신규

- 재사용: 세션·CSRF 인증, `can_access_classroom`, `eligible_on`(휴원·수강 기간), `audit_log`, `app.domain`의 문장 함수, 공통 오류 형식,
  React 레이아웃·API 클라이언트(CSRF 자동), classwork의 반·수업 목록·수업 표기.
- 신규: `app/modules/notifications/`(engine, sender, repository, service, schemas, router), Migration 008, React `features/notifications/`.

## 4. DB 스키마 변경 / 5. Migration

Revision **`008_phase8_notifications`** (down: 007) — 새 테이블 3개만 추가, 기존 테이블·Java 테이블 변경 없음.

| 테이블 | 핵심 제약 |
|---|---|
| `notification_template` | 이름 UNIQUE, 본문 1~2000자, `version` 트리거, 기본 템플릿 1개 삽입 |
| `parent_notification` | 복합 FK `(lesson_id, classroom_id)`, `(enrollment_id, classroom_id)` → 다른 반 조합 불가 · 상태 CHECK 6종 · 승인 계열 상태는 `approved_at` 필수 · 본문 1~2000자 · **부분 UNIQUE (수업, 학생, 템플릿) WHERE 취소 아님** · 스냅샷 `body`·`template_body`·`template_version`·`recipient_email`·`source_hash` |
| `notification_send_attempt` | `channel = 'MOCK'` CHECK · `result IN (MOCK_SUCCESS, MOCK_FAILURE)` + 실패 시 `error_code` 필수 · `idempotency_key` UNIQUE · **부분 UNIQUE: 메시지당 성공 1회** · 메시지 삭제 RESTRICT |

적용 상태: 테스트 DB **적용**(head 008, `alembic check` 차이 없음, downgrade→upgrade 왕복 검증) · 개발 DB **미적용(승인 대기)**.
설계 중 `template_body` 컬럼을 추가하며 008을 테스트 DB에서만 되돌렸다가 재적용했다(개발 DB에는 적용된 적 없음).

## 6. 템플릿 엔진 및 지원 변수

`{변수}` 단순 치환만 허용(표현식·속성 접근·코드 실행 없음). 화이트리스트 밖 변수, 짝 없는 중괄호, 빈 본문, 2000자 초과는 저장 거부.
출력은 평문이며 React가 텍스트로 렌더링한다(HTML 미해석).

| 변수 | 내용 | 누락 시 |
|---|---|---|
| `{학생명}` `{분반명}` `{수업일자}` | 학생·반·수업일 | 항상 존재 |
| `{교시}` `{시험회차}` | 2교시 이상일 때 "N교시", 시험 회차 | 빈 값 |
| `{수업주제}` | 수업 주제 | **생성 불가** |
| `{출결}` | 출석/지각/결석/인정결석 | **생성 불가**(미입력 ≠ 결석) |
| `{보강메시지}` | 결석일 때 기존 보강 문장(인정결석은 없음) | 출결 미입력이면 생성 불가 |
| `{성적요약}` | 이 수업에 연결된 평가 결과("단원 평가 18/20점", "미응시") | 결과 미입력 **생성 불가**(≠ 0점), 연결 평가 없음은 빈 값 + 경고 |
| `{예습메시지}` `{주간메시지}` `{테스트메시지}` | 기존 Import 데이터 문장 | 빈 값(기존 규칙) |

## 7. 메시지 생성 규칙 / 8. 데이터 누락 정책

- 대상: 학생 미지정 시 수업 명단(수업일 기준 수강 대상 + 출결 기록 있는 학생). 지정 시 최대 100명, 중복 400.
- 템플릿이 **실제로 쓰는 변수만** 평가한다(출결 변수가 없으면 출결 미입력이어도 생성 가능).
- 공통 생성 불가: 취소된 수업(결석으로 안내하지 않음), 수업일 기준 수강 대상 아님(휴원·기간 밖)이면서 출결 기록 없음,
  보호자 이메일 없음, 다른 반 학생(이름 등 정보 미노출), 비활성 템플릿, 결과가 비거나 2000자 초과.
- 미리보기는 DB에 아무것도 쓰지 않는다(테스트로 메시지·감사 로그 수 불변 확인).
- 저장: 생성 불가·기존 초안 있는 학생은 사유와 함께 건너뛰고, 가능한 학생은 한 트랜잭션으로 저장. 같은 요청을 반복하면 기존 초안을 건너뛴다(멱등).
  동시 저장으로 UNIQUE 충돌 시 전체 롤백 후 409.
- **DB에 저장된 초안은 항상 필수 데이터가 갖춰진 상태** → 누락 데이터 초안이 승인 가능 상태가 되는 경로가 없다.

## 9. 상태 머신

`DRAFT → READY_FOR_REVIEW → APPROVED → MOCK_SENT | MOCK_FAILED`, 승인은 DRAFT·READY 모두 허용, `APPROVED → DRAFT`(승인 취소),
`DRAFT·READY·APPROVED·MOCK_FAILED → CANCELLED`. 본문 수정은 DRAFT·READY에서만, 승인 후 수정은 409 `NOTIFICATION_LOCKED`.
승인 시 생성 당시 템플릿으로 현재 원천 데이터를 다시 렌더링해 지문이 다르면 409 `SOURCE_CHANGED`(취소 후 재생성).
MOCK_SENT는 종결, MOCK_FAILED 재시도는 Phase 9(이번에는 취소만). 허용되지 않은 전이는 409 `INVALID_TRANSITION`.

## 10. 승인 및 권한

**학원 업무 정책(2026-11-18 사용자 결정): 실제 발송은 조교가 한다. 조교가 내용을 직접 확정하고 발송하며, 선생님·관리자도 같은 작업을 할 수 있다.**
초기 설계(ASSISTANT 승인·발송 불가)는 이 결정에 따라 변경했다.

| 작업 | ADMIN | 배정 TEACHER | 배정 ASSISTANT |
|---|---|---|---|
| 템플릿 등록·수정·사용 여부·검증 | O | X | X |
| 템플릿 조회 | 전체 | 사용 중만 | 사용 중만 |
| 미리보기·초안 저장·본문 수정·검토 요청 | O | O | O |
| 내용 확정(승인)·확정 취소·모의 발송·취소 | O | O | **O** |

- 화면 용어: 직원에게 "승인"이 낯설어 **"내용 확정"**으로 표기한다(상태 `APPROVED` = "확정됨 (발송 대기)").
  의미는 같다 — 발송 직전에 "이 내용으로 보낸다"고 확정하면 본문이 잠기고 확정자·시각이 기록되며, 확정된 메시지만 발송할 수 있다.
- 단일 확정 단계(다단계 결재 미도입). 작성자 본인 확정 허용. 누가 확정·발송했는지는 확정자·시도 요청자·감사 로그로 남는다.
- 모든 API는 메시지/수업의 반으로 `can_access_classroom` 검사 → **담당 반이 아닌 조교·선생님은 403**(다른 반 ID IDOR/BOLA 포함),
  배정 해제 즉시 403, 비활성 직원 401.

## 11. Mock Sender

`MockSender.send()`는 프로세스 내부 함수다(네트워크·SMS·이메일 없음). 결정적 실패 규칙: 수신 도메인 `mock-fail.invalid`(RFC 2606 예약)
→ `MOCK_RECIPIENT_REJECTED`. UI에 실패 조작 기능 없음. 화면·API 표기는 "모의 발송 성공 (실제 미전송)" / "모의 발송 실패"이며
`SENT`/`DELIVERED`를 쓰지 않는다. 테스트에서 `socket.create_connection`을 차단한 상태로 모의 발송이 성공함을 확인했다.

## 12. 멱등성·트랜잭션·동시성

- 모의 발송은 `Idempotency-Key`(UUID) 헤더 필수. 메시지 행 `FOR UPDATE` 후 키 조회 → 같은 키면 **이전 결과 재반환**(`replayed: true`),
  다른 메시지의 키면 409 `IDEMPOTENCY_KEY_REUSED`, 이미 성공이면 409 `ALREADY_MOCK_SENT`, 미승인이면 409 `NOT_APPROVED`.
- 시도 기록·상태 변경·감사 로그는 한 트랜잭션. DB가 메시지당 성공 1회와 키 유일성을 보장.
- 상태 전이·본문 수정: `version` 일치 + 행 잠금. 동시 승인 2건 → 200/409, 승인 이력 1건(테스트).
- 동시 모의 발송(다른 키) → 200/409, 성공 1건. 같은 키 동시 → 한 건만 기록되고 다른 요청은 재반환(테스트).
- 화면은 클릭마다 키를 만들고 응답을 받을 때까지 유지(재클릭·재시도 시 같은 키), 처리 중 버튼 비활성화.

## 13. 개인정보 및 보안

감사 로그에 본문·수신자 미기록(길이·변경 여부만).
수신자 표시(2026-11-18 사용자 결정 "3번"): **메시지 목록은 마스킹**(`p***@example.invalid`), **메시지 상세는 전체 주소**(`recipient_email`) —
상세는 담당 반 직원만 열 수 있고, 확정·발송하는 사람이 수신 주소를 확인하기 위함이다.
학생 목록의 보호자 이름·이메일은 **관리자에게만 응답에 포함**되고, 선생님·조교 응답에는 키 자체가 없다(Phase 6A 보안 테스트 "응답에 parent 없음" 그대로 통과).
모의 실패 메시지에 수신 주소 미포함(테스트). 다른 반 학생은 미리보기에서 이름도 반환하지 않음. 테스트는 가상 학생·`.invalid` 이메일만 사용.
CSRF는 모든 변경 API에 적용(테스트). 일괄 요청 100명 제한. 템플릿 변수 화이트리스트.

## 14. API

| Method | Path | 권한 |
|---|---|---|
| GET | `/api/notification-templates`, `/api/notification-templates/variables` | 직원 |
| POST | `/api/notification-templates/validate` | ADMIN |
| POST · PATCH | `/api/notification-templates` · `/{id}` (`version`) | ADMIN + CSRF |
| POST | `/api/lessons/{id}/notifications/preview` | 반 접근(DB 쓰기 없음) |
| POST | `/api/lessons/{id}/notifications` | 반 접근 + CSRF |
| GET | `/api/notifications?classroom_id=&lesson_id=&status=` · `/api/notifications/{id}` | 반 접근 |
| PATCH | `/api/notifications/{id}` (`version`, `body`) | 반 접근 + CSRF |
| POST | `/api/notifications/{id}/submit` · `approve`(내용 확정) · `revoke`(확정 취소) · `cancel` (`version`) | 반 접근 + CSRF |
| POST | `/api/notifications/{id}/mock-send` (`Idempotency-Key`) | 반 접근 + CSRF (조교 포함) |

기존 `POST /api/messages/preview`는 변경 없음.

### 14-1. 보호자 연락처 수정 (사용자 요청 추가 기능)

| Method | Path | 권한 |
|---|---|---|
| GET | `/api/students/{id}/contact` → `{id, name, parent_name, parent_email}` | ADMIN |
| PATCH | `/api/students/{id}/contact` `{parent_name?, parent_email?}` | ADMIN + CSRF |

- 보내지 않은 항목은 유지, `null`/빈 문자열은 삭제. 이메일 형식 검증·소문자 정규화, 다른 필드(이름 등) 400, 없는 학생 404.
- 감사 로그 `STUDENT_CONTACT_UPDATED`에는 바뀐 항목 이름과 이메일 존재 여부만 기록(연락처 값 미기록). 값이 같으면 기록 없음.
- `GET /api/classrooms/{id}/students`: 관리자 응답에 `parent_name`·`parent_email` 포함, 그 외 역할은 키 미포함(`response_model_exclude_unset`).
- 화면: 관리자 학생 목록에 "보호자 이메일" 열(없으면 "미등록" 태그), 연락처 저장 후 목록 새로고침.
- 메시지 상세 화면의 "수신 주소"는 전체 이메일, 메시지 목록은 마스킹 유지.
- 연락처를 바꾸면 아직 확정하지 않은 기존 메시지는 원천 변경으로 확정이 막히고, 다시 생성하면 새 주소가 쓰인다(테스트).
- 화면: 학생·반 관리 → 학생 목록 "연락처 수정" → 보호자 이름·이메일 입력 창(ADMIN).
  개발 중 이 창의 입력칸 id가 학생 등록 양식의 `parent_email`과 겹쳐 라벨이 엉뚱한 입력칸을 가리키던 문제를 테스트로 발견해 양식 이름으로 분리했다.

## 15. React 화면

메뉴 **학부모 안내**(`/notifications`, 2026-11-20 **'성적 안내'**로 이름 변경 — `phase8-1-excel-upload.md` 7.6), 상단에 "모의 발송 — 실제 전송 없음" 안내. 반 선택 + 탭 3개.
- **메시지 생성**: 수업·템플릿 선택 → 미리보기(저장 안 됨) → 학생별 "생성 가능/생성 불가/이미 메시지 있음" 태그와 사유·경고·본문 →
  생성 가능한 학생만 체크 가능 → 초안 저장 → 검토 탭으로 이동.
- **검토·발송**: 상태·수업 필터, 목록(수신자 마스킹) 클릭 → 상세 패널(상태·수업·전체 수신 주소·작성자·확정자, 원천 변경 경고, 본문 편집,
  상태별 버튼 "본문 저장/검토 요청/내용 확정/확정 취소/모의 발송/메시지 취소", 모의 발송 확인 팝업, 시도 내역, 처리 이력 타임라인).
- **템플릿**: 목록(버전·사용 여부), 변수 설명, ADMIN 등록·수정·사용 전환, "검증·예시 보기"(가상 데이터).
- 상태는 아이콘+글자로 표시. Loading/Empty/Error/Success/권한/충돌/원천 변경/발송 실패 상태 처리.

## 16. 테스트 결과 (2026-11-18, 테스트 DB head 008)

| 항목 | 결과 |
|---|---|
| Ruff · `alembic check` | PASS · 차이 없음 |
| pytest 전체 (PostgreSQL 포함) | **90 PASS** (Phase 8 신규 21: 엔진 7, DB 제약 3, 통합 11 — 연락처 수정 포함) |
| Java Maven (PostgreSQL) | **48 PASS / 0 fail / 0 skip** |
| React Vitest | **11 files, 38 PASS** (Phase 8 신규 5: 미리보기·차단 사유·선택 저장, 조교 확정·모의 발송·요청 키·실제 미전송 표기, 원천 변경 시 확정 차단, 템플릿 검증, 보호자 연락처 수정) |
| React lint / tsc / build | PASS (기존 500kB chunk 경고만) |

권한 정책 변경(조교 확정·발송), 연락처 수정, 수신 주소 표시(관리자 학생 목록 이메일 열·메시지 상세 전체 주소) 반영 후
다시 실행한 결과다(2026-11-18 03시, 38 PASS — 기존 테스트에 표시 검증을 추가해 개수는 동일). 정책 변경 전 실행은 결과로 쓰지 않고 중단했다.

Phase 8 통합 테스트 범위: 템플릿 관리·검증·권한·버전 충돌, 미리보기 DB 무변경, 미입력 출결·성적 차단, 휴원 학생 차단, 다른 반 학생, 100명 초과·중복,
일괄 저장 멱등성·CSRF, 본문 수정·검토 요청·**조교의 내용 확정**·확정 취소·잘못된 전이·확정 후 수정 차단·담당 아닌 조교 차단·이력 순서·감사 로그 본문 미포함,
템플릿 수정 후 기존 메시지 보존, 원천 변경 시 확정 차단·재생성, 동시 확정, 모의 발송(**조교가 확정·발송**, 미확정·키 누락·잘못된 키·담당 아닌 조교·CSRF·성공·재요청·중복·Java 발송 로그 0건·네트워크 차단),
모의 실패 기록·재시도 불가·취소, 동시 발송·같은 키 동시·키 재사용, 다른 반 직원 IDOR·배정 해제·비활성 직원.

## 17. Browser E2E

**NOT RUN — 사용자 수동 확인 대기.** 개발 DB 008 적용과 서버 기동은 완료했다. 자동화 테스트(API·React 단위)를 브라우저 E2E로 간주하지 않는다.

수동 절차 (`http://127.0.0.1:5173`, 관리자 비밀번호는 사용자가 직접 입력):
1. ADMIN: 학생·반 관리 → 학생 "연락처 수정"에서 가상 보호자 이메일 입력(예: `parent@example.invalid`)
2. 수업·출결·성적: 수업 주제가 있는 수업에 출결 입력(필요하면 연결 평가와 점수)
3. 학부모 안내 → 메시지 생성: 수업·템플릿 선택 → 미리보기(생성 가능/불가 사유 확인) → 초안 저장
4. 검토·발송: 메시지 열기 → 본문 수정 → **내용 확정** → 모의 발송 → "모의 발송 성공 (실제 미전송)"·시도 내역·처리 이력 확인
5. 조교 계정으로 같은 흐름(확정·발송 가능), 담당 반이 아닌 직원은 메시지가 보이지 않음 확인
6. (선택) 이메일을 `…@mock-fail.invalid`로 바꾼 학생으로 모의 발송 실패 기록 확인

## 18. 기존 기능 회귀

기존 pytest 전체(인증·RBAC·직원·배정·학생·수업·출결·성적·메시지 미리보기·Import Preview/Confirm/History·계약 fixture)와
Java 48개가 테스트 DB 008에서 통과했다. 기존 테스트 기대값 변경은 스키마 확장 반영뿐이다
(`test_postgres_integration.py` head·트리거 4개·007 단계 허용, `test_db_safety.py` 테이블 3개, `test_phase7_schema_integrity.py` head).

## 19. 개발 DB Migration

008 **적용 완료** (2026-11-18, 사용자 승인).

1. 식별: `academy-learningops-postgres-dev` healthy, `127.0.0.1:55431`, 라벨 `isolated-development`/`destructive-tests=forbidden`,
   볼륨 `academy_learningops_postgres_dev_data`, `academy_learningops_dev`/`academy_dev`, 적용 전 revision 007.
2. SQL 확인(`alembic upgrade 007:008 --sql`): 새 테이블 3개·인덱스·트리거 생성, 새 템플릿 테이블에 기본 템플릿 1행 INSERT, `alembic_version` 갱신뿐.
   기존 테이블 `ALTER`/`DROP`/`DELETE` 없음.
3. 백업: `.dev-data\backups\academy_learningops_dev-pre008-20261118-024407.dump` (95,343 bytes,
   SHA-256 `051159271668336F9F3E51653787449D7FC152D6EECE63DAF81A291CBD4D5716`), `pg_restore --list` 성공(238 entries).
4. 적용: 성공, `alembic check` 차이 없음.
5. 사후 읽기 전용 검증: 직원(ADMIN 1, TEACHER 1)·반 1·학생 1·수강 1·휴원 1·배정 1·수업 2·출결 1·평가 0·감사 11 동일,
   직원·학생·수강·수업·출결·평가 지문(md5) 적용 전과 동일, Java 메시지 테이블 0건 유지,
   신규 테이블 3개, 기본 템플릿 "수업 안내 (기본)" v1, 제약 21개, 부분 UNIQUE 2개, 트리거 4개.
6. 서버: FastAPI(preflight PASS, Phase 8 경로 14개)와 React 개발 서버 기동, 미인증 401(직접·Vite 프록시).

## 20. 미완료·알려진 제약

1. 개발 DB 008 적용과 브라우저 E2E.
2. 보호자 연락처는 `student.parent_email` 하나뿐이다(수신자 단일). 학생 등록 화면에 보호자 이메일 입력칸을 추가했고,
   **기존 학생 연락처 수정 기능**(§14-1)을 추가했다. 연락처 수정은 관리자 전용이며 학생 등록 API의 이메일 형식 검증은 기존 동작을 유지했다(화면에서 검증).
3. 초안 저장 전 화면 편집은 없다(저장 후 검토 탭에서 수정).
4. 승인 후 원천 데이터가 바뀌어도 승인된 본문은 스냅샷 그대로다(의도된 동작). 생성~승인 사이 변경만 차단한다.
5. MOCK_FAILED 재시도·처리 현황·누락 탐지는 Phase 9.
6. 메시지 이력은 `audit_log` 이벤트로 보여 주며 본문 변경 내용(전/후 문장)은 보존하지 않는다(개인정보 최소화). 현재 본문과 승인된 본문은 보존된다.

## 21. Phase 9 연계 준비도

메시지별 학생(수강)·반·수업, 현재 상태, 생성자·수정자·승인자·승인 시각, 템플릿 버전·스냅샷, 시도별 시각·결과·오류 코드·사유·요청자·Idempotency-Key가 남는다.
메시지가 없다는 사실만으로 미발송을 판단하지 않도록 설계했다 — 발송 의무 대상·기준 시점은 Phase 9에서 정의한다.

## 22. 최종 판정

**조건부 완료.** 템플릿·자동 생성·미리보기·검토·내용 확정·모의 발송·이력의 업무 흐름이 실제 PostgreSQL(테스트 DB)과
React 단위 테스트에서 동작함을 확인했다(Python 90, Java 48, React 38, lint·tsc·build PASS).
개발 DB Migration 008은 승인 후 백업·적용·보존 검증까지 마쳤다. 남은 항목: 실제 브라우저 E2E(사용자 수동 확인 대기, §17).
