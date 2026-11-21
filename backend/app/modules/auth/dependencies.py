import hmac
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models.tables import (
    AuthSession,
    Classroom,
    ClassroomStaffAssignment,
    StaffUser,
)
from app.db.session import get_db
from app.errors import CompatibilityError
from app.modules.auth import service as auth_service
from app.modules.auth.service import token_digest


@dataclass(frozen=True)
class Principal:
    user_id: int
    email: str
    role: str
    auth_session: AuthSession
    user: StaffUser


def require_session_token(request: Request) -> str:
    token = request.cookies.get(get_settings().session_cookie_name)
    if not token or len(token) > 256:
        raise CompatibilityError(401, "AUTHENTICATION_REQUIRED", "로그인이 필요합니다.")
    return token


def get_current_principal(
    request: Request,
    token: Annotated[str, Depends(require_session_token)],
    db: Annotated[Session, Depends(get_db)],
) -> Principal:
    row = db.execute(
        select(AuthSession, StaffUser)
        .join(StaffUser, StaffUser.id == AuthSession.staff_user_id)
        .where(AuthSession.token_hash == token_digest(token))
    ).one_or_none()
    if row is None:
        raise CompatibilityError(401, "AUTHENTICATION_REQUIRED", "로그인이 필요합니다.")
    auth_session, user = row
    now = auth_service.utc_now()
    if (
        auth_session.revoked_at is not None
        or auth_session.expires_at <= now
        or user.status != "ACTIVE"
    ):
        raise CompatibilityError(
            401, "SESSION_EXPIRED", "세션이 만료되었습니다. 다시 로그인해주세요."
        )
    _check_idle(db, request, auth_session, now)
    return Principal(user.id, user.email, user.role, auth_session, user)


def _check_idle(db: Session, request: Request, auth_session: AuthSession, now: datetime) -> None:
    """SEC-05 (Phase 11-4-B): server-side idle expiry on the server clock.

    * Idle longer than ACADEMY_SESSION_IDLE_MINUTES: the session is revoked (a later request
      cannot revive it) and the request gets 401 SESSION_IDLE_EXPIRED.
    * Otherwise the request counts as activity, written at most once per
      ``ACTIVITY_WRITE_SECONDS`` and only forward in time (conditional UPDATE, so concurrent
      requests never move it back and need no lock). Requests marked as automatic
      (``X-Academy-Background: 1``) never extend the session.
    These two writes commit on their own: they must survive the request's own rollback."""
    idle = timedelta(minutes=get_settings().session_idle_minutes)
    if now - auth_session.last_seen_at >= idle:
        db.execute(
            update(AuthSession)
            .where(AuthSession.id == auth_session.id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        db.commit()
        raise CompatibilityError(
            401,
            "SESSION_IDLE_EXPIRED",
            "오랫동안 사용하지 않아 로그아웃되었습니다. 다시 로그인해주세요.",
        )
    if request.headers.get(auth_service.BACKGROUND_HEADER) == "1":
        return
    step = timedelta(seconds=auth_service.ACTIVITY_WRITE_SECONDS)
    if now - auth_session.last_seen_at >= step:
        db.execute(
            update(AuthSession)
            .where(AuthSession.id == auth_session.id, AuthSession.last_seen_at < now - step)
            .values(last_seen_at=now)
        )
        db.commit()


def require_csrf(
    request: Request, principal: Annotated[Principal, Depends(get_current_principal)]
) -> Principal:
    settings = get_settings()
    cookie = request.cookies.get(settings.csrf_cookie_name)
    header = request.headers.get("X-CSRF-Token")
    if (
        not cookie
        or not header
        or not hmac.compare_digest(cookie, header)
        or not hmac.compare_digest(token_digest(header), principal.auth_session.csrf_token_hash)
    ):
        raise CompatibilityError(403, "CSRF_FAILED", "요청을 확인할 수 없습니다.")
    return principal


def require_roles(*roles: str) -> Callable:
    def dependency(
        principal: Annotated[Principal, Depends(get_current_principal)],
    ) -> Principal:
        if principal.role not in roles:
            raise CompatibilityError(403, "FORBIDDEN", "요청한 작업을 수행할 권한이 없습니다.")
        return principal

    return dependency


require_authenticated = require_roles("ADMIN", "TEACHER", "ASSISTANT")
require_admin = require_roles("ADMIN")


def require_admin_csrf(
    principal: Annotated[Principal, Depends(require_csrf)],
) -> Principal:
    if principal.role != "ADMIN":
        raise CompatibilityError(403, "FORBIDDEN", "요청한 작업을 수행할 권한이 없습니다.")
    return principal


def require_classroom_access(
    db: Session, principal: Principal, class_name: str, class_type: str
) -> None:
    if principal.role == "ADMIN":
        return
    today = date.today()
    allowed = db.scalar(
        select(Classroom.id)
        .join(
            ClassroomStaffAssignment,
            ClassroomStaffAssignment.classroom_id == Classroom.id,
        )
        .where(
            Classroom.name == class_name,
            Classroom.class_type == class_type,
            Classroom.is_active.is_(True),
            ClassroomStaffAssignment.staff_user_id == principal.user_id,
            ClassroomStaffAssignment.assignment_role == principal.role,
            ClassroomStaffAssignment.valid_from <= today,
            or_(
                ClassroomStaffAssignment.valid_to.is_(None),
                ClassroomStaffAssignment.valid_to >= today,
            ),
        )
    )
    if allowed is None:
        raise CompatibilityError(403, "CLASSROOM_ACCESS_DENIED", "담당 반에만 접근할 수 있습니다.")
