from logging.config import fileConfig

from alembic import context
from app.config import get_settings
from app.db.base import Base
from app.db.models import tables  # noqa: F401
from app.db.safety import require_database_url

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

url = require_database_url(get_settings().database_url)
config.set_main_option(
    "sqlalchemy.url", url.render_as_string(hide_password=False).replace("%", "%%")
)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=str(url), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    from app.db.session import create_db_engine

    engine = create_db_engine()
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
