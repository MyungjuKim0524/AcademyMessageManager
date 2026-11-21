# ruff: noqa: F811  -- fixtures imported from the auth suite are injected by name
"""Phase 11-2-B-2 (SEC-03): log-in limits per address, per account and behind proxies, over the
real API and the isolated PostgreSQL test DB (fictional accounts)."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from test_auth_rbac_integration import _seed, clean_auth_data, engine  # noqa: F401

from app.main import app
from app.modules.auth import service as auth_service

pytestmark = pytest.mark.postgres
PASSWORD = "correct horse battery staple"
TEACHER, ADMIN = "teacher@example.invalid", "admin@example.invalid"


class Clock:
    def __init__(self) -> None:
        self.now = 50_000.0

    def monotonic(self) -> float:
        return self.now


@pytest.fixture()
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    fake = Clock()
    monkeypatch.setattr(auth_service, "time", fake)  # the limiter's clock only
    for name in ("ACADEMY_LOGIN_IP_ATTEMPT_LIMIT", "ACADEMY_LOGIN_ACCOUNT_ATTEMPT_LIMIT"):
        monkeypatch.delenv(name, raising=False)  # defaults: 20 / 20 (pair limit 5 from fixture)
    for name in (
        "ACADEMY_TRUSTED_PROXIES",
        "ACADEMY_EDGE_SECRET",
        "ACADEMY_CLIENT_IP_HEADER",
        "ACADEMY_PROXY_DIAGNOSTICS",
    ):
        monkeypatch.delenv(name, raising=False)
    return fake


def _client(ip: str) -> TestClient:
    return TestClient(app, raise_server_exceptions=False, client=(ip, 40000))


def _login(client: TestClient, email: str, password: str = PASSWORD, forwarded: str | None = None):
    headers = {"X-Forwarded-For": forwarded} if forwarded else {}
    return client.post(
        "/api/auth/login", json={"email": email, "password": password}, headers=headers
    ).status_code


def test_one_users_failures_do_not_lock_out_colleagues_on_the_same_address(
    engine: Engine, clock: Clock
) -> None:
    _seed(engine)
    office = _client("198.51.100.1")
    assert [_login(office, TEACHER, "wrong") for _ in range(5)] == [401] * 5
    assert _login(office, TEACHER) == 429  # that account from that address: limited (5)
    assert _login(office, ADMIN) == 200  # a colleague behind the same address is not
    assert _login(_client("203.0.113.9"), TEACHER) == 200  # nor the same account elsewhere
    clock.now += 901  # window over
    assert _login(office, TEACHER) == 200


def test_forged_forwarded_for_is_ignored_without_a_trusted_proxy(
    engine: Engine, clock: Clock
) -> None:
    _seed(engine)
    attacker = _client("198.51.100.66")
    results = [_login(attacker, TEACHER, "wrong", forwarded=f"192.0.2.{i}") for i in range(6)]
    assert results == [401] * 5 + [429]


def test_behind_a_trusted_proxy_each_client_is_counted_apart(
    engine: Engine, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ACADEMY_TRUSTED_PROXIES", "10.0.0.0/8")
    _seed(engine)
    proxy = _client("10.0.0.2")
    assert [_login(proxy, TEACHER, "wrong", "203.0.113.10") for _ in range(5)] == [401] * 5
    assert _login(proxy, TEACHER, forwarded="203.0.113.10") == 429
    assert _login(proxy, TEACHER, forwarded="203.0.113.20") == 200  # another user, same proxy
    # Rotating the client-written (left) part does not help: the proxy-appended address counts.
    rotated = [_login(proxy, ADMIN, "wrong", f"192.0.2.{i}, 203.0.113.30") for i in range(6)]
    assert rotated == [401] * 5 + [429]
    # A peer outside the trusted range cannot speak for others with the header.
    outsider = _client("192.0.2.200")
    forged = [_login(outsider, ADMIN, "wrong", f"203.0.113.{40 + i}") for i in range(6)]
    assert forged == [401] * 5 + [429]


def test_rotating_addresses_hits_the_account_limit(engine: Engine, clock: Clock) -> None:
    _seed(engine)
    for i in range(5):  # 5 addresses x 4 failures = 20 = account limit (each pair below 5)
        assert [_login(_client(f"192.0.2.{i}"), TEACHER, "wrong") for _ in range(4)] == [401] * 4
    assert _login(_client("192.0.2.99"), TEACHER) == 429  # even with the right password
    assert _login(_client("192.0.2.99"), ADMIN) == 200  # other accounts unaffected
    clock.now += 901
    assert _login(_client("192.0.2.99"), TEACHER) == 200


def test_own_successful_login_does_not_reset_the_address_limit(
    engine: Engine, clock: Clock
) -> None:
    _seed(engine)
    insider = _client("198.51.100.7")
    targets = [f"guess{i}@example.invalid" for i in range(5) for _ in range(4)][:19]
    assert [_login(insider, t, "wrong") for t in targets] == [401] * 19  # each pair below 5
    assert _login(insider, ADMIN) == 200  # a valid account of the attacker's own
    assert _login(insider, TEACHER, "wrong") == 401  # 20th failure
    assert _login(insider, TEACHER, "wrong") == 429  # address-wide limit still applies


# ------------------------------------------------------------- follow-up (proxy / lock-out)
SECRET = "e" * 40


def test_parallel_wrong_passwords_cannot_exceed_the_limit(engine: Engine, clock: Clock) -> None:
    """Before the follow-up fix: 30 parallel wrong passwords -> 30 x 401, no 429 (the check and
    the failure count were separate steps). Now each attempt is reserved atomically."""
    _seed(engine)

    def attempt(_) -> int:
        return _login(_client("198.51.100.50"), TEACHER, "wrong")

    with ThreadPoolExecutor(max_workers=30) as pool:
        codes = list(pool.map(attempt, range(30)))
    assert (codes.count(401), codes.count(429)) == (5, 25)

    def spread(i: int) -> int:  # many addresses at once: the account limit (20) holds
        return _login(_client(f"192.0.2.{i % 10}"), ADMIN, "wrong")

    with ThreadPoolExecutor(max_workers=30) as pool:
        codes = list(pool.map(spread, range(40)))
    assert codes.count(401) == 20 and codes.count(429) == 20


def test_owner_is_not_locked_out_from_a_known_address(engine: Engine, clock: Clock) -> None:
    _seed(engine)
    office = _client("198.51.100.1")
    assert _login(office, TEACHER) == 200  # the owner's usual address becomes known
    for i in range(5):  # someone spends the account's 20 failures from elsewhere
        assert [_login(_client(f"192.0.2.{i}"), TEACHER, "wrong") for _ in range(4)] == [401] * 4
    assert _login(_client("192.0.2.77"), TEACHER) == 429  # new address: account limit applies
    assert _login(office, TEACHER) == 200  # the owner at the office still gets in
    # The known address is not a free pass: address+account (5) still applies there.
    assert [_login(office, TEACHER, "wrong") for _ in range(5)] == [401] * 5
    assert _login(office, TEACHER) == 429


def test_rotating_ipv6_addresses_inside_one_64_does_not_reset_counters(
    engine: Engine, clock: Clock
) -> None:
    _seed(engine)
    codes = [_login(_client(f"2001:db8:5:6::{i + 1:x}"), TEACHER, "wrong") for i in range(6)]
    assert codes == [401] * 5 + [429]
    assert _login(_client("2001:db8:5:7::1"), TEACHER) == 200  # another network


def test_server_errors_do_not_count_as_failures(
    engine: Engine, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(engine)
    original = auth_service.AuthService._authenticate

    def broken(self, *args):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(auth_service.AuthService, "_authenticate", broken)
    client = _client("198.51.100.3")
    assert [_login(client, TEACHER) for _ in range(8)] == [500] * 8
    monkeypatch.setattr(auth_service.AuthService, "_authenticate", original)
    assert _login(client, TEACHER) == 200


def test_edge_secret_counts_the_visitor_and_ignores_forgeries(
    engine: Engine, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ACADEMY_EDGE_SECRET", SECRET)
    _seed(engine)
    edge = _client("10.0.0.2")  # our front proxy, e.g. a Vercel rewrite

    def via_edge(visitor: str, password: str = "wrong") -> int:
        return edge.post(
            "/api/auth/login",
            json={"email": TEACHER, "password": password},
            headers={"X-Forwarded-For": visitor, "X-Academy-Edge-Secret": SECRET},
        ).status_code

    assert [via_edge("203.0.113.10") for _ in range(6)] == [401] * 5 + [429]
    assert via_edge("203.0.113.20", PASSWORD) == 200  # another visitor through the same edge
    # Direct callers (bypassing the edge) cannot pick an address with the header.
    direct = _client("10.9.9.9")
    forged = [_login(direct, ADMIN, "wrong", forwarded=f"192.0.2.{i}") for i in range(6)]
    assert forged == [401] * 5 + [429]


def test_client_address_diagnosis_is_admin_only_and_off_by_default(
    engine: Engine, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(engine)
    admin, teacher = _client("10.0.0.2"), _client("10.0.0.2")
    assert _login(admin, ADMIN) == 200 and _login(teacher, TEACHER) == 200
    assert admin.get("/api/auth/client-address").status_code == 404  # off by default
    monkeypatch.setenv("ACADEMY_PROXY_DIAGNOSTICS", "1")
    monkeypatch.setenv("ACADEMY_EDGE_SECRET", SECRET)
    assert teacher.get("/api/auth/client-address").status_code == 403
    assert TestClient(app).get("/api/auth/client-address").status_code == 401
    seen = admin.get(
        "/api/auth/client-address",
        headers={"X-Forwarded-For": "203.0.113.5, 76.76.21.1", "X-Academy-Edge-Secret": SECRET},
    )
    assert seen.status_code == 200
    assert seen.json() == {
        "peer": "10.0.0.2",
        "forwarded_for": ["203.0.113.5", "76.76.21.1"],
        "client_ip_header": None,
        "client_ip_header_value": None,
        "edge_secret": "valid",
        "resolved": "203.0.113.5",
        "source": "edge",
        "limiter_bucket": "203.0.113.5",
    }
    assert SECRET not in seen.text
    forged = admin.get("/api/auth/client-address", headers={"X-Forwarded-For": "6.6.6.6"}).json()
    assert (forged["edge_secret"], forged["resolved"], forged["source"]) == (
        "missing",
        "10.0.0.2",
        "peer",
    )
