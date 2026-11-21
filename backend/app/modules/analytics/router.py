"""Read-only analytics endpoints (GET only — no CSRF needed, nothing is written).

Every endpoint passes the classroom access check of the 수업·출결·성적 screens; student and
assessment ids are resolved inside that classroom, so changing an id cannot reach another class.
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.dependencies import Principal, require_authenticated
from app.security import require_local_db_api

from .schemas import (
    AssessmentDetail,
    AttendanceAnalytics,
    GradeAnalytics,
    StudentAttendanceHistory,
    StudentGradeTrend,
    StudentReport,
    Watchlist,
)
from .service import AnalyticsService

router = APIRouter(prefix="/api/analytics", dependencies=[Depends(require_local_db_api)])

Reader = Annotated[Principal, Depends(require_authenticated)]
Db = Annotated[Session, Depends(get_db)]
ClassroomId = Annotated[int, Query(ge=1)]
From = Annotated[date, Query()]
To = Annotated[date, Query()]


@router.get("/attendance", response_model=AttendanceAnalytics)
def attendance(principal: Reader, db: Db, classroom_id: ClassroomId, date_from: From, date_to: To):
    return AnalyticsService(db, principal).attendance(classroom_id, date_from, date_to)


@router.get("/attendance/students/{student_id}", response_model=StudentAttendanceHistory)
def student_attendance(
    student_id: int,
    principal: Reader,
    db: Db,
    classroom_id: ClassroomId,
    date_from: From,
    date_to: To,
):
    return AnalyticsService(db, principal).student_attendance(
        classroom_id, student_id, date_from, date_to
    )


@router.get("/grades", response_model=GradeAnalytics)
def grades(principal: Reader, db: Db, classroom_id: ClassroomId, date_from: From, date_to: To):
    return AnalyticsService(db, principal).grades(classroom_id, date_from, date_to)


@router.get("/grades/assessments/{assessment_id}", response_model=AssessmentDetail)
def assessment_detail(assessment_id: int, principal: Reader, db: Db):
    return AnalyticsService(db, principal).assessment_detail(assessment_id)


@router.get("/grades/students/{student_id}", response_model=StudentGradeTrend)
def student_grades(
    student_id: int,
    principal: Reader,
    db: Db,
    classroom_id: ClassroomId,
    date_from: From,
    date_to: To,
):
    return AnalyticsService(db, principal).student_grades(
        classroom_id, student_id, date_from, date_to
    )


@router.get("/watchlist", response_model=Watchlist)
def watchlist(principal: Reader, db: Db, classroom_id: ClassroomId):
    """관심 필요 학생 of the last 4 weeks, each with the reasons (rules in the response)."""
    return AnalyticsService(db, principal).watchlist(classroom_id)


@router.get("/students/{student_id}/report", response_model=StudentReport)
def student_report(
    student_id: int,
    principal: Reader,
    db: Db,
    classroom_id: ClassroomId,
    date_from: From,
    date_to: To,
):
    return AnalyticsService(db, principal).student_report(
        classroom_id, student_id, date_from, date_to
    )
