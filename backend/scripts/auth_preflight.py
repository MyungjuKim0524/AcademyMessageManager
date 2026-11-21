import sys
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text

from app.db.session import create_db_engine

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


def _alembic_head() -> str:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(ALEMBIC_INI.parent / "alembic"))
    return ScriptDirectory.from_config(config).get_current_head()


def main() -> int:
    engine = create_db_engine()
    try:
        with engine.connect() as connection:
            database, user = connection.execute(
                text("SELECT current_database(), current_user")
            ).one()
            revision = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            active_admins = connection.execute(
                text(
                    "SELECT count(*) FROM staff_user "
                    "WHERE role = 'ADMIN' AND status = 'ACTIVE'"
                )
            ).scalar_one()
    finally:
        engine.dispose()

    if database != "academy_learningops_dev" or user != "academy_dev":
        raise RuntimeError("development database identity does not match the allowlist")
    head = _alembic_head()
    if revision != head:
        raise RuntimeError(f"Alembic head {head} is not applied (current: {revision})")
    if active_admins < 1:
        raise RuntimeError("no ACTIVE administrator exists; run bootstrap_admin.py first")
    print("Authentication preflight passed for the local development database.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
    except Exception as exc:
        print(f"ERROR: authentication preflight failed ({type(exc).__name__})", file=sys.stderr)
        raise SystemExit(1) from None
