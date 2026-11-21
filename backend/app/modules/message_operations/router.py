from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.dependencies import Principal, require_authenticated

from .schemas import (
    ClassroomCounts,
    ObligationDetail,
    ObligationPage,
    ObligationStatus,
    Summary,
    TodoList,
)
from .service import OperationsService

router = APIRouter(prefix="/api/message-operations")

Reader = Annotated[Principal, Depends(require_authenticated)]
Db = Annotated[Session, Depends(get_db)]


def _service(db: Session, principal: Principal, request: Request) -> OperationsService:
    return OperationsService(db, principal, getattr(request.state, "request_id", None))


@router.get("/summary", response_model=Summary)
def summary(principal: Reader, db: Db, request: Request, date_from: date, date_to: date):
    """Totals and per-classroom counts over the classrooms this staff member may see."""
    return _service(db, principal, request).summary(date_from, date_to)


@router.get("/todo", response_model=TodoList)
def todo(principal: Reader, db: Db, request: Request):
    """Dashboard: unfinished notices per class lesson (last 3 months), most urgent first."""
    return _service(db, principal, request).todo()


@router.get("/classrooms/{classroom_id}", response_model=ClassroomCounts)
def classroom_summary(
    classroom_id: int, principal: Reader, db: Db, request: Request, date_from: date, date_to: date
):
    return _service(db, principal, request).classroom_summary(classroom_id, date_from, date_to)


@router.get("/obligations", response_model=ObligationPage)
def obligations(
    principal: Reader,
    db: Db,
    request: Request,
    classroom_id: Annotated[int, Query(gt=0)],
    date_from: date,
    date_to: date,
    status: ObligationStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    items, total = _service(db, principal, request).obligations(
        classroom_id, date_from, date_to, status, limit, offset
    )
    return ObligationPage(items=items, total=total, limit=limit, offset=offset)


@router.get("/obligations/{lesson_id}/{enrollment_id}", response_model=ObligationDetail)
def obligation_detail(
    lesson_id: int, enrollment_id: int, principal: Reader, db: Db, request: Request
):
    return _service(db, principal, request).obligation_detail(lesson_id, enrollment_id)
