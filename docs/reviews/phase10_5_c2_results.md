# Phase 10.5-C-2 — 결과: 레거시 메시지 의존성(M4) · '진행된 수업' 규칙(B-2)

작업일: 2026-11-20 · 근거: `phase10_5_architecture_review.md`, `phase10_5_improvement_plan.md`, `phase10_5_c1_results.md` · 기준: C-1 수정 이후 코드
요약 판정: **M4 = 부분 수정**(메시지 엔진 → 레거시 의존 제거, 레거시 API·화면은 유지) · **B-2 = 공통화**(같은 업무 불변식 확인됨)

---

## 1. 레거시 코드 의존성 분석 결과 (M4)

### 1.1 호출 관계 (import·라우트·테스트로 확인)
| 대상 | 등록·호출 | 근거 |
|---|---|---|
| `POST /api/messages/preview` (FastAPI) | **등록됨, 동작 중** | `app/main.py:79-90`, 미들웨어의 경로·Content-Type 규칙 `app/middleware.py:40,100,111` |
| 같은 API (Java) | Java 서버에도 같은 경로 | `src/main/java/.../api/ApiRoutes.java`(`MessagePreviewHandler`) |
| React | 라우트 `/messages/preview`가 등록되어 URL로 진입 가능. **사이드바 메뉴에는 없음** | `frontend/src/app/router.tsx:11,27`, `layout/AppLayout.tsx`(메뉴 항목에 없음), `features/message-preview/*`, 구 진입점 `src/App.tsx` |
| FastAPI 내부 호출 | `app.domain`을 import하는 앱 코드는 `main.py`와 **`notifications/engine.py:18`(`_pre`, `_weekly`)** 뿐 | grep `app.domain` |
| 테스트 | `tests/test_domain.py`, `test_api.py`(검증·415·405 등), `test_auth_rbac_integration.py:204-214`(반 이름 기반 권한), **`test_contract_fixtures.py`(Java와 공유하는 계약 fixture 7건)**, `test_phase8_template_engine.py:8`(`_pre` import) | |
| 도구·문서 | `scripts/compare_contract.py`(Java ↔ Python 응답 비교), `docs/api/openapi.yaml`, README 2곳 | |

### 1.2 엔진이 레거시 비공개 함수에 의존한 이유
Phase 8에서 새 템플릿 엔진의 `{예습메시지}`·`{주간메시지}`가 **기존 학부모 안내 문장을 그대로** 쓰도록 `app.domain`의 `_pre`/`_weekly`를 재사용했다. 결과적으로 **현행 메시지 도메인의 문장 규칙이 레거시 파일 안에** 있었고, 같은 성격의 `MAKEUP_SENTENCE`와 빈 줄 정리는 엔진에 **복사본**(`# same as app.domain` 주석으로만 동기화)으로 존재했다. → 현행 핵심 경로가 레거시를 의존하는 **역방향 의존** + 문장 규칙 출처가 두 곳.

### 1.3 레거시 출결 상태와 현재 도메인 상태
| | 상태 | 쓰임 |
|---|---|---|
| `app/domain.py` `AttendanceStatus` | PRESENT · ABSENT · LATE (3) | 자유 입력 미리보기 API의 **입력 검증**. Java `AttendanceStatus.java`와 정확히 같은 3상태 |
| DB `lesson_result.attendance_status` / 엔진 | PRESENT · LATE · ABSENT · **EXCUSED** (4) | 저장된 출결, `engine.ATTENDANCE_LABEL` |

- **기능 결함 아님**: 레거시 API는 DB 출결을 읽지 않는다(요청 본문만 검증). 엔진은 레거시 enum을 쓰지 않고 문자열 상태로 4상태를 직접 처리한다. 두 enum이 섞이는 경로는 없다.
- **인정결석 정책 일관성**: 엔진은 EXCUSED → "인정결석" 표시, **보강 문장 없음**(결석만 보강 안내) — `test_phase8_template_engine.py:86-87`로 고정, 이번에 전수 비교로 재확인(6절). 레거시 미리보기에 EXCUSED를 넣으면 Java 계약(3상태, `invalid-enum` 400)과 Python이 달라지므로 **추가하지 않는다**. 대신 enum에 "Java 계약 전용, EXCUSED는 엔진이 처리" 주석을 남겼다.

### 1.4 의존성 변경이 Java 계약에 미치는 영향
문장 원문을 한 글자도 바꾸지 않고 **위치만 엔진으로 옮기고 레거시가 그것을 import**하므로 응답 본문은 동일하다. 계약 fixture 7건 + 전수 비교 5,264건으로 확인(6·7절). Java 소스·Java 서버는 손대지 않았다.

## 2. 실제 사용 중인 코드 vs 제거 후보
| 구분 | 항목 | 판정 |
|---|---|---|
| **사용 중 (Case A)** | `POST /api/messages/preview`, `app/domain.py`의 `validate_preview`·`compose_message`·enum, `app/models.py`의 요청/응답 모델 | 공개 API + Java 계약 테스트 대상. **유지** |
| **현행 규칙 (Case B)** | 학부모 안내 문장(예습·주간 등급 문장, 보강 문장) | 현행 메시지 엔진의 도메인 규칙 → **엔진으로 이동**(아래 3절) |
| **제거 후보 (Case C, 삭제 안 함)** | 프론트 `features/message-preview/*` + `/messages/preview` 라우트(메뉴 없음, URL로만 접근), 구 진입점 `src/App.tsx`(`main.tsx`가 쓰지 않으면 미사용 — 이번에 확정하지 않음), `/deliveries` ComingSoon 라우트, 백엔드 `/api/messages/preview`·`app/domain.py`·`app/models.py`의 미리보기 모델, `scripts/compare_contract.py`, 계약 fixture | 외부(Java 클라이언트·포트폴리오 문서·`openapi.yaml`) 사용 여부를 확인할 수 없고 Java 계약 테스트가 걸려 있음 → **Phase 11 "Java 유지·제거 결정" 때 함께 판단** |

## 3. 수정·유지·보류 결정과 이유
| 결정 | 내용 | 이유 |
|---|---|---|
| **수정** | 예습·주간 문장(`PREWORK_SENTENCE`, `WEEKLY_SENTENCE`)을 `notifications/engine.py`로 이동, 엔진의 `from app.domain import …` 제거. 보강 문장은 엔진의 기존 `MAKEUP_SENTENCE` 하나로 통일(레거시가 import) | 의존 방향이 **레거시 → 현행**으로 바로잡힘. Phase 11에서 레거시를 지울 때 엔진을 건드릴 필요가 없음(삭제만 하면 됨). 문장 규칙 출처 1곳 |
| **얇은 호환 래퍼 유지** | `app/domain.py`의 `_pre`/`_weekly`는 엔진 사전을 읽는 2줄 래퍼로 남김 | 기존 호출(`compose_message`)·테스트(`test_phase8_template_engine.py`의 `_pre` import) 계약 유지 |
| **유지** | `/api/messages/preview`, 레거시 enum(3상태), 프론트 미리보기 화면 | Case A — 공개 API·Java 계약 |
| **유지(안 바꿈)** | 빈 줄 정리 함수가 레거시(`compose_message`)와 엔진(`_normalize`)에 같은 4줄로 존재 | 업무 규칙이 아닌 텍스트 정리. 공통화하려면 엔진의 비공개 함수를 레거시가 import하는 새 결합이 생김 — 이득 < 결합. 레거시 삭제 시 자연 소멸 |
| **보류(Phase 11)** | 2절의 제거 후보 전부 | 개선 계획(B) 5절과 같은 이유 |

순환 의존: 없음. `app.domain → app.modules.notifications.engine`(엔진은 표준 라이브러리만 import), 엔진 → `app.domain` 경로는 제거됨(import 검사로 확인). 새 모듈·계층 없음.

## 4. 공통 업무 규칙 비교 (B-2 '진행된 수업')
| 비교 항목 | 메시지 처리 현황 (수정 전) | 출결 분석 | 같은가 |
|---|---|---|---|
| 도메인 개념 | 안내 의무가 생기는 '진행된 수업' | 출결 대상이 되는 '진행된 수업' | **같음** — `phase9-message-operations.md:16`이 정의, `phase10-metric-definitions.md:6`이 "메시지 처리 현황과 **같은 정의**"라고 명시, 분석 응답의 `policy.held_lesson` 문구도 같은 정의 |
| 상태·취소 | Python: CANCELLED 분기 먼저, `status == COMPLETED or 출결 1건 이상` | SQL: `status <> CANCELLED AND (COMPLETED OR 출결 존재)` | 같음 — 수업 상태는 DB CHECK로 3개뿐(SCHEDULED·COMPLETED·CANCELLED) |
| 날짜 경계 | 조회 끝 = `min(date_to, date.today())` (미래 수업은 조회하지 않음) | `lesson_date <= today`, `today = date.today()`, 끝 = `min(date_to, today)` | 같음 — 둘 다 서버 로컬 날짜, 오늘 포함 |
| 시간대 | 서버 로컬 `date.today()` | 같음 | 같음 (시간대 설정은 둘 다 없음 — 5·8절) |
| 수강·휴원 예외 | 수업 판정과 **분리**: 학생 단위는 `eligible_on` | 같음 (`eligible_on`) | 수업 판정은 같음. **학생 단위 대상은 의도적으로 다름**: 처리 현황은 자격 밖이어도 출결이 있으면 안내 의무, 분석은 '대상 외 기록'(`phase10-metric-definitions.md` 0절, 개선 계획 1절 "문제 없음") |
| 결과가 같은 이유 | 우연이 아니라 **명시된 공통 정책**이지만, 코드로는 두 구현(Python 판정 + SQL 식)이 문서로만 묶여 있었음 | | |
| 한쪽이 바뀌면 | 예: 새 수업 상태 추가, '완료'만 진행으로 보는 정책 변경 → 두 화면의 수업 집합이 같이 바뀌어야 함(같은 수업을 처리 현황은 '안내 대상', 분석은 '진행 기록 없음'으로 보이면 업무 혼선) | | **같이 바뀌어야 함** |

→ **같은 업무 불변식으로 확인되어 공통화.** 학생 단위 대상 차이는 다른 지표이므로 통합하지 않았다(새 테스트에서 차이를 명시적으로 고정).

공통화 방식: 기존 공용 규칙 위치인 `academics/repository.py`의 `eligible_on` 옆에 `held_lesson(today)`(SQL 식)를 두고, 분석·처리 현황 저장소가 import. 새 Service·유틸 모듈 없음. 모듈 의존 방향은 기존과 같음(`analytics → academics`, `message_operations → academics`는 이미 존재).

## 5. 실제 변경한 파일·함수
| 파일 | 변경 |
|---|---|
| `backend/app/modules/notifications/engine.py` | `from app.domain import …` 삭제. `PREWORK_SENTENCE`·`WEEKLY_SENTENCE` 추가(원문 동일), `_value()`의 예습·주간 분기가 사전 조회 사용. `MAKEUP_SENTENCE` 주석 정리 |
| `backend/app/domain.py` | 엔진 상수 import, `_pre`/`_weekly`를 2줄 래퍼로, `compose_message`의 보강 문장 리터럴 → `MAKEUP_SENTENCE`, `AttendanceStatus`에 계약 범위 주석 |
| `backend/app/modules/academics/repository.py` | `held_lesson(today)` 추가(분석 저장소에서 원문 그대로 이동, 문서 주석 보강) |
| `backend/app/modules/analytics/repository.py` | 자체 `held_lesson` 정의 삭제 → academics에서 import(같은 이름으로 계속 노출) |
| `backend/app/modules/message_operations/repository.py` | `recorded_lessons()`(출결 있는 수업 id) → `held_lessons(ids, today)`(공용 `held_lesson` 식으로 진행된 수업 id). 쿼리 수 동일(1회) |
| `backend/app/modules/message_operations/service.py` | `items()`: `today`를 한 번만 계산해 조회 끝·판정에 같이 사용, `held = lesson.id in held_ids`. 취소·미진행·대상 아님 분류 로직은 그대로 |
| `backend/tests/test_phase10_analytics_integration.py` | 신규 1건 `test_held_lessons_are_the_same_set_in_message_operations_and_analytics` |
| `docs/phase10-5-progress.md` | B-2·M4 상태 행 |

API 경로·요청·응답, DB 스키마, 프론트엔드, Java: **변경 없음**. C-1 변경(`notifications/service.py`, 프론트 2파일)과 H2·M2·M1 관련 코드: 손대지 않음.

## 6. 변경 전후 동작 동등성 검증
- **M4 전수 비교**(백업한 수정 전 `domain.py`·`engine.py` vs 수정 후, `scratchpad/compare_m4.py`): 레거시 미리보기 — 수업 유형 2 × 출결 입력 6(한글·영문) × 예습 4 × 주간 4 × 포함 플래그 27 = 5,184건 **본문 동일**. 엔진 — 출결 5(미입력·4상태) × 예습 4 × 주간 4 = 80건 **본문·issues·warnings·`source_hash` 동일**, EXCUSED는 보강 문장 없음. 합계 **5,264건 동일**.
  - `source_hash`가 같다는 것은 **이미 저장된 초안·확정 메시지가 이번 변경으로 '원본 변경'(C-1 차단)으로 오판되지 않는다**는 뜻.
- **B-2 동등성**:
  - 신규 테스트를 **수정 전 코드**(백업 6파일로 잠시 교체)에서 실행 → PASS, 복원 후 해시 일치 확인. 즉 두 화면의 결과는 수정 전에도 같았고 수정 후에도 같다(동작 변경 없음).
  - **변이 확인**: 처리 현황 판정만 `status == "COMPLETED"`로 바꾸면 신규 테스트 FAIL(`{L1,L2,L3,L6,L8} != {L1,L2,L3,L8}`) → 한쪽 규칙만 바뀌는 회귀를 잡는다. 복원 후 해시 일치.
  - 동치 근거: 처리 현황은 미래 수업을 조회하지 않고 CANCELLED를 먼저 분기하므로, 그 밖의 수업에서 공용 식은 `COMPLETED or 출결 존재`와 같다. 이제 `date.today()`를 한 번만 읽어 자정 경계에서 두 번 읽던 미세한 불일치 가능성도 없어짐.
- 신규 테스트가 고정하는 것: 진행된 수업 집합 일치(완료 3·**지난 예정+출결 1건**·같은 날 2교시), 진행 기록 없음(지난 예정+출결 0) = 처리 현황 `LESSON_NOT_HELD` = 분석 `not_held_lessons`, 취소 수업은 양쪽 모두 진행 아님(처리 현황은 면제 사유로 표시), 미래 수업은 양쪽 모두 없음, 수업별 대상 학생 수 동일(중도 등록·퇴원·휴원 포함 데이터) + **의도된 차이 1건**(L1의 퇴원생 출결 기록: 처리 현황 안내 의무 / 분석 대상 외).

## 7. 실행한 테스트 (2026-11-20, 실제 실행)
격리 테스트 DB `academy_learningops_test`@127.0.0.1:55432(컨테이너 라벨 `isolated-test`·`destructive-tests=allowed`, DB 이름·사용자 확인 후). 통합 테스트 픽스처가 이 DB 테이블을 비우고 가상 데이터를 넣음(기존과 같은 방식). 개발 DB(55431)·볼륨 접근 없음. 산출물·백업은 D 드라이브 scratchpad.

| 명령 | 결과 |
|---|---|
| 수정 전 기준선 `pytest`(단위 + PostgreSQL 전체) | **113 PASS** |
| `ruff check app tests alembic scripts` | PASS |
| `ruff format --check`(변경 파일) | 변경으로 인한 위반 없음. `analytics/repository.py` 끝 빈 줄 1개는 **수정 전부터 있던 것**(백업 파일도 같은 결과) — 범위 밖이라 그대로 둠 |
| 대상 묶음(phase8 엔진·phase9 처리 현황·phase10 분석·domain·계약 fixture·api) | 43 PASS |
| 신규 테스트 × 수정 전 코드 | PASS (동등성) |
| 신규 테스트 × 변이 코드 | FAIL (의도대로 검출) |
| 수정 후 `pytest` 전체 | **114 PASS** (113 + 신규 1), 실패 0 |
| `pytest -m "not postgres"` | 39 PASS (변동 없음) |
| M4 전수 비교 스크립트 | 5,264건 동일 |
| import 검사 | `app.main`·`app.domain` 단독 import 정상, 엔진에 `app.domain` import 없음, `analytics.repository.held_lesson` 이름 유지 |
| Vitest / tsc / build | **미실행** — 프론트엔드 변경 없음 |
| Java `mvn test`, `scripts/compare_contract.py` | **미실행** — Java 소스 변경 없음, 비교 스크립트는 Java·Python 서버 동시 기동 필요. Java 쪽 동등성은 Java와 공유하는 계약 fixture(Python 측 7건 PASS)와 문장 원문 전수 동일로 간접 확인한 것에 한정 |

## 8. 미해결 위험 및 Phase 11 이관
| 항목 | 내용 |
|---|---|
| M4 제거 범위 결정 | 2절 제거 후보(백엔드 미리보기 API·`app/domain.py`·모델, 프론트 미리보기 화면·라우트·`App.tsx`, `/deliveries`, 계약 fixture·비교 스크립트, `openapi.yaml`) — Java 유지·제거 결정과 함께. **이번 변경으로 엔진은 이 삭제에 영향받지 않음** |
| 시간대 | 두 화면 모두 서버 로컬 `date.today()`. 서버를 KST 외 시간대(예: UTC 컨테이너)로 배포하면 오전 9시 전 '오늘 수업'이 미래로 취급될 수 있음 — 두 화면이 **같이** 틀어지므로 불일치는 아님. 배포 준비(M6)에서 기준 시간대 결정 |
| `lesson_counts`의 '진행 기록 없음' | 분석의 `not_held` 집계는 `SCHEDULED AND 출결 없음`을 별도 식으로 가짐(처리 현황의 `LESSON_NOT_HELD` 분기와 같은 결과, 신규 테스트로 고정). 수업 상태가 추가되면 함께 검토 |
| **(신규 발견) 테스트 안전장치 스크립트** | `scripts/run-postgres-integration.ps1:15`의 `docker inspect --format '…"academy.environment"…'`는 Windows PowerShell 5.1에서 큰따옴표가 빠져 템플릿 오류 → `$identity`가 비어 **라벨 검사가 통과해 버림**(이번 세션에서 같은 패턴으로 재현). 다음 줄의 DB 이름·사용자 검사와 URL의 고정 포트(55432)가 남아 있어 개발 DB로 갈 수는 없지만, 이중 안전장치 중 하나가 무력함. 이번에는 범위 밖이라 수정하지 않았고, 이번 세션의 실행은 `\"`로 이스케이프하고 빈 값이면 거부하도록 고친 별도 스크립트로 함. **Phase 11 초반에 1줄 수정 권장** |
| 원본 행 잠금(C-1 이관) | 변동 없음 |

## 9. 전체 아키텍처에 미친 영향
- 의존 방향: `notifications(현행) → app.domain(레거시)` 제거, `app.domain → notifications.engine`으로 역전. 레거시가 현행에 기대는 단방향이 되어 레거시는 **잎(leaf) 노드**. 순환 없음.
- 단일 규칙 위치: 학부모 안내 문장 = `notifications/engine.py`, 진행된 수업 = `academics/repository.py:held_lesson`(같은 파일의 `eligible_on`과 함께 '수업일 기준 판정' 공용 규칙 두 개가 한 곳에).
- 모듈 수·계층·API·스키마 변화 없음. 앱 코드 순 증감 +7줄(엔진 +12, `domain.py` −8, academics +16, 분석 −12, 처리 현황 저장소 −3·서비스 +2 — 대부분 규칙 설명 주석). 코드량 감소가 목적이 아니었고 실제로 줄지도 않았다.
- 개선 계획 9절 '모듈 응집도·결합도' 감점 사유 2건(진행된 수업 이중 구현, 엔진의 레거시 비공개 함수 의존)이 해소됨.

---

## 최종 답변: "유지보수 비용과 변경 위험을 줄였는가, 아니면 코드 위치만 옮겼는가?"

**줄였다. 다만 두 건 모두 효과의 크기는 '중간'이고, 그 이상을 주장하지 않는다.**

- **B-2 — 실질적 개선.** 이전에는 같은 정책이 Python 분기와 SQL 식 두 곳에 있었고, 문서 문장 하나가 둘을 묶고 있었다. 이제는 식이 하나이고, 두 화면이 같은 결과를 내는지 **테스트가 직접 비교**한다. 변이 실험으로 보였듯, 앞으로 한쪽만 바꾸면 테스트가 실패한다. 이전에는 각 화면 테스트가 자기 기대값만 확인해서, 두 테스트를 함께 고치면 불일치가 조용히 통과할 수 있었다.
- **M4 — 의존 방향의 개선이지 코드 감소가 아니다.** 문장은 같은 내용으로 옮겨졌을 뿐이라 이것만 보면 '위치 이동'이다. 그래도 남는 효과가 두 가지 있다. ① 현행 핵심 경로가 레거시 파일의 비공개 함수에 기대지 않게 되었다. Phase 11에서 레거시 삭제를 결정하면 엔진을 고치지 않고 파일만 지우면 된다. ② 문장 출처가 하나가 되었다. 이전에는 보강 문장이 두 군데 복사되어 주석으로만 동기화되었다. 레거시 API·화면 자체를 지우는 것이 진짜 비용 절감인데, 그것은 Java 계약과 외부 사용 여부를 확인할 수 없어서 **하지 않았다**(Phase 11 결정 사항).
- 하지 않은 것: 빈 줄 정리 함수 공통화, 레거시 enum에 EXCUSED 추가, 미리보기 API·화면 삭제. 각각 이득보다 새 결합이나 계약 위험이 커서 현 구조를 유지했다.
