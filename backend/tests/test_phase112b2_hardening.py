"""Phase 11-2-B-2: proxy-aware client address, limiter bookkeeping, XLSX resource limits, redacted
error logs, API docs and HSTS switches. No database needed (fictional values only)."""

import dataclasses
import ipaddress
import logging
import re
import time
import zipfile
from io import BytesIO

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy.exc import IntegrityError

from app import uploads
from app.config import get_settings
from app.db.session import create_db_engine, get_db
from app.errors import CompatibilityError
from app.main import app
from app.middleware import CompatibilityMiddleware
from app.modules.auth import service as auth_service
from app.modules.auth.service import LoginRateLimiter, client_address
from app.modules.lesson_upload.workbook import parse_workbook

PROXIES = (ipaddress.ip_network("10.0.0.0/8"), ipaddress.ip_network("fd00::/8"))


# ------------------------------------------------------------------------- SEC-03 address
@pytest.mark.parametrize(
    ("peer", "forwarded", "trusted", "expected"),
    [
        # No trusted proxy configured: the header is ignored, whatever it says.
        ("198.51.100.1", ["1.2.3.4"], (), "198.51.100.1"),
        # A peer that is not a trusted proxy cannot speak for anyone else.
        ("198.51.100.1", ["1.2.3.4"], PROXIES, "198.51.100.1"),
        # Behind a trusted proxy: the address the proxy appended (rightmost untrusted).
        ("10.0.0.2", ["203.0.113.10"], PROXIES, "203.0.113.10"),
        # Forged entries on the left are never used.
        ("10.0.0.2", ["6.6.6.6, 7.7.7.7, 203.0.113.10"], PROXIES, "203.0.113.10"),
        # Chains of our own proxies are skipped; split header lines are joined.
        ("10.0.0.2", ["6.6.6.6", "203.0.113.10, 10.0.0.9"], PROXIES, "203.0.113.10"),
        ("fd00::2", ["2001:db8::7"], PROXIES, "2001:db8::7"),
        # Garbage where a proxy would have appended an address: counted apart, never as the
        # shared proxy address (which would let one client lock out everyone).
        ("10.0.0.2", ["203.0.113.10, not-an-ip"], PROXIES, "invalid-forwarded"),
        # Trusted proxy with no header (e.g. health check): the proxy itself.
        ("10.0.0.2", [], PROXIES, "10.0.0.2"),
        # Non-IP peers (test client, unix socket) and no peer at all.
        ("testclient", ["1.2.3.4"], PROXIES, "testclient"),
        (None, ["1.2.3.4"], PROXIES, "unknown"),
    ],
)
def test_client_address_trusts_forwarded_for_only_from_configured_proxies(
    peer, forwarded, trusted, expected
) -> None:
    assert client_address(peer, forwarded, trusted) == expected


def test_invalid_trusted_proxy_setting_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ACADEMY_TRUSTED_PROXIES", "10.0.0.0/8, render-proxy")
    with pytest.raises(ValueError):
        get_settings()
    monkeypatch.setenv("ACADEMY_TRUSTED_PROXIES", "10.0.0.0/8,192.0.2.1")
    assert len(get_settings().trusted_proxies) == 2
    monkeypatch.delenv("ACADEMY_TRUSTED_PROXIES")
    assert get_settings().trusted_proxies == ()


# ------------------------------------------------------------------------- SEC-03 limiter
class Clock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def monotonic(self) -> float:
        return self.now


def test_limiter_window_expiry_and_no_key_build_up(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = Clock()
    monkeypatch.setattr(auth_service, "time", clock)
    monkeypatch.setenv("ACADEMY_LOGIN_WINDOW_SECONDS", "900")
    limiter = LoginRateLimiter()
    for _ in range(3):
        limiter.check("k", 3)
        limiter.fail("k")
    with pytest.raises(CompatibilityError) as blocked:
        limiter.check("k", 3)
    assert blocked.value.status_code == 429
    clock.now += 901  # window over
    limiter.check("k", 3)
    assert "k" not in limiter._attempts  # expired keys are dropped, not kept empty
    limiter.check("never-failed", 3)
    assert limiter._attempts == {}
    limiter.check("k", 0)  # 0 = that limit is off

    monkeypatch.setattr(LoginRateLimiter, "MAX_KEYS", 5)
    for i in range(5):
        limiter.fail(f"old{i}")
    clock.now += 901
    limiter.fail("fresh")  # 6 keys > 5: the expired ones are swept
    assert set(limiter._attempts) == {"fresh"}


# ------------------------------------------------------------------------------ SEC-06
def _workbook(rows: int = 3) -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.title = "10시"
    sheet.append(["중3 토10", "출결", "예습 과제", "주간 과제", "어휘 (10)"])
    for i in range(rows):
        sheet.append([f"가상학생{i}", "출석", "A", "B", 9])
    out = BytesIO()
    book.save(out)
    return out.getvalue()


def _rewrite_sheet(content: bytes, change) -> bytes:
    source = zipfile.ZipFile(BytesIO(content))
    out = BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
        for info in source.infolist():
            data = source.read(info.filename)
            if info.filename == "xl/worksheets/sheet1.xml":
                data = change(data.decode()).encode()
            target.writestr(info, data)
    return out.getvalue()


def test_normal_workbook_is_unaffected() -> None:
    [block] = parse_workbook(_workbook(rows=200))
    assert block.class_name == "중3 토10" and len(block.students) == 200


def test_far_away_row_number_is_refused_quickly() -> None:
    """A ~5KB file whose sheet claims A1:XFD1048576 and has a row at 1,048,576: openpyxl pads
    the gap with blank rows (measured before the fix: ~27s CPU for one sheet)."""

    def far_row(xml: str) -> str:
        xml = re.sub(r'<dimension ref="[^"]*" ?/>', '<dimension ref="A1:XFD1048576"/>', xml)
        return xml.replace(
            "</sheetData>",
            '<row r="1048576"><c r="A1048576" t="inlineStr"><is><t>y</t></is></c></row>'
            "</sheetData>",
        )

    content = _rewrite_sheet(_workbook(), far_row)
    assert len(content) < 10_000
    started = time.perf_counter()
    with pytest.raises(CompatibilityError) as refused:
        parse_workbook(content)
    assert (refused.value.status_code, refused.value.code) == (413, "ROW_LIMIT_EXCEEDED")
    assert time.perf_counter() - started < 10


def test_zip_entry_count_and_total_size_are_checked_before_unpacking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    out = BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        for i in range(uploads.MAX_ZIP_ENTRIES + 1):
            archive.writestr(f"x/{i}.xml", "<a/>")
    with pytest.raises(CompatibilityError) as many:
        uploads.check_xlsx_zip(out.getvalue())
    assert many.value.code == "INVALID_XLSX"

    normal = _workbook()
    uploads.check_xlsx_zip(normal)  # a real workbook passes the default limits
    declared = sum(i.file_size for i in zipfile.ZipFile(BytesIO(normal)).infolist())
    monkeypatch.setattr(uploads, "MAX_UNCOMPRESSED_BYTES", declared - 1)
    with pytest.raises(CompatibilityError) as large:
        uploads.check_xlsx_zip(normal)
    assert large.value.code == "INVALID_XLSX"


def test_compression_bomb_is_refused_from_metadata() -> None:
    out = BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/worksheets/sheet1.xml", b"0" * 5_000_000)  # 5MB -> ~5KB
    content = out.getvalue()
    assert len(content) < 20_000
    with pytest.raises(CompatibilityError) as bomb:
        parse_workbook(content)
    assert bomb.value.code == "INVALID_XLSX"


def test_xml_entity_declarations_are_refused() -> None:
    def entities(xml: str) -> str:
        return (
            '<?xml version="1.0"?><!DOCTYPE w [<!ENTITY a "aaaaaaaaaa">'
            '<!ENTITY b "&a;&a;&a;&a;&a;">]>' + xml.replace("<t>가상학생0</t>", "<t>&b;</t>")
        )

    with pytest.raises(CompatibilityError) as refused:
        parse_workbook(_rewrite_sheet(_workbook(), entities))
    assert refused.value.code == "INVALID_XLSX"


# ------------------------------------------------------------------------------ SEC-07
GUARDIAN = "guardian-log@example.invalid"


def test_unhandled_database_error_is_logged_without_its_text(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    class Orig(Exception):
        sqlstate = "23505"

        class diag:  # noqa: N801 - mimics psycopg's error.diag
            constraint_name = "uq_student_business_key"

    def broken_db():
        class Session:
            def _fail(self, *_a, **_k):
                raise IntegrityError(
                    "INSERT INTO student (name, parent_email) VALUES (%(name)s, %(email)s)",
                    {"name": "가상학생", "email": GUARDIAN},
                    Orig(f"DETAIL: Key (name)=(가상학생) already exists. {GUARDIAN}"),
                )

            scalar = scalars = execute = get = _fail

            def rollback(self):
                pass

        yield Session()

    monkeypatch.setenv("ACADEMY_ENABLE_DB_APIS", "1")
    monkeypatch.setenv("ACADEMY_DB_MODE", "test")
    monkeypatch.setenv("ACADEMY_API_HOST", "127.0.0.1")
    app.dependency_overrides[get_db] = broken_db
    caplog.set_level(logging.INFO)
    try:
        # raise_server_exceptions=True: the error must not escape the app at all — otherwise
        # the server (uvicorn) logs the whole traceback with the exception text.
        response = TestClient(app).post(
            "/api/auth/login", json={"email": "nobody@example.invalid", "password": "x" * 12}
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 500 and response.json()["code"] == "INTERNAL_ERROR"
    assert response.headers["x-request-id"]
    logged = "\n".join(record.getMessage() for record in caplog.records)
    for secret in (GUARDIAN, "가상학생", "nobody@example.invalid", "parent_email", "x" * 12):
        assert secret not in logged and secret not in response.text
    assert "error_type=sqlalchemy.exc.IntegrityError" in logged
    assert "sqlstate=23505" in logged and "constraint=uq_student_business_key" in logged
    assert response.headers["x-request-id"] in logged  # traceable to the request
    assert "auth" in logged  # stack frames are kept (where it failed)


def test_engine_hides_sql_parameters(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ACADEMY_DB_MODE", "test")
    monkeypatch.setenv("ACADEMY_DB_TEST_MODE", "1")
    engine = create_db_engine(
        "postgresql+psycopg://academy_test:not-used@127.0.0.1:55432/academy_learningops_test"
    )  # no connection is opened
    try:
        assert engine.hide_parameters is True
    finally:
        engine.dispose()


# --------------------------------------------------------------------------- SEC-08/09
def test_api_description_is_not_published_by_default() -> None:
    client = TestClient(app, raise_server_exceptions=False)
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404, path


def test_hsts_header_only_when_configured() -> None:
    def build(settings) -> TestClient:
        tiny = FastAPI()
        tiny.add_api_route("/api/health", lambda: {"status": "UP"})
        tiny.add_middleware(CompatibilityMiddleware, settings=settings)
        return TestClient(tiny)

    base = get_settings()
    assert "strict-transport-security" not in build(base).get("/api/health").headers
    on = build(dataclasses.replace(base, hsts_max_age=31_536_000)).get("/api/health")
    assert on.headers["strict-transport-security"] == "max-age=31536000"
