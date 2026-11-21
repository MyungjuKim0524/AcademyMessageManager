import hashlib
import hmac
import ipaddress
import logging
import secrets
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models.tables import AuditLog, AuthSession, StaffUser
from app.errors import CompatibilityError

password_hasher = PasswordHasher()
_dummy_hash: str | None = None


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(stored_hash: str | None, password: str) -> bool:
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = password_hasher.hash(secrets.token_urlsafe(32))
    candidate = stored_hash or _dummy_hash
    try:
        return password_hasher.verify(candidate, password) and stored_hash is not None
    except (VerifyMismatchError, InvalidHashError):
        return False


def token_digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def utc_now() -> datetime:
    """The one clock for session times (login, absolute and idle expiry, activity, password
    changes): the application server's UTC time. Tests replace this function to move time."""
    return datetime.now(UTC)


# Phase 11-4-B (SEC-05): activity is recorded at most once per this interval, so an active user
# costs one small UPDATE per minute, not one per request. Idle expiry is therefore exact to
# within this interval (a session idle for N minutes expires between N and N + 1 minutes).
ACTIVITY_WRITE_SECONDS = 60
BACKGROUND_HEADER = "x-academy-background"  # "1" = automatic request: does not count as activity
MIN_PASSWORD_LENGTH = 12  # same rule as staff creation (learningops StaffCreate)


@dataclass(frozen=True)
class IssuedSession:
    user: StaffUser
    session_token: str
    csrf_token: str
    expires_at: datetime


def parse_address(value: str | None):
    """An IP address from a header entry: plain v4/v6, "v4:port", "[v6]:port" or quoted.
    IPv4-mapped IPv6 ("::ffff:1.2.3.4") becomes IPv4. Anything else (e.g. "unknown") -> None."""
    if not value:
        return None
    text = value.strip().strip('"')
    if text.startswith("["):  # [2001:db8::1]:443
        end = text.find("]")
        text = text[1:end] if end > 0 else ""
    elif text.count(":") == 1:  # 203.0.113.5:4711
        text = text.split(":", 1)[0]
    try:
        address = ipaddress.ip_address(text)
    except ValueError:
        return None
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped
    return address


def limiter_bucket(client: str) -> str:
    """Key the log-in counters use for an address. An IPv6 user normally holds a whole /64
    (privacy addresses rotate inside it), so IPv6 is counted per /64; otherwise rotating
    addresses inside one's own network would give fresh counters."""
    address = parse_address(client)
    if isinstance(address, ipaddress.IPv6Address):
        return str(ipaddress.ip_network(f"{address}/64", strict=False))
    return str(address) if address is not None else client


def _hops(forwarded_for: list[str]) -> list[str]:
    return [hop.strip() for value in forwarded_for for hop in value.split(",") if hop.strip()]


def client_address(peer: str | None, forwarded_for: list[str], trusted: tuple) -> str:
    """The address login limits are counted for (SEC-03).

    X-Forwarded-For is used only when the direct peer is a configured trusted proxy. The list is
    read from the right (entries appended by our own proxies) and the first address that is not
    a trusted proxy is the client; entries further left are written by the client and can be
    forged, so they are never used. With no trusted proxy configured the header is ignored.
    """
    if not peer:
        return "unknown"
    parse = parse_address

    def is_trusted(address) -> bool:
        return address is not None and any(address in network for network in trusted)

    if not trusted or not is_trusted(parse(peer)):
        return peer
    client = peer
    for hop in reversed(_hops(forwarded_for)):
        address = parse(hop)
        if address is None:
            # Our proxies append valid addresses, so this entry came from the client side:
            # count it apart from real addresses (never as the shared proxy address).
            return "invalid-forwarded"
        if not is_trusted(address):
            return str(address)
        client = str(address)
    return client


_unconfigured_warning_logged = False


def resolve_client(peer: str | None, headers, settings) -> tuple[str, str]:
    """(client address, source) for a request. Every source is opt-in configuration; with none
    configured the socket peer is used and forwarded headers are ignored.

    1. ``edge``: the request carries the shared secret our own front proxy adds (e.g. a Vercel
       rewrite). That proxy overwrites X-Forwarded-For with the visitor's address, so its
       left-most entry is the visitor; proxies after it only append to the right.
    2. ``client-ip-header``: a single-address header that the outermost edge overwrites on every
       request (e.g. Cloudflare's CF-Connecting-IP in front of Render web services).
    3. ``trusted-proxies``: X-Forwarded-For walked from the right past configured proxies.
    4. ``peer``.
    """
    global _unconfigured_warning_logged
    forwarded = headers.getlist("x-forwarded-for")
    if settings.edge_secret:
        given = headers.get(settings.edge_secret_header) or ""
        if hmac.compare_digest(given.encode(), settings.edge_secret.encode()):
            hops = _hops(forwarded)
            if hops:
                address = parse_address(hops[0])
                return (str(address) if address else "invalid-forwarded"), "edge"
    if settings.client_ip_header:
        address = parse_address(headers.get(settings.client_ip_header))
        if address is not None:
            return str(address), "client-ip-header"
    if settings.trusted_proxies:
        resolved = client_address(peer, forwarded, settings.trusted_proxies)
        return resolved, "trusted-proxies" if resolved != (peer or "unknown") else "peer"
    if forwarded and not settings.edge_secret and not settings.client_ip_header:
        if not _unconfigured_warning_logged:  # once per process; no addresses in the line
            _unconfigured_warning_logged = True
            logging.getLogger("academy.api").warning(
                "forwarded_header_ignored: X-Forwarded-For received but no client address "
                "source is configured (ACADEMY_EDGE_SECRET / ACADEMY_CLIENT_IP_HEADER / "
                "ACADEMY_TRUSTED_PROXIES); log-in limits count every client as the proxy"
            )
    return (peer or "unknown"), "peer"


class LoginRateLimiter:
    """Log-in attempts per key in a sliding window, kept in process memory.

    An attempt is reserved atomically *before* the password is checked (all keys checked and
    recorded under one lock), so parallel requests cannot all pass the check first — measured
    before this change: 30 parallel wrong passwords, 30 x 401, no 429. A successful log-in or
    a server error gives the reservation back; a wrong password keeps it (= one failure).

    One process = one counter set: with N worker processes the effective limit is up to N times
    higher (run one worker, or move the counters to a shared store — Phase 11-2-B-2 notes)."""

    MAX_KEYS = 10_000  # expired keys are swept once more keys than this are held
    KNOWN_ADDRESS_SECONDS = 30 * 24 * 3600
    KNOWN_ADDRESSES_PER_ACCOUNT = 5

    def __init__(self) -> None:
        self._attempts: dict[str, list[float]] = {}
        # account -> {address bucket: last successful log-in}. Failures from these addresses do
        # not lock the owner out through the account-wide counter (see AuthService.login).
        self._known: dict[str, dict[str, float]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _limited() -> CompatibilityError:
        return CompatibilityError(
            429, "LOGIN_RATE_LIMITED", "로그인 시도가 너무 많습니다. 잠시 후 다시 시도해주세요."
        )

    def _current(self, key: str, now: float, window: int) -> list[float]:
        current = [t for t in self._attempts.get(key, []) if now - t < window]
        if current:
            self._attempts[key] = current
        else:
            self._attempts.pop(key, None)  # no empty keys left behind
        return current

    def _sweep(self, now: float, window: int) -> None:
        if len(self._attempts) > self.MAX_KEYS:
            for stale in [k for k, times in self._attempts.items() if now - times[-1] >= window]:
                del self._attempts[stale]
        if len(self._known) > self.MAX_KEYS:
            self._known.clear()  # only successful log-ins add entries; this is a safety net

    def reserve(self, limits: list[tuple[str, int]]) -> float:
        """Check every (key, limit) and record this attempt on all of them, atomically.
        A limit of 0 is not checked but the attempt is still recorded. Raises 429."""
        window = get_settings().login_window_seconds
        now = time.monotonic()
        with self._lock:
            for key, limit in limits:
                if limit > 0 and len(self._current(key, now, window)) >= limit:
                    raise self._limited()
            for key, _ in limits:
                self._attempts.setdefault(key, []).append(now)
            self._sweep(now, window)
        return now

    def release(self, keys: list[str], stamp: float) -> None:
        """Give one reservation back (successful log-in, or an error that was not a failure)."""
        with self._lock:
            for key in keys:
                times = self._attempts.get(key)
                if times and stamp in times:
                    times.remove(stamp)
                    if not times:
                        del self._attempts[key]

    def is_known(self, account: str, bucket: str) -> bool:
        now = time.monotonic()
        with self._lock:
            seen = self._known.get(account, {}).get(bucket)
            return seen is not None and now - seen < self.KNOWN_ADDRESS_SECONDS

    def remember(self, account: str, bucket: str) -> None:
        now = time.monotonic()
        with self._lock:
            addresses = self._known.setdefault(account, {})
            addresses[bucket] = now
            for old in sorted(addresses, key=addresses.get)[: -self.KNOWN_ADDRESSES_PER_ACCOUNT]:
                del addresses[old]

    def check(self, key: str, limit: int | None = None) -> None:
        """Check one key without recording (kept for callers outside the log-in flow)."""
        settings = get_settings()
        limit = settings.login_attempt_limit if limit is None else limit
        with self._lock:
            current = self._current(key, time.monotonic(), settings.login_window_seconds)
            if limit > 0 and len(current) >= limit:
                raise self._limited()

    def fail(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            self._attempts.setdefault(key, []).append(now)
            self._sweep(now, get_settings().login_window_seconds)

    def success(self, key: str) -> None:
        with self._lock:
            self._attempts.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._attempts.clear()
            self._known.clear()


login_rate_limiter = LoginRateLimiter()


class PasswordResetCodes:
    """SEC-10 (Phase 11-4-B): one-time password reset codes an administrator issues and hands
    over in person — no e-mail or SMS is sent. Only a digest is kept, in process memory (like
    the log-in counters: one worker; a restart simply voids open codes, the admin issues a new
    one). A code is bound to one account, expires after ``RESET_CODE_MINUTES``, is gone after
    one use or ``MAX_WRONG`` wrong tries, and a new code replaces the previous one."""

    ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O, 1/I: read out without mistakes
    LENGTH = 10  # 32^10 ≈ 2^50 combinations
    MAX_WRONG = 5

    def __init__(self) -> None:
        self._codes: dict[int, list] = {}  # user id -> [digest, expires_at, wrong tries]
        self._lock = threading.Lock()

    @staticmethod
    def _digest(user_id: int, raw: str) -> str:
        return hashlib.sha256(f"{user_id}:{raw}".encode()).hexdigest()

    @classmethod
    def _normalize(cls, code: str) -> str:
        return "".join(ch for ch in code.upper() if ch.isalnum())

    def issue(self, user_id: int, now: datetime, minutes: int) -> tuple[str, datetime]:
        raw = "".join(secrets.choice(self.ALPHABET) for _ in range(self.LENGTH))
        expires = now + timedelta(minutes=minutes)
        with self._lock:
            self._codes[user_id] = [self._digest(user_id, raw), expires, 0]
        return f"{raw[:5]}-{raw[5:]}", expires

    def consume(self, user_id: int, code: str, now: datetime) -> bool:
        with self._lock:
            entry = self._codes.get(user_id)
            if entry is None:
                return False
            if now >= entry[1]:
                del self._codes[user_id]
                return False
            if hmac.compare_digest(entry[0], self._digest(user_id, self._normalize(code))):
                del self._codes[user_id]  # one use only
                return True
            entry[2] += 1
            if entry[2] >= self.MAX_WRONG:
                del self._codes[user_id]
            return False

    def clear(self) -> None:
        with self._lock:
            self._codes.clear()


password_reset_codes = PasswordResetCodes()
RESET_CODE_MINUTES = 15
RESET_FAILED = ("RESET_FAILED", "이메일 또는 재설정 코드가 올바르지 않거나 만료되었습니다.")


def password_problem(new_password: str, *, email: str, current: str | None = None) -> str | None:
    """The new-password rule shared by change and reset (same minimum as staff creation)."""
    if len(new_password) < MIN_PASSWORD_LENGTH:
        return f"새 비밀번호는 {MIN_PASSWORD_LENGTH}자 이상이어야 합니다."
    if len(new_password) > 1024:
        return "새 비밀번호가 너무 깁니다."
    if not new_password.strip():
        return "새 비밀번호를 입력해주세요."
    if current is not None and new_password == current:
        return "현재 비밀번호와 다른 비밀번호를 입력해주세요."
    if new_password.strip().lower() == email.lower():
        return "이메일과 같은 비밀번호는 사용할 수 없습니다."
    return None


class AuthService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _set_password(self, user_id: int, new_password: str, keep_session=None) -> int:
        """Store the new hash and revoke the account's sessions (all, or all but ``keep``).
        Returns how many sessions were revoked."""
        user = self.session.scalar(
            select(StaffUser).where(StaffUser.id == user_id).with_for_update()
        )
        user.password_hash = hash_password(new_password)
        query = update(AuthSession).where(
            AuthSession.staff_user_id == user_id, AuthSession.revoked_at.is_(None)
        )
        if keep_session is not None:
            query = query.where(AuthSession.id != keep_session)
        return self.session.execute(query.values(revoked_at=utc_now())).rowcount

    def change_password(
        self, user: StaffUser, auth_session: AuthSession, current: str, new: str, request_id: str
    ) -> int:
        """SEC-10-A: the signed-in member changes their own password. The current password is
        required (a stolen session alone is not enough) and wrong tries are counted like log-in
        failures; other sessions are revoked, this one stays."""
        key = f"password-change:{user.id}"
        stamp = login_rate_limiter.reserve([(key, get_settings().login_attempt_limit)])
        if not verify_password(user.password_hash, current):
            raise CompatibilityError(
                400, "INVALID_CURRENT_PASSWORD", "현재 비밀번호가 올바르지 않습니다."
            )  # the reservation stays: it counts as a failed try
        problem = password_problem(new, email=user.email, current=current)
        if problem:
            login_rate_limiter.release([key], stamp)
            raise CompatibilityError(400, "WEAK_PASSWORD", problem)
        revoked = self._set_password(user.id, new, keep_session=auth_session.id)
        self.session.add(
            AuditLog(
                actor_staff_user_id=user.id,
                event_type="STAFF_PASSWORD_CHANGED",
                target_type="STAFF_USER",
                target_id=str(user.id),
                request_id=UUID(request_id),
                details={"other_sessions_revoked": revoked},
            )
        )
        self.session.commit()
        login_rate_limiter.success(key)
        return revoked

    def complete_reset(
        self, email: str, code: str, new: str, request_id: str, client_key: str
    ) -> None:
        """SEC-10-B: set a new password with an administrator-issued one-time code. Every
        failure — unknown or inactive account, wrong, used or expired code — gets the same
        answer, so the endpoint tells nothing about which accounts exist."""
        normalized = email.strip().lower()
        settings = get_settings()
        problem = password_problem(new, email=normalized)
        if problem:
            raise CompatibilityError(400, "WEAK_PASSWORD", problem)
        keys = [f"ip:{client_key}", f"reset:{normalized}"]
        stamp = login_rate_limiter.reserve(
            [(keys[0], settings.login_ip_attempt_limit), (keys[1], settings.login_attempt_limit)]
        )
        user = self.session.scalar(
            select(StaffUser).where(func.lower(StaffUser.email) == normalized)
        )
        if (
            user is None
            or user.status != "ACTIVE"
            or not password_reset_codes.consume(user.id, code, utc_now())
        ):
            raise CompatibilityError(400, *RESET_FAILED)  # reservation kept: a failed try
        revoked = self._set_password(user.id, new)
        self.session.add(
            AuditLog(
                actor_staff_user_id=user.id,
                event_type="STAFF_PASSWORD_RESET_COMPLETED",
                target_type="STAFF_USER",
                target_id=str(user.id),
                request_id=UUID(request_id),
                details={"sessions_revoked": revoked},
            )
        )
        self.session.commit()
        login_rate_limiter.release([keys[0]], stamp)
        login_rate_limiter.success(keys[1])

    def login(self, email: str, password: str, request_id: str, client_key: str) -> IssuedSession:
        """``client_key`` is the limiter bucket of the client address (see ``limiter_bucket``)."""
        normalized = email.strip().lower()
        settings = get_settings()
        # Three counters (SEC-03): address + account (5), address over all accounts — loose so
        # that colleagues behind one office address are not locked out by one typo-prone user —
        # and account over all addresses, so rotating addresses does not give unlimited guesses.
        rate_key = f"pair:{client_key}|{normalized}"
        ip_key = f"ip:{client_key}"
        account_key = f"account:{normalized}"
        keys = [ip_key, rate_key, account_key]
        # Targeted lock-out: anyone can spend an account's 20 failures from other addresses. From
        # an address where the owner logged in recently that counter is not applied (the
        # address+account limit of 5 and the address limit still are), so the owner keeps access.
        known = login_rate_limiter.is_known(normalized, client_key)
        account_limit = 0 if known else settings.login_account_attempt_limit
        stamp = login_rate_limiter.reserve(
            [
                (ip_key, settings.login_ip_attempt_limit),
                (rate_key, settings.login_attempt_limit),
                (account_key, account_limit),
            ]
        )
        try:
            issued = self._authenticate(normalized, password, request_id)
        except CompatibilityError as error:
            if error.code != "INVALID_CREDENTIALS":
                login_rate_limiter.release(keys, stamp)
            raise  # a wrong password keeps its reservation: that is the failure count
        except Exception:
            login_rate_limiter.release(keys, stamp)  # server error: not the user's failure
            raise
        # Only the owner's counters are reset. The address-wide counter only gets this attempt
        # back: otherwise any valid account could reset it between guesses against others.
        login_rate_limiter.release([ip_key], stamp)
        login_rate_limiter.success(rate_key)
        login_rate_limiter.success(account_key)
        login_rate_limiter.remember(normalized, client_key)
        return issued

    def _authenticate(self, normalized: str, password: str, request_id: str) -> IssuedSession:
        user = self.session.scalar(
            select(StaffUser).where(func.lower(StaffUser.email) == normalized)
        )
        valid = verify_password(user.password_hash if user else None, password)
        if not valid or user is None or user.status != "ACTIVE":
            raise CompatibilityError(
                401, "INVALID_CREDENTIALS", "이메일 또는 비밀번호가 올바르지 않습니다."
            )

        if password_hasher.check_needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)

        raw_session = secrets.token_urlsafe(32)
        raw_csrf = secrets.token_urlsafe(32)
        now = utc_now()
        expires = now + timedelta(minutes=get_settings().session_ttl_minutes)
        auth_session = AuthSession(
            id=uuid4(),
            staff_user_id=user.id,
            token_hash=token_digest(raw_session),
            csrf_token_hash=token_digest(raw_csrf),
            expires_at=expires,
            last_seen_at=now,  # same clock as the idle check (SEC-05)
        )
        self.session.add(auth_session)
        self.session.add(
            AuditLog(
                actor_staff_user_id=user.id,
                event_type="AUTH_LOGIN",
                target_type="AUTH_SESSION",
                target_id=str(auth_session.id),
                request_id=UUID(request_id),
                details={"role": user.role},
            )
        )
        self.session.commit()
        return IssuedSession(user, raw_session, raw_csrf, expires)

    def revoke(self, auth_session: AuthSession, user: StaffUser, request_id: str) -> None:
        auth_session.revoked_at = utc_now()
        self.session.add(
            AuditLog(
                actor_staff_user_id=user.id,
                event_type="AUTH_LOGOUT",
                target_type="AUTH_SESSION",
                target_id=str(auth_session.id),
                request_id=UUID(request_id),
            )
        )
        self.session.commit()
