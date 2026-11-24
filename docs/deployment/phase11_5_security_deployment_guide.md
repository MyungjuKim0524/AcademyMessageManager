# Phase 11-5 보안 배포 설정 가이드 (확정본)

작성: 2026-11-20 (Phase 11-2-B-2 후속) · 대상: Vercel(프론트) + Render(FastAPI) 배포를 직접 수행하는 사람
근거 문서: `docs/reviews/phase11_2_b2_results.md`, `docs/reviews/phase11_2_b2_followup_results.md`, `docs/reviews/phase11_4_b_runtime_account_results.md`
갱신: 2026-11-21 (Phase 11-4-B) — production 실행 모드, 운영 DB URL(TLS), 유휴 세션 만료, 최초 관리자·재설정 절차 반영

> **(2026-11-25) 배포 완료**: 이 가이드대로 2026-11-24에 배포했다(구성 A′). 본문의 "아직 확인하지 않았다"·"확인 필요"는 배포 전 기준 문구다. 실제 점검 결과와 남은 미확인 항목은 [`DEVELOPMENT_HISTORY.md`](../DEVELOPMENT_HISTORY.md) 3절 Phase 11 "11-5 클라우드 배포"를 본다.

> **먼저 알아둘 점 — 실행 모드(SEC-04, Phase 11-4-B 반영)**: 배포 서버는 `ACADEMY_DB_MODE=production`으로 실행한다. development/test 모드는 지금도 루프백 호스트와 고정된 로컬 DB만 허용하므로, 이 두 모드로 배포하면 로그인·업무 API가 404다.
> production 모드에서는 루프백 검사를 하지 않는다(`app/security.py`). 대신 **시작할 때 아래 조건을 모두 검사하고, 하나라도 어기면 앱이 시작되지 않는다**(`app/config.py::production_problems`, `app/main.py`). 오류 메시지에는 설정 **이름만** 나오고 값은 나오지 않는다.
> - `ACADEMY_ENABLE_DB_APIS=1`
> - `ACADEMY_DATABASE_URL`: PostgreSQL이고 `sslmode`가 `require`·`verify-ca`·`verify-full` 중 하나다. 로컬 개발·테스트 DB(55431/55432)를 가리키면 안 된다(`app/db/safety.py::validate_production_database_url`).
> - `ACADEMY_COOKIE_SECURE=1`
> - `ACADEMY_CORS_ORIGINS`: 정확한 `https://` 출처만 넣는다. `localhost`·`127.0.0.1`·`*`는 넣으면 안 된다.
> - `ACADEMY_TRUSTED_PROXIES`에 `/0`(전체 신뢰)이 없다.
> - `ACADEMY_DB_TEST_MODE`, `ACADEMY_RUN_POSTGRES_INTEGRATION`이 설정되어 있지 않다.
> - `ACADEMY_SESSION_IDLE_MINUTES`: 1 이상, `ACADEMY_SESSION_TTL_MINUTES` 이하.
>
> `ACADEMY_PROXY_DIAGNOSTICS=1`은 6절 점검 때 잠깐 켜야 하므로 production에서도 허용한다.
> 이 시작 검증은 로컬에서 subprocess import로만 모의 검증했다. **실제 Render 환경에서는 아직 확인하지 않았다**(6절 0단계).

플랫폼 동작은 공식 문서·플랫폼 글을 근거로 적었다. 계정·요금제마다 다를 수 있으므로 **모든 항목은 6절의 진단 절차로 실제 환경에서 확인한 뒤 확정**한다. "확인 필요"는 문서만으로 단정할 수 없는 항목이다.

---

## 1. 권장 구성

```
브라우저 ──HTTPS──▶ Vercel (프론트 + /api/* Rewrite) ──HTTPS──▶ Render(Cloudflare → 로드밸런서) ──▶ uvicorn(FastAPI, 워커 1)
                    · X-Forwarded-For를 방문자 주소로 덮어씀        · CF-Connecting-IP: 직접 연결한 주소(=Vercel)
                    · 비밀 헤더 X-Academy-Edge-Secret 추가           · X-Forwarded-For 뒤에 덧붙임(지우지 않음)
```

- **같은 출처(Vercel Rewrite)를 쓴다.** 세션 쿠키가 `SameSite=Lax`라서 프론트와 API가 다른 사이트면 로그인이 유지되지 않는다(B-2 문서 5절). 브라우저가 Render 주소를 직접 부르는 구성은 지원하지 않는다.
- 근거:
  - Vercel은 요청이 들어올 때 `X-Forwarded-For`를 연결 주소로 **덮어써** 위조를 막는다([Vercel Request headers](https://vercel.com/docs/headers/request-headers), [Vercel WAF honeypot 가이드](https://vercel.com/kb/guide/how-to-build-a-honeypot-with-vercel-web-application-firewall)).
  - Vercel은 외부 원본(origin)이 이 헤더를 **Vercel에서 온 요청에만** 믿고, 비밀 헤더로 Vercel을 우회한 요청을 구별하라고 권한다([Vercel Rewrites](https://vercel.com/docs/routing/rewrites)).
  - Render 공개 웹 서비스 앞에는 Cloudflare가 있다. `CF-Connecting-IP`는 매 요청 Cloudflare가 덮어쓴다. 반면 Render 프록시는 들어온 `X-Forwarded-For`를 지우지 않고 뒤에 덧붙이므로 **왼쪽 값은 위조될 수 있다**([Render: Host PocketBase](https://render.com/articles/host-pocketbase-on-render), [Render 커뮤니티](https://community.render.com/t/accessing-client-ips-in-a-node-express-app/36282), [Render: DDoS 대응](https://render.com/articles/how-render-handles-ddos-attacks)).
  - `onrender.com` 주소는 Vercel을 거치지 않고도 접속할 수 있다.

## 2. 클라이언트 주소 식별 설정 (로그인 시도 제한의 기준)

앱은 아래 순서로 주소를 정한다(`app/modules/auth/service.py::resolve_client`). **모두 기본 꺼짐**이며, 아무것도 설정하지 않으면 소켓 상대 주소만 쓴다.

| 순서 | 출처 | 켜는 설정 | 믿는 값 | 위조 방어 |
|---|---|---|---|---|
| 1 | `edge` | `ACADEMY_EDGE_SECRET`(32자 이상) | 비밀 헤더가 맞을 때만 `X-Forwarded-For`의 **가장 왼쪽** | 비밀을 모르면 이 경로를 탈 수 없음. Vercel이 XFF를 덮어씀 |
| 2 | `client-ip-header` | `ACADEMY_CLIENT_IP_HEADER=cf-connecting-ip` | 그 헤더의 단일 주소 | Cloudflare가 매 요청 덮어씀 |
| 3 | `trusted-proxies` | `ACADEMY_TRUSTED_PROXIES=<CIDR>` | XFF를 오른쪽부터 신뢰 프록시를 건너뛰며 첫 주소 | 상대 주소가 목록에 있을 때만 |
| 4 | `peer` | (기본) | 소켓 상대 주소 | — |

**구성별 확정값**

| 구성 | `ACADEMY_EDGE_SECRET` | `ACADEMY_CLIENT_IP_HEADER` | `ACADEMY_TRUSTED_PROXIES` | 결과 |
|---|---|---|---|---|
| **A. 권장**: Vercel Rewrite가 비밀 헤더를 붙일 수 있음 | 무작위 48자 이상 | `cf-connecting-ip` | 비움 | Vercel 경유 → 방문자 주소. Render 직접 접속 → 실제 접속 주소. 위조 불가 |
| **A′. 대안**: 비밀 헤더를 붙일 수 없음 | 비움 | `cf-connecting-ip` | 비움 | Vercel 경유 요청은 **Vercel 송신 주소로 묶임**(3절 영향 참고). 위조는 불가 |
| 사용 금지 | — | `x-forwarded-for`·`forwarded`(설정 시 시작 실패) | `0.0.0.0/0`, `::/0` | 누구나 주소 위조 가능 |

- `x-real-ip`·`x-vercel-forwarded-for`는 쓰지 않는다. 덮어쓰기 보장 문구가 없거나, 앞단 프록시가 있으면 의미가 달라진다(Vercel 문서).
- **확인 필요 ①**: Vercel에서 외부 원본 Rewrite에 **요청 헤더를 추가**하는 방법(Rewrites 문서의 권장 사항, 프로그래매틱 설정 `vercel.ts` 또는 Routing Middleware). 비밀값은 저장소에 커밋하지 말고 Vercel 환경변수로 넣는다. 붙일 수 없으면 A′로 운영하고 3절의 영향을 받아들이거나, 아래 7절의 대안을 검토한다.
- **확인 필요 ②**: Vercel이 외부 원본에 보내는 `X-Forwarded-For` 첫 값이 방문자 주소인지. 6절 진단 절차로 확인한다.
- **확인 필요 ③**: Render 서비스에 `CF-Connecting-IP`가 실제로 오는지(공개 웹 서비스에만 있고 프라이빗 서비스에는 없음 — Render 글). 6절에서 확인한다. 없으면 이 설정은 아무 효과 없이 상대 주소로 대체된다(안전하지만 묶임).
- 아무 출처도 설정하지 않았는데 `X-Forwarded-For`가 들어오면 서버 로그에 **`forwarded_header_ignored` 경고가 한 번** 찍힌다(주소 값은 기록하지 않음). 배포 직후 로그에서 이 줄이 보이면 설정이 빠진 것이다.

## 3. 로그인 시도 제한 (사용자 결정: 20/20 유지)

| 카운터 | 키 | 한도(15분 창) | 환경변수 |
|---|---|---|---|
| 주소+계정 | 주소 묶음 + 이메일 | 5 | `ACADEMY_LOGIN_ATTEMPT_LIMIT=5` |
| 주소 전체 | 주소 묶음 | 20 | `ACADEMY_LOGIN_IP_ATTEMPT_LIMIT=20` |
| 계정 전체 | 이메일 | 20 | `ACADEMY_LOGIN_ACCOUNT_ATTEMPT_LIMIT=20` |
| 창 길이 | — | 900초 | `ACADEMY_LOGIN_WINDOW_SECONDS=900` |

동작 요약(후속 작업에서 검증·보강한 내용):
- **동시 요청 우회 차단**: 비밀번호 검사 전에 모든 카운터를 한 번에 확인하고 예약한다. 병렬 30회 요청을 보내도 401은 5회만 나온다.
- **주소 묶음**: IPv6는 /64 단위, IPv4-mapped IPv6는 IPv4로 센다. `주소:포트`, `[v6]:포트` 형식도 처리한다.
- **계정 잠금 완화**: 최근 30일 안에 그 계정으로 로그인에 성공한 주소(계정당 최근 5개)에서는 계정 전체 한도를 적용하지 않는다. 주소+계정 5회와 주소 전체 20회 한도는 그대로 적용된다. 따라서 남이 계정 실패 20회를 소진해도 소유자는 평소 주소(학원·집)에서 로그인할 수 있다.
- 서버 오류(500)는 실패로 세지 않는다. 성공한 로그인은 주소 전체 카운터에서 자기 시도만 빼고, 다른 실패 기록은 지우지 않는다.

**구성 A′(Vercel 송신 주소로 묶임)일 때의 영향**: 같은 Vercel 송신 주소를 공유하는 사용자들이 같은 주소 키를 쓴다.
- 한 공격자가 Vercel을 거쳐 실패 20회를 내면, 그 송신 주소를 쓰는 **모든 사용자가 최대 15분간 로그인할 수 없다.**
- 같은 계정에 대해서는 실패 5회로 그 송신 주소의 계정 소유자도 막힌다.
- Vercel 송신 주소가 몇 개이고 어떻게 바뀌는지는 공개 정보로 단정할 수 없다(확인 필요).
- 그래서 **구성 A(비밀 헤더)를 강하게 권장한다.**

**운영 메모**
- 카운터와 "알려진 주소"는 프로세스 메모리에 있다. **재배포·재시작하면 모두 초기화된다.** 계정이 잠겼을 때 긴급히 푸는 방법도 이것뿐이다(별도 해제 API 없음).
- **워커는 1개**로 운영한다. 워커가 N개면 한도도 실질적으로 N배가 된다.

## 4. Render(API) 설정

**시작 명령**(워커 1, 프록시 판단은 앱이 함, 쿼리 문자열이 들어가는 접근 로그 끔):
```
uvicorn app.main:app --host 0.0.0.0 --port $PORT --no-proxy-headers --no-access-log
```
- `--forwarded-allow-ips='*'`는 쓰지 않는다. uvicorn 0.54는 기본으로 프록시 헤더를 처리하므로 `--no-proxy-headers`를 반드시 넣는다.
- `--host 0.0.0.0`은 `ACADEMY_DB_MODE=production`일 때만 동작한다. development/test 모드는 루프백만 허용한다.
- **워커는 반드시 1개**다(`--workers`를 쓰지 않는다). 로그인 시도 카운터와 비밀번호 재설정 코드가 프로세스 메모리에 있으므로, 워커가 여러 개면 한도가 N배로 늘고 발급한 재설정 코드가 다른 워커에서 "없는 코드"로 처리된다.

**DB 마이그레이션**: 배포 전에 운영 환경변수(아래 표)를 설정한 상태에서 `backend` 디렉터리에서 `alembic upgrade head`를 한 번 실행한다. 이번 단계(11-4-B)에는 스키마 변경이 없다.

실행 전 확인할 두 가지(2026-11-22 추가):
- **저장소 전체가 있는 위치에서 실행한다.**
  - 첫 Migration `001_java_schema_baseline`은 저장소 루트의 `sql/schema_postgresql.sql`을 읽는다(`backend/alembic/versions/001_java_schema_baseline.py`).
  - `backend/` 폴더만 복사한 곳에서 실행하면 001이 파일을 찾지 못해 실패한다.
  - 앱 실행에는 이 파일이 필요 없고, Migration을 실행할 때만 필요하다.
  - ☁️ Render의 Root Directory를 `backend`로 두었을 때 Render 셸에서 루트의 `sql/`이 보이는지는 확인이 필요하다. 보이지 않으면 저장소 전체를 받은 로컬 PC에서 운영 DB 주소로 실행한다.
- **`btree_gist` 확장을 만들 권한이 필요하다.**
  - `007_phase71_sessions_pauses`가 `CREATE EXTENSION IF NOT EXISTS btree_gist`를 실행한다. 휴원 기간이 겹치지 않게 막는 EXCLUDE 제약에 필요하다.
  - PostgreSQL 13 이상에서 `btree_gist`는 "trusted" 확장이라, 슈퍼유저가 아니어도 해당 DB에 CREATE 권한이 있으면 만들 수 있다.
  - ☁️ Neon은 프로젝트 소유자 역할로 Migration을 실행하면 007이 확장을 직접 만든다. 대시보드에서 미리 켜는 단계는 없다. 생성되었는지는 `phase11_5_a_neon_guide.md` 5절 쿼리로 확인한다.
  - 권한이 없으면 007에서 실패한다. `alembic/env.py`는 한 번의 `upgrade` 전체를 하나의 트랜잭션으로 실행하므로, 이때 001~006도 함께 롤백되어 DB는 빈 상태로 돌아간다.
  - Neon 연결·Migration·Seed 절차 전체는 `phase11_5_a_neon_guide.md`를 따른다.

**최초 관리자 계정**: 서비스 셸에서 한 번만 실행한다. 값은 셸 입력으로만 넣고, 실행 후 환경변수를 지운다. 문서·채팅·커밋에 남기지 않는다.
```
ACADEMY_BOOTSTRAP_ADMIN=1 ACADEMY_BOOTSTRAP_EMAIL=<관리자 이메일> ACADEMY_BOOTSTRAP_PASSWORD=<12자 이상> python scripts/bootstrap_admin.py
```
- 같은 이메일 계정이 이미 있으면 덮어쓰지 않고 실패한다.
- 유일한 관리자가 비밀번호를 잊었을 때도 이 스크립트로 **새 관리자**를 만든다. 그 관리자가 직원 관리 화면에서 기존 계정에 재설정 코드를 발급한다. 일이 끝나면 필요 없는 관리자 계정은 비활성화하거나 삭제한다.

**환경변수**

| 변수 | 값 | 비고 |
|---|---|---|
| `ACADEMY_DB_MODE` | `production` | 시작할 때 설정을 검증한다. 위반이 있으면 시작하지 않는다(맨 위 안내) |
| `ACADEMY_DATABASE_URL` | `postgresql+psycopg://<user>:<url-encoded-password>@<host>:<port>/<db>?sslmode=require` | Render Secret으로 저장한다. `verify-full` 권장(CA 준비 시). `sslmode` 없으면 시작 실패 |
| `ACADEMY_ENABLE_DB_APIS` | `1` | 0이면 시작 실패 |
| `ACADEMY_API_HOST` | 미설정 | 시작 명령의 `--host`가 실제 바인딩. production은 루프백 검사 생략 |
| `ACADEMY_COOKIE_SECURE` | `1` (또는 미설정) | **0 금지**(시작 실패) |
| `ACADEMY_CORS_ORIGINS` | `https://<Vercel 운영 도메인>` | 정확히 일치. 미리보기 도메인을 넣을지는 별도 결정 |
| `ACADEMY_API_DOCS` | 미설정(0) | 시연용 공개를 원할 때만 1 |
| `ACADEMY_HSTS_MAX_AGE` | 아래 5절 확인 후 결정 | 기본 0 |
| `ACADEMY_EDGE_SECRET` | 무작위 48자 이상(구성 A) | Render Secret으로 저장, 출력·커밋 금지 |
| `ACADEMY_EDGE_SECRET_HEADER` | 미설정(`x-academy-edge-secret`) | Vercel 쪽과 같은 이름 |
| `ACADEMY_CLIENT_IP_HEADER` | `cf-connecting-ip` | 6절에서 헤더 존재 확인 |
| `ACADEMY_TRUSTED_PROXIES` | 비움 | 구성 A/A′에서는 쓰지 않음 |
| `ACADEMY_PROXY_DIAGNOSTICS` | 평소 `0` | 6절 점검 동안에만 1 |
| `ACADEMY_LOGIN_*` | 5 / 20 / 20 / 900 | 3절 |
| `ACADEMY_LOG_LEVEL` | `INFO` | |
| `ACADEMY_SESSION_TTL_MINUTES` | `480` | 절대 만료(8시간) |
| `ACADEMY_SESSION_IDLE_MINUTES` | `60` | SEC-05 유휴 만료. 1..TTL만 가능, 0(무제한) 금지. 만료 시 401 `SESSION_IDLE_EXPIRED` |
| `ACADEMY_DB_TEST_MODE`, `ACADEMY_RUN_POSTGRES_INTEGRATION` | 설정하지 않음 | 있으면 시작 실패 |

비밀값 생성 예(로컬에서 한 번 실행하고 값은 화면 밖에 보관):
```
python -c "import secrets; print(secrets.token_urlsafe(48))"
```
Vercel과 Render 양쪽에 같은 값을 넣는다. 값이 짧거나(32자 미만) 헤더 이름 설정이 잘못되면 **앱이 시작되지 않는다**(fail closed). 비밀을 바꿀 때는 두 곳을 동시에 바꾼다. 잠깐 어긋나는 동안에는 Vercel 경유 요청이 A′처럼 묶일 뿐 오류는 나지 않는다.

## 5. Vercel(프론트) 설정
- [ ] `/api/:path*` → `https://<Render 서비스 주소>/api/:path*` Rewrite
- [ ] 그 Rewrite 요청에 `X-Academy-Edge-Secret: <비밀>` 추가(확인 필요 ①). 비밀은 Vercel 환경변수로 관리
- [ ] 프론트가 API를 같은 출처(`/api`)로 부르는지 확인(브라우저 개발자 도구에서 요청 URL 확인)
- [ ] HSTS: 운영 도메인 응답에 `Strict-Transport-Security`가 이미 있는지 확인. Vercel이 붙여 주면 API의 `ACADEMY_HSTS_MAX_AGE`는 0으로 둬도 된다. 없고 HTTPS 전용이면 `15552000`(180일)부터 시작. `includeSubDomains`·preload는 도메인 전체 정책이므로 별도 결정

## 6. 배포 직후 진단 절차 (반드시 수행, 약 15분)

준비: Render에 `ACADEMY_PROXY_DIAGNOSTICS=1`을 넣고 재배포한다. 이 엔드포인트는 관리자 전용이며 호출자 **자신의** 주소와 프록시 경로만 보여 준다(비밀값은 표시하지 않음).

0. **시작 검증(Phase 11-4-B)**: Render 배포 로그에 앱 시작 오류(`RuntimeError`, 설정 이름 목록)가 없고 서비스가 Live인지 확인한다. 실패하면 로그에 나온 **설정 이름**을 고친다(값은 로그에 나오지 않는다). 시험 삼아 `ACADEMY_COOKIE_SECURE=0`으로 한 번 배포해 보고 시작이 거부되는지 확인한 뒤 되돌려도 된다(선택).
   - 로그인 후 아무 조작 없이 `ACADEMY_SESSION_IDLE_MINUTES`보다 오래 두면, 다음 조작 때 "오랫동안 사용하지 않아 로그아웃되었습니다. 다시 로그인해주세요." 안내와 함께 로그인 화면으로 돌아가는지 확인한다(점검 동안에만 값을 줄여도 된다. 끝나면 60으로 되돌린다).

1. **정상 경로**: 운영 도메인에서 관리자로 로그인한 뒤, 같은 브라우저 주소창에서 `https://<운영 도메인>/api/auth/client-address`를 연다.
   - 기대(구성 A): `source: "edge"`, `edge_secret: "valid"`, `resolved` = 내 공인 IP(외부 "내 IP 확인" 서비스 값과 비교)
   - 구성 A′: `source: "client-ip-header"`, `resolved` = Vercel 송신 주소(내 IP 아님)
   - `client_ip_header_value`가 비어 있으면 확인 필요 ③ 실패 → `CF-Connecting-IP` 미전달
2. **위조 시도(Vercel 경유)**: 관리자 쿠키로 같은 URL에 `X-Forwarded-For: 192.0.2.123`을 붙여 호출한다(예: curl `-H "Cookie: ..."`). 쿠키는 다른 곳에 저장하거나 공유하지 말고, 끝나면 로그아웃해 무효화한다.
   - 기대: `resolved`가 여전히 내 IP(Vercel이 덮어씀). `192.0.2.123`이 보이면 **구성 A 사용 금지** → 확인 필요 ② 실패이므로 A′로 바꾼다.
3. **우회 시도(Render 직접)**: `https://<서비스>.onrender.com/api/auth/client-address`에 같은 쿠키와 위조 헤더로 호출한다.
   - 기대: `edge_secret: "missing"`, `source: "client-ip-header"`(또는 `peer`), `resolved` ≠ `192.0.2.123`
4. **로그인 제한**: 테스트용 계정으로 틀린 비밀번호 6회 → 6번째 429. 다른 네트워크(휴대폰 LTE 등)의 다른 계정은 바로 로그인되는지 확인.
5. **로그**: Render 로그에서 확인한다.
   - `request_complete … endpoint=/api/...` 줄에 쿼리 문자열·이메일이 없어야 한다.
   - `forwarded_header_ignored` 경고가 없어야 한다(구성 A·A′에서는 나오지 않음).
   - `unhandled_request_error` 줄이 있다면 예외 문구 없이 유형·SQLSTATE만 있어야 한다.
6. **마무리**: `ACADEMY_PROXY_DIAGNOSTICS=0`(또는 삭제)으로 재배포하고, 같은 URL이 404인지 확인한다.

## 7. 확인 결과에 따른 분기

| 결과 | 조치 |
|---|---|
| 1~3 모두 기대대로 | 구성 A 확정 |
| Vercel에서 비밀 헤더를 붙일 수 없음 | A′ 운영. 3절 영향을 감수하거나, 로그인 경로만 Vercel Routing Middleware로 헤더를 붙이는 방법을 검토(코드 변경 없이 Vercel 설정 작업) |
| 2에서 위조값이 보임 | `ACADEMY_EDGE_SECRET` 제거 → A′ |
| `CF-Connecting-IP` 없음 | `ACADEMY_CLIENT_IP_HEADER` 제거. Render 직접 접속은 상대 주소(프록시)로 묶인다. 구성 A가 동작하면 실제 사용자에게는 영향 없음 |
| 로그인 429가 사용자 전체에 나타남 | 주소가 묶인 상태. 1단계 진단 결과로 원인 확인 → 재시작으로 즉시 해제 |

## 8. 그 밖의 배포 보안 점검
- [ ] HTTPS 응답의 `Set-Cookie`: `academy_session`에 `HttpOnly; Secure; SameSite=lax; Path=/`가 있고 `academy_csrf`에 `Secure`가 있는지 확인
- [ ] (선택) 세션 쿠키 이름을 `__Host-academy_session`으로(`ACADEMY_SESSION_COOKIE`). Secure·Path=/·Domain 없음 조건을 이미 만족한다. CSRF 쿠키 이름은 프론트 코드가 읽으므로 바꾸지 않는다
- [ ] `/docs`, `/redoc`, `/openapi.json` → 404
- [ ] 다른 출처에서 `fetch('https://<운영 도메인>/api/auth/me', {credentials:'include'})` → 403 `CORS_FORBIDDEN`
- [ ] 배포 이미지에 `defusedxml` 설치 확인(`pip show defusedxml`)
- [ ] Render·Vercel 플랫폼 HTTP 로그가 쿼리 문자열(`/api/students?q=` 학생 이름)을 남기는지 확인 → 남기면 로그 접근 권한·보존 기간 제한
- [ ] CI에 `pip-audit`, `npm audit` 추가(SEC-11)
- [ ] 첫 커밋 전 `git status`로 `.env`, `.dev-data`가 추적되지 않는지 확인

## 9. 남는 위험 (알고 운영할 것)
- 계정 소유자가 **처음 쓰는 주소**에서는, 남이 계정 실패 20회를 소진한 동안 최대 15분 로그인할 수 없다(새 PC·새 네트워크). 재시작으로 해제된다.
- 카운터가 메모리에 있어 재시작하면 공격자의 시도 기록도 사라진다. 15분 창 기준이므로 실질 영향은 작다.
- 구성 A′에서는 Vercel 송신 주소 단위로 묶인다(3절).
- 정확한 IP 식별을 Cloudflare·Vercel의 헤더 덮어쓰기에 의존한다. 플랫폼 동작이 바뀌면 6절 진단을 다시 수행한다.
- (11-4-B) 비밀번호 재설정 코드는 프로세스 메모리에만 있다. **재배포·재시작하면 발급한 코드가 모두 사라진다**(다시 발급하면 된다). 워커가 여러 개면 동작하지 않는다.
- (11-4-B) 유휴 판정은 활동 기록을 60초에 한 번만 저장한다. 그래서 세션이 설정값보다 **최대 약 1분 일찍** 끝날 수 있다. 늦게 끝나는 일은 없다.
