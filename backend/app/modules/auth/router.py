import hmac
import time
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import get_db
from app.errors import CompatibilityError
from app.modules.auth.dependencies import (
    Principal,
    get_current_principal,
    require_admin,
    require_csrf,
)
from app.modules.auth.schemas import (
    AuthResponse,
    ClientAddressDiagnosis,
    CurrentStaff,
    LoginRequest,
    LogoutResponse,
    PasswordChange,
    PasswordChanged,
    PasswordResetComplete,
    PasswordResetDone,
)
from app.modules.auth.service import AuthService, limiter_bucket, resolve_client
from app.security import require_local_db_api

router = APIRouter(prefix="/api/auth", dependencies=[Depends(require_local_db_api)])


def _staff(principal: Principal) -> CurrentStaff:
    return CurrentStaff(
        id=principal.user_id,
        email=principal.email,
        display_name=principal.user.display_name,
        role=principal.role,
    )


def _set_cookies(response: Response, session_token: str, csrf_token: str, max_age: int) -> None:
    settings = get_settings()
    response.set_cookie(
        settings.session_cookie_name,
        session_token,
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        settings.csrf_cookie_name,
        csrf_token,
        max_age=max_age,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


@router.post("/login", summary="로그인", response_model=AuthResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> AuthResponse:
    # Forwarded addresses only from configured sources (SEC-03). Run uvicorn with
    # --no-proxy-headers so the peer address here is the real socket peer.
    client, _ = resolve_client(
        request.client.host if request.client else None, request.headers, get_settings()
    )
    client_key = limiter_bucket(client)
    issued = AuthService(db).login(
        payload.email, payload.password, request.state.request_id, client_key
    )
    _set_cookies(
        response,
        issued.session_token,
        issued.csrf_token,
        max(0, int(issued.expires_at.timestamp() - time.time())),
    )
    return AuthResponse(
        user=CurrentStaff(
            id=issued.user.id,
            email=issued.user.email,
            display_name=issued.user.display_name,
            role=issued.user.role,
        )
    )


@router.post("/password", summary="내 비밀번호 변경", response_model=PasswordChanged)
def change_password(
    payload: PasswordChange,
    request: Request,
    principal: Annotated[Principal, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
) -> PasswordChanged:
    """SEC-10-A: change one's own password (current password required, CSRF, other sessions
    revoked). Wrong current password: 400 — not 401, which would end the session client-side."""
    revoked = AuthService(db).change_password(
        principal.user,
        principal.auth_session,
        payload.current_password,
        payload.new_password,
        request.state.request_id,
    )
    return PasswordChanged(changed=True, other_sessions_revoked=revoked)


@router.post(
    "/password-reset", summary="재설정 코드로 비밀번호 재설정", response_model=PasswordResetDone
)
def complete_password_reset(
    payload: PasswordResetComplete,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> PasswordResetDone:
    """SEC-10-B: set a new password with the one-time code an administrator handed over. No
    session is needed (the member cannot log in); the code is the proof. JSON only, like log-in
    (cross-site forms cannot send it), and limited like log-in attempts."""
    client, _ = resolve_client(
        request.client.host if request.client else None, request.headers, get_settings()
    )
    AuthService(db).complete_reset(
        payload.email,
        payload.code,
        payload.new_password,
        request.state.request_id,
        limiter_bucket(client),
    )
    return PasswordResetDone(reset=True)


@router.post("/logout", summary="로그아웃", response_model=LogoutResponse)
def logout(
    request: Request,
    response: Response,
    principal: Annotated[Principal, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
) -> LogoutResponse:
    AuthService(db).revoke(principal.auth_session, principal.user, request.state.request_id)
    settings = get_settings()
    response.delete_cookie(settings.session_cookie_name, path="/")
    response.delete_cookie(settings.csrf_cookie_name, path="/")
    return LogoutResponse(loggedOut=True)


@router.get(
    "/client-address",
    summary="로그인 제한 기준 주소 진단(배포 점검용, 기본 꺼짐)",
    response_model=ClientAddressDiagnosis,
)
def client_address_diagnosis(
    request: Request, _: Annotated[Principal, Depends(require_admin)]
) -> ClientAddressDiagnosis:
    """Deployment check (Phase 11-5): which address the log-in limits would count for this
    request. Enabled only with ACADEMY_PROXY_DIAGNOSTICS=1; turn it off again afterwards."""
    settings = get_settings()
    if not settings.proxy_diagnostics:
        raise CompatibilityError(404, "NOT_FOUND", "요청한 기능을 사용할 수 없습니다.")
    peer = request.client.host if request.client else None
    resolved, source = resolve_client(peer, request.headers, settings)
    if not settings.edge_secret:
        secret_state = "not-configured"
    else:
        given = request.headers.get(settings.edge_secret_header)
        secret_state = (
            "missing"
            if given is None
            else "valid"
            if hmac.compare_digest(given.encode(), settings.edge_secret.encode())
            else "invalid"
        )
    return ClientAddressDiagnosis(
        peer=peer,
        forwarded_for=[
            hop.strip()
            for value in request.headers.getlist("x-forwarded-for")
            for hop in value.split(",")
            if hop.strip()
        ],
        client_ip_header=settings.client_ip_header or None,
        client_ip_header_value=(
            request.headers.get(settings.client_ip_header) if settings.client_ip_header else None
        ),
        edge_secret=secret_state,
        resolved=resolved,
        source=source,
        limiter_bucket=limiter_bucket(resolved),
    )


@router.get("/me", summary="현재 로그인한 직원 정보", response_model=AuthResponse)
def me(principal: Annotated[Principal, Depends(get_current_principal)]) -> AuthResponse:
    return AuthResponse(user=_staff(principal))
