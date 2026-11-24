import logging
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import get_settings, production_problems
from app.db.session import get_db
from app.domain import compose_message, validate_preview
from app.errors import ApiError, CompatibilityError
from app.middleware import (
    INTERNAL_MESSAGE,
    CompatibilityMiddleware,
    classify_database_error,
    log_unhandled,
)
from app.models import HealthResponse, MessagePreviewRequest, MessagePreviewResponse
from app.modules.academics.router import router as academics_router
from app.modules.analytics.router import router as analytics_router
from app.modules.auth.dependencies import Principal, require_authenticated, require_classroom_access
from app.modules.auth.router import router as auth_router
from app.modules.learningops.router import router as learningops_router
from app.modules.lesson_upload.router import router as lesson_upload_router
from app.modules.message_operations.router import router as message_operations_router
from app.modules.notifications.router import router as notifications_router

settings = get_settings()
if settings.db_mode == "production":
    # SEC-04 (Phase 11-4-B): a deployed process refuses to start with unsafe settings instead of
    # running with them. The message lists setting names only, never their values.
    problems = production_problems(settings)
    if problems:
        raise RuntimeError("Unsafe production configuration: " + "; ".join(problems))
logging.basicConfig(
    level=getattr(logging, settings.log_level, logging.INFO),
    format="%(asctime)s level=%(levelname)s logger=%(name)s message=%(message)s",
)
# SEC-08: the API description (/docs, /redoc, /openapi.json) is published only when
# ACADEMY_API_DOCS=1 (the local start script sets it); a deployment leaves it off.
docs = settings.api_docs_enabled
app = FastAPI(
    title="Academy LearningOps API",
    version="2.0.0",
    docs_url="/docs" if docs else None,
    redoc_url="/redoc" if docs else None,
    openapi_url="/openapi.json" if docs else None,
)
app.add_middleware(CompatibilityMiddleware, settings=settings)
app.include_router(auth_router)
app.include_router(learningops_router)
app.include_router(academics_router)
app.include_router(notifications_router)
app.include_router(lesson_upload_router)
app.include_router(message_operations_router)
app.include_router(analytics_router)


def error_response(status: int, code: str, message: str, fields: list[dict] | None = None):
    payload = ApiError(code=code, message=message, fields=fields or [])
    return JSONResponse(status_code=status, content=payload.model_dump())


@app.exception_handler(CompatibilityError)
async def compatibility_error_handler(_request: Request, exc: CompatibilityError):
    return error_response(
        exc.status_code,
        exc.code,
        exc.message,
        [field.model_dump() for field in exc.fields],
    )


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(_request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:  # unknown path, or /docs·/openapi.json while they are off
        return error_response(404, "NOT_FOUND", "요청한 기능을 사용할 수 없습니다.")
    if exc.status_code == 405:
        return error_response(405, "METHOD_NOT_ALLOWED", "허용되지 않은 HTTP 메서드입니다.")
    return error_response(exc.status_code, "INTERNAL_ERROR", "요청 처리 중 오류가 발생했습니다.")


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(_request: Request, _exc: RequestValidationError):
    return error_response(400, "INVALID_JSON", "올바른 JSON 요청이 아닙니다.")


@app.exception_handler(Exception)
async def internal_error_handler(request: Request, exc: Exception):
    # Request errors are handled (and logged without their text) in CompatibilityMiddleware;
    # this covers anything raised outside it, with the same redacted log line (SEC-07).
    request_id = request.scope.get("state", {}).get("request_id")
    log_unhandled(exc, request_id, request.method, request.url.path)
    classified = classify_database_error(exc)
    status, code, message = classified or (500, "INTERNAL_ERROR", INTERNAL_MESSAGE)
    return error_response(status, code, message)


@app.get(
    "/api/health",
    summary="서버 상태 확인",
    response_model=HealthResponse,
)
async def health() -> HealthResponse:
    return HealthResponse(status="UP")


@app.post(
    "/api/messages/preview",
    summary="메시지 문구 미리보기(Java 시절 계약 호환)",
    response_model=MessagePreviewResponse,
)
async def preview_message(
    payload: MessagePreviewRequest,
    principal: Annotated[Principal, Depends(require_authenticated)],
    db: Annotated[Session, Depends(get_db)],
) -> MessagePreviewResponse:
    values, fields = validate_preview(payload)
    if fields:
        raise CompatibilityError(400, "VALIDATION_ERROR", "입력값을 확인해주세요.", tuple(fields))
    assert values is not None
    require_classroom_access(db, principal, values.class_name, values.class_type.value)
    return MessagePreviewResponse(message=compose_message(values))
