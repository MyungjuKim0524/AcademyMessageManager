import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import get_db
from app.main import app

client = TestClient(app, raise_server_exceptions=False)
VALID = {
    "studentName": "샘플학생1",
    "className": "CLASS-DEMO",
    "classType": "REGULAR",
    "lessonDate": "2026-10-05",
    "testRound": "1회차",
    "attendance": "PRESENT",
    "preGrade": "A",
    "weeklyGrade": "B",
    "correctCount": 13,
    "totalCount": 39,
}


# The shared local-only DB gate and error redaction are checked through endpoints that remain
# (the legacy /api/imports endpoints these tests used were removed on 2026-11-20).
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _upload(size: int):
    return client.post(
        "/api/lesson-uploads/preview",
        files={"file": ("week.xlsx", b"PK" + b"0" * size, XLSX)},
        data={"lesson_date": "2026-11-03"},
    )


def test_database_apis_are_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ACADEMY_ENABLE_DB_APIS", "0")
    monkeypatch.delenv("ACADEMY_DB_MODE", raising=False)
    me = client.get("/api/auth/me")
    assert me.status_code == 404
    assert me.json() == {
        "code": "DB_API_DISABLED",
        "message": "요청한 기능을 사용할 수 없습니다.",
        "fields": [],
    }
    upload = _upload(10)
    assert upload.status_code == 404
    assert upload.json()["code"] == "DB_API_DISABLED"


def test_database_apis_reject_non_loopback_binding(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ACADEMY_ENABLE_DB_APIS", "1")
    monkeypatch.setenv("ACADEMY_DB_MODE", "development")
    monkeypatch.setenv("ACADEMY_API_HOST", "0.0.0.0")
    response = client.get("/api/auth/me")
    assert response.status_code == 404
    assert response.json()["code"] == "DB_API_DISABLED"


def test_workbook_upload_accepts_real_sized_files_and_rejects_over_10mb(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A weekly workbook is ~20KB: it must reach the upload API, not hit the 16KB JSON limit."""
    monkeypatch.setenv("ACADEMY_ENABLE_DB_APIS", "0")
    assert _upload(20_000).json()["code"] == "DB_API_DISABLED"  # passed the size gate
    assert _upload(2_000_000).json()["code"] == "DB_API_DISABLED"
    too_big = _upload(10 * 1024 * 1024 + 70_000)
    assert too_big.status_code == 413
    assert too_big.json()["code"] == "FILE_TOO_LARGE"
    # JSON endpoints keep the small limit.
    json_body = client.post(
        "/api/auth/login",
        content=b"{" + b" " * 17_000 + b"}",
        headers={"content-type": "application/json"},
    )
    assert json_body.status_code == 413
    assert json_body.json()["code"] == "PAYLOAD_TOO_LARGE"


def test_database_error_is_redacted_and_session_is_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed = False

    class BrokenSession:
        def _fail(self, *_args, **_kwargs):
            raise SQLAlchemyError("SELECT secret FROM internal_table password=do-not-leak")

        scalar = scalars = execute = get = _fail

        def rollback(self):
            pass

    def override_db():
        nonlocal closed
        try:
            yield BrokenSession()
        finally:
            closed = True

    monkeypatch.setenv("ACADEMY_ENABLE_DB_APIS", "1")
    monkeypatch.setenv("ACADEMY_DB_MODE", "test")
    monkeypatch.setenv("ACADEMY_API_HOST", "127.0.0.1")
    app.dependency_overrides[get_db] = override_db
    try:
        response = client.post(
            "/api/auth/login", json={"email": "nobody@example.invalid", "password": "x" * 12}
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 500
    assert response.json()["code"] in {"INTERNAL_ERROR", "DATABASE_ERROR"}
    assert "secret" not in response.text and "password=" not in response.text
    assert closed


def test_health_contract_and_headers() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "UP"}
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-request-id"]
    assert response.headers["content-type"] == "application/json; charset=UTF-8"


def test_preview_success_is_privacy_minimal() -> None:
    response = client.post(
        "/api/messages/preview",
        json=VALID,
        headers={"origin": "http://localhost:5173"},
    )
    assert response.status_code == 200
    assert set(response.json()) == {"message"}
    assert "샘플학생1" in response.json()["message"]
    assert "13/39" in response.json()["message"]
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_validation_and_json_errors() -> None:
    response = client.post("/api/messages/preview", json=dict(VALID, studentName=""))
    assert response.status_code == 400
    assert response.json()["fields"] == [{"field": "studentName", "message": "필수 값입니다."}]
    response = client.post("/api/messages/preview", json={**VALID, "unexpected": True})
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_JSON"


def test_transport_guards() -> None:
    response = client.post(
        "/api/messages/preview", content=b"{}", headers={"content-type": "text/plain"}
    )
    assert response.status_code == 415
    assert response.json()["code"] == "UNSUPPORTED_MEDIA_TYPE"
    response = client.post(
        "/api/messages/preview",
        content=b'{"studentName":"' + b"x" * 17_000 + b'"}',
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 413
    assert response.json()["code"] == "PAYLOAD_TOO_LARGE"
    assert client.get("/api/messages/preview").status_code == 405
    response = client.post(
        "/api/messages/preview",
        json=VALID,
        headers={"origin": "https://untrusted.invalid"},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "CORS_FORBIDDEN"
