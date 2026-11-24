import json
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import TypeAdapter, ValidationError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.errors import CompatibilityError
from app.modules.auth.dependencies import Principal, require_authenticated, require_csrf
from app.security import require_local_db_api
from app.uploads import MAX_FILE_BYTES

from .schemas import Decision, SheetList, UploadPreview, UploadResult
from .service import LessonUploadService
from .workbook import parse_workbook

router = APIRouter(prefix="/api/lesson-uploads", dependencies=[Depends(require_local_db_api)])
DECISIONS = TypeAdapter(dict[str, Decision])


async def _read(file: UploadFile) -> bytes:
    content = await file.read(MAX_FILE_BYTES + 1)
    if len(content) > MAX_FILE_BYTES:
        raise CompatibilityError(413, "FILE_TOO_LARGE", "파일이 너무 큽니다.")
    if not content:
        raise CompatibilityError(400, "FILE_REQUIRED", "엑셀 파일을 선택해주세요.")
    return content


def _service(db: Session, principal: Principal, request: Request):
    return LessonUploadService(db, principal, getattr(request.state, "request_id", None))


# Sheets (time slots) to check and save. Omitted = every sheet (callers that do not choose).
Sheets = Annotated[list[str] | None, Form()]


@router.post("/sheets", summary="엑셀 파일의 시트(시간대) 목록", response_model=SheetList)
async def list_sheets(
    principal: Annotated[Principal, Depends(require_authenticated)],
    file: Annotated[UploadFile, File()],
):
    """The workbook's time-slot sheets, so the user can choose what to upload. Reads no data."""
    blocks = await run_in_threadpool(parse_workbook, await _read(file))
    return SheetList(sheets=LessonUploadService.sheet_summaries(blocks))


@router.post("/preview", summary="업로드 미리보기(저장 안 함)", response_model=UploadPreview)
async def preview_upload(
    request: Request,
    principal: Annotated[Principal, Depends(require_authenticated)],
    db: Annotated[Session, Depends(get_db)],
    file: Annotated[UploadFile, File()],
    lesson_date: Annotated[date, Form()],
    sheets: Sheets = None,
):
    """Parse and match only; nothing is written."""
    service = _service(db, principal, request)
    parsed, views, blocking = await run_in_threadpool(
        service.analyse, await _read(file), lesson_date, sheets
    )
    summaries = service.sheet_summaries(parsed)
    return UploadPreview(
        lesson_date=lesson_date,
        blocks=service.public_view(views),
        can_confirm=not blocking,
        blocking=blocking,
        sheets=summaries,
        selected_sheets=[s["name"] for s in summaries if sheets is None or s["name"] in sheets],
    )


@router.post("/confirm", summary="업로드 확정·저장", response_model=UploadResult)
async def confirm_upload(
    request: Request,
    principal: Annotated[Principal, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
    file: Annotated[UploadFile, File()],
    lesson_date: Annotated[date, Form()],
    decisions: Annotated[str, Form()] = "{}",
    sheets: Sheets = None,
):
    try:
        parsed = DECISIONS.validate_python(json.loads(decisions))
    except (ValueError, ValidationError):
        raise CompatibilityError(
            400, "INVALID_DECISIONS", "학생 처리 선택값이 올바르지 않습니다."
        ) from None
    # Parsing and saving are CPU / DB bound: run them off the event loop (SEC-06) so one large
    # workbook does not stall every other request.
    summary = await run_in_threadpool(
        _service(db, principal, request).confirm, await _read(file), lesson_date, parsed, sheets
    )
    return UploadResult(lesson_date=lesson_date, **summary)
