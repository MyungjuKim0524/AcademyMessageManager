# Phase 11-2-B-2 후속 — 프록시 IP 식별·계정 잠금 위험 검증과 배포 가이드 확정

작업일: 2026-11-20 · 사용자 결정: **로그인 한도 주소 20회 / 계정 20회 유지**(주소+계정 5회, 15분 창도 유지)
산출물: 이 문서, `docs/deployment/phase11_5_security_deployment_guide.md`(배포 설정 확정본)
제약 준수: DB 스키마 변경·새 인프라·새 라이브러리 없음. 인증·세션·CSRF 구조 유지. SEC-04·05 미변경. 모든 새 동작은 **설정으로만 켜지고 기본값은 기존과 같다**(아래 표의 동시성·IPv6·잠금 완화 3가지 제외 — 이들은 결함 수정).

## 1. 검증 결과

| # | 확인한 위험 | 방법 | 결과 |
|---|---|---|---|
| V1 | **동시 요청으로 한도 우회** | 격리 DB에서 같은 계정·같은 주소로 틀린 비밀번호 30건 병렬 전송 | **30건 모두 401, 429 0건** — 확인 검사와 실패 기록이 따로라서 동시에 들어온 요청이 모두 검사를 통과. 5회·20회·20회 한도 전부 우회 가능. **결함(High)** |
| V2 | Render 앞단에서 `X-Forwarded-For` 위조 | Render 공식 글·커뮤니티 | Render 프록시는 들어온 XFF를 지우지 않고 덧붙임. `onrender.com`으로 직접 접속 가능. → XFF 왼쪽 값은 믿으면 안 됨. Cloudflare의 `CF-Connecting-IP`는 매 요청 덮어씀 |
| V3 | Vercel Rewrite 경유 시 방문자 주소 | Vercel 공식 문서 | Vercel은 XFF를 연결 주소로 덮어씀. 외부 원본은 **Vercel에서 온 요청에만** 이 헤더를 믿고 비밀 헤더로 구분하라고 권고 |
| V4 | 기존 B-2 설정만으로 배포할 때 | 위 사실 + 코드 | B-2의 `ACADEMY_TRUSTED_PROXIES`는 Render 내부 프록시 주소와 Vercel 송신 주소를 알아야 한다. 둘 다 공개 정보로 확정할 수 없어 **실제로는 비워 두게 되고**, 전원이 프록시 주소 하나로 묶임 → 공격자 1명이 실패 20회로 **전 사용자 로그인 15분 차단**, 실패 5회로 특정 계정 소유자 차단 |
| V5 | 특정 계정 표적 잠금 | 코드 분석 | 계정 20회 한도는 누구나 다른 주소들에서 소진할 수 있다 → 소유자는 정확한 주소 식별이 되어도 15분씩 반복해서 잠길 수 있었음 |
| V6 | IPv6 주소 회전 | 코드 분석 | IPv6 사용자는 보통 /64 전체를 가진다 → 주소를 바꿔 가며 주소별 카운터를 새로 받음(계정 20회만 남음) |
| V7 | 프록시 헤더 형식 | 코드 분석 | `주소:포트`, `[v6]:포트`, IPv4-mapped 형식을 해석하지 못해 `invalid-forwarded` 하나로 묶일 수 있었음 |
| V8 | 서버 오류의 실패 집계 | 코드 분석 | 기존 코드는 예외 시 실패를 기록하지 않음(정상). 예약 방식으로 바꾼 뒤에도 유지되도록 반환 처리 필요 |
| V9 | 설정 실수 감지 | — | 프록시 뒤인데 식별 설정이 빠져도 아무 신호가 없었음 |

## 2. 수정 내용 (코드)

| 대상 | 변경 |
|---|---|
| `auth/service.py` `LoginRateLimiter.reserve/release` | **V1**: 세 카운터를 한 잠금 안에서 모두 확인하고 이번 시도를 즉시 기록(예약). 틀린 비밀번호면 예약이 실패 1회가 됨. 성공 시 주소 카운터에서 자기 예약만 반환하고, 주소+계정·계정 카운터는 비움(기존 동작). 서버 오류면 예약 전부 반환(V8) |
| `auth/service.py` `is_known/remember` | **V5**: 최근 30일 안에 그 계정으로 로그인에 성공한 주소(계정당 최근 5개, 메모리)에서는 **계정 전체 한도만** 적용하지 않음. 주소+계정 5회·주소 20회는 그대로. 성공한 로그인(비밀번호 필요)만 주소를 등록 |
| `auth/service.py` `parse_address`, `limiter_bucket` | **V6·V7**: 포트·대괄호·따옴표·IPv4-mapped 형식 해석, IPv6는 /64 단위로 집계 |
| `auth/service.py` `resolve_client` | **V2~V4**: 설정으로 켜는 주소 출처 2개 추가(우선순위 순). ① `ACADEMY_EDGE_SECRET`: 비밀 헤더가 맞는 요청(우리 Vercel Rewrite)만 XFF 가장 왼쪽 사용 ② `ACADEMY_CLIENT_IP_HEADER`(예: `cf-connecting-ip`): 바깥 엣지가 덮어쓰는 단일 주소 헤더. 기존 `ACADEMY_TRUSTED_PROXIES`는 ③으로 유지. 비밀 비교는 상수 시간(`hmac.compare_digest`) |
| `auth/service.py` | **V9**: 아무 출처도 설정하지 않았는데 XFF가 오면 경고 로그 1회(`forwarded_header_ignored`, 주소 값 없음) |
| `config.py` | 새 설정 4개. 비밀 32자 미만, 또는 `x-forwarded-for`·`forwarded`를 단일 주소 헤더로 지정하면 **시작 실패**. 비밀은 설정 객체 `repr`에 나오지 않음 |
| `auth/router.py`, `auth/schemas.py` | 로그인은 `resolve_client` → `limiter_bucket` 사용. **`GET /api/auth/client-address`**: 관리자 전용, `ACADEMY_PROXY_DIAGNOSTICS=1`일 때만 열림(기본 404). 호출자 자신의 상대 주소·XFF·출처·판정 결과를 보여 줌. 비밀값은 표시하지 않고 상태(`valid/missing/invalid/not-configured`)만 표시. 배포 점검용 |
| `backend/.env.example` | 새 변수 설명 |

API 계약: 로그인 요청·응답, 오류 코드(401/429)는 같다. 진단 엔드포인트만 추가되었고 기본 비활성이다. DB 변경은 없다.

## 3. 테스트

| 명령 | 결과 |
|---|---|
| `ruff check app tests` | All checks passed |
| `pytest -m "not postgres"` | **76 passed**(B-2 60 + 신규 16) |
| `pytest -m postgres`(격리 테스트 DB, 전체) | **105 passed**(B-2 99 + 신규 6). 기존 인증·RBAC·CSRF·업로드·감사 테스트 포함 |
| 백엔드 합계 | **181 passed, 0 failed** |

격리 확인: B-1·B-2와 같은 실행기(`run-postgres-integration.ps1`의 컨테이너 라벨·포트·DB 이름·사용자 검사를 그대로 수행). 가상 데이터만 사용했다.

**신규 테스트**
- `tests/test_phase112b2_client_identity.py`(단위 16):
  - 헤더 주소 형식 9종, IPv6 /64·IPv4-mapped 묶음
  - 기본 설정에서 XFF·CF 헤더 무시 + 경고 1회(주소 없음)
  - 비밀 헤더 경로: 맞으면 왼쪽 주소, 없거나 틀리면 무시
  - 단일 주소 헤더 경로, 그리고 비밀 헤더가 CF 헤더보다 우선
  - 위험한 설정의 시작 실패, `repr`에 비밀 없음
  - **스레드 32개·요청 200건에서 정확히 5건만 통과**
  - 예약 반환, 알려진 주소 상한·만료
- `tests/test_phase112b2_login_integration.py`(통합 6건 추가, 실제 API·PostgreSQL):
  - `test_parallel_wrong_passwords_cannot_exceed_the_limit`: V1 재현을 회귀 테스트로 전환. 병렬 30건 → **401 5건 + 429 25건**. 10개 주소 병렬 40건 → 계정 한도 20에서 멈춤
  - `test_owner_is_not_locked_out_from_a_known_address`: 남이 계정 실패 20회 소진 → 새 주소는 429, **소유자의 평소 주소는 200**. 그 주소에서도 5회 한도는 그대로
  - `test_rotating_ipv6_addresses_inside_one_64_does_not_reset_counters`
  - `test_server_errors_do_not_count_as_failures`: 500 8회 후에도 정상 로그인
  - `test_edge_secret_counts_the_visitor_and_ignores_forgeries`: 같은 엣지 뒤 방문자별 분리, 직접 접속자의 XFF 위조 무시
  - `test_client_address_diagnosis_is_admin_only_and_off_by_default`: 기본 404, 선생님 403, 미인증 401, 관리자 응답 전체 값 검증, 비밀값 미노출

## 4. 배포 설정 가이드 확정 요약
`docs/deployment/phase11_5_security_deployment_guide.md`에 정리했다.
- **구성 A(권장)**: Vercel Rewrite가 `X-Academy-Edge-Secret`을 붙이고, Render에 `ACADEMY_EDGE_SECRET` + `ACADEMY_CLIENT_IP_HEADER=cf-connecting-ip`를 설정한다. 방문자별로 정확히 세고 위조할 수 없다.
- **구성 A′(대안)**: 비밀 헤더를 붙일 수 없으면 `cf-connecting-ip`만 설정한다. 위조는 불가하지만 Vercel 송신 주소 단위로 묶인다(영향을 문서화함).
- uvicorn `--no-proxy-headers --no-access-log`, 워커 1, 쿠키·CORS·HSTS·문서 비공개·로그 확인.
- 배포 직후 **진단 절차 6단계**(정상 경로 → Vercel 경유 위조 → Render 직접 우회 → 로그인 제한 → 로그 → 진단 끄기)와 결과별 분기.
- 문서만으로 단정할 수 없는 3가지를 "확인 필요"로 표시하고, 진단 절차로 확인하게 했다:
  - ① Vercel 외부 Rewrite에 요청 헤더를 추가하는 방법
  - ② Vercel이 원본에 보내는 XFF 첫 값이 방문자 주소인지
  - ③ Render에 `CF-Connecting-IP`가 도착하는지

## 5. 남은 사항
- **SEC-04(Phase 11-4)가 먼저 필요하다**: 현재 코드로는 배포 환경에서 DB API가 404다. 가이드 상단에 명시했다.
- 계정 소유자가 처음 쓰는 주소에서는 표적 잠금 중 최대 15분 기다려야 한다. 해제 수단은 재시작뿐이다(관리자 해제 API는 만들지 않음 — 필요하면 11-4에서 결정).
- 카운터·알려진 주소는 프로세스 메모리에 있다(재시작 시 초기화, 워커 1 전제). 공유 저장소는 스키마 승인이 필요하다.
- 플랫폼 동작은 공식 문서 기준이며 실제 확인은 11-5 진단 절차로 한다.

## 6. 판정 — **PASS**
- 검증 중 발견한 **동시 요청 우회(High)**, IPv6 회전, 헤더 형식, 표적 잠금, 배포 시 전원 묶임 위험을 코드로 해결했고 회귀 테스트로 고정했다.
- 20/20 한도는 유지했다.
- 남은 것은 실제 플랫폼에서만 확인할 수 있는 항목이며, 그 절차를 가이드로 확정했다.

참고 자료: [Vercel Request headers](https://vercel.com/docs/headers/request-headers), [Vercel Rewrites](https://vercel.com/docs/routing/rewrites), [Vercel WAF honeypot 가이드](https://vercel.com/kb/guide/how-to-build-a-honeypot-with-vercel-web-application-firewall), [Render: Host PocketBase](https://render.com/articles/host-pocketbase-on-render), [Render 커뮤니티: client IP](https://community.render.com/t/accessing-client-ips-in-a-node-express-app/36282), [Render: DDoS 대응](https://render.com/articles/how-render-handles-ddos-attacks)
