from fastapi.testclient import TestClient

from app.db.session import get_db, get_engine, get_session_factory
from app.main import app


def test_login_reports_safe_service_error_when_database_url_is_missing(monkeypatch) -> None:
    monkeypatch.setenv("ACADEMY_ENABLE_DB_APIS", "1")
    monkeypatch.setenv("ACADEMY_API_HOST", "127.0.0.1")
    monkeypatch.setenv("ACADEMY_DB_MODE", "development")
    monkeypatch.delenv("ACADEMY_DATABASE_URL", raising=False)
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    app.dependency_overrides.pop(get_db, None)

    try:
        response = TestClient(app, raise_server_exceptions=False).post(
            "/api/auth/login",
            json={
                "email": "synthetic@example.invalid",
                "password": "synthetic-invalid-password",
            },
        )
    finally:
        get_engine.cache_clear()
        get_session_factory.cache_clear()

    assert response.status_code == 503
    assert response.json() == {
        "code": "DATABASE_UNAVAILABLE",
        "message": "데이터베이스 연결 설정을 확인해주세요.",
        "fields": [],
    }


def test_unauthenticated_me_returns_401_before_database_initialization(monkeypatch) -> None:
    monkeypatch.setenv("ACADEMY_ENABLE_DB_APIS", "1")
    monkeypatch.setenv("ACADEMY_API_HOST", "127.0.0.1")
    monkeypatch.setenv("ACADEMY_DB_MODE", "development")
    monkeypatch.delenv("ACADEMY_DATABASE_URL", raising=False)
    get_engine.cache_clear()
    get_session_factory.cache_clear()

    response = TestClient(app, raise_server_exceptions=False).get("/api/auth/me")

    assert response.status_code == 401
    assert response.json() == {
        "code": "AUTHENTICATION_REQUIRED",
        "message": "로그인이 필요합니다.",
        "fields": [],
    }
