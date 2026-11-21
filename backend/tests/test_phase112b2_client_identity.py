"""Phase 11-2-B-2 follow-up: client address sources for the deployment proxies, address
normalisation, atomic limiter reservations and the known-address rule. No database needed."""

import dataclasses
import logging
from concurrent.futures import ThreadPoolExecutor

import pytest
from starlette.datastructures import Headers

from app.config import get_settings
from app.errors import CompatibilityError
from app.modules.auth import service as auth_service
from app.modules.auth.service import (
    LoginRateLimiter,
    limiter_bucket,
    parse_address,
    resolve_client,
)

SECRET = "s" * 40


def _headers(**values: str) -> Headers:
    return Headers({key.replace("_", "-"): value for key, value in values.items()})


def _settings(**changes):
    return dataclasses.replace(get_settings(), **changes)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("203.0.113.5", "203.0.113.5"),
        (" 203.0.113.5:4711 ", "203.0.113.5"),
        ("[2001:db8::1]:443", "2001:db8::1"),
        ("2001:db8::1", "2001:db8::1"),
        ('"203.0.113.5"', "203.0.113.5"),
        ("::ffff:203.0.113.5", "203.0.113.5"),
        ("unknown", None),
        ("", None),
        (None, None),
    ],
)
def test_header_address_forms(raw, expected) -> None:
    parsed = parse_address(raw)
    assert (str(parsed) if parsed else None) == expected


def test_ipv6_is_counted_per_64_network() -> None:
    assert limiter_bucket("2001:db8:1:2:aaaa::1") == limiter_bucket("2001:db8:1:2:bbbb::9")
    assert limiter_bucket("2001:db8:1:2::1") == "2001:db8:1:2::/64"
    assert limiter_bucket("2001:db8:1:3::1") != limiter_bucket("2001:db8:1:2::1")
    assert limiter_bucket("::ffff:198.51.100.1") == "198.51.100.1"
    assert limiter_bucket("testclient") == "testclient"


def test_default_ignores_forwarded_headers_and_warns_once(caplog, monkeypatch) -> None:
    monkeypatch.setattr(auth_service, "_unconfigured_warning_logged", False)
    caplog.set_level(logging.WARNING, logger="academy.api")
    forged = _headers(x_forwarded_for="6.6.6.6", cf_connecting_ip="7.7.7.7")
    settings = _settings(trusted_proxies=(), client_ip_header="", edge_secret="")
    assert resolve_client("10.1.2.3", forged, settings) == ("10.1.2.3", "peer")
    assert resolve_client("10.1.2.3", forged, settings) == ("10.1.2.3", "peer")
    messages = [r.getMessage() for r in caplog.records]
    warnings = [m for m in messages if "forwarded_header_ignored" in m]
    assert len(warnings) == 1
    assert "6.6.6.6" not in warnings[0] and "10.1.2.3" not in warnings[0]


def test_edge_secret_trusts_the_left_most_address_written_by_our_front_proxy() -> None:
    settings = _settings(edge_secret=SECRET, edge_secret_header="x-academy-edge-secret")
    via_edge = _headers(x_forwarded_for="203.0.113.5, 76.76.21.1", x_academy_edge_secret=SECRET)
    assert resolve_client("10.0.0.2", via_edge, settings) == ("203.0.113.5", "edge")
    # Without (or with a wrong) secret the header is not believed: direct callers cannot forge.
    for headers in (
        _headers(x_forwarded_for="203.0.113.5"),
        _headers(x_forwarded_for="203.0.113.5", x_academy_edge_secret="s" * 39 + "x"),
    ):
        assert resolve_client("10.0.0.2", headers, settings) == ("10.0.0.2", "peer")
    garbage = _headers(x_forwarded_for="nonsense", x_academy_edge_secret=SECRET)
    assert resolve_client("10.0.0.2", garbage, settings) == ("invalid-forwarded", "edge")


def test_client_ip_header_from_the_outer_edge() -> None:
    settings = _settings(client_ip_header="cf-connecting-ip", edge_secret="")
    headers = _headers(cf_connecting_ip="198.51.100.7", x_forwarded_for="6.6.6.6, 198.51.100.7")
    assert resolve_client("10.0.0.2", headers, settings) == ("198.51.100.7", "client-ip-header")
    # Missing / unparsable -> the peer, never the forgeable X-Forwarded-For.
    forged = _headers(x_forwarded_for="6.6.6.6")
    assert resolve_client("10.0.0.2", forged, settings)[0] == "10.0.0.2"
    assert resolve_client("10.0.0.2", _headers(cf_connecting_ip="x"), settings)[0] == "10.0.0.2"
    # Edge secret wins over the client-ip header (Vercel -> Render: the header holds Vercel's
    # egress address, the secret-verified X-Forwarded-For the visitor's).
    both = _settings(client_ip_header="cf-connecting-ip", edge_secret=SECRET)
    via_edge = _headers(
        cf_connecting_ip="76.76.21.1", x_forwarded_for="203.0.113.5", x_academy_edge_secret=SECRET
    )
    assert resolve_client("10.0.0.2", via_edge, both) == ("203.0.113.5", "edge")
    direct = _headers(cf_connecting_ip="198.51.100.7", x_forwarded_for="203.0.113.5")
    assert resolve_client("10.0.0.2", direct, both) == ("198.51.100.7", "client-ip-header")


def test_unsafe_settings_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ACADEMY_EDGE_SECRET", "too-short")
    with pytest.raises(ValueError):
        get_settings()
    monkeypatch.setenv("ACADEMY_EDGE_SECRET", SECRET)
    for header in ("X-Forwarded-For", "forwarded"):
        monkeypatch.setenv("ACADEMY_CLIENT_IP_HEADER", header)
        with pytest.raises(ValueError):
            get_settings()
    monkeypatch.setenv("ACADEMY_CLIENT_IP_HEADER", "CF-Connecting-IP")
    settings = get_settings()
    assert settings.client_ip_header == "cf-connecting-ip"
    assert SECRET not in repr(settings)  # the secret never shows up in a settings dump


def test_reservations_are_atomic_under_parallel_requests() -> None:
    limiter = LoginRateLimiter()

    def attempt(_) -> bool:
        try:
            limiter.reserve([("pair:x", 5), ("account:x", 20)])
            return True
        except CompatibilityError:
            return False

    with ThreadPoolExecutor(max_workers=32) as pool:
        admitted = list(pool.map(attempt, range(200)))
    assert admitted.count(True) == 5


def test_release_and_known_addresses(monkeypatch: pytest.MonkeyPatch) -> None:
    class Clock:
        now = 100.0

        def monotonic(self):
            return self.now

    clock = Clock()
    monkeypatch.setattr(auth_service, "time", clock)
    limiter = LoginRateLimiter()
    stamp = limiter.reserve([("k", 1)])
    with pytest.raises(CompatibilityError):
        limiter.reserve([("k", 1)])
    limiter.release(["k"], stamp)  # given back: e.g. a server error, not a failure
    limiter.reserve([("k", 1)])
    # Known addresses: last 5 per account, valid for 30 days.
    for i in range(7):
        clock.now += 1
        limiter.remember("a@example.invalid", f"198.51.100.{i}")
    assert not limiter.is_known("a@example.invalid", "198.51.100.0")
    assert limiter.is_known("a@example.invalid", "198.51.100.6")
    clock.now += LoginRateLimiter.KNOWN_ADDRESS_SECONDS
    assert not limiter.is_known("a@example.invalid", "198.51.100.6")
    assert not limiter.is_known("b@example.invalid", "198.51.100.6")
