from sqlalchemy import Connection, inspect, text

LEGACY_TABLES = frozenset(
    {
        "student",
        "classroom",
        "enrollment",
        "lesson",
        "lesson_result",
        "makeup_request",
        "message_template",
        "message_draft",
        "delivery_job",
        "delivery_attempt",
        "import_job",
        "import_row",
        "import_error",
    }
)

# Part of the Java baseline (001) but dropped by migration 010 with the legacy CSV/XLSX import.
LEGACY_IMPORT_TABLES = frozenset({"import_job", "import_row", "import_error"})

AUTH_TABLES = frozenset(
    {"staff_user", "classroom_staff_assignment", "auth_session", "audit_log"}
)
ACADEMIC_TABLES = frozenset({"assessment", "assessment_result", "enrollment_pause"})
NOTIFICATION_TABLES = frozenset(
    {"notification_template", "parent_notification", "notification_send_attempt"}
)
EXPECTED_TABLES = (
    (LEGACY_TABLES - LEGACY_IMPORT_TABLES) | AUTH_TABLES | ACADEMIC_TABLES | NOTIFICATION_TABLES
)


def server_identity(connection: Connection) -> dict[str, object]:
    row = connection.execute(
        text(
            "SELECT current_database(), current_user, inet_server_addr()::text, "
            "inet_server_port(), version()"
        )
    ).one()
    return {
        "database": row[0],
        "user": row[1],
        "address": row[2],
        "port": row[3],
        "version": row[4],
    }


def assert_expected_schema(connection: Connection) -> None:
    tables = set(inspect(connection).get_table_names()) - {"alembic_version"}
    if tables != EXPECTED_TABLES:
        raise RuntimeError(
            f"기존 스키마와 테이블 목록이 다릅니다: missing={sorted(EXPECTED_TABLES - tables)}, "
            f"unexpected={sorted(tables - EXPECTED_TABLES)}"
        )
