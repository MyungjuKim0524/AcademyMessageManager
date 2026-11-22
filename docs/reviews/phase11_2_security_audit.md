# Phase 11-2-A — 보안 아키텍처 감사 및 수정 계획

작업일: 2026-11-20 · 범위: FastAPI 백엔드(`backend/app`), React 프론트엔드(`frontend/src`) 인증·API 계층, 설정·스크립트
방식: 라우트 전수 목록(의존성 자동 추출) → 고위험 경로 코드 추적 → 기존 보안 테스트 실행 → 의심 경로 1건은 격리 테스트 DB에서 재현
**소스코드·DB 스키마·설정은 수정하지 않았다.** 산출물은 이 문서 1개다. 재현 스크립트는 저장소 밖(scratchpad)에 있다.
참고 문서: `phase10_5_architecture_review.md`, `phase10_5_improvement_plan.md`, `phase10_5_c1/c2_results.md`, Phase 11 변경 문서(`docs/phase11-*.md`). Phase 11-1 테스트 결과 문서는 따로 없다.

---

## 1. Executive Summary

인증·세션·CSRF·역할·담당 반 경계는 **기본기가 잘 갖춰져 있다.**
- Argon2와 더미 해시로 계정 존재를 추론하기 어렵다.
- 토큰은 해시로만 저장하고, 매 요청마다 세션·직원 상태·담당 반 배정을 다시 확인한다.
- 상태를 바꾸는 요청은 모두 CSRF 검사를 받는다(로그인 제외).
- 객체 ID는 반 안에서만 해석한다.

이 내용을 기존 보안 테스트 60건(격리 DB)으로 확인했고, 모두 통과했다.

**확인된 결함은 1건(High)이다. 격리 DB에서 재현했다.**
- 엑셀 업로드에서 '신규' 결정을 하면, 같은 이름(·학교)의 **기존 학생을 말없이 재사용**한다.
- 그 결과 ① 담당 반만 가진 선생님·조교가 다른 반 학생을 자기 반에 붙이고 그 **보호자 이메일을 볼 수 있다.**
- ② 악의 없이도 동명이인(정규반은 학교가 비어 있음)이 **한 학생으로 합쳐져 성적 안내가 다른 아이의 보호자에게 갈 수 있다.**

그 밖에 다음 항목이 있다.
- **M1 감사 공백(Medium)**: 직원·권한·수강 관리 이벤트가 감사되지 않고, 배정 해제는 이력이 사라진다.
- **배포 시 필수 조치(Medium/Informational)**: 프록시 뒤 로그인 제한, 실행 모드 게이트, 문서 노출, 쿠키·HSTS.
- **방어 강화(Low)**: 유휴 만료, 업로드 자원 한도, 로그 개인정보.

**최종 판정: CONDITIONAL PASS.** SEC-01(High)과 M1(SEC-02)을 Phase 11-2에서 고치면 PASS로 볼 수 있다. 배포 관련 항목은 Phase 11-5 필수 검증으로 넘긴다.

## 2. 보안 아키텍처 및 공격 표면

```
브라우저(React, axios withCredentials + X-CSRF-Token)
  → (개발) Vite 프록시 /api → FastAPI 127.0.0.1:8000
  → CompatibilityMiddleware: Origin 허용 목록·CORS·본문 크기(JSON 16KB / 업로드 10MB+64KB)·보안 헤더·접근 로그
  → 라우터 의존성: require_local_db_api(실행 모드 게이트) → get_current_principal(세션) → require_roles / require_csrf / require_admin_csrf
  → 서비스: 역할 집합(LESSON_WRITERS 등) + _require_classroom(담당 반) + 반 안에서 ID 해석
  → PostgreSQL(RESTRICT FK·CHECK·UNIQUE·트리거) + audit_log(변경과 같은 트랜잭션)
```

**라우트 전수(81개, 의존성 자동 추출 결과 요약)**
- 인증 없음: `GET /api/health`, `POST /api/auth/login`, FastAPI 기본 `/docs`·`/redoc`·`/openapi.json`(SEC-08)
- 세션만, 상태 변경 없음(조회·계산): GET 전부, `POST …/notification-templates/validate`, `POST /lessons/{id}/notifications/preview`, `POST /lesson-uploads/sheets|preview`, `POST /api/messages/preview`. **모두 쓰기를 하지 않는다**(코드 확인).
- 세션 + CSRF: 나머지 POST/PATCH/PUT/DELETE 전부(로그아웃 포함). 관리자 전용은 `require_admin_csrf`.
- 역할·객체 검사는 서비스에서 한다: 수업 등록·수정은 관리자·선생님, 출결·성적·평가는 담당 반 전원, 수강·휴원·복귀(수동)·템플릿 관리는 관리자, 메시지 확정·발송은 담당 반 전원(2026-11-18 정책).
- 파일 입력: `/api/lesson-uploads/*`(XLSX). 구 CSV/XLSX 가져오기는 제거되었다.

## 3. 인증·세션 평가
| # | 항목 | 결과 | 근거 |
|---|---|---|---|
| 1 | 비밀번호 해싱 | **양호**: Argon2(`argon2-cffi`), 재해싱 필요 시 갱신 | `auth/service.py:18,22-34,107-108` |
| 2 | 로그인 실패 처리·계정 추론 | **양호**: 없는 계정은 더미 해시로 같은 시간 검증. 비활성·틀린 비밀번호·없는 계정 모두 같은 401 문구 | `auth/service.py:26-34,99-105`, 테스트 `test_invalid_inactive_rate_limit_and_no_enumeration` |
| 3 | 로그인 후 세션 재발급 | **양호**: 로그인마다 새 무작위 토큰(32바이트). 전달된 기존 쿠키를 쓰지 않음 → 세션 고정 불가 | `auth/service.py:110-119` |
| 4 | 로그아웃 | **양호**: 서버에서 `revoked_at` 기록 + 쿠키 삭제, 재사용 차단 | `auth/router.py:75-86`, 테스트 `test_login_me_logout_and_session_reuse_is_blocked` |
| 5 | 만료·비활성 차단 | **양호**: 매 요청마다 폐기·만료·직원 `ACTIVE` 확인. 비활성화·삭제 시 세션 폐기 | `auth/dependencies.py:39-59`, `learningops/service.py`(update_staff_status·delete_staff) |
| 5a | 유휴 만료 | **미흡(SEC-05)**: `last_seen_at` 미갱신, 로그인 후 8시간 절대 만료만 | `config.py:36`, `tables.py:453` |
| 6 | 쿠키 속성 | 세션: HttpOnly·SameSite=Lax·Path=/·Secure(기본 켜짐, 환경변수로 끔). CSRF: JS가 읽어야 하므로 HttpOnly 아님(이중 제출 패턴상 정상). Domain 미지정(호스트 전용) | `auth/router.py:26-45`, `config.py:35` |
| 7 | 토큰 로그 노출 | **없음**: 토큰은 SHA-256 해시로만 저장. 접근 로그는 메서드·경로·상태·요청 ID만 남김(쿼리·헤더·쿠키 없음) | `auth/service.py:116-117`, `middleware.py:165-174` |
| 8 | 반복 로그인 제한 | 클라이언트 IP별·IP+이메일별 15분 5회. **프로세스 메모리**에 두고 키를 지우지 않음. **프록시 뒤에서는 모든 사용자가 같은 IP(SEC-03)** | `auth/service.py:49-84`, `auth/router.py:55` |
| 9 | 계정 존재 추론 | 응답 문구·상태 동일(2와 같음) | 위와 같음 |
| 10 | 세션 저장소 | DB(`auth_session`, 토큰·CSRF 해시). **만료 행 정리 작업 없음**(SEC-05 부속) | `tables.py` AuthSession |
- 비밀번호 정책: 직원 생성 시 12자 이상. 본인 비밀번호 변경·재설정 기능이 없다(SEC-10, 정보).

## 4. RBAC·객체 접근 제어 평가
- **미인증 차단**: 세션이 필요한 라우트는 모두 `get_current_principal`을 거친다(자동 추출로 확인). 테스트 `test_requests_need_a_session…`, 업로드·배치 401 테스트.
- **역할 구분**: 관리자 전용 API(직원·반·학생·수강·배정·템플릿 관리)는 `require_admin(_csrf)` 또는 서비스 `_require_role(ADMIN)`. 프론트 `/staff`도 관리자 전용(`router.tsx:29`)이지만, **서버가 독립적으로 거부한다**(UI 숨김에만 의존하지 않음. 예: 선생님 직원 삭제 403 테스트).
- **담당 반 경계**: `can_access_classroom`(오늘 날짜로 배정 유효 기간 확인) 단일 구현을 모든 모듈이 사용한다. 배정 해제·비활성화 즉시 반영(요청마다 재검사). 테스트 `test_assignment_revocation_and_inactive_staff`, `test_cross_classroom_access_revocation_and_inactive_staff`.
- **IDOR(경로·본문 ID)**: 모두 반 안에서 해석한다.
  - 수업·평가 ID → 그 반 검사 → 이후 처리
  - `records/{enrollment_id}`: 다른 반이면 404
  - `pauses/{pause_id}`: 열린 휴원과 일치해야 함(`academics/service.py:667-671`)
  - 학생 기록·분석 학생 ID: `enrollment_of_student`로 반 소속 확인
  - 처리 현황 상세: 수업의 반 403 → 의무 목록 안에서만 조회
  - 메시지 일괄 처리: 다른 수업 ID는 `NOT_IN_LESSON`
  - 초안 생성 `enrollment_ids`: 다른 반은 데이터 없음 + 복합 FK
  - 테스트: `test_access_is_limited_to_assigned_classes_and_ids_cannot_cross_classes`, `test_assignment_concurrency_listing_revocation_and_bola` 등
- **예외 — SEC-01(High)**: 업로드 '신규' 결정이 반 경계 밖의 기존 학생을 끌어온다(9절).
- 개인정보 응답: 반별 학생 목록의 보호자 연락처는 관리자에게만(`learningops/router.py`의 `show_contact`, 테스트 `…scope_privacy…`). 메시지 목록·일괄 검토는 마스킹. 메시지 상세의 전체 주소는 **M2 정책(사용자 결정)** 이라 이번 감사 대상이 아니다. 단 SEC-01을 거치면 정책 밖의 학생 주소까지 볼 수 있게 된다.

## 5. CSRF·CORS 평가
- **CSRF**: 이중 제출(쿠키 = 헤더) **+ 서버 측 세션 결합**(헤더 SHA-256이 세션의 `csrf_token_hash`와 일치해야 함, `auth/dependencies.py:62-75`). 다른 사람의 CSRF 쿠키를 심는 공격도 통하지 않는다. 상태 변경 라우트 전부에 적용(2절). 테스트 `test_roles_csrf_and_classroom_scope_are_enforced`, 각 모듈의 CSRF 403 테스트.
- 로그인 CSRF: 로그인은 `application/json`만 허용(`middleware.py:111-119`). 교차 출처 JSON은 사전 요청(preflight)이 필요하고 Origin 허용 목록에서 막힌다.
- **CORS·Origin**: 허용 목록에 정확히 일치하는 Origin만 허용하고, 다른 Origin은 요청 자체를 403으로 막는다(`middleware.py:54-64,82-84`). 자격 증명 허용은 허용 출처에만. `null` Origin도 거부한다. Origin이 없는 요청(서버 간)은 통과하지만 세션·CSRF가 필요하다.
- 브라우저 보안 헤더: `nosniff`, `no-store`, API용 CSP `default-src 'none'; frame-ancestors 'none'`, `no-referrer`. HSTS 없음(SEC-09, 배포 시).
- 프론트: `dangerouslySetInnerHTML`·`eval` 없음. 메시지 본문은 텍스트로 표시(React 이스케이프).
- **배포(Vercel + Render) 분리 시 위험 → Phase 11-5 필수 검증**:
  - 프론트와 API가 다른 사이트면 SameSite=Lax 세션 쿠키가 교차 사이트 XHR에 실리지 않아 로그인이 깨진다. SameSite=None으로 바꾸면 CSRF 방어가 이 구조에 더 의존하게 된다. **권장: Vercel Rewrite로 같은 출처(`/api` 프록시) 사용.**
  - Rewrite를 쓰면 Origin이 Vercel 도메인이다. `ACADEMY_CORS_ORIGINS`에 그 도메인만 넣는다.
  - Render·Vercel 뒤에서는 `request.client.host`가 프록시 IP다. 로그인 제한(SEC-03)과 접근 로그에 신뢰할 수 있는 프록시 헤더 처리가 필요하다.

## 6. 개인정보·입력 검증 평가
- **SQL 인젝션**: 모든 조회가 SQLAlchemy 식/바인드 파라미터를 쓴다. 문자열로 SQL을 조립하는 곳은 마이그레이션의 상수 DDL·테이블명뿐이다(사용자 입력 없음). 검색 `q`는 바인드되고 와일드카드는 이스케이프된다(Phase 8.1 테스트).
- **입력 검증**: Pydantic `extra="forbid"`, 길이·형식 제한, 검증 실패 응답은 일반 문구(`main.py:63-65`). 예외 응답은 내부 정보를 노출하지 않는다(`main.py:56-71`, 테스트 `test_database_error_is_redacted…`).
- **파일**:
  - 10MB 제한(미들웨어에서 본문을 읽는 단계)
  - ZIP 시그니처·압축률(<1%) 검사
  - 행 5,000·열 64 제한
  - openpyxl read-only·data_only
  - 다만 압축률 검사가 파일별 비율만 보고 전체 해제 크기 상한이 없으며, **빈 행은 행 수 제한에 들어가지 않는다**(SEC-06, Low)
  - `uploads.py:24-37`, `workbook.py:207-211`
- **로그·감사의 개인정보**:
  - 연락처 수정 감사는 바뀐 필드 이름과 이메일 유무만 남긴다(값 없음).
  - 메시지 생성 감사에 본문이 없다(테스트로 고정).
  - 업로드 감사에는 점수 이전→이후만 남는다.
  - 예외 로그(`logger.exception`)의 스택에 SQL 파라미터(이름·이메일)가 포함될 수 있다(SEC-07, Low).
- **H2(엑셀 덮어쓰기)·M2(보호자 이메일 노출) 정책**: 변경 제안 없음. 단 SEC-01은 M2 정책 범위 밖의 주소 노출이다.

## 7. M1 감사 로그 검토
**데이터 모델**: `audit_log`
- 행위자: `actor_staff_user_id`, FK SET NULL. 이제 직원 삭제가 SOFT라 기록이 남는다.
- 대상: `event_type`, `target_type`, `target_id`
- 그 외: `request_id`, `details` JSONB, `created_at`
- 행위자·동작·대상·시각을 모두 기록한다.
- 기록 경로: 각 서비스가 변경과 **같은 트랜잭션**에서 `AuditLog`를 추가하고 커밋한다(원자적).

| 이벤트 | 현재 감사 | 근거 |
|---|---|---|
| 로그인·로그아웃 | O (`AUTH_LOGIN/LOGOUT`) | `auth/service.py:121-146` |
| 수업·출결·평가·성적·휴원·복귀·업로드·메시지·템플릿·연락처 | O | 각 서비스 |
| 반 이름 수정·운영 종료/재개·삭제, 직원 삭제 | O (`CLASSROOM_UPDATED/DELETED`, `STAFF_DELETED`) | Phase 11 변경 |
| **직원 생성** | X | `learningops/service.py` `create_staff` |
| **직원 활성/비활성 전환** | X(세션 폐기는 함) | `update_staff_status` |
| 직원 이름 변경 | X | `update_staff_profile` |
| **담당 반 배정** | X | `assign` |
| **담당 반 배정 해제** | X, **물리 삭제로 행 자체가 사라짐**(누가 언제 그 반 권한을 가졌는지 복원 불가) | `remove_assignment`(`self.db.delete(row)`, `learningops/service.py:383`) |
| **수동 수강 등록** | X (업로드 경로는 `ENROLLMENT_CREATED_FROM_UPLOAD`로 O → 경로마다 다름) | `enroll` |
| 학생 등록(+수강) | X | `create_student` |
| 반 등록 | X | `create_classroom` |
| 로그인 실패 | X(제한기만) | 의도된 설계. 배포 시 로그 정책으로 검토 |

- **개인정보 최소화**: 신규 감사 상세에는 ID·역할·날짜·상태만 넣고 이메일·이름 원문은 넣지 않는다(기존 연락처 감사 방식과 같음).
- **재사용**: `learningops/service.py`의 `_audit(principal, request_id, event, target, details, target_type)`가 이미 있다. 라우터에서 `principal`·`request_id`를 넘기기만 하면 된다. **DB 스키마 변경 불필요.**
- **배정 해제 이력 보존 방안**:
  - (권장) 삭제 직전 행의 스냅샷(반·직원·역할·valid_from/to)을 `ASSIGNMENT_REMOVED` 감사에 남긴다. 스키마 변경이 없고, 즉시 권한 회수 동작도 그대로다.
  - (대안) 물리 삭제 대신 `valid_to`로 종료. 오늘 배정한 건은 `valid_to >= valid_from` CHECK 때문에 어제로 끝낼 수 없다. `valid_to = 오늘`이면 오늘 하루 권한이 남는다. 따라서 의미 변경·스키마 검토가 필요해 이번에는 권장하지 않는다.

## 8. 의존성·비밀정보·환경설정 검토
- **의존성 취약점 검사: 수행하지 않음(미검증).** `pip-audit`·`safety`가 설치되어 있지 않고, 외부 취약점 DB 조회를 하지 않았다. 버전만 기록한다.
  - 백엔드: FastAPI 0.162.0, Starlette 1.10.0, SQLAlchemy 2.1.8, pydantic 2.14.2, argon2-cffi 25.1.0, openpyxl 3.1.5, python-multipart 0.0.33, uvicorn 0.54.0, psycopg 3.3.8
  - 프론트: react 19.2.x, axios 1.20.x, antd 6.6.x, react-router 8.4.x, vite 8.3.x
  - → Phase 11-5에서 `pip-audit`·`npm audit`를 CI에 넣어 검사한다(SEC-11).
- **비밀정보**: 저장소 안에 `.env`·키 파일이 없다(`.env.example`만 있음). `.gitignore`가 `.env*`·키·`.dev-data`·`.venv`를 제외한다. 코드·스크립트·문서의 비밀번호 형태 문자열 12곳은 모두 자리표시자(`<…>`)·테스트용 가상 값·환경변수 읽기 코드였다(값은 이 문서에 옮기지 않음). Java 소스에도 하드코딩된 비밀번호 리터럴이 없다.
  - 참고: 현재 폴더는 **Git 저장소가 아니다**. "Git 추적 여부"는 `.gitignore` 규칙으로만 판단했다. 첫 커밋 전에 `git status`로 다시 확인해야 한다.
- **설정**:
  - Debug 모드 없음, 예외 응답은 일반화됨
  - 쿠키 Secure 기본 켜짐
  - DB API는 `ACADEMY_DB_MODE ∈ {development,test}`이고 루프백일 때만 열린다(`security.py:8-19`)
  - DB URL은 허용 목록(dev 55431 / test 55432)과 일치해야 한다(`db/safety.py`)
  - **즉, 배포 환경(Render/Neon)에서는 현재 코드로 API가 열리지 않는다**(SEC-04, 의도된 로컬 정책).
- 테스트 환경 분리: 통합 테스트는 컨테이너 라벨(`isolated-test`/`destructive-tests=allowed`)·DB 이름·사용자·포트를 확인한 뒤에만 실행한다. Phase 11-0에서 PS 5.1 라벨 검사 결함을 수정했다.

## 9. 발견 문제와 근거

### SEC-01 [High] 업로드 '신규'가 다른 반의 기존 학생을 말없이 재사용 — **재현함**
- **위치**: `lesson_upload/service.py:548-563`(`_resolve`의 NEW 분기: `select(Student).where(Student.name == row["name"], same_school) … or Student(...)`), 학생 업무 키 `tables.py:51`(`name + coalesce(school_name,'')` UNIQUE)
- **근거**: '신규' 결정은 "이 반의 미등록 학생"에게 나온다. 하지만 서버는 같은 이름(정규반은 학교 없음, 내신반은 반 이름에서 나온 학교)의 학생이 **다른 반에 이미 있으면 그 학생을 이 반에 수강시킨다.** 화면에는 "신규 등록 n명"으로만 표시된다.
- **성립 조건**:
  - ① 담당 반 A만 가진 선생님·조교(정상 로그인)가 반 B 학생의 이름(내신반이면 학교 포함)을 알고 엑셀 반 A 블록에 넣은 뒤 '신규'를 고른다.
  - ② 악의 없이: 서로 다른 아이가 같은 이름이고 학교가 비어 있다(정규반). 업무 키 UNIQUE 때문에 원래 두 학생이 따로 있을 수 없는데, 업로드는 오류 대신 합친다.
- **재현(격리 테스트 DB, 가상 데이터)**:
  - 반 A만 담당한 선생님은 반 B 목록에 403, 수동 수강 등록에도 403이었다(통제 정상).
  - 같은 선생님이 엑셀에 반 B 학생 `other`를 넣고 '신규'로 확정했다 → 200, 학생 수 6→6(새 학생 없음), `other`가 반 A에 수강됨.
  - 생성된 메시지 상세에서 **반 B 학생의 보호자 이메일 전체 주소**를 열람했다.
  - 스크립트: `scratchpad/sec/test_upload_links_other_class_student.py`
- **기존 방어**: 업로드 확정은 파일의 모든 반이 본인 담당이어야 한다. 행위는 `ENROLLMENT_CREATED_FROM_UPLOAD`로 감사된다(행위자 기록). 반 B의 과거 기록은 여전히 볼 수 없다.
  - 이 방어로는 막히지 않는다. 대상 반(A)이 담당 반이라 통과하고, 감사는 사후 추적일 뿐이다.
- **영향**: 담당 반 경계 밖 학생의 보호자 연락처 노출(M2 정책 범위 밖). 동명이인이 합쳐지면 **성적 안내가 다른 아이의 보호자에게 발송**된다(지금은 모의 발송, 실제 발송 도입 시 사고). 관리자 전용인 수동 수강 등록 정책을 우회한다.
- **최소 수정**: '신규' 결정에서 같은 업무 키의 **기존 학생이 있으면 재사용하지 않는다.**
  - 미리보기에서 행을 '확인 필요'로 표시하고, 확정은 400 `EXISTING_STUDENT_ELSEWHERE`로 거부한다.
  - 안내: "같은 이름의 학생이 이미 등록되어 있습니다. 관리자가 학생·반 관리에서 수강 등록하거나 학교 정보로 구분해 주세요."
  - 관리자에게는 명시적 결정 값('기존 학생으로 연결')을 허용할지 **정책 결정이 필요하다.** 기본값은 관리자도 화면에서 수강 등록하도록 하는 것이다.
  - 진짜 신규(같은 키 없음)는 지금처럼 생성한다. Phase 8.1 정책(조교·선생님도 신규·복귀 처리)은 유지한다.
- **회귀 위험**: 낮음~중간. 업로드 통합 테스트에서 신규 학생 생성 경로는 그대로이고, 기존 학생 재사용에 기대던 경우만 거부로 바뀐다. 기존 테스트 기대값 확인이 필요하다.
- **처리**: **Phase 11-2**

### SEC-02 [Medium] 권한·인사·수강 관리 변경 감사 누락 + 배정 해제 이력 소실 (M1)
- **위치**: `learningops/service.py` `create_staff`·`update_staff_status`·`update_staff_profile`·`assign`·`remove_assignment`(:383 물리 삭제)·`enroll`·`create_student`·`create_classroom`
- **근거**: 7절 표. 같은 모듈의 연락처 수정과 Phase 11의 반·직원 삭제는 감사하는데, 권한 부여·회수와 수동 수강은 감사하지 않는다. 업로드 수강은 감사하므로 경로마다 불일치한다.
- **성립 조건**: 공격이 아니라 **사후 추적 불가**다. "누가 언제 이 조교에게 B반 권한을 줬다 뺐나", "누가 이 직원을 비활성화했나"를 답할 수 없다.
- **기존 방어**: 관리자 전용 + CSRF + 세션. 데이터 손상은 없다.
- **최소 수정**:
  - 기존 `_audit` 재사용(스키마 변경 없음), 같은 트랜잭션
  - 이벤트: `STAFF_CREATED`(역할), `STAFF_STATUS_CHANGED`(이전→이후, 폐기한 세션 수), `STAFF_RENAMED`(필드명), `ASSIGNMENT_CREATED`, `ASSIGNMENT_REMOVED`(삭제 직전 스냅샷), `ENROLLMENT_CREATED`(source MANUAL), `STUDENT_CREATED`(수강 포함 여부, 연락처는 유무만), `CLASSROOM_CREATED`
  - 라우터 8곳에 `principal`·`request_id`를 전달한다.
- **회귀 위험**: 낮음(추가만). 감사 행 수를 세는 기존 테스트가 있으면 기대값 조정이 필요하다(확인 필요).
- **처리**: **Phase 11-2**

### SEC-03 [Medium · 조건부(배포)] 로그인 제한기가 프록시 뒤에서 전원을 하나로 묶음
- **위치**: `auth/router.py:55`(`request.client.host`), `auth/service.py:49-84`(프로세스 메모리 dict, 키 삭제 없음)
- **성립 조건**: Render·Vercel 같은 리버스 프록시 뒤에서는 모든 요청의 `client.host`가 프록시 IP다. 누군가 15분에 5번 틀리면 **모든 사용자의 로그인이 15분간 막힌다**(서비스 거부). 여러 워커·인스턴스면 제한이 워커마다 따로라 우회된다. 키가 계속 쌓인다(L4).
- **재현**: 미실행(배포 환경 없음). 코드상 확정.
- **기존 방어**: 로컬(루프백 단일 사용자)에서는 문제없다.
- **최소 수정(11-5)**: 신뢰할 프록시 목록에서만 `X-Forwarded-For`를 사용한다(uvicorn `--proxy-headers --forwarded-allow-ips`). 계정 키(이메일) 단독 제한도 추가한다. 오래된 키를 정리한다. 다중 인스턴스면 DB·캐시 기반으로 바꾼다.
- **처리**: **Phase 11-5**

### SEC-04 [Medium · 배포 차단 요인, 결함 아님] 실행 모드 게이트·DB 허용 목록이 로컬 전용
- **위치**: `security.py:8-19`, `db/safety.py:10-33`
- **내용**: 루프백이 아니거나 dev/test 모드가 아니면 모든 DB API가 404다. 허용 DB가 로컬 dev/test로 고정되어 있다. 로컬 안전 정책과는 일치한다.
- **조치(11-5)**: 명시적 `production` 모드를 추가한다. DB URL을 환경변수로 받되 TLS(`sslmode=require`)를 요구한다. 파괴적 테스트 차단은 유지한다. 운영에서는 Secure 쿠키를 강제한다.
- **처리**: **Phase 11-5**

### SEC-05 [Low] 유휴 세션 만료 없음, 만료 세션 정리 없음
- **위치**: `config.py:36`(8시간 절대 만료), `tables.py:453`(`last_seen_at` 갱신 안 함)
- **조건**: 공용 PC에 로그인한 채 두면 8시간 동안 유효하다.
- **최소 수정**: 요청 시 `last_seen_at`을 갱신하고(예: 5분 단위로만 쓰기) 유휴 N분 초과 시 401. 만료 행은 정리 작업으로 지운다. 유휴 시간 값은 사용자가 결정한다.
- **처리**: Phase 11-5(보안 강화 묶음) — 원하면 11-2에 포함 가능

### SEC-06 [Low] 업로드 자원 한도 보완
- **위치**: `uploads.py:28-33`(파일별 압축률만 검사, 해제 크기 합계 상한 없음), `workbook.py:207-211`(빈 행은 `MAX_ROWS`에 안 셈)
- **조건**: 로그인한 직원이 1% 직전 압축률의 큰 파일(빈 행 대량)을 올리면 파싱 CPU 시간이 길어진다. 인증된 내부자만 가능하다.
- **최소 수정**: ZIP 해제 크기 합계 상한(예: 100MB), 읽은 전체 행 수 상한(빈 행 포함)
- **처리**: Phase 11-5

### SEC-07 [Low] 예외 로그에 개인정보가 섞일 수 있음
- **위치**: `main.py:68-71`(`logger.exception`). SQLAlchemy 예외 문자열에는 SQL 파라미터가 포함된다.
- **조건**: DB 오류가 나면 서버 로그(배포 시 Render 로그)에 학생 이름·이메일이 남을 수 있다. 응답에는 노출되지 않는다(테스트로 확인).
- **최소 수정**: 운영 모드에서 예외 로그를 정제한다(SQLAlchemy `hide_parameters=True` 엔진 옵션 + 예외 클래스·요청 ID만 기록).
- **처리**: Phase 11-5

### SEC-08 [Informational] OpenAPI 문서(`/docs`, `/redoc`, `/openapi.json`)가 인증 없이 열림
- **위치**: `main.py:30`(FastAPI 기본값). 전체 API 구조가 공개된다. 데이터는 노출되지 않는다.
- **처리**: Phase 11-5(운영에서 `docs_url=None` 등. 포트폴리오 시연용으로 공개할지는 사용자 결정)

### SEC-09 [Informational] 배포 시 브라우저 보안 설정
- HSTS 없음, 쿠키 `__Host-` 접두사 미사용, Rewrite 구성 시 Origin 허용 목록·쿠키 Secure 확인 필요(5절)
- **처리**: Phase 11-5

### SEC-10 [Informational] 직원 비밀번호 변경·재설정 기능 없음
- 관리자가 정한 초기 비밀번호를 직원이 바꿀 수 없다. 관리자가 모든 초기 비밀번호를 안다.
- **처리**: 정책 결정 후 Phase 11-5 또는 이후

### SEC-11 [Informational] 의존성 취약점 검사 미수행
- 8절. **PASS로 표시하지 않는다.**
- **처리**: Phase 11-5(CI에 pip-audit·npm audit)

**반박 검증("놓친 방어 장치가 있는가")**
- SEC-01: 업로드 확정의 담당 반 검사, 감사 기록, DB UNIQUE를 확인했다. 대상 반이 담당 반이라 통과하고, UNIQUE는 오히려 재사용을 유도하며, 감사는 사후 추적만 가능하다. **재현으로 확정.**
- SEC-02: 다른 감사 테이블·트리거가 있는지 확인했다. `audit_log` 외 이력 테이블이 없고, 배정 테이블에 버전·이력 트리거가 없다. **확정.**
- SEC-03: uvicorn 기본값은 프록시 헤더를 신뢰하지 않는다(`--forwarded-allow-ips` 기본 127.0.0.1). 배포 구성 파일이 아직 없어 **조건부**다.
- 상태 변경 GET이 있는가: GET 핸들러에 쓰기가 없음을 확인했다(분석·처리 현황·목록은 읽기 전용 테스트로 고정). **문제 없음.**
- 세션 고정·계정 추론·CSRF 우회: 3·5절 근거와 테스트로 **문제 없음.**

## 10. 수정 우선순위 및 최소 변경 계획 (승인 후 실행)
| 순서 | ID | 작업 | 파일 | 규모 | 테스트 |
|---|---|---|---|---|---|
| 1 | SEC-01 | '신규'에서 기존 학생 재사용 금지: 미리보기 '확인 필요' + 확정 400. 관리자 '기존 학생 연결' 허용 여부는 **사용자 결정** | `lesson_upload/service.py`(`_analyse_row`·`_resolve`), `UploadTab.tsx`(안내 문구) | 백엔드 수십 줄 + 프론트 소규모 | 재현 시나리오를 저장소 테스트로 편입(거부·학생 수 불변·다른 반 미수강·이메일 미노출), 진짜 신규는 기존대로, 동명이인 정규반 사례 |
| 2 | SEC-02 | 관리자 변경 감사 8종 + 배정 해제 스냅샷 | `learningops/service.py`·`router.py` | 백엔드 소규모 | 이벤트별 행위자·대상·트랜잭션(롤백 시 감사 없음)·상세에 이메일 원문 없음 |
| (선택) | SEC-05 | 유휴 만료(값 결정 필요) | `auth/dependencies.py`, `config.py` | 소규모 | 유휴 초과 401, 갱신 쓰기 빈도 |
원칙: 인증 구조 유지, DB 스키마 변경 없음, 새 라이브러리 없음, 작업마다 백업(Git 없음).

## 11. Phase 11-5 이관 사항
| 항목 | 출처 |
|---|---|
| 배포 아키텍처: Vercel Rewrite(같은 출처) + `ACADEMY_CORS_ORIGINS`에 운영 도메인만 + Secure 쿠키 + HSTS·`__Host-` 접두사 검토 | 5절, SEC-09 |
| 프록시 헤더 신뢰 범위(uvicorn `--proxy-headers --forwarded-allow-ips`), 로그인 제한 키·저장소 | SEC-03 |
| `production` 실행 모드, 운영 DB(Neon) TLS, 허용 DB 검증 방식 | SEC-04 |
| 유휴 만료·만료 세션 정리(11-2에서 안 하면) | SEC-05 |
| 업로드 해제 크기·전체 행 상한 | SEC-06 |
| 운영 로그 정제(`hide_parameters`), 로그인 실패 로그 정책 | SEC-07 |
| OpenAPI 문서 공개 여부 | SEC-08 |
| 비밀번호 변경·재설정 정책 | SEC-10 |
| CI 의존성 취약점 검사(pip-audit, npm audit) | SEC-11 |
| 첫 커밋 전 `git status`로 비밀정보·`.dev-data` 미추적 확인 | 8절 |

## 12. 검증 범위와 한계
- **실행한 것**:
  - 라우트 81개 의존성 자동 추출
  - 격리 테스트 DB(`academy_learningops_test`@127.0.0.1:55432, 컨테이너 라벨·DB 이름·사용자 확인)에서 보안 관련 테스트 8개 파일 **60건 PASS**: 인증·세션·만료·재사용, 비활성·제한·계정 추론, Secure 쿠키, 역할·CSRF·담당 반, 직원 수명주기·세션 폐기, 배정 BOLA, 교차 반·IDOR, 개인정보 최소 응답, 업로드 크기, DB 오류 은닉
  - SEC-01 재현 1건(가상 데이터, 저장소 밖 스크립트)
  - 테스트 픽스처가 격리 DB 테이블을 비우고 가상 데이터를 넣는다. 개발 DB·볼륨·`academy-postgres`에는 접근하지 않았다.
- **코드 추적만 한 것**: SEC-03·04·05·06·07(배포 환경·부하 없이 판단)
- **하지 않은 것**:
  - 의존성 취약점 DB 조회(도구 없음·외부 조회 안 함)
  - 브라우저 동작(쿠키 저장·CORS 실제 브라우저)
  - Java 레거시 보안(포트폴리오 공개 대상 아님)
  - 부하·동시성 공격
  - 운영 배포 설정(아직 없음)

## 13. 최종 판정 — **CONDITIONAL PASS**
인증·세션·CSRF·역할·담당 반 경계와 오류 은닉은 코드와 테스트로 확인되었다. 인증 구조를 바꿀 필요는 없다. 단 다음 두 가지를 **Phase 11-2에서 수정**해야 PASS로 볼 수 있다.
- **SEC-01(High, 재현됨)**: 업로드가 반 경계 밖 학생을 끌어오고, 동명이인을 합쳐 보호자를 잘못 연결한다.
- **SEC-02(M1)**: 권한 변경 감사가 빠져 있다.

배포 관련 항목(SEC-03·04·08·09·11)은 결함이 아니라 **배포 전 필수 검증**으로 Phase 11-5에 넘긴다.

**사용자 결정 필요**:
1. SEC-01 수정 시 관리자에게 '기존 학생으로 연결' 선택지를 줄지(기본안: 업로드에서는 거부하고 관리자가 학생·반 관리에서 수강 등록)
2. SEC-05 유휴 만료를 이번에 넣을지와 그 시간(예: 60분)
