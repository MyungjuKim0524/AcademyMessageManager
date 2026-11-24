# ruff: noqa: E501  -- Korean description strings for the generated document kept on one line
"""Generate docs/api/openapi.json and docs/api/README.md from the FastAPI app.

The API description is derived from code, so it cannot drift from the routes: rerun after an API change.

    cd backend
    .venv\\Scripts\\python.exe scripts\\generate_openapi.py           # writes ../docs/api/
    .venv\\Scripts\\python.exe scripts\\generate_openapi.py --check   # exit 1 if either file is stale

No database connection is needed. The deployed server keeps /openapi.json closed (SEC-08);
this script reads the schema straight from the app object, so it does not change that.
"""

import importlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.routing import APIRoute  # noqa: E402

from app.main import app  # noqa: E402
from app.modules.auth.dependencies import (  # noqa: E402
    get_current_principal,
    require_admin,
    require_admin_csrf,
    require_authenticated,
    require_csrf,
)

API_DIR = Path(__file__).resolve().parents[2] / "docs" / "api"
SPEC = API_DIR / "openapi.json"
SUMMARY = API_DIR / "README.md"

# Router module → section title, in the order the app includes them.
MODULES: list[tuple[str, str]] = [
    ("auth", "인증·계정"),
    ("learningops", "학생·반·직원 관리"),
    ("academics", "수업·출결·성적"),
    ("notifications", "성적 안내 메시지"),
    ("lesson_upload", "주간 엑셀 업로드"),
    ("message_operations", "메시지 처리 현황·일괄 처리"),
    ("analytics", "출결·성적 분석"),
    ("main", "상태 확인·이전 미리보기(레거시)"),
]
METHOD_ORDER = ["GET", "POST", "PUT", "PATCH", "DELETE"]


def dependency_calls(dependant) -> set:
    calls = set()
    for dep in dependant.dependencies:
        if dep.call is not None:
            calls.add(dep.call)
        calls |= dependency_calls(dep)
    return calls


def access_label(route: APIRoute) -> tuple[str, str]:
    calls = dependency_calls(route.dependant)
    if require_admin_csrf in calls or require_admin in calls:
        who = "관리자"
    elif calls & {require_authenticated, require_csrf, get_current_principal}:
        who = "직원"
    else:
        who = "공개"
    csrf = "필요" if (require_csrf in calls or require_admin_csrf in calls) else ""
    return who, csrf


def routes_of(key: str) -> list[APIRoute]:
    """Routes of one router module, or the routes declared on the app itself for "main"."""
    if key == "main":
        source = app.routes
    else:
        source = importlib.import_module(f"app.modules.{key}.router").router.routes
    return [r for r in source if isinstance(r, APIRoute) and r.include_in_schema]


def build_spec() -> str:
    return json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def build_summary() -> str:
    rows: dict[str, list[tuple[str, str, str, str, str]]] = {key: [] for key, _ in MODULES}
    unnamed: list[str] = []
    for key, _title in MODULES:
        for route in routes_of(key):
            who, csrf = access_label(route)
            summary = (route.summary or "").strip()
            if not summary:
                unnamed.append(f"{route.path} ({route.name})")
            for method in sorted(route.methods, key=METHOD_ORDER.index):
                rows[key].append((route.path, method, who, csrf, summary))

    if unnamed:  # every route needs a Korean summary="..." for the table and Swagger UI
        raise SystemExit("routes without summary=: " + ", ".join(unnamed))

    total = sum(len(r) for r in rows.values())
    spec_total = sum(len(ops) for ops in app.openapi()["paths"].values())
    if total != spec_total:  # a router missing from MODULES would silently drop rows
        raise SystemExit(
            f"summary has {total} operations but openapi.json has {spec_total}; update MODULES"
        )
    lines = [
        "# API 명세",
        "",
        "> **자동 생성 문서**: `backend/scripts/generate_openapi.py`가 FastAPI 앱에서 만든다. "
        "직접 고치지 말고, API를 바꾼 뒤 스크립트를 다시 실행한다.",
        "",
        f"- 전체 명세: [openapi.json](openapi.json) (OpenAPI {app.openapi()['openapi']}, "
        f"API 버전 {app.version}, 엔드포인트 {total}개)",
        "- 보기: [Swagger Editor](https://editor.swagger.io/)에 `openapi.json`을 불러오거나, "
        "로컬에서 `scripts/start-fastapi.ps1`로 실행한 뒤 http://127.0.0.1:8000/docs 를 연다.",
        "- 배포 서버는 `/docs`·`/openapi.json`을 공개하지 않는다(`ACADEMY_API_DOCS` 기본값 0).",
        "- 인증: 로그인하면 서버 세션 쿠키가 발급된다. 근거와 보안 점검은 "
        "[ADR 0001 세션 인증](../decisions/0001-local-session-authentication.md), "
        "[Phase 11-2 보안 감사](../reviews/phase11_2_security_audit.md)에 있다.",
        '- 오류 응답 형식: `{"code": "...", "message": "...", "fields": [...]}`',
        "",
        "**권한 열**: `공개`는 로그인 불필요, `직원`은 관리자·선생님·조교, `관리자`는 관리자만. "
        "반 데이터를 다루는 `직원` 엔드포인트에서 선생님·조교는 **배정된 반만** 다룰 수 있다(서비스 계층에서 판정). "
        "**CSRF 열**: `필요`이면 `X-CSRF-Token` 헤더를 보내야 한다.",
        "",
    ]
    for key, title in MODULES:
        if not rows[key]:
            continue
        lines += [
            f"## {title}",
            "",
            "| 메서드 | 경로 | 권한 | CSRF | 설명 |",
            "|---|---|---|---|---|",
        ]
        for path, method, who, csrf, summary in rows[key]:
            lines.append(f"| `{method}` | `{path}` | {who} | {csrf} | {summary} |")
        lines.append("")
    lines += [
        "## 이전 기록",
        "",
        "Java v1.x 로컬 HTTP 어댑터 시절의 문서다. 현재 API가 아니다.",
        "",
        "- [openapi-java-v1-legacy.yaml](openapi-java-v1-legacy.yaml): API 계약",
        "- [HTTP_API_SECURITY.md](HTTP_API_SECURITY.md): 보안 모델",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    outputs = {SPEC: build_spec(), SUMMARY: build_summary()}
    if "--check" in sys.argv:
        stale = [
            p
            for p, text in outputs.items()
            if not p.exists() or p.read_text(encoding="utf-8") != text
        ]
        for path in stale:
            print(f"{path} is out of date; run scripts/generate_openapi.py", file=sys.stderr)
        return 1 if stale else 0
    for path, text in outputs.items():
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
