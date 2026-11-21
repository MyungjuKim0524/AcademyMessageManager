"""Java PostgreSQL schema v1.1 baseline.

Revision ID: 001_java_schema_baseline
"""

from pathlib import Path

from alembic import op

revision = "001_java_schema_baseline"
down_revision = None
branch_labels = None
depends_on = None


def _canonical_ddl() -> str:
    path = Path(__file__).parents[3] / "sql" / "schema_postgresql.sql"
    ddl = path.read_text(encoding="utf-8-sig")
    lines = [line for line in ddl.splitlines() if line.strip().upper() not in {"BEGIN;", "COMMIT;"}]
    return "\n".join(lines)


def upgrade() -> None:
    # The reviewed Java DDL remains the single schema source of truth.
    op.get_bind().exec_driver_sql(_canonical_ddl())


def downgrade() -> None:
    # Downgrade is intentionally explicit and is allowed only by the test-DB safety gate in env.py.
    op.get_bind().exec_driver_sql(
        "DROP TABLE IF EXISTS import_error, import_row, import_job, delivery_attempt, "
        "delivery_job, message_draft, message_template, makeup_request, lesson_result, "
        "lesson, enrollment, classroom, student CASCADE; DROP FUNCTION IF EXISTS set_updated_at();"
    )
