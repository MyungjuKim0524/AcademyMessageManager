import os

from sqlalchemy.engine import URL, make_url


class UnsafeDatabaseError(RuntimeError):
    pass


ALLOWED_DATABASES = {
    "development": ("academy_learningops_dev", "academy_dev", "127.0.0.1", 55431),
    "test": ("academy_learningops_test", "academy_test", "127.0.0.1", 55432),
}


PRODUCTION_SSL_MODES = frozenset({"require", "verify-ca", "verify-full"})


def validate_production_database_url(url: URL) -> URL:
    """Phase 11-4-B (SEC-04): a deployed database is not on the local allow-list, so it is
    checked by rule instead: PostgreSQL, TLS required, never one of the local development /
    test databases, and never together with the test switches (destructive tests need mode
    ``test`` and the test target, so they can never reach it)."""
    if url.get_backend_name() != "postgresql":
        raise UnsafeDatabaseError("production에는 PostgreSQL만 허용됩니다.")
    if os.getenv("ACADEMY_DB_TEST_MODE") == "1":
        raise UnsafeDatabaseError("production에서는 ACADEMY_DB_TEST_MODE를 켤 수 없습니다.")
    if url.query.get("sslmode") not in PRODUCTION_SSL_MODES:
        raise UnsafeDatabaseError("production DB 연결에는 sslmode=require 이상이 필요합니다.")
    target = (url.database, url.username, url.host, url.port)
    if target in ALLOWED_DATABASES.values() or not url.host or not url.database:
        raise UnsafeDatabaseError("production이 로컬 개발·테스트 DB를 가리킬 수 없습니다.")
    return url


def validate_test_database_url(raw_url: str) -> URL:
    url = make_url(raw_url)
    mode = os.getenv("ACADEMY_DB_MODE")
    if mode == "production":
        return validate_production_database_url(url)
    if mode not in ALLOWED_DATABASES:
        raise UnsafeDatabaseError(
            "ACADEMY_DB_MODE는 development, test 또는 production이어야 합니다."
        )
    if mode == "test" and os.getenv("ACADEMY_DB_TEST_MODE") != "1":
        raise UnsafeDatabaseError("test 모드에는 ACADEMY_DB_TEST_MODE=1이 필요합니다.")

    actual = (url.database, url.username, url.host, url.port)
    required = ALLOWED_DATABASES[mode]
    if actual != required:
        raise UnsafeDatabaseError(
            "테스트 DB 대상이 허용 목록과 일치하지 않습니다: "
            f"database={url.database}, user={url.username}, host={url.host}, port={url.port}"
        )
    if url.get_backend_name() != "postgresql":
        raise UnsafeDatabaseError("PostgreSQL 테스트 DB만 허용됩니다.")
    return url


def require_database_url(raw_url: str | None) -> URL:
    if not raw_url:
        raise UnsafeDatabaseError("ACADEMY_DATABASE_URL이 설정되지 않았습니다.")
    return validate_test_database_url(raw_url)
