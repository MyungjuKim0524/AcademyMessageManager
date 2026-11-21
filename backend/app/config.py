import ipaddress
import os
from dataclasses import dataclass, field


def _csv(name: str, default: str) -> tuple[str, ...]:
    return tuple(value.strip() for value in os.getenv(name, default).split(",") if value.strip())


def _networks(name: str) -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    """Trusted reverse-proxy addresses / CIDR ranges. An invalid entry raises at start-up
    (fail closed) instead of silently trusting or ignoring it."""
    return tuple(ipaddress.ip_network(value, strict=False) for value in _csv(name, ""))


def _client_ip_header() -> str:
    name = os.getenv("ACADEMY_CLIENT_IP_HEADER", "").strip().lower()
    if name in {"x-forwarded-for", "forwarded"}:
        # Lists that clients can prepend to — never a single trustworthy address.
        raise ValueError("ACADEMY_CLIENT_IP_HEADER must name a single-address header")
    return name


def _edge_secret() -> str:
    secret = os.getenv("ACADEMY_EDGE_SECRET", "")
    if secret and len(secret) < 32:
        raise ValueError("ACADEMY_EDGE_SECRET must be at least 32 characters")
    return secret


@dataclass(frozen=True)
class Settings:
    log_level: str
    cors_origins: tuple[str, ...]
    max_json_body_bytes: int
    database_url: str | None
    api_host: str
    db_apis_enabled: bool
    session_cookie_name: str
    csrf_cookie_name: str
    cookie_secure: bool
    session_ttl_minutes: int
    login_attempt_limit: int  # failures per client address + account (unchanged: 5)
    login_window_seconds: int
    # Phase 11-2-B-2 (SEC-03): failures per client address over all accounts, and per account
    # over all addresses. 0 disables that limit.
    login_ip_attempt_limit: int
    login_account_attempt_limit: int
    # Proxies whose X-Forwarded-For is believed. Empty (default) = the header is ignored.
    trusted_proxies: tuple
    # Client address sources (see auth/service.py resolve_client); all off by default.
    client_ip_header: str  # e.g. "cf-connecting-ip": a single address the edge overwrites
    edge_secret_header: str
    edge_secret: str = field(repr=False)  # shared secret added by our own front proxy
    proxy_diagnostics: bool  # admin-only GET /api/auth/client-address (deployment check)
    # SEC-08: /docs, /redoc, /openapi.json are off unless explicitly enabled.
    api_docs_enabled: bool
    # SEC-09: Strict-Transport-Security max-age in seconds; 0 (default) = no header.
    hsts_max_age: int
    # Phase 11-4-B. SEC-04: development | test | production (anything else: DB APIs stay off).
    # SEC-05: a session unused for this long is revoked (absolute TTL above still applies).
    db_mode: str = ""
    session_idle_minutes: int = 60


def _idle_minutes(ttl_minutes: int) -> int:
    value = int(os.getenv("ACADEMY_SESSION_IDLE_MINUTES", "60"))
    if value < 1 or value > ttl_minutes:
        # No "0 = never expires": an unlimited idle session is never a valid setting.
        raise ValueError("ACADEMY_SESSION_IDLE_MINUTES must be 1..ACADEMY_SESSION_TTL_MINUTES")
    return value


def production_problems(settings: "Settings") -> list[str]:
    """Settings a production (deployed) process must not start with. Names only, no values."""
    from app.db.safety import UnsafeDatabaseError, require_database_url

    problems = []
    if not settings.db_apis_enabled:
        problems.append("ACADEMY_ENABLE_DB_APIS must be 1")
    try:
        require_database_url(settings.database_url)
    except UnsafeDatabaseError as error:
        problems.append(f"ACADEMY_DATABASE_URL: {error}")
    if not settings.cookie_secure:
        problems.append("ACADEMY_COOKIE_SECURE must be 1 (cookies only over HTTPS)")
    if not settings.cors_origins:
        problems.append("ACADEMY_CORS_ORIGINS must name the deployed front-end origin")
    for origin in settings.cors_origins:
        lowered = origin.lower()
        if not lowered.startswith("https://") or "*" in lowered:
            problems.append("ACADEMY_CORS_ORIGINS must list exact https:// origins")
            break
        if any(local in lowered for local in ("localhost", "127.0.0.1", "[::1]")):
            problems.append("ACADEMY_CORS_ORIGINS must not include local development origins")
            break
    if any(network.prefixlen == 0 for network in settings.trusted_proxies):
        problems.append("ACADEMY_TRUSTED_PROXIES must not trust every address (/0)")
    if os.getenv("ACADEMY_DB_TEST_MODE") == "1" or os.getenv("ACADEMY_RUN_POSTGRES_INTEGRATION"):
        problems.append(
            "test switches (ACADEMY_DB_TEST_MODE, ACADEMY_RUN_POSTGRES_INTEGRATION) must be unset"
        )
    # ACADEMY_PROXY_DIAGNOSTICS stays allowed: the deployment guide enables it briefly
    # (admin-only endpoint) for the post-deployment address check.
    return problems


def get_settings() -> Settings:
    return Settings(
        log_level=os.getenv("ACADEMY_LOG_LEVEL", "INFO").upper(),
        cors_origins=_csv("ACADEMY_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"),
        max_json_body_bytes=int(os.getenv("ACADEMY_MAX_JSON_BODY_BYTES", str(16 * 1024))),
        database_url=os.getenv("ACADEMY_DATABASE_URL") or None,
        api_host=os.getenv("ACADEMY_API_HOST", "127.0.0.1"),
        db_apis_enabled=os.getenv("ACADEMY_ENABLE_DB_APIS", "0") == "1",
        session_cookie_name=os.getenv("ACADEMY_SESSION_COOKIE", "academy_session"),
        csrf_cookie_name=os.getenv("ACADEMY_CSRF_COOKIE", "academy_csrf"),
        cookie_secure=os.getenv("ACADEMY_COOKIE_SECURE", "1") == "1",
        session_ttl_minutes=int(os.getenv("ACADEMY_SESSION_TTL_MINUTES", "480")),
        login_attempt_limit=int(os.getenv("ACADEMY_LOGIN_ATTEMPT_LIMIT", "5")),
        login_window_seconds=int(os.getenv("ACADEMY_LOGIN_WINDOW_SECONDS", "900")),
        login_ip_attempt_limit=int(os.getenv("ACADEMY_LOGIN_IP_ATTEMPT_LIMIT", "20")),
        login_account_attempt_limit=int(os.getenv("ACADEMY_LOGIN_ACCOUNT_ATTEMPT_LIMIT", "20")),
        trusted_proxies=_networks("ACADEMY_TRUSTED_PROXIES"),
        client_ip_header=_client_ip_header(),
        edge_secret_header=os.getenv("ACADEMY_EDGE_SECRET_HEADER", "x-academy-edge-secret")
        .strip()
        .lower(),
        edge_secret=_edge_secret(),
        proxy_diagnostics=os.getenv("ACADEMY_PROXY_DIAGNOSTICS", "0") == "1",
        api_docs_enabled=os.getenv("ACADEMY_API_DOCS", "0") == "1",
        hsts_max_age=int(os.getenv("ACADEMY_HSTS_MAX_AGE", "0")),
        db_mode=os.getenv("ACADEMY_DB_MODE", "").strip(),
        session_idle_minutes=_idle_minutes(int(os.getenv("ACADEMY_SESSION_TTL_MINUTES", "480"))),
    )
