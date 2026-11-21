# ruff: noqa: E501  -- Korean description strings for the generated document kept on one line
"""Generate docs/database/ERD.md (Mermaid) from the SQLAlchemy models.

The ERD is derived from code, so it cannot drift from the schema: rerun after a migration.

    cd backend
    .venv\\Scripts\\python.exe scripts\\generate_erd.py           # writes ../docs/database/ERD.md
    .venv\\Scripts\\python.exe scripts\\generate_erd.py --check   # exit 1 if the file is stale

No database connection is needed (models only).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import Table, UniqueConstraint  # noqa: E402
from sqlalchemy.dialects import postgresql  # noqa: E402

from app.db.base import Base  # noqa: E402
from app.db.models import tables as _models  # noqa: E402,F401  (registers every table)

OUTPUT = Path(__file__).resolve().parents[2] / "docs" / "database" / "ERD.md"

# Business areas. Every table must belong to exactly one (checked below).
AREAS: list[tuple[str, str, list[str]]] = [
    (
        "학사: 학생·반·수강·수업·출결·성적",
        "학원 운영의 기본 데이터. 출결은 `lesson_result`, 평가 점수는 `assessment_result`에 저장한다. "
        "`makeup_request`는 Java 버전의 보강 관리용 테이블로, 웹 버전에는 화면·API가 없다.",
        [
            "student", "classroom", "enrollment", "enrollment_pause", "lesson", "lesson_result",
            "assessment", "assessment_result", "makeup_request",
        ],
    ),
    (
        "직원·인증·감사",
        "직원 계정(역할 ADMIN/TEACHER/ASSISTANT, 상태 ACTIVE/INACTIVE/DELETED), 서버 세션, "
        "담당 반 배정, 변경 감사 기록.",
        ["staff_user", "auth_session", "classroom_staff_assignment", "audit_log"],
    ),
    (
        "학부모 안내 메시지(웹 버전)",
        "템플릿 → 메시지(초안·검토·확정·모의 발송) → 발송 시도 원장. 발송 채널은 CHECK로 `MOCK`만 허용하며, "
        "`Idempotency-Key` UNIQUE와 메시지당 성공 1회 부분 UNIQUE로 중복 발송을 막는다.",
        ["notification_template", "parent_notification", "notification_send_attempt"],
    ),
    (
        "Java 레거시 메시지(웹 버전 미사용)",
        "Java v1.2의 실제 발송 기록용 테이블. 기준선 Migration 001에서 넘어왔고 웹 서비스는 읽거나 쓰지 않는다.",
        ["message_template", "message_draft", "delivery_job", "delivery_attempt"],
    ),
]


def mermaid_type(column) -> str:
    """Short, Mermaid-safe type name (no spaces or parentheses)."""
    try:
        name = column.type.compile(dialect=postgresql.dialect())
    except Exception:  # noqa: BLE001  (types without a PostgreSQL rendering)
        name = type(column.type).__name__
    name = name.split("(")[0].strip().lower().replace(" ", "_")
    return {"timestamp_with_time_zone": "timestamptz", "character_varying": "varchar"}.get(name, name)


def single_unique_columns(table: Table) -> set[str]:
    out = {c.name for c in table.columns if c.unique}
    for constraint in table.constraints:
        if isinstance(constraint, UniqueConstraint) and len(constraint.columns) == 1:
            out.update(c.name for c in constraint.columns)
    for index in table.indexes:
        if index.unique and len(index.expressions) == 1 and getattr(index.expressions[0], "name", None):
            if index.dialect_options["postgresql"].get("where") is None:
                out.add(index.expressions[0].name)
    return out


def entity(table: Table) -> list[str]:
    unique = single_unique_columns(table)
    lines = [f"    {table.name} {{"]
    for column in table.columns:
        keys = []
        if column.primary_key:
            keys.append("PK")
        if column.foreign_keys:
            keys.append("FK")
        if column.name in unique and not column.primary_key:
            keys.append("UK")
        nullable = "" if column.primary_key or not column.nullable else ' "nullable"'
        key_text = f" {', '.join(keys)}" if keys else ""
        lines.append(f"        {mermaid_type(column)} {column.name}{key_text}{nullable}")
    lines.append("    }")
    return lines


def relations(tables: list[Table], include: set[str]) -> list[str]:
    """One line per foreign-key constraint (composite keys such as (id, classroom_id) stay one
    relation, labelled with all their columns)."""
    lines = []
    for table in tables:
        for constraint in table.foreign_key_constraints:
            parent = constraint.referred_table.name
            if parent not in include:
                continue
            columns = list(constraint.columns)
            label = ", ".join(c.name for c in columns)
            parent_card = "o|" if any(c.nullable for c in columns) else "||"
            child_card = "|o" if len(columns) == 1 and columns[0].unique else "}o"
            lines.append(f'    {parent} {parent_card}--{child_card} {table.name} : "{label}"')
    return sorted(set(lines))


def render() -> str:
    metadata_tables = {t.name: t for t in Base.metadata.sorted_tables}
    listed = [name for _, _, names in AREAS for name in names]
    missing, unknown = set(metadata_tables) - set(listed), set(listed) - set(metadata_tables)
    if missing or unknown or len(listed) != len(set(listed)):
        raise SystemExit(f"AREAS out of date: missing={sorted(missing)} unknown={sorted(unknown)}")

    out = [
        "# Database ERD (현재 스키마)",
        "",
        "> **자동 생성 문서**: `backend/scripts/generate_erd.py`가 SQLAlchemy 모델"
        "(`backend/app/db/models/tables.py`)에서 만든다. 직접 고치지 말고, Migration 뒤에 스크립트를 다시 실행한다.",
        f"> 기준: 테이블 {len(metadata_tables)}개, Alembic head와 일치하는 모델"
        "(`alembic check` 차이 없음 확인 대상).",
        "",
        "- 표기: `PK` 기본키, `FK` 외래키, `UK` 단일 열 UNIQUE, `\"nullable\"` NULL 허용 열.",
        "- 관계선: `||` 반드시 1, `o|` 0 또는 1(외래키 NULL 허용), `}o` 0개 이상.",
        "- 여러 열 UNIQUE, 부분 UNIQUE, CHECK, EXCLUDE, 트리거는 그림에 나오지 않는다. 정의는 `tables.py`와 `backend/alembic/versions/`에 있다.",
        "- 이전 ERD(`AMM_PostgreSQL_ERD_v1.3.*`, `PostgreSQL ERD v1.2.drawio`, `import-audit-erd.md`)는 Java v1.2 시절 스키마 기록이다.",
        "",
        "## 전체 관계 개요",
        "",
        "```mermaid",
        "erDiagram",
    ]
    out += relations(list(metadata_tables.values()), set(metadata_tables))
    out += ["```", ""]
    for title, note, names in AREAS:
        area_tables = [metadata_tables[n] for n in names]
        out += [f"## {title}", "", note, "", "```mermaid", "erDiagram"]
        for table in area_tables:
            out += entity(table)
        out += relations(area_tables, set(names))
        out += ["```", ""]
    return "\n".join(out)


def main() -> int:
    text = render()
    if "--check" in sys.argv:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current != text:
            print(f"{OUTPUT} is out of date; run scripts/generate_erd.py", file=sys.stderr)
            return 1
        print("ERD is up to date.")
        return 0
    OUTPUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUTPUT} ({len(text.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
