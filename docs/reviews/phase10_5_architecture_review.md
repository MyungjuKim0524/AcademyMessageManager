# Phase 10.5-A — 아키텍처 및 코드 리뷰

리뷰일: 2026-11-20 · 대상: `backend/app`(FastAPI), `backend/alembic`, `backend/tests`, `frontend/src`(React) · 기준: Phase 10 완료 시점 코드
리뷰 방식: 디렉터리·import 그래프 파악 → 6개 핵심 흐름의 호출 경로 추적 → 의심 지점은 코드로 확인, 핵심 결함 1건은 격리 테스트 DB에서 재현.
**이 리뷰에서 소스·스키마·설정은 수정하지 않았다.** (작성 파일: 이 문서 1개)

---

## 1. Executive Summary

**전체 평가: 신입 개발자 결과물로서는 기대 이상.** 데이터 무결성을 애플리케이션이 아니라 **DB 제약으로 먼저 지키는 설계**(복합 FK로 만점 복제·검증, 부분 UNIQUE, 휴원 기간 EXCLUDE, 버전 트리거)와 "상태 변경 + 감사 로그 = 한 트랜잭션" 규율이 대부분 모듈에 일관되게 적용되어 있다. 모듈 의존성은 순환이 없고 계층(Router→Service→Repository)도 대체로 지켜진다. 과잉 설계(불필요한 추상화, 인터페이스 남발, 메시지 큐 등)는 없다.

다만 **핵심 업무 불변식 하나가 경로마다 다르게 적용**된다. 확정(APPROVED)된 메시지는 원본 데이터가 바뀌어도 화면에 경고가 뜨지 않는다. 그 상태로 **틀린 본문 그대로 모의 발송된다.** 같은 메시지를 "재시도"로 보내면 차단된다. 격리 테스트 DB에서 재현했다(5.1 H1). 이외에 엑셀 재업로드가 앱에서 고친 점수를 조용히 덮어쓰는 문제(H2)가 있다. 관리자 권한 변경이 감사되지 않는 문제(M1)도 있다.

Critical(데이터 유실·권한 우회)은 **검토 범위 안에서 발견하지 못했다.**

**최종 의견: Request Changes** — H1·H2는 수정 범위가 작고 회귀 위험이 낮으니 Phase 10.5에서 고친 뒤 승인 권장.

---

## 2. 현재 시스템 아키텍처 요약

```
React(Vite, antd) ── axios(쿠키 세션 + X-CSRF-Token) ──▶ FastAPI
  CompatibilityMiddleware(요청 ID·CORS·본문 크기·보안 헤더·접근 로그)
  └ Router(입력 파싱·의존성·응답 조립) → Service(업무 규칙·트랜잭션·감사) → Repository(조회·잠금)
     → SQLAlchemy 2 → PostgreSQL 17 (Alembic 001~010, 트리거·EXCLUDE·복합 FK)
```

| 모듈 | 책임 | 규모(줄) |
|---|---|---|
| `auth` | 로그인·세션·CSRF·역할 의존성 | service 147, dependencies 129 |
| `learningops` | 반·학생·직원·배정·수강·연락처 | service 234, router 320 |
| `academics` | 수업·출결·평가·성적·휴원·학습 현황 격자·학생 기록 | **service 1,024** |
| `notifications` | 템플릿·렌더링 엔진·초안·상태 전이·모의 발송 | service 664, engine 216 |
| `lesson_upload` | 주간 엑셀 파싱·검증·미리보기·확정 | service 515, workbook 225 |
| `message_operations` | 안내 의무(계산형) 집계·조치 | service 315 |
| `analytics` | 출결·성적 통계(읽기 전용) | service ~260, repository ~260 |
| 최상위 `app/domain.py`, `app/models.py`, `main.py`의 `/api/messages/preview` | **Java 호환 시절 레거시** | domain 215 |

문서와 코드의 일치: Phase 8~10 문서(`docs/archive/phases/phase*-*.md`)는 코드와 잘 맞는다. **불일치**: `docs/api/openapi.yaml`은 Java 서버(8080) 계약이고 FastAPI 경로를 담지 않는다. 루트 `README.md` 상단 설명도 Java/Swing 중심이다(M5).

## 3. 계층 및 모듈 의존성 분석

- **모듈 import 그래프(코드 grep 확인)**: `auth ← learningops ← academics ← notifications ← {lesson_upload, message_operations}`, `analytics → academics`. **순환 없음.** 접근 규칙 `LearningOpsRepository.can_access_classroom`(`learningops/repository.py:92`)이 단일 구현이고, 수업일 자격 `eligible_on`(`academics/repository.py:19`)도 단일 구현을 출결·성적·메시지·분석이 공유한다 — 좋은 응집.
- **Router**: 대부분 얇다. `learningops/router.py:189-224`, `:292-320`은 응답 조립(DTO 매핑)을 라우터에서 하지만 업무 규칙은 없다 — 허용 범위.
- **Service**: 업무 규칙·트랜잭션·감사가 서비스에 모여 있다. 단, 반 접근 검사 래퍼(`_require_classroom`)가 `academics/service.py:104`, `notifications/service.py:82`, `analytics/service.py:64`에 반복되고 `learningops/service.py:226-233`, `lesson_upload/service.py:130`은 인라인으로 반복한다(L1).
- **Repository**: 조회·잠금에 집중. `academics/repository.py`의 `eligible_on`처럼 업무 규칙을 SQL 식으로 표현한 부분은 의도된 재사용 지점이다.
- **Model/Schema**: SQLAlchemy 모델 1파일(`db/models/tables.py`) + 모듈별 Pydantic 스키마. 역할이 명확하다.
- **레거시 경계 위반**: `notifications/engine.py:18`이 레거시 `app/domain.py`의 **비공개 함수** `_pre`, `_weekly`를 import한다. `app/domain.py:14-17`의 `AttendanceStatus`에는 `EXCUSED`가 없어 현재 DB CHECK(4상태)와 다르다(M4).

## 4. 핵심 업무 흐름 검토

| # | 흐름 | 결과 | 근거 |
|---|---|---|---|
| 1 | 로그인 → 세션 → 권한 | **양호** | Argon2 + 더미 해시로 타이밍 균등화(`auth/service.py:26-34`), 세션·CSRF 토큰은 해시만 저장(`:113-118`), CSRF 이중 제출 + 서버 해시 비교(`auth/dependencies.py:62-75`), 비활성 직원은 매 요청 401(`:51-58`), 반 배정은 요청마다 오늘 날짜로 재검사(`learningops/repository.py:92-106`). 개선점: L3·M6 |
| 2 | 엑셀 Preview → Confirm | **양호, H2 1건** | 확정 시 파일 재파싱·재검증(`lesson_upload/service.py:235`), 데이터+감사 단일 커밋(`:262-277`), 동시 생성은 UNIQUE→409, 초안은 커밋 후 별도(의도·문서화, `:498-509`). 문제: 기존 점수 덮어쓰기(H2) |
| 3 | 학생·반·수강 변경 | **양호, M1 1건** | UNIQUE 위반을 409로 번역(`learningops/service.py:37-42`), 마지막 관리자 비활성화 차단 + 잠금(`:186-197`), 비활성화 시 세션 폐기(`:199-200`). 문제: 감사 누락(M1), 학생 목록 50명 절단(M3) |
| 4 | 수업 → 출결·성적 | **양호** | 취소·미래 수업 기록 차단, 기록 있는 수업 취소·이동 차단(`academics/service.py:293-302,327-330`), 행 잠금 + `version` 비교, **버전은 DB 트리거로 증가**(`alembic/versions/006…:20`) → 업로드 경로 변경도 낙관적 잠금에 반영 |
| 5 | 메시지 생성 → 확정 → 모의 발송 → 재시도 | **H1 결함** | 행 잠금·버전·멱등 키·성공 1건 부분 UNIQUE는 견고. 그러나 확정 후 원본 변경 검사가 재시도에만 있음(H1) |
| 6 | 출결·성적 → 집계 API → 화면 | **양호** | 대상 집합 CTE + LEFT JOIN + `FILTER` 집계, 읽기 전용, 권한·IDOR 테스트, EXPLAIN 실측(Phase 10 보고서 14절) |

## 5. 발견된 문제

### H1 [High] 확정된 메시지는 원본이 바뀌어도 경고 없이 틀린 본문으로 발송된다 — **재현함**
- **위치**: `backend/app/modules/notifications/service.py:594-600`(`mock_send`), `:619`(`retry_mock_send`의 검사), `:424,433`(`_detail`)
- **근거**: `retry_mock_send`는 `if self.source_changed(row): … SOURCE_CHANGED`로 막는데 `mock_send`는 `row.status != "APPROVED"`만 본다. `_detail`은 `check_source = notification.status in EDITABLE`이라 APPROVED에서는 `source_changed`를 항상 `False`로 돌려준다 → 검토 화면(`ReviewTab.tsx`) 경고도 사라진다. 원본(출결·성적·연락처)을 바꾸는 경로(`academics`, `lesson_upload`, 연락처 수정)는 확정된 메시지를 무효화하지 않는다.
- **원인**: "원본이 바뀐 메시지는 다시 확정해야 한다"는 불변식(Phase 9 문서 `phase9-message-operations.md:59`)이 재시도 경로에만 구현됨.
- **재현(격리 테스트 DB, 가상 데이터)**: 출결 결석으로 초안 생성 → 확정(200) → 출결을 출석으로 수정 → 상세 `source_changed: False` → `POST /mock-send` **200, MOCK_SENT, 본문 "출결: 결석"**.
- **영향**: 학부모에게 사실과 다른 출결·성적이 안내된다(현재는 모의 발송이지만 실제 발송 도입 시 그대로 사고).
- **개선(최소)**: `mock_send`에 `retry_mock_send`와 같은 `source_changed` 검사 추가 + `_detail`에서 `APPROVED`도 검사(또는 응답에 표시). UI는 기존 경고 문구 재사용.
- **회귀 위험**: 낮음(검사 1줄 + 기존 오류 코드 재사용). 확정 후 원본이 바뀐 건의 발송이 이제 409가 되므로 테스트 1~2건 추가.
- **처리**: **Phase 10.5**

### H2 [High] 엑셀 재업로드가 앱에서 고친 점수·과제 등급을 미리보기 표시 없이 덮어쓴다
- **위치**: `backend/app/modules/lesson_upload/service.py:435-469`(`_apply_row`), 미리보기 경고 `:177-203`
- **근거**: 출결은 앱 값과 다르면 유지하고 `attendance_mismatch`로 표시한다(`:435-436`, `:201-203`). 반면 점수·등급은 `existing.result_status, existing.score = status, value`(`:468-469`), `result.prework_grade = row["prework"]`(`:437-440`)로 무조건 덮어쓴다. 미리보기 경고는 출결만 다룬다(grep: `warnings`·`mismatch`는 출결 전용).
- **재현 조건(코드 추적, 실행 안 함)**: 학습 현황에서 점수 8→9 정정 → 다른 학생 오타를 고친 **같은 주 엑셀을 재업로드**(문서화된 정상 절차) → 9가 8로 되돌아가고 미리보기·결과 어디에도 표시 없음. 버전 트리거가 올라가므로 낙관적 잠금으로도 감지되지 않음.
- **영향**: 직원이 고친 성적이 사라짐 + 그 학생의 확정 메시지는 H1에 따라 틀린 본문으로 발송 가능.
- **개선(최소)**: 출결과 같은 규칙으로 통일하거나(앱 값 유지 + 불일치 표시), 최소한 미리보기에서 "앱 값과 다른 점수 n건"을 행별로 보여 주고 확정 시 덮어쓸지 선택하게 한다. **어느 쪽이 맞는지는 업무 정책 결정 필요**(사용자 승인 대상).
- **회귀 위험**: 중간(업로드 결과 의미가 바뀜). 기존 업로드 통합 테스트 기대값 영향.
- **처리**: **Phase 10.5**(정책 결정 후)

### M1 [Medium] 관리자 권한·인사 변경이 감사 로그에 남지 않는다
- **위치**: `backend/app/modules/learningops/service.py:44-49`(반 생성), `:51-61`(학생 생성), `:116-131`(수강 등록), `:133-149`(담당 반 배정), `:151-162`(직원 생성), `:173-178`(이름 변경), `:180-203`(**직원 비활성화**), `:216-221`(배정 **물리 삭제**)
- **근거**: 같은 모듈의 연락처 수정(`:99-111`), `academics`·`notifications`·`lesson_upload`는 모든 변경에 `AuditLog`를 같은 트랜잭션으로 남긴다. 위 함수들은 `AuditLog`를 만들지 않고, 배정 삭제는 `db.delete`로 이력까지 사라진다.
- **영향**: "누가 언제 어느 반 학생 정보 접근 권한을 받았/잃었나", "누가 직원을 비활성화했나"를 추적할 수 없음(설계 원칙 '보안·감사'와 불일치). 데이터 손상은 아님.
- **개선**: 각 함수에 기존 `_audit` 패턴 1줄씩. 배정 삭제는 `valid_to` 종료로 바꾸는 방안 검토(물리 삭제 대신) — 후자는 정책 결정 필요.
- **회귀 위험**: 낮음(추가만). **처리**: Phase 10.5

### M2 [Medium] 보호자 이메일 노출 범위가 화면마다 다르다 (정책 결정 필요)
- **위치**: `learningops/router.py:300`(학생 목록: 관리자만 보호자 연락처), `notifications/service.py:427`(메시지 상세: 모든 담당 직원에게 `recipient_email` 원문), 목록은 마스킹(`:37-39`)
- **영향**: "보호자 연락처는 관리자만" 정책이 메시지 상세로 우회된다. 다만 조교·선생님이 발송 확인 때 수신 주소를 봐야 한다는 Phase 9.5 결정과 충돌 — **어느 쪽이 정책인지 확정 필요**.
- **개선**: 정책 확정 후 (a) 상세도 마스킹 + 확인 창에 마스킹 주소, 또는 (b) "발송 권한자는 수신 주소 열람 가능"으로 정책 문서화. **처리**: Phase 10.5(결정만), 구현은 결정에 따라

### M3 [Medium] 반별 학생 목록이 50명에서 조용히 잘린다
- **위치**: `frontend/src/features/learningops/api.ts:23`(limit 미전달), `backend/app/modules/learningops/router.py:296`(기본 `limit=50`, 최대 100)
- **영향**: 51번째 이후 학생이 학생·반 관리 표와 성적 분석의 학생 선택에서 보이지 않음(경고 없음). 반 목록은 `limit:100`으로 같은 구조(관리자 반 100개 초과 시).
- **개선**: 프론트에서 `limit:100` 전달 + 응답 건수가 limit와 같으면 페이지 이동 또는 경고. **회귀 위험**: 낮음. **처리**: Phase 10.5

### M4 [Medium] Java 호환 레거시가 FastAPI 핵심 경로와 섞여 있다
- **위치**: `app/main.py`의 `/api/messages/preview`(+`auth/dependencies.py:101-129` 반 이름 기반 권한), `app/domain.py`(`AttendanceStatus`에 `EXCUSED` 없음, `:14-17`), `notifications/engine.py:18`(레거시 비공개 함수 의존), `frontend/src/features/message-preview/*`, `/deliveries` ComingSoon 라우트(`app/router.tsx`)
- **영향**: 업무 흐름에서 쓰지 않는 두 번째 메시지 생성 경로·두 번째 출결 enum이 유지보수 대상으로 남음. 사용자는 GitHub에 Python만 올릴 계획(2026-11-20) → 포트폴리오 관점에서 혼란.
- **개선**: `_pre`/`_weekly`를 `notifications/engine.py`로 옮기고 레거시 미리보기 경로·화면 제거 여부를 사용자 결정. **회귀 위험**: 낮음~중간(Java 계약 비교 테스트 영향). **처리**: Phase 10.5(결정) / Phase 11(정리)

### M5 [Medium] API 계약 문서·타입이 실제 FastAPI와 동기화되지 않는다
- **위치**: `docs/api/openapi.yaml`(서버 `http://127.0.0.1:8080`, Java 계약), `frontend/src/features/*/api.ts`(수기 TS 타입), 루트 `README.md` 상단(Java/Swing 설명)
- **영향**: 백엔드 응답 변경 시 프론트 타입이 조용히 어긋날 수 있음(프론트 테스트는 API 모듈을 mock). 실제 백엔드·프론트 계약은 PostgreSQL 통합 테스트와 사람 확인에만 의존.
- **개선**: FastAPI가 생성하는 OpenAPI를 산출물로 저장하고 README를 현재 구조로 갱신. **처리**: Phase 11(문서 정리 범위)

### M6 [Medium] 배포 전 해결 필요: 실행 모드 게이트·로그인 제한기
- **위치**: `app/security.py:8-19`·`app/db/safety.py:18-20`(DB API는 `ACADEMY_DB_MODE ∈ {development,test}` + 루프백 호스트에서만), `auth/service.py:49-84`(프로세스 메모리 제한기, 키 무한 증가), `auth/router.py:55`(`request.client.host` — 프록시 뒤에서는 모든 사용자가 같은 IP)
- **영향**: 현재 로컬 정책과는 일치(결함 아님). 배포하면 API가 열리지 않거나, 프록시 뒤에서 한 사람의 실패가 전원을 잠글 수 있음.
- **처리**: **Phase 11**(배포 준비) — 지금 고치지 않는다.

### M7 [Medium] 발송기 호출이 DB 트랜잭션·행 잠금 안에 있다
- **위치**: `notifications/service.py:631`(`self.sender.send(...)` 후 `:660` 커밋), `:52`(`MockSender()` 직접 생성)
- **영향**: 모의 발송에서는 문제없음. 실제 발송기를 붙이면 "외부 전송 성공 + 커밋 실패 = 보냈는데 기록 없음"이 가능(멱등 키로 재요청은 막지만 외부 중복은 못 막음).
- **처리**: 실제 발송 도입 시점(Phase 11 이후). 지금 아웃박스 등을 만들지 않는다.

### L1 [Low] 반 접근 검사 래퍼 반복 — 규칙은 단일, 404/403 문구만 5곳 반복(`academics/service.py:104`, `notifications/service.py:82`, `analytics/service.py:64`, `learningops/service.py:226-233`, `lesson_upload/service.py:130`). 지금은 일관됨 → **규칙이 바뀔 때** 한 함수로 추출. Phase 11 이후.
### L2 [Low] `academics/service.py` 1,024줄에 수업·출결·평가·성적·휴원·격자·학생 기록이 모두 있음. 기능은 응집되어 있고 테스트가 두꺼워 **지금 분리할 이득이 작다** — 이 파일을 크게 바꿀 일이 생길 때 하위 도메인별로 나눈다.
### L3 [Low] `auth_session.last_seen_at`이 갱신되지 않아 유휴 만료 없음(로그인 후 8시간 절대 만료만, `config.py:36`). 공용 PC 사용 시 위험 — Phase 11 보안 점검에서 결정.
### L4 [Low] 로그인 제한기 딕셔너리가 키를 지우지 않고 누적(`auth/service.py:58-63`은 창 밖 시도만 정리). 로컬 단일 사용자 규모에서 무시 가능 — M6와 함께 처리.

**검토했지만 문제로 보지 않은 것**: 초안 생성을 엑셀 저장 커밋 뒤에 분리한 설계(문서화된 의도, 결과 화면에 사유 표시), 조교도 확정·발송하는 권한(사용자 결정 2026-11-18), 출결 미입력 학생을 화면에서 '출석' 미리 선택(저장 전 표시로 구분, Phase 8.1 결정), 프론트의 권한별 버튼 숨김(서버가 모두 재검사).

## 6. 구조적으로 잘 설계된 부분

1. **DB가 불변식을 지킨다**: 성적 행이 평가의 `max_score`를 복합 FK로 복제하고 `score ≤ max_score` CHECK(`tables.py:240-251`) → 만점을 낮추면 DB가 거부. 휴원 기간 겹침 EXCLUDE(`:103-108`), 학생·반 수강 1건 UNIQUE, 활성 메시지 부분 UNIQUE, 메시지당 성공 발송 1건 부분 UNIQUE, `version` 트리거.
2. **변경 + 감사 = 한 트랜잭션**, 행 잠금 + 버전 비교 + 멱등 키(`notifications/service.py:576-592`) — 중복 클릭·재시도가 안전.
3. **"모르는 것은 추정하지 않는다"** 규칙이 코드로 표현됨: `eligible_on`이 종료일 없는 퇴원·이력 없는 휴원을 대상에서 제외, 실패 사유는 저장된 코드에서만 분류.
4. **인증 기본기**: 토큰 해시 저장, CSRF 서버 측 해시 검증, 비활성 즉시 차단, 마지막 관리자 보호, 개인정보 응답 필드 역할별 제외(`response_model_exclude_unset`).
5. **테스트 DB 안전장치**: 컨테이너 라벨·DB 이름·사용자 확인 후에만 파괴적 테스트, 통합 테스트가 실제 PostgreSQL에서 업무 규칙과 실패 시나리오(동시성·권한·버전 충돌)를 검증.
6. **과잉 설계가 없다**: 인터페이스·DI 컨테이너·이벤트 버스 없이 모듈형 모놀리스 규모에 맞는 구조.

## 7. 개선 우선순위 TOP 5
1. **H1** 확정 메시지 원본 변경 시 발송 차단·경고 — 1줄 수준, 효과 최대
2. **H2** 업로드 점수 덮어쓰기 정책 결정 + 미리보기 표시
3. **M1** 관리자 권한·인사 변경 감사(+ 배정 물리 삭제 재검토)
4. **M3** 학생 목록 50명 절단
5. **M2/M4** 보호자 이메일 노출 정책·레거시 경로 정리 결정(코드보다 결정이 먼저)

## 8. Phase 10.5 / Phase 11 경계
| Phase 10.5 (수정) | Phase 10.5 (사용자 결정만) | Phase 11 |
|---|---|---|
| H1, M1, M3 | H2 정책, M2 정책, M4 제거 범위 | M5 문서·계약, M6 배포 게이트·제한기, M7 발송 트랜잭션, L1~L4 |

## 9. 미검증 사항
- **실행으로 확인한 것**: H1 재현(격리 테스트 DB, 가상 데이터 — 재현 스크립트가 테스트 DB 테이블을 초기화하고 가상 행을 남겼으며, 다음 테스트 실행의 픽스처가 다시 초기화함). 개발 DB·운영 데이터는 건드리지 않음.
- **이번 리뷰에서 다시 돌리지 않은 테스트**: 전체 회귀는 같은 날 Phase 10 종료 시 실행한 결과(pytest 단위 39·PostgreSQL 69, Vitest 82, mvn 48/skip 6)를 인용 — 그 뒤 소스 변경 없음. 이 리뷰에서 새로 PASS를 주장하지 않는다.
- **코드 추적만 한 것**: H2 재현 시나리오, M3(51명 이상 반 데이터로 실행 안 함), 동시 업로드 경합(UNIQUE로 409 예상).
- **보지 않은 것**: Java 레거시 소스, `frontend` 화면별 접근성·브라우저 동작(브라우저 도구 없음), `academics/service.py`의 휴원 처리 세부(`:600-695`)와 학생 기록(`:1013-`) 전체 줄 단위, 의존성 취약점 스캔, 부하·동시성 스트레스.

## 10. 최종 리뷰 의견 — **Request Changes**

신입 개발자에게: 무결성을 DB 제약과 트랜잭션으로 지키려는 감각, 테스트 DB를 보호하는 습관, 결정을 문서로 남기는 태도는 이미 시니어 수준이다. 이번 요청 사항은 많지 않다. **같은 업무 규칙을 모든 진입 경로에 똑같이 적용했는지** 확인하는 습관이 남았다. 재시도에는 있는 원본 변경 검사가 첫 발송에는 없었다(H1). 출결에는 있는 보호 규칙이 점수에는 없었다(H2). H1·M1·M3를 고치고 H2·M2 정책을 정하면 **Approve**하겠다.
