from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.errors import CompatibilityError
from app.modules.auth.dependencies import Principal, require_authenticated, require_csrf

from .schemas import (
    BatchApproveRequest,
    BatchResponse,
    BatchSendRequest,
    BatchView,
    BodyUpdate,
    GenerateRequest,
    GenerateResponse,
    MockSendResponse,
    NotificationDetail,
    NotificationListItem,
    NotificationPage,
    NotificationStatus,
    PreviewResponse,
    TemplateCreate,
    TemplateUpdate,
    TemplateValidate,
    TemplateValidation,
    TemplateVariable,
    TemplateView,
    VersionOnly,
)
from .service import NotificationService

router = APIRouter(prefix="/api")

Reader = Annotated[Principal, Depends(require_authenticated)]
Writer = Annotated[Principal, Depends(require_csrf)]
Db = Annotated[Session, Depends(get_db)]


def _service(db: Session, principal: Principal, request: Request | None = None):
    request_id = getattr(request.state, "request_id", None) if request is not None else None
    return NotificationService(db, principal, request_id)


# -------------------------------------------------------------- templates
@router.get(
    "/notification-templates", summary="메시지 템플릿 목록", response_model=list[TemplateView]
)
def list_templates(principal: Reader, db: Db):
    return _service(db, principal).templates()


@router.get(
    "/notification-templates/variables",
    summary="템플릿에 쓸 수 있는 변수 목록",
    response_model=list[TemplateVariable],
)
def template_variables(principal: Reader, db: Db):
    return _service(db, principal).variables()


@router.post(
    "/notification-templates/validate",
    summary="템플릿 문법 검사",
    response_model=TemplateValidation,
)
def validate_template(payload: TemplateValidate, principal: Reader, db: Db):
    return _service(db, principal).validate_template(payload.body)


@router.post(
    "/notification-templates",
    summary="메시지 템플릿 생성",
    response_model=TemplateView,
    status_code=status.HTTP_201_CREATED,
)
def create_template(payload: TemplateCreate, principal: Writer, db: Db, request: Request):
    return _service(db, principal, request).create_template(payload)


@router.patch(
    "/notification-templates/{template_id}",
    summary="메시지 템플릿 수정",
    response_model=TemplateView,
)
def update_template(
    template_id: int, payload: TemplateUpdate, principal: Writer, db: Db, request: Request
):
    return _service(db, principal, request).update_template(template_id, payload)


# ------------------------------------------------------ generation flow
@router.post(
    "/lessons/{lesson_id}/notifications/preview",
    summary="수업 메시지 초안 미리보기(저장 안 함)",
    response_model=PreviewResponse,
)
def preview_notifications(lesson_id: int, payload: GenerateRequest, principal: Reader, db: Db):
    lesson, template, items = _service(db, principal).preview(lesson_id, payload)
    return PreviewResponse(
        lesson_id=lesson.id, template_id=template.id, template_version=template.version, items=items
    )


@router.post(
    "/lessons/{lesson_id}/notifications",
    summary="수업 메시지 초안 생성",
    response_model=GenerateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_notifications(
    lesson_id: int, payload: GenerateRequest, principal: Writer, db: Db, request: Request
):
    created, skipped = _service(db, principal, request).create_drafts(lesson_id, payload)
    return GenerateResponse(created=created, skipped=skipped)


# ---------------------------------------------------- review / approval
@router.get("/notifications", summary="메시지 목록", response_model=NotificationPage)
def list_notifications(
    principal: Reader,
    db: Db,
    classroom_id: Annotated[int, Query(gt=0)],
    lesson_id: Annotated[int | None, Query(gt=0)] = None,
    status: NotificationStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    service = _service(db, principal)
    rows = service.listing(classroom_id, lesson_id, status, limit, offset)
    return NotificationPage(
        items=[NotificationListItem(**service.list_item(*row)) for row in rows],
        limit=limit,
        offset=offset,
    )


@router.get(
    "/notifications/{notification_id}", summary="메시지 상세", response_model=NotificationDetail
)
def get_notification(notification_id: int, principal: Reader, db: Db):
    return _service(db, principal).detail(notification_id)


@router.patch(
    "/notifications/{notification_id}",
    summary="메시지 내용 수정",
    response_model=NotificationDetail,
)
def edit_notification(
    notification_id: int, payload: BodyUpdate, principal: Writer, db: Db, request: Request
):
    return _service(db, principal, request).edit(notification_id, payload)


def _transition(action: str):
    def handler(
        notification_id: int, payload: VersionOnly, principal: Writer, db: Db, request: Request
    ):
        service = _service(db, principal, request)
        return getattr(service, action)(notification_id, payload.version)

    handler.__name__ = f"{action}_notification"
    return handler


_TRANSITION_SUMMARY = {
    "submit": "검토 요청(초안 → 검토 대기)",
    "approve": "메시지 확정",
    "revoke": "확정 취소(확정 → 초안)",
    "cancel": "메시지 취소(발송 안 함)",
}
for _action in ("submit", "approve", "revoke", "cancel"):
    router.add_api_route(
        f"/notifications/{{notification_id}}/{_action}",
        _transition(_action),
        methods=["POST"],
        response_model=NotificationDetail,
        summary=_TRANSITION_SUMMARY[_action],
    )


# ------------------------------------------- class batch (one class lesson at a time)
@router.get(
    "/lessons/{lesson_id}/notifications/batch",
    summary="반 단위 일괄 검토 화면 데이터",
    response_model=BatchView,
)
def batch_view(lesson_id: int, principal: Reader, db: Db):
    """Every active message of the lesson with its body, for reviewing the class on one screen."""
    return _service(db, principal).batch_view(lesson_id)


@router.post(
    "/lessons/{lesson_id}/notifications/batch-approve",
    summary="반 단위 일괄 확정",
    response_model=BatchResponse,
)
def batch_approve(
    lesson_id: int, payload: BatchApproveRequest, principal: Writer, db: Db, request: Request
):
    """Confirms the chosen messages one by one; each result says confirmed or why it was skipped."""
    items = [(item.id, item.version) for item in payload.items]
    return BatchResponse(results=_service(db, principal, request).batch_approve(lesson_id, items))


@router.post(
    "/lessons/{lesson_id}/notifications/batch-mock-send",
    summary="반 단위 일괄 모의 발송",
    response_model=BatchResponse,
)
def batch_mock_send(
    lesson_id: int, payload: BatchSendRequest, principal: Writer, db: Db, request: Request
):
    """Mock-sends confirmed messages (and retries failed ones) one by one, each with its own key."""
    items = [(item.id, item.idempotency_key) for item in payload.items]
    service = _service(db, principal, request)
    return BatchResponse(results=service.batch_mock_send(lesson_id, items))


IdempotencyKey = Annotated[str | None, Header(alias="Idempotency-Key")]


def _key(value: str | None) -> UUID:
    try:
        return UUID(value or "")
    except ValueError:
        raise CompatibilityError(
            400, "IDEMPOTENCY_KEY_REQUIRED", "Idempotency-Key 헤더(UUID)가 필요합니다."
        ) from None


@router.post(
    "/notifications/{notification_id}/mock-send",
    summary="모의 발송",
    response_model=MockSendResponse,
)
def mock_send(
    notification_id: int,
    principal: Writer,
    db: Db,
    request: Request,
    idempotency_key: IdempotencyKey = None,
):
    key = _key(idempotency_key)
    detail, attempt, replayed = _service(db, principal, request).mock_send(notification_id, key)
    return MockSendResponse(notification=detail, attempt=attempt, replayed=replayed)


@router.post(
    "/notifications/{notification_id}/retry-mock-send",
    summary="실패한 모의 발송 재시도",
    response_model=MockSendResponse,
)
def retry_mock_send(
    notification_id: int,
    principal: Writer,
    db: Db,
    request: Request,
    idempotency_key: IdempotencyKey = None,
):
    """Phase 9: manual retry of a failed mock send (same confirmed body, new ledger row)."""
    key = _key(idempotency_key)
    service = _service(db, principal, request)
    detail, attempt, replayed = service.retry_mock_send(notification_id, key)
    return MockSendResponse(notification=detail, attempt=attempt, replayed=replayed)
