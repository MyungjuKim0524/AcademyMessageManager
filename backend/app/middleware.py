import json
import logging
import time
import traceback
import uuid

from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import Settings
from app.uploads import MAX_REQUEST_BYTES, UPLOAD_PATHS

logger = logging.getLogger("academy.api")
INTERNAL_MESSAGE = "요청 처리 중 오류가 발생했습니다."
# Bodies that must be JSON: a cross-site HTML form cannot send it without a CORS preflight, which
# the Origin allow-list refuses (log-in-CSRF defence; Phase 11-4-B adds the password reset).
JSON_ONLY_PATHS = frozenset(
    {"/api/messages/preview", "/api/auth/login", "/api/auth/password-reset", "/api/auth/password"}
)


# Phase 11-4-A: database failures that are not programming errors get an answer the user can act
# on, instead of the generic 500. The transaction is always rolled back first (get_db).
RETRYABLE_SQLSTATES = {
    "40P01": "deadlock",
    "40001": "serialization failure",
    "55P03": "lock not available",
}
UNAVAILABLE_SQLSTATE_PREFIXES = ("08", "28", "53", "57P")  # connection, auth, resources, shutdown


def classify_database_error(exc: BaseException) -> tuple[int, str, str] | None:
    """(status, code, message) for a database failure the client can retry, else None."""
    if isinstance(exc, SQLAlchemyTimeoutError):  # connection pool exhausted (pool_timeout)
        return 503, "DATABASE_UNAVAILABLE", DATABASE_UNAVAILABLE_MESSAGE
    if not isinstance(exc, DBAPIError):
        return None
    sqlstate = getattr(exc.orig, "sqlstate", None)
    if sqlstate in RETRYABLE_SQLSTATES:
        return 409, "TRANSACTION_CONFLICT", TRANSACTION_CONFLICT_MESSAGE
    if isinstance(exc, OperationalError) and (
        sqlstate is None or sqlstate.startswith(UNAVAILABLE_SQLSTATE_PREFIXES)
    ):
        return 503, "DATABASE_UNAVAILABLE", DATABASE_UNAVAILABLE_MESSAGE
    return None


DATABASE_UNAVAILABLE_MESSAGE = "데이터베이스에 연결할 수 없습니다. 잠시 후 다시 시도해주세요."
TRANSACTION_CONFLICT_MESSAGE = (
    "다른 작업과 동시에 처리되어 저장하지 않았습니다. 잠시 후 다시 시도해주세요."
)


def log_unhandled(exc: BaseException, request_id: str | None, method: str, path: str) -> None:
    """Log an unexpected error without its message (SEC-07).

    Exception texts can carry personal data: SQLAlchemy / PostgreSQL errors quote SQL
    parameters and ``DETAIL: Key (name, …)=(…)`` values (student names, guardian e-mails).
    Kept for debugging: error type, PostgreSQL SQLSTATE / constraint name, request id and the
    stack frames (file, line, function, source line — code, not data)."""
    orig = getattr(exc, "orig", None)
    diag = getattr(orig, "diag", None)
    frames = traceback.extract_tb(exc.__traceback__)[-12:]
    logger.error(
        "unhandled_request_error request_id=%s method=%s endpoint=%s error_type=%s "
        "db_error_type=%s sqlstate=%s constraint=%s\n%s",
        request_id,
        method,
        path,
        f"{type(exc).__module__}.{type(exc).__qualname__}",
        type(orig).__qualname__ if orig is not None else "-",
        getattr(orig, "sqlstate", None) or "-",
        getattr(diag, "constraint_name", None) or "-",
        "".join(traceback.format_list(frames)).rstrip(),
    )


def _error(code: str, message: str) -> bytes:
    return json.dumps(
        {"code": code, "message": message, "fields": []},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()


class CompatibilityMiddleware:
    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started, request_id = time.perf_counter(), str(uuid.uuid4())
        method, path = scope["method"], scope["path"]
        scope.setdefault("state", {})["request_id"] = request_id
        headers = {key.lower(): value for key, value in scope["headers"]}
        origin = headers.get(b"origin", b"").decode("latin-1")
        allowed_method = (
            "POST"
            if path
            in {
                "/api/messages/preview",
                "/api/auth/login",
                "/api/auth/logout",
                "/api/auth/password",
                "/api/auth/password-reset",
            }
            else "GET"
        )
        status_code, error_code = 500, "-"
        common_headers = [
            (b"x-request-id", request_id.encode()),
            (b"x-content-type-options", b"nosniff"),
            (b"cache-control", b"no-store"),
            (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'"),
            (b"referrer-policy", b"no-referrer"),
        ]
        if self.settings.hsts_max_age > 0:  # SEC-09: only when configured for an HTTPS host
            common_headers.append(
                (
                    b"strict-transport-security",
                    f"max-age={self.settings.hsts_max_age}".encode(),
                )
            )
        response_started = False
        if origin in self.settings.cors_origins:
            common_headers += [
                (b"access-control-allow-origin", origin.encode()),
                (b"vary", b"Origin"),
                (b"access-control-allow-methods", f"{allowed_method}, OPTIONS".encode()),
                (
                    b"access-control-allow-headers",
                    b"Content-Type, Idempotency-Key, X-CSRF-Token",
                ),
                (b"access-control-allow-credentials", b"true"),
            ]

        async def send_error(status: int, code: str, message: str, allow: bool = False) -> None:
            nonlocal status_code, error_code, response_started
            response_started = True
            status_code, error_code = status, code
            body = _error(code, message)
            response_headers = common_headers + [
                (b"content-type", b"application/json; charset=UTF-8"),
                (b"content-length", str(len(body)).encode()),
            ]
            if allow:
                response_headers.append((b"allow", f"{allowed_method}, OPTIONS".encode()))
            await send(
                {"type": "http.response.start", "status": status, "headers": response_headers}
            )
            await send({"type": "http.response.body", "body": body})

        try:
            if origin and origin not in self.settings.cors_origins:
                await send_error(403, "CORS_FORBIDDEN", "허용되지 않은 요청 출처입니다.")
                return
            if method == "OPTIONS":
                requested = headers.get(b"access-control-request-method", b"").decode()
                if requested and requested != allowed_method:
                    await send_error(
                        405, "METHOD_NOT_ALLOWED", "허용되지 않은 HTTP 메서드입니다.", True
                    )
                    return
                status_code = 204
                await send(
                    {"type": "http.response.start", "status": 204, "headers": common_headers}
                )
                await send({"type": "http.response.body", "body": b""})
                return
            known_paths = {
                "/api/health",
                "/api/messages/preview",
                "/api/auth/login",
                "/api/auth/logout",
                "/api/auth/me",
                "/api/auth/password",
                "/api/auth/password-reset",
            }
            if path in known_paths and method != allowed_method:
                await send_error(
                    405, "METHOD_NOT_ALLOWED", "허용되지 않은 HTTP 메서드입니다.", True
                )
                return
            content_type = headers.get(b"content-type", b"").decode("latin-1").lower()
            if path in JSON_ONLY_PATHS and not content_type.startswith("application/json"):
                await send_error(
                    415,
                    "UNSUPPORTED_MEDIA_TYPE",
                    "Content-Type은 application/json이어야 합니다.",
                )
                return

            # bytearray, not bytes +=: appending chunk by chunk to bytes copies the whole body each
            # time (measured: ~0.5 s CPU on the event loop for a 10MB upload in 64KB chunks,
            # before any authentication). Phase 11-4-A.
            buffer, more_body = bytearray(), True
            # File uploads get the file limit (10MB + multipart overhead); everything else the
            # small JSON limit. Before 2026-11-20 only the removed legacy import paths had the
            # file limit, so a real weekly workbook (>16KB) was rejected as PAYLOAD_TOO_LARGE.
            body_limit = (
                MAX_REQUEST_BYTES if path in UPLOAD_PATHS else self.settings.max_json_body_bytes
            )
            while more_body:
                message = await receive()
                buffer += message.get("body", b"")
                if len(buffer) > body_limit:
                    if path in UPLOAD_PATHS:
                        await send_error(413, "FILE_TOO_LARGE", "파일은 10MB 이하여야 합니다.")
                    else:
                        await send_error(413, "PAYLOAD_TOO_LARGE", "요청 본문이 너무 큽니다.")
                    return
                more_body = message.get("more_body", False)
            body = bytes(buffer)
            delivered = False

            async def replay_receive() -> Message:
                nonlocal delivered
                if delivered:
                    return {"type": "http.request", "body": b"", "more_body": False}
                delivered = True
                return {"type": "http.request", "body": body, "more_body": False}

            async def wrapped_send(message: Message) -> None:
                nonlocal status_code, response_started
                if message["type"] == "http.response.start":
                    response_started = True
                    status_code = message["status"]
                    original = [
                        item
                        for item in message.get("headers", [])
                        if item[0].lower() != b"content-type"
                    ]
                    original.append((b"content-type", b"application/json; charset=UTF-8"))
                    current = {key.lower() for key, _ in original}
                    message["headers"] = original + [
                        item for item in common_headers if item[0] not in current
                    ]
                await send(message)

            try:
                await self.app(scope, replay_receive, wrapped_send)
            except Exception as exc:
                # Handled here, not re-raised: Starlette's outer error middleware re-raises
                # every exception after its handler, and the server then logs the full
                # traceback including the exception text (SEC-07).
                log_unhandled(exc, request_id, method, path)
                status, code, message = classify_database_error(exc) or (
                    500,
                    "INTERNAL_ERROR",
                    INTERNAL_MESSAGE,
                )
                if not response_started:
                    await send_error(status, code, message)
                else:
                    error_code = code
        finally:
            logger.info(
                "request_complete method=%s endpoint=%s status=%s "
                "duration_ms=%s request_id=%s error_code=%s",
                method,
                path,
                status_code,
                int((time.perf_counter() - started) * 1000),
                request_id,
                error_code,
            )
