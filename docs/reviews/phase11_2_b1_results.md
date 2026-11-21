# Phase 11-2-B-1 — 학생 식별 보안 결함(SEC-01)·관리자 감사 로그(SEC-02) 보완 결과

작업일: 2026-11-20 · 기준 문서: `phase11_2_security_audit.md`(SEC-01 High, SEC-02 Medium)
범위: SEC-01·SEC-02만 수정. SEC-03 이후 항목, H2(엑셀 덮어쓰기)·M2(보호자 이메일 노출) 정책, 인증·RBAC·CSRF 구조는 건드리지 않았다.
**DB 스키마·Migration 변경 없음. 신규 라이브러리 없음.** 수정 전 원본은 저장소 밖(scratchpad `backup\`)에 백업했다(Git 없음).

---

## 1. 수정한 파일·함수

| 파일 | 함수·위치 | 변경 |
|---|---|---|
| `backend/app/modules/lesson_upload/service.py` | 모듈 docstring, 상수 `STUDENT_KEY_INDEX`·`EXISTING_STUDENT_TEXT` | SEC-01 정책 명시, 안내 문구(다른 학생 정보 없음) |
| 〃 | `_taken_student_keys()` (신규) | 학생 업무 키(`name + coalesce(school_name,'')`)가 이미 있는 이름 집합만 반환(누구·어느 반인지는 조회하지 않음) |
| 〃 | `_analyse_block()` | 담당 반 블록에서, 이 반에 없는 미등록 행의 키가 이미 있으면 `existing_student_conflict=True` + 경고 |
| 〃 | `_analyse_row()` | 행 기본값 `existing_student_conflict: False` |
| 〃 | `_resolve()` NEW 분기 | **기존 학생 조회·재사용 코드 삭제.** 충돌 행이면 400 `EXISTING_STUDENT_ELSEWHERE`, 아니면 항상 새 `Student` 생성 |
| 〃 | `confirm()` 예외 처리 | 확인 직후 다른 요청이 같은 키를 만든 경우(유니크 인덱스 위반) 409 `EXISTING_STUDENT_ELSEWHERE` + 전체 롤백 |
| `backend/app/modules/lesson_upload/schemas.py` | `UploadRowView` | 응답 필드 `existing_student_conflict: bool = False` 추가(기존 필드 변경 없음) |
| `backend/app/modules/learningops/service.py` | `_flush()`·`_assignment_snapshot()`·`_assignments_of()`·`_audit_enrollment()` (신규 보조) | 감사 행에 ID가 필요하므로 flush 후 같은 트랜잭션에서 감사 추가 |
| 〃 | `create_classroom`·`create_student`·`enroll`·`assign`·`remove_assignment`·`create_staff`·`update_staff_profile`·`update_staff_status` | 감사 기록 추가(2절 표). 서명에 `principal`·`request_id` 추가 |
| 〃 | `delete_staff`(HARD)·`delete_classroom` | CASCADE로 함께 지워지는 배정의 스냅샷을 기존 `STAFF_DELETED`/`CLASSROOM_DELETED` 상세에 `assignments_removed`로 추가 |
| `backend/app/modules/learningops/repository.py` | `revoke_sessions()` | 폐기한 세션 수 반환(기존 호출부 영향 없음) |
| `backend/app/modules/learningops/router.py` | 라우트 8곳 + `_request_id()` | `principal`·`request_id` 전달만 추가(경로·의존성·요청/응답 스키마 동일) |
| `frontend/src/features/notifications/uploadApi.ts` | `UploadRow` | 선택 필드 `existing_student_conflict?` |
| `frontend/src/features/notifications/UploadTab.tsx` | `decisionCell` | 충돌 행은 '신규 수강생인가요? → 예' 버튼 비활성 + 안내. '아니요 → 제외'는 그대로 가능 |
| `backend/tests/test_phase112_security_fixes_integration.py` | 신규 | SEC-01 9건 + SEC-02 3건 회귀 테스트 |
| `backend/tests/test_phase6a_learningops_integration.py` | 반 감사 순서 검증 1곳 | 새 `CLASSROOM_CREATED`를 제외하도록 조건 조정(감사 기록 추가에 따른 기대값 조정) |
| `frontend/src/features/notifications/NotificationsPage.test.tsx` | 신규 테스트 1건 | 충돌 행 '신규' 비활성·제외 가능 |

## 2. SEC-01 수정 내용과 학생 식별 정책

### 원인
`_resolve`의 NEW 분기가 `select(Student).where(name == …, same_school) or Student(...)`로 **같은 이름(·학교)의 기존 학생을 말없이 재사용**했다. 대상 반이 담당 반이면 통과하므로, 담당 반 A의 선생님·조교가 반 B 학생을 A에 붙이고 메시지 상세에서 그 보호자 이메일을 볼 수 있었다. 동명이인(정규반은 학교 없음)은 한 학생으로 합쳐졌다.

### 적용한 정책
1. **업로드의 '신규'는 언제나 새 학생을 만든다. 기존 학생과 연결하지 않는다.** 역할과 무관하다(관리자 포함). 관리자용 '기존 학생 연결' 선택지는 만들지 않았다.
2. 이름·학교로 동일인을 확정하지 않는다. 업무 키(이름+학교)가 이미 있으면 업로드는 **판단하지 않고 멈춘다.**
   - 미리보기: 행은 `UNREGISTERED` 그대로, `existing_student_conflict=true` + 경고 "같은 이름(·학교)의 학생이 이미 등록되어 있어 … 관리자가 학생·반 관리에서 수강 등록하거나, 다른 학생이면 학교 정보로 구분해 등록해야 합니다. 이번 업로드에서는 '제외'를 선택하세요."
   - 확정: 그 행에 NEW를 보내면 400 `EXISTING_STUDENT_ELSEWHERE`, **아무것도 저장하지 않는다**(같은 파일의 다른 행·수업·감사·초안 포함). '제외'로 결정하면 나머지는 정상 저장된다.
3. 기존 학생을 이 반에 넣는 일은 기존 관리자 전용 기능(`POST /api/classrooms/{id}/enrollments`, `POST /api/students`)으로만 한다.
4. **Preview → Confirm 사이 변경**: 확정 시 `analyse()`를 다시 실행하므로 미리보기 이후 생긴 같은 키 학생도 잡힌다. 검사와 INSERT 사이의 동시 등록은 DB 유니크 인덱스 `uq_student_business_key`가 거부하고, 이를 409 `EXISTING_STUDENT_ELSEWHERE`로 바꿔 전체를 롤백한다. 어떤 경로에서도 기존 행을 재사용하는 코드는 남아 있지 않다.
5. **개인정보**: 충돌 검사는 "그 키가 있는가"만 본다. 학생 ID·반·연락처는 조회·응답하지 않는다. 담당 반이 아닌 블록은 검사 자체를 하지 않는다(이름 존재 신호도 주지 않음). 기존 담당 반 접근 검사·역할 검사는 그대로다.
6. 진짜 신규(키 없음)는 기존처럼 생성·수강·`ENROLLMENT_CREATED_FROM_UPLOAD` 감사·초안 생성된다. 휴원 복귀(RETURNING)·제외는 변경 없다.

### 상황별 동작
| 상황 | 결과 |
|---|---|
| 처음 보는 이름(정규반·학교 없음) | 신규 생성(기존과 동일) |
| 같은 이름 학생이 다른 반에 있음(정규반, 학교 없음 = 같은 키) | 확인 필요 → NEW 거부. 같은 아이면 관리자가 수강 등록, 다른 아이면 관리자가 학교 정보로 구분해 등록 → 이후 업로드는 이 반 학생과 MATCHED |
| 같은 이름·학교 학생이 **어느 반에도 없음** | 역시 연결하지 않음(NEW 거부) |
| 내신반(`00고1 토10` → 학교 `00고`)인데 기존 `x`는 학교 없음 | 키가 달라 새 학생 `x/00고` 생성. 기존 `x`는 건드리지 않음 |
| 같은 반 명단에 같은 이름 2명 / 파일에 같은 이름 2행 | 기존대로 `INVALID` |
| 담당 반이 아닌 블록 | 기존대로 "담당 반이 아닙니다"로 확정 차단, 충돌 검사 안 함 |

### 기존 DB 제약과의 관계(동명이인 등록이 영구 차단되지 않는가)
- 학생 업무 키 `UNIQUE(name, coalesce(school_name,''))`는 **원래부터** 같은 이름·학교 없음 학생 2명을 허용하지 않는다(관리자 `POST /api/students`도 409 `STUDENT_BUSINESS_KEY_CONFLICT`). 이번 수정은 이 정책을 바꾸지 않았다.
- 서로 다른 아이는 관리자가 학교 정보로 구분해 등록할 수 있고, 등록 후 업로드는 반 명단 기준으로 정확히 그 학생과 연결된다(테스트로 확인). 따라서 정상 등록이 영구 차단되지는 않는다.
- 다만 **학교 정보로도 구분할 수 없는 동명이인**(예: 같은 학교 같은 이름, 또는 학교를 모름)은 현재 키 구조로 두 학생을 만들 수 없다. 이를 해결하려면 새 식별 정보(생년, 학생 번호 등)와 스키마 변경이 필요하다. 지시대로 임의로 도입하지 않았다 → 6절 승인 사항.

## 3. SEC-02 감사 로그 보완 범위

기존 `audit_log` 테이블과 `LearningOpsService._audit()`를 재사용했다. 행위자(`actor_staff_user_id`), 행위(`event_type`), 대상(`target_type`·`target_id`), 시각(`created_at`), 요청(`request_id`)이 모두 남는다. 모든 기록은 **업무 변경과 같은 세션·같은 commit**에서 저장된다(flush로 ID 확보 → 감사 추가 → commit). 제약 위반 등 업무 실패 시 rollback되어 성공 감사가 남지 않는다.

| 작업 | event_type | target_type | details(이름·이메일·비밀번호·세션 정보 없음) |
|---|---|---|---|
| 직원 생성 | `STAFF_CREATED` | `STAFF_USER` | `role`, `status` |
| 직원 이름 변경(실제 변경 시만) | `STAFF_RENAMED` | `STAFF_USER` | `changed: ["display_name"]` (값 없음) |
| 직원 활성화·비활성화(실제 변경 시만) | `STAFF_STATUS_CHANGED` | `STAFF_USER` | `before`, `after`, `role`, `sessions_revoked`(개수) |
| 반 등록 | `CLASSROOM_CREATED` | `CLASSROOM` | `name`, `class_type` (기존 `CLASSROOM_DELETED`와 같은 형식) |
| 담당 반 배정 | `ASSIGNMENT_CREATED` | `CLASSROOM_STAFF_ASSIGNMENT` | `assignment_id`, `classroom_id`, `staff_user_id`, `assignment_role`, `valid_from`, `valid_to` |
| 담당 반 배정 해제 | `ASSIGNMENT_REMOVED` | 〃 | 삭제 직전 같은 스냅샷 |
| 학생 등록 | `STUDENT_CREATED` | `STUDENT` | `school_present`, `parent_name_present`, `parent_email_present`, `enrollment_id` |
| 학생 등록 시 함께 수강 | `ENROLLMENT_CREATED` | `ENROLLMENT` | `classroom_id`, `student_id`, `enrolled_at`, `status`, `source: STUDENT_REGISTRATION` |
| 수동 수강 등록 | `ENROLLMENT_CREATED` | `ENROLLMENT` | 위와 같고 `source: MANUAL` |
| (보강) 직원 HARD 삭제·반 삭제 시 CASCADE된 배정 | 기존 `STAFF_DELETED`·`CLASSROOM_DELETED` | — | `assignments_removed: [스냅샷…]` 추가 |

- **수강 상태 변경**: 현재 API에서 수강 상태를 바꾸는 경로는 휴원(`ENROLLMENT_PAUSE_RECORDED`)·복귀(`ENROLLMENT_RESUMED`, 수동·업로드)뿐이며 이미 감사되고 있다. 퇴원 처리 API는 없다. 추가 작업 없음.
- **FK·ON DELETE 확인**: `audit_log.actor_staff_user_id`는 `ON DELETE SET NULL`이고 대상은 문자열 `target_id`라 FK가 없다. 배정 행이 삭제(직접 해제·직원 HARD 삭제 CASCADE·반 삭제 CASCADE)되어도 감사 행은 남는다. 배정 해제는 기존대로 물리 삭제해 즉시 권한을 회수한다. 이력은 감사 스냅샷으로 보존한다(스키마 변경 없음, 감사 문서 7절 권장안).
- **직원 삭제 판정 영향 없음**: `staff_has_history`는 *행위자* 기록만 보므로, 관리자가 행위자인 새 감사 행이 대상 직원을 SOFT 삭제로 바꾸지 않는다(기존 HARD/SOFT 테스트 통과).
- 조회(GET)는 기록하지 않는다.

## 4. 테스트 결과

### 테스트 DB 격리 확인(실행 전)
`scripts/run-postgres-integration.ps1`의 검사 블록을 그대로 실행해 확인했다.
- `academy-learningops-postgres-test` → 통과(라벨 `isolated-test`/`allowed`, 포트 `127.0.0.1:55432`, DB·사용자 `academy_learningops_test|academy_test`)
- `academy-learningops-postgres-dev`, `academy-postgres`, 없는 컨테이너 → 모두 거부
- DB 테스트는 같은 검사를 거친 Python 전용 실행기(scratchpad)로 수행했다. 각 픽스처도 `current_database()/current_user`를 다시 확인한다. 개발 DB·볼륨·`academy-postgres`에는 접근하지 않았다. 데이터는 모두 가상 값(`*.invalid`)이다.

### 결과
| 항목 | 결과 |
|---|---|
| Ruff `check app tests` | **All checks passed** |
| Ruff format(수정한 모듈) | 통과(저장소 전체 format 불일치 몇 건은 기존 파일, 손대지 않음) |
| Backend 단위 테스트(`-m "not postgres"`) | **39 passed** |
| Backend PostgreSQL 통합 전체(기존 보안 테스트 포함) | **94 passed**(신규 12 포함). 첫 실행 1건 실패 → 1절의 감사 기대값 조정 후 통과 |
| 신규 SEC-01 테스트의 결함 검출력 | 수정 전 `service.py`로 바꿔 실행 → SEC-01 회귀 7건 **실패**(진짜 신규·담당 외 반 2건은 통과가 정상), 복원 후 통과 |
| Frontend `tsc -b` | 통과 |
| Frontend `src/features/notifications` | 22 passed / 1 failed — 실패 1건은 **기존 결함**(아래) |
| Frontend 전체 vitest | 14 파일 중 13 통과 · **105 passed / 1 failed**(실패는 아래 기존 결함 1건과 동일) |

**신규 회귀 테스트(`test_phase112_security_fixes_integration.py`)**
- SEC-01
  - `test_new_decision_never_links_another_class_student[teacher|assistant|admin]`: 11-2-A 재현 스크립트를 회귀 테스트로 바꿨다. 미리보기 플래그, 확정 400, 학생·수강·수업·결과·평가·초안·감사 행 수 불변(부분 저장 없음), 제외 시 나머지 저장, 반 B 학생 미수강, 메시지 목록·상세·응답에 반 B 보호자 이메일·반 이름 없음, 선생님·조교의 반 B 조회·수동 수강 403(통제 유지)
  - `test_same_name_student_is_registered_by_admin_not_by_upload`: 동명이인. 관리자 같은 키 등록은 409(기존 정책), 학교로 구분해 등록하면 업로드가 이 반 학생과 MATCHED되고 반 B 학생에게는 기록되지 않음
  - `test_school_follows_exam_prep_class_and_any_taken_key_blocks_new`: 학교 누락·내신반 학교, 어느 반에도 없는 기존 학생도 연결 안 함
  - `test_student_registered_between_preview_and_confirm_is_not_linked`: Preview/Confirm 사이 데이터 변경
  - `test_concurrent_insert_of_the_same_key_rolls_back_the_whole_upload`: 검사 통과 후 동시 등록 → 409, 전체 롤백
  - `test_genuinely_new_student_is_still_registered`: 정상 신규 등록(조교)
  - `test_upload_to_a_class_not_assigned_reveals_no_student_key`: 담당 외 반은 차단되고 키 검사 신호 없음
- SEC-02
  - `test_admin_management_changes_are_audited`: 8종 이벤트의 행위자·대상·request_id·시각, 변경 없는 요청은 감사 없음, 배정 해제 후 행은 없어도 생성·해제 스냅샷 보존, 이메일·이름·비밀번호·보호자 정보 미기록
  - `test_failed_or_unauthorised_changes_leave_no_audit_row`: 409 실패 5종에서 감사 없음, 선생님의 8개 변경 요청 403 및 감사 없음, **감사 INSERT를 강제로 실패시키면 업무 변경(반 등록·배정 해제·직원 비활성화)도 롤백**(동일 트랜잭션 입증)
  - `test_assignments_removed_with_a_staff_account_or_class_stay_on_record`: CASCADE 삭제된 배정의 스냅샷 보존

**기존 프론트 테스트 실패(이번 변경과 무관)**: `NotificationsPage.test.tsx` › "uploads only the chosen time slot and reports rows already equal to the app as skipped"가 시트 체크박스 클릭 후 '미리보기' 버튼 활성화를 기다리다 실패한다. **수정 전 `UploadTab.tsx`로 되돌려 단독 실행해도 같은 실패**가 나므로 기존 문제다. 고치지 않았다(범위 밖).

**실행하지 않은 것**: Java(Maven) PostgreSQL 테스트(이번 변경은 Python 백엔드만 해당), 실제 브라우저 확인.

## 5. API·DB 호환성
- **DB**: 스키마·제약·인덱스·Migration 변경 없음. 기존 `audit_log` 컬럼만 사용한다.
- **요청**: 모든 라우트의 경로·메서드·요청 본문·인증/CSRF 의존성이 같다. 서버 내부에서 `Request`만 추가로 받는다.
- **응답**: 업로드 미리보기 행에 `existing_student_conflict`(기본 `false`) 필드가 추가되었다(추가만, 기존 클라이언트 무시 가능). 관리 API 응답은 변경 없다.
- **동작 변경(의도된 것)**: 업로드 확정에서 같은 키 학생이 있는데 NEW를 보내면 이전에는 200(기존 학생 재사용)이었고, 이제는 400/409 `EXISTING_STUDENT_ELSEWHERE`다. 이 경우 외의 업로드 결과는 같다.
- **감사 로그 소비자**: 새 event_type 7종이 추가되고 `STAFF_DELETED`·`CLASSROOM_DELETED` 상세에 키 1개가 추가되었다. 감사 행 수를 그대로 세는 테스트 1곳을 조정했다.

## 6. 해결되지 않은 사항·승인 필요
| # | 내용 | 영향 | 필요한 결정 |
|---|---|---|---|
| 1 | **학교로도 구분되지 않는 동명이인**(같은 학교 같은 이름, 또는 학교 정보 없음)은 현재 학생 키로 두 명을 만들 수 없다(기존부터 그렇다). 이번에는 합치지 않고 멈추게만 했다 | 해당 학생은 업로드로 신규 등록 불가. 관리자가 학교 칸에 구분 값을 넣어 등록하는 것이 현재 유일한 우회 | 학생 식별자(예: 생년, 학생 번호) 도입과 키 변경 여부. **스키마 변경이 필요하므로 별도 승인 필요** |
| 2 | 충돌 경고는 "이 이름(·내신반이면 학교)의 학생이 어딘가에 있다"는 사실만 알려 준다(담당 반 블록에서만). 반·연락처·ID는 알 수 없다 | Low. 업무상 안내에 필요한 최소 정보. 이전에는 아무 표시 없이 연결되었다 | 수용 여부 확인 |
| 3 | 내신반 업로드에서 학교 없는 기존 `x`와 다른 키 `x/00고`는 새 학생으로 생성된다. 같은 아이라면 중복 기록이 될 수 있다(기존 동작과 같음, 합치지는 않음) | 데이터 품질 문제. 보안 문제는 아님 | 필요하면 관리자 화면에서 정리하는 운영 지침 |
| 4 | 배정 해제는 계속 물리 삭제한다. 이력은 감사 스냅샷으로만 남는다 | 조회 화면이 없어 DB에서 직접 확인해야 함 | `valid_to` 종료 방식 전환은 의미·CHECK 제약 검토가 필요하므로 별도 승인 |
| 5 | 감사 로그 조회 API·화면 없음 | 사후 추적은 DB 질의로 | 이후 단계 검토 |
| 6 | 위 기존 프론트 테스트 1건 실패 | 테스트 신뢰도 | 별도 수정 작업 |

## 7. 최종 판정 — **PASS**
- SEC-01: 업로드 NEW에서 기존 학생을 재사용하는 코드를 제거했다. 미리보기 '확인 필요', 확정 거부, 확정 시 재검사, DB 유니크 위반 시 전체 롤백의 3중으로 막았다. 다른 반 학생의 수강 연결과 보호자 이메일 노출 경로가 차단되었고, 수정 전 코드에서 실패하는 회귀 테스트로 고정했다. RBAC·담당 반 접근 제어는 그대로다.
- SEC-02: 지적된 관리 작업 8종(직원 생성·상태·이름, 배정·해제, 수동 수강, 학생·반 등록)을 업무 변경과 같은 트랜잭션에서 감사한다. 배정이 삭제되어도 스냅샷이 남고, 개인정보·비밀정보는 기록하지 않는다.
- 남은 항목(6절)은 정책·스키마 결정이 필요한 사항이나 기존 테스트 결함이며, SEC-01·SEC-02의 완료 기준을 막지 않는다.
