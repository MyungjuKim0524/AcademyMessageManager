# Phase 11-2-B-2 — 로그인 보호·파일 처리·로그 보안 안정화 결과

작업일: 2026-11-20 · 기준: `phase11_2_security_audit.md`(SEC-03, 06~11), `phase11_2_b1_results.md`
범위 밖(지시대로 손대지 않음): SEC-04 실행 모드(`require_local_db_api`, `db/safety.py`), SEC-05 유휴 만료, 인증·세션·CSRF 구조, H2·M2 정책.
**DB 스키마·Migration 변경 없음. 신규 인프라·외부 서비스 없음.** 원본은 저장소 밖(scratchpad `backup-b2\`)에 백업했다(Git 없음).

---

## 1. SEC-03·06·07 검증 및 수정 결과

### SEC-03 로그인 시도 제한 — **수정 완료**

**현재 구조 분석(수정 전)**
| 항목 | 확인 결과 |
|---|---|
| 1. 클라이언트 IP | `request.client.host`(소켓 상대 주소)를 그대로 사용 |
| 2. 프록시 헤더 | 앱은 읽지 않음. **그러나 uvicorn 0.54는 기본값 `proxy_headers=True`, `forwarded_allow_ips=127.0.0.1,::1`이다.** 루프백에서 온 요청의 `X-Forwarded-For`로 `client.host`를 바꾼다 |
| 3. XFF 조작 | 로컬에서는 Vite 프록시(127.0.0.1)를 거친 요청이 임의 XFF를 보내면 uvicorn이 그 값을 클라이언트 주소로 쓴다 → **요청마다 XFF를 바꾸면 주소별 제한을 우회할 수 있었다.** 배포에서 흔히 쓰는 `--forwarded-allow-ips='*'`도 같은 우회가 된다 |
| 4. 전원 동일 IP | 프록시 뒤(헤더 미사용)에서는 모든 사용자가 프록시 주소 하나로 묶인다. 주소 키 한도가 **5회**라서, 아무나 5번 틀리면 **전원이 15분간 로그인 불가**였다. 같은 학원 와이파이(같은 공인 IP)에서도 마찬가지 |
| 5. 저장·다중 프로세스 | 프로세스 메모리 dict. 워커마다 따로 센다. 만료 키를 지우지 않음(`check`가 빈 리스트로 키를 남김) |
| 6. 정책 | 15분(900초) 창, 주소 5회 + (주소+계정) 5회. 성공 시 두 키 모두 초기화 |
| 7. 부당 차단·우회 | (a) 4번의 전원 차단. (b) **자기 계정으로 한 번 성공하면 주소 키가 초기화**돼, 정상 계정을 가진 내부자는 다른 계정에 대한 시도를 계속 이어갈 수 있었다. (c) 계정 단위 한도가 없어 주소를 바꾸면 한 계정에 시도 횟수 제한이 없었다 |

**수정 내용**
1. **신뢰 프록시에서만 XFF 사용**(`auth/service.py::client_address`): `ACADEMY_TRUSTED_PROXIES`(IP·CIDR, 기본 비어 있음)에 든 상대 주소에서 온 요청만 XFF를 읽는다. 오른쪽(우리 프록시가 덧붙인 쪽)부터 신뢰 프록시를 건너뛰고 **처음 나오는 비신뢰 주소**를 클라이언트로 본다. 클라이언트가 쓴 왼쪽 값은 절대 쓰지 않는다. 형식이 깨진 값은 `invalid-forwarded`라는 별도 키로 센다(프록시 주소로 묶지 않아 전원 차단이 생기지 않음). 설정값이 잘못되면 시작 시 오류(fail closed).
2. **uvicorn 프록시 처리 끄기**: 로컬 실행 스크립트에 `--no-proxy-headers` 추가. 앱이 신뢰 판단을 한 곳에서 한다.
3. **카운터 3종**(기존 5회 키 유지):
   - (주소+계정) **5회**: 기존과 동일 → 비밀번호 추측 방어는 그대로
   - 주소 전체 **20회**(`ACADEMY_LOGIN_IP_ATTEMPT_LIMIT`, 기존 5): 한 사람의 오타로 같은 사무실 동료가 막히지 않게 완화. 다른 계정 5개를 4번씩 시도하는 수준까지만 허용
   - 계정 전체 **20회**(`ACADEMY_LOGIN_ACCOUNT_ATTEMPT_LIMIT`, 신규): 주소를 바꿔 가며 한 계정을 추측하는 공격을 15분 20회로 제한
   - 0으로 설정하면 해당 한도 끔. 존재하지 않는 계정도 같은 방식으로 세어 계정 존재 추론 불가(기존 동일 401 유지)
4. **성공 시 초기화 범위 축소**: 성공하면 (주소+계정)·계정 키만 지운다. 주소 키는 지우지 않아 7(b) 우회를 막았다.
5. **메모리 정리**: 빈 키를 남기지 않고, 키가 10,000개를 넘으면 만료 키를 정리한다.

**판단 근거·트레이드오프**: 계정 전체 한도는 공격자가 특정 계정을 15분씩 잠글 수 있게 한다(계정 잠금 DoS). 반면 없으면 분산 추측이 무제한이다. 감사 문서 권고대로 넣고 값을 넉넉히(20) 잡았으며, 환경변수로 조정·해제할 수 있다. 주소 한도 20은 사용자 결정으로 바꿀 수 있는 값이다.

**남는 사항**: 다중 워커는 워커 수만큼 한도가 늘어난다(공유 저장소는 Redis·DB 테이블 금지 조건 때문에 미도입 → 배포 시 워커 1개 권장, 6·7절).

### SEC-06 XLSX 압축 해제·자원 고갈 — **실제 위험 확인, 수정 완료**

| 항목 | 수정 전 | 수정 후 |
|---|---|---|
| 압축 파일 크기 | 10MB(미들웨어 본문 단계) | 변경 없음 |
| 항목별 압축률 | 1% 미만 거부(약 100배) | 변경 없음 |
| ZIP 항목 수 | 제한 없음 | **1,000개**(실제 엑셀 13~23개) |
| 압축 해제 총량 | **제한 없음** — 10MB 파일이 항목마다 99배면 약 1GB까지 통과 | **선언 크기 합계 100MB**(실제 엑셀 70KB 미만) |
| 행 순회 | 내용 있는 행만 5,000행 제한 | 기존 5,000 유지 + **빈 행 포함 순회 50,000행**(실제 약 400행) |
| 열 | 읽은 뒤 64열로 자름 | `iter_rows(max_col=64)` — 64열만 만든다(결과 동일) |
| XML 엔티티·외부 참조 | openpyxl이 `defusedxml`을 쓰는데 **의존성에 선언되지 않음**(다른 도구의 하위 의존성으로만 설치됨) | `pyproject.toml`에 `defusedxml==0.7.1` 명시(이미 설치된 버전) |
| 처리 위치 | `async` 라우트에서 동기 파싱 → 파싱 중 **이벤트 루프 전체가 멈춤** | 파싱·확정을 스레드풀에서 실행(`run_in_threadpool`) |

**재현으로 확인한 위험(격리 스크립트, 서버 미사용)**: 행 번호 1,048,576과 크기 `A1:XFD1048576`을 적은 **4.8KB** 파일을 만들었다. openpyxl은 행 사이 빈칸을 빈 행으로 채운다(행마다 16,384열). 이 파일 시트 하나로 `parse_workbook`이 **27.2초** CPU를 썼다. 시트를 늘리면 비례해서 늘고, 로그인한 직원 누구나 `/sheets`·`/preview`로 보낼 수 있으며, 이벤트 루프까지 막았다. 수정 후 같은 파일은 **413 `ROW_LIMIT_EXCEEDED`, 실측 1.6초**(27.2초 → 1.6초. 테스트로 10초 미만 고정. 시트가 여러 개여도 순회 상한이 파일 전체 기준이라 늘어나지 않음).

ZIP 메타데이터 검사의 근거: 압축을 풀기 전에 중앙 디렉터리만 본다. Python `zipfile`(openpyxl이 사용)은 항목의 선언 크기보다 많은 바이트를 돌려주지 않는다(`ZipExtFile._read1`에서 `data[:self._left]`로 자름, 코드 확인). 따라서 선언 크기 합계를 상한으로 신뢰할 수 있다. 엔티티 선언(XML bomb 형태)은 `INVALID_XLSX` 400으로 거부됨을 테스트로 확인했다. 시트 XML이 중간에 깨진 파일도 500 없이 처리된다.

정상 업로드 계약(10MB, 5,000행, 64열, 오류 코드)은 바꾸지 않았다. 새 한도는 실제 파일보다 수십~수천 배 크다.

### SEC-07 개인정보 로그 노출 — **실제 경로 확인, 수정 완료**

| 경로 | 수정 전 | 수정 후 |
|---|---|---|
| FastAPI 전역 예외 처리 | `logger.exception`이 예외 문구 전체를 남김. SQLAlchemy 예외 문구에는 `[parameters: {...}]`(학생 이름·보호자 이메일), PostgreSQL `DETAIL: Key (...)=(값)`이 들어 있음 | 오류 유형·DB 오류 유형·SQLSTATE·제약 이름·요청 ID·메서드·경로·스택 프레임(파일·줄·함수·소스 코드 줄)만 기록. **예외 문구는 기록하지 않음** |
| **서버(uvicorn) 로그** | Starlette `ServerErrorMiddleware`는 `Exception` 핸들러를 부른 뒤 **항상 예외를 다시 던진다**(소스 확인). 그래서 uvicorn이 "Exception in ASGI application"과 함께 **전체 traceback·문구를 다시 출력**했다 | 예외를 `CompatibilityMiddleware`에서 처리하고 다시 던지지 않는다 → uvicorn까지 가지 않음(`raise_server_exceptions=True` 테스트로 고정). 앱 핸들러도 같은 정제 로그 사용 |
| DB 엔진 | 파라미터가 예외 문구에 포함 | `create_engine(hide_parameters=True)`(이중 방어) |
| 접근 로그 | 앱 로그는 경로만(쿼리 없음). **uvicorn 접근 로그는 쿼리 문자열 포함** → `GET /api/students?q=<학생 이름>`이 남음 | 로컬 실행 스크립트에 `--no-access-log`(앱 자체 요청 로그가 대신함) |
| 인증·인가 실패 | 이메일·비밀번호·토큰 로그 없음(본문·헤더·쿠키를 기록하지 않음). 토큰은 해시로만 저장 | 변경 없음(확인) |
| 엑셀 파싱 오류 | 사용자에게 행 위치·문구만 반환, 로그 없음 | 변경 없음(확인) |
| 메시지 생성·모의 발송 | 로그 출력 없음. 감사에 본문 없음(기존 테스트) | 변경 없음(확인) |
| 감사 로그 | 연락처는 필드명·유무만, B-1 신규 감사도 ID·역할·날짜만 | 변경 없음(확인) |
| DB 연결 문자열 | 안전 검사 오류 문구에 DB·사용자·호스트·포트(비밀번호 없음). 응답은 503 일반 문구, 로그 없음 | 변경 없음(확인) |

## 2. SEC-08~11 검토 결과

| ID | 결과 | 내용 |
|---|---|---|
| **SEC-08** API 문서 | **수정** | `/docs`·`/redoc`·`/openapi.json`이 `ACADEMY_API_DOCS=1`일 때만 열린다(기본 꺼짐 → 404). 로컬 실행 스크립트는 켠다. 참고: 앱의 CSP(`default-src 'none'`) 때문에 `/docs` 화면은 원래 브라우저에서 동작하지 않았고, `/openapi.json`(전체 API 구조)만 실제로 노출되었다. 데이터는 노출되지 않는다. 포트폴리오 시연용으로 공개할지는 사용자 결정(환경변수 하나로 켬) |
| **SEC-09** HTTPS·쿠키·헤더 | **확인 + 선택적 HSTS 추가** | 세션 쿠키 HttpOnly·Secure(기본 켜짐)·SameSite=Lax·Path=/·Domain 없음. CSRF 쿠키는 JS가 읽어야 하므로 HttpOnly 아님(이중 제출 + 세션 결합, 정상). 보안 헤더 nosniff·no-store·CSP·no-referrer 유지. **HSTS는 `ACADEMY_HSTS_MAX_AGE`>0일 때만** 보냄(기본 0). HTTPS 확인 전 켜면 안 되므로 배포 체크리스트로 넘김. `Secure`를 끄는 `ACADEMY_COOKIE_SECURE=0`은 로컬 HTTP 전용 |
| **SEC-10** 비밀번호 변경 | **개발하지 않음(근거)** | 현재 관리자가 초기 비밀번호를 정하고, 직원은 바꿀 수 없으며, 관리자 재설정 API도 없다. 이는 결함이 아니라 기능 공백이다. 포트폴리오 데모(가상 계정)에는 필수가 아니다. 실사용 전에는 "본인 변경 + 관리자 재설정(세션 폐기·감사)"이 필요하다 → 요구사항 결정 후 개발(6절). 지시대로 신규 기능은 만들지 않았다 |
| **SEC-11** 의존성 | **검사 수행, 2건 패치** | 아래 표 |

**SEC-11 상세**
- **Python**: 프로젝트 venv의 고정 버전 61개(`pip freeze`, 개발 도구 포함)를 `pip-audit 2.10.1`(venv에 이미 설치됨)로 검사했다. 데이터 출처는 **PyPI 권고 DB와 OSV 두 곳**이며, 결과는 모두 **알려진 취약점 0건**이다.
- **npm**: `npm audit`(npm 레지스트리 권고 DB) 결과 **high 2건**. 둘 다 간접 의존성이다.

| 패키지 | 경로 | 권고 | 실제 영향 | 조치 |
|---|---|---|---|---|
| follow-redirects 1.16.1 | axios → (Node용 http 어댑터) | GHSA-mrwp-f3q8-3g9p(리다이렉트 시 자격 증명 헤더) | 브라우저 번들은 XHR 어댑터를 써서 **포함되지 않음**(빌드 산출물 검색 0건). 실제 영향 없음 | lockfile 패치 1.16.3 |
| undici 7.30.0 | jsdom(테스트 전용) | GHSA-4qv8, -xjj6, -4w7w, -2m5v 등 8건(DoS·TLS 검증 등) | 개발·테스트 도구. 배포물에 없음 | lockfile 패치 7.30.2 |

`npm audit fix`(`--force` 없음)로 **`package-lock.json`의 두 패키지만** 패치 버전으로 올렸다(`package.json` 변경 없음). 이후 `npm audit` 0건, `npm run build` 통과, 프론트 전체 테스트 결과는 4절에 적었다. 오래된 버전이라는 이유만으로 올린 패키지는 없다.

## 3. 변경 파일·함수

| 파일 | 함수·위치 | 변경 |
|---|---|---|
| `backend/app/config.py` | `_networks()`(신규), `Settings`·`get_settings()` | `login_ip_attempt_limit`(20), `login_account_attempt_limit`(20), `trusted_proxies`, `api_docs_enabled`, `hsts_max_age` |
| `backend/app/modules/auth/service.py` | `client_address()`(신규), `LoginRateLimiter.check/fail`, `AuthService.login` | 신뢰 프록시 XFF 해석, 카운터 3종, 성공 시 주소 키 유지, 키 정리 |
| `backend/app/modules/auth/router.py` | `login` | `client_address()` 사용 |
| `backend/app/uploads.py` | 상수 3개, `check_xlsx_zip()` | ZIP 항목 수·선언 크기 합계 검사 |
| `backend/app/modules/lesson_upload/workbook.py` | `parse_workbook()` | `max_col=64`, 빈 행 포함 순회 상한 |
| `backend/app/modules/lesson_upload/router.py` | `list_sheets`·`preview_upload`·`confirm_upload` | 파싱·확정을 `run_in_threadpool`으로 실행 |
| `backend/app/middleware.py` | `log_unhandled()`(신규), `CompatibilityMiddleware.__call__` | 미처리 예외를 정제 로그 + 500으로 처리하고 다시 던지지 않음, HSTS 선택 헤더 |
| `backend/app/main.py` | `FastAPI(...)`, `internal_error_handler` | 문서 URL 조건부, 정제 로그 사용 |
| `backend/app/db/session.py` | `create_db_engine()` | `hide_parameters=True` |
| `backend/pyproject.toml` | dependencies | `defusedxml==0.7.1` 명시 |
| `backend/.env.example` | — | 새 환경변수 5개 설명 |
| `scripts/start-fastapi.ps1` | uvicorn 실행 줄 | `--no-proxy-headers --no-access-log`, `ACADEMY_API_DOCS=1`(로컬 전용) |
| `frontend/package-lock.json` | — | follow-redirects 1.16.3, undici 7.30.2 |
| `backend/tests/test_phase112b2_hardening.py` | 신규 21건 | 주소 해석 10, 설정 오류, 한도 만료·키 정리, 정상·원거리 행·ZIP 항목/총량·압축 폭탄·XML 엔티티, 로그 정제, 엔진 설정, 문서 비공개, HSTS |
| `backend/tests/test_phase112b2_login_integration.py` | 신규 5건(PostgreSQL) | 아래 4절 |
| `backend/tests/test_auth_rbac_integration.py` | `test_invalid_inactive_rate_limit_and_no_enumeration` | 주소 전체 한도를 이 테스트에서만 5로 지정(기본값이 20으로 바뀌었기 때문, 검증 의도 유지) |
| `docs/reviews/phase11_2_b1_results.md` | 4절 표 | B-1 당시 진행 중이던 프론트 전체 테스트 결과 기입 |

## 4. 테스트 명령 및 실제 결과

**DB 격리 확인**: `scripts/run-postgres-integration.ps1`의 검사 블록(라벨 `isolated-test`/`allowed`, 포트 `127.0.0.1:55432`, `academy_learningops_test|academy_test`)을 그대로 실행하는 Python 전용 실행기로 돌렸다(B-1과 같음, scratchpad `run-db-tests.ps1`). dev 컨테이너·`academy-postgres`·없는 컨테이너는 거부됨을 B-1에서 확인했다. 비밀번호는 출력하지 않았다. 데이터는 모두 가상 값이다.

| 명령 | 결과 |
|---|---|
| `ruff check app tests` | All checks passed |
| `ruff format --check`(수정한 파일) | 통과 |
| `pytest -m "not postgres"` | **60 passed**(기존 39 + 신규 21) |
| `pytest -m postgres`(격리 DB, 전체) | **99 passed**(B-1 이후 94 + 신규 5) |
| 백엔드 합계 | **159 passed, 0 failed** |
| `npm audit` / `npm run build` / `tsc -b` | 0 vulnerabilities / 통과 / 통과 |
| 프론트 전체 `vitest run`(lockfile 패치 후) | 14 파일 중 13 통과 · **105 passed / 1 failed**. 패치 전(B-1)과 같은 결과이며, 실패 1건은 기존 결함(시간대 선택 후 '미리보기' 활성화 테스트) |
| `pip-audit -r freeze.txt --no-deps --disable-pip`(PyPI, OSV) | No known vulnerabilities found(2회) |

**신규 SEC-03 통합 테스트**(`test_phase112b2_login_integration.py`, 실제 API·PostgreSQL)
- `test_one_users_failures_do_not_lock_out_colleagues_on_the_same_address`: 정상 주소별 제한(5회 후 429), 같은 주소의 다른 사용자는 로그인됨, 다른 주소의 같은 계정도 로그인됨, **창 만료 후 정상 로그인**
- `test_forged_forwarded_for_is_ignored_without_a_trusted_proxy`: XFF를 매번 바꿔도 6번째 429
- `test_behind_a_trusted_proxy_each_client_is_counted_apart`: 신뢰 프록시 뒤 사용자별 분리, 왼쪽 위조값 회전 무력화, **비신뢰 상대의 XFF 무시**
- `test_rotating_addresses_hits_the_account_limit`: 주소 5개×4회 = 계정 한도 20 → 올바른 비밀번호도 429, 다른 계정 영향 없음, 만료 후 정상
- `test_own_successful_login_does_not_reset_the_address_limit`: 내부자 우회 차단

**기존 보안 테스트 재실행**: 11-2-A 문서는 "8개 파일 60건"이라고만 적고 파일 목록을 남기지 않아 **같은 집합을 정확히 재구성할 수 없었다.** 그래서 문서가 나열한 범주(인증·세션·만료·재사용, 비활성·제한·계정 추론, Secure 쿠키, 역할·CSRF·담당 반, 직원 수명주기·세션 폐기, 배정 BOLA, 교차 반·IDOR, 개인정보 최소 응답, 업로드 크기, DB 오류 은닉)를 담은 기존 파일 전체를 다시 실행했다. **모두 통과했다**:
`test_auth_rbac_integration` 5, `test_auth_configuration` 2, `test_db_safety` 8, `test_api` 8, `test_phase6a_learningops_integration` 4, `test_phase6b_staff_management_integration` 3, `test_phase7_academics_integration` 5, `test_phase8_notifications_integration` 16, `test_phase81_lesson_upload_integration` 6, `test_phase9_message_operations_integration` 7 = **10개 파일 64건**. 여기에 Phase 11-2 신규 보안 테스트 38건(B-1 12 + B-2 26)이 더해진다. 전체 백엔드 159건에 모두 포함되어 있으며 실패 0이다.

## 5. 수정하지 않은 항목과 근거
| 항목 | 근거 |
|---|---|
| SEC-04 실행 모드·DB 허용 목록 | 지시상 Phase 11-4. 현재 코드로는 배포 환경에서 DB API가 404다(배포 차단 요인, 결함 아님) |
| SEC-05 유휴 만료 | 지시상 이번에 구현하지 않음 |
| SEC-10 비밀번호 변경·재설정 | 신규 기능. 요구사항(본인 변경, 관리자 재설정, 첫 로그인 변경 강제 여부) 결정이 필요 |
| 로그인 제한 공유 저장소 | Redis·DB 테이블 추가 금지. 워커 1개로 운영하면 현재 코드로 충분 |
| `Forwarded`(RFC 7239) 헤더 | Render·Vercel은 `X-Forwarded-For`를 쓴다. 표준 `Forwarded`는 읽지 않는다(무시가 안전한 기본값) |
| `__Host-` 쿠키 접두사 | 세션 쿠키는 `ACADEMY_SESSION_COOKIE` 환경변수만으로 바꿀 수 있다. CSRF 쿠키 이름은 프론트 코드가 읽으므로 바꾸려면 코드 변경이 필요하다. 배포 도메인 확정 후 결정 |
| 학생 검색어가 쿼리 문자열(`?q=`)에 있음 | 앱·uvicorn 로그에서는 제거했다. 배포 플랫폼 자체의 HTTP 로그에 남을 수 있다 → 7절 확인 항목. API 계약 변경(POST 검색 등)은 하지 않음 |
| 프론트 기존 실패 테스트 1건 | B-1에서 기존 결함으로 확인. 보안 범위 밖 |

## 6. Phase 11-4로 이관할 코드 작업
1. **SEC-04**: 명시적 `production` 실행 모드, 운영 DB URL(환경변수·`sslmode=require`) 허용 방식, 파괴적 테스트 차단 유지
2. **SEC-05**: 유휴 만료(`last_seen_at` 갱신 주기·유휴 시간 결정)와 만료 세션 정리
3. **SEC-10**: 비밀번호 본인 변경·관리자 재설정(세션 폐기 + 감사). 요구사항 결정 후
4. (선택) 다중 워커가 필요해질 때 로그인 제한 공유 저장소(DB 테이블 → 스키마 승인 필요)
5. (선택) 학생 검색을 쿼리 문자열이 아닌 방식으로 바꿀지 여부(플랫폼 로그 확인 결과에 따라)
6. 프론트 기존 실패 테스트(시간대 선택 후 '미리보기' 활성화) 수정

## 7. Phase 11-5에서 사용자가 직접 확인할 배포 설정
> **후속 작업으로 확정본이 나왔다**: `docs/deployment/phase11_5_security_deployment_guide.md`. 아래 목록과 다르면 확정본을 따른다. 특히 프록시 주소는 `ACADEMY_TRUSTED_PROXIES` 대신 비밀 헤더(`ACADEMY_EDGE_SECRET`)와 `ACADEMY_CLIENT_IP_HEADER=cf-connecting-ip`를 쓰는 구성이 권장안이다. 근거와 검증 결과는 `phase11_2_b2_followup_results.md`에 있다.

- [ ] **uvicorn 실행 명령**에 `--no-proxy-headers --no-access-log` 포함. `--forwarded-allow-ips='*'` 사용 금지(앱이 신뢰 판단을 함)
- [ ] **워커 1개**(`--workers` 미지정 = 1). 늘리면 로그인 한도가 워커 수만큼 늘어남
- [ ] **`ACADEMY_TRUSTED_PROXIES`**: 배포 후 앱에 실제로 접속하는 상대 주소(Render 내부 프록시)를 확인해 그 범위만 넣는다. `0.0.0.0/0`·`::/0` 금지. 비워 두면 안전하지만 전원이 프록시 주소 하나로 집계된다(주소 한도 20, 계정별 한도는 정상 동작)
- [ ] Vercel Rewrite → Render 구성이면 XFF에 어떤 주소들이 차례로 붙는지 확인(Vercel 엣지 주소가 클라이언트로 보이면 사용자들이 소수 주소로 묶임 → 주소 한도 값 조정 또는 신뢰 범위 재검토)
- [ ] 로그인 실패를 반복해 429가 사용자별로 나는지 실제 환경에서 확인
- [ ] `ACADEMY_API_DOCS` 미설정(0). 시연용 공개를 원하면 의도적으로 1
- [ ] `ACADEMY_COOKIE_SECURE` 미설정 또는 1(0 금지). HTTPS에서 `Set-Cookie`에 `Secure; HttpOnly; SameSite=lax` 확인
- [ ] HSTS: 플랫폼이 이미 보내는지 응답 헤더 확인. 없고 HTTPS만 쓰면 `ACADEMY_HSTS_MAX_AGE`(예: 15552000) 설정
- [ ] `ACADEMY_CORS_ORIGINS`에 운영 프론트 출처만
- [ ] 배포 이미지에 `defusedxml` 설치 확인(`pyproject.toml` 의존성으로 설치됨)
- [ ] 플랫폼(Render/Vercel) HTTP 로그가 쿼리 문자열을 남기는지 확인 → 남기면 로그 보존 기간·접근 권한 제한
- [ ] 서버 로그에 이메일·학생 이름·SQL 파라미터가 없는지 일부러 500을 내지 않는 범위에서 표본 확인(정상 요청 로그는 경로·상태·요청 ID만)
- [ ] CI에 `pip-audit`·`npm audit` 추가(SEC-11)
- [ ] 첫 커밋 전 `git status`로 `.env`·`.dev-data` 미추적 확인(11-2-A 이관 항목)

## 8. 전체 Phase 11-2 종료 판정 — **PASS**
- **11-2-A 감사의 코드 결함은 모두 처리되었다**: SEC-01(High)·SEC-02(B-1), SEC-03·06·07(이번 단계)을 수정했다. SEC-08·09는 운영 설정으로 제어할 수 있게 했고, SEC-11은 실제 취약점 데이터로 검사해 해당 2건을 패치했다.
- 관련 테스트와 기존 보안 테스트가 모두 통과했다(백엔드 159/159). 회귀는 없다. 프론트 실패 1건은 이번 변경 전부터 있던 것이다.
- 남은 항목은 결함이 아니다. 지시로 이관한 기능·정책(SEC-04·05·10)과 실제 클라우드에서만 확인할 수 있는 설정(7절)이며, Phase 11-4·11-5 진행을 막지 않는다.
