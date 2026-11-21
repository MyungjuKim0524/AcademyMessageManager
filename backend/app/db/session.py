from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.db.safety import UnsafeDatabaseError, require_database_url
from app.errors import CompatibilityError

DB_CONNECT_TIMEOUT_SECONDS = 5


def create_db_engine(database_url: str | None = None) -> Engine:
    raw_url = database_url or get_settings().database_url
    url = require_database_url(raw_url)
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        pool_timeout=10,
        pool_recycle=1800,
        echo=False,
        # SEC-07: SQL parameters (names, e-mails) are left out of exception texts and logs.
        hide_parameters=True,
        # Phase 11-4-A: libpq waits indefinitely for a connection by default (measured: still
        # waiting after 25s for an unreachable host). Bound it; the request then answers 503
        # DATABASE_UNAVAILABLE instead of hanging a worker thread.
        connect_args={"connect_timeout": DB_CONNECT_TIMEOUT_SECONDS},
    )


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return create_db_engine()


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    return create_session_factory(get_engine())


def get_db() -> Generator[Session]:
    try:
        session = get_session_factory()()
    except UnsafeDatabaseError as exc:
        raise CompatibilityError(
            503,
            "DATABASE_UNAVAILABLE",
            "데이터베이스 연결 설정을 확인해주세요.",
        ) from exc
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
