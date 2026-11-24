from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.dependencies import Principal, require_authenticated, require_csrf

from .schemas import (
    AssessmentCreate,
    AssessmentDetail,
    AssessmentListItem,
    AssessmentPage,
    AssessmentUpdate,
    AssessmentView,
    AttendanceBulk,
    AttendanceRecord,
    AttendanceRoster,
    AttendanceRow,
    AttendanceSummary,
    ClassProgress,
    GradeBulk,
    GradeRecord,
    GradeRoster,
    GradeRow,
    GradeSummary,
    LessonCreate,
    LessonDetail,
    LessonListItem,
    LessonPage,
    LessonUpdate,
    LessonView,
    PauseCreate,
    PausePage,
    PauseResume,
    PauseView,
    RecordSaved,
    RecordUpdate,
    StudentGradeRecord,
    StudentLessonRecord,
    StudentRecords,
    TodayLesson,
)
from .service import AcademicsService

router = APIRouter(prefix="/api")

Reader = Annotated[Principal, Depends(require_authenticated)]
Writer = Annotated[Principal, Depends(require_csrf)]
Db = Annotated[Session, Depends(get_db)]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


def _service(db: Session, principal: Principal, request: Request | None = None):
    request_id = getattr(request.state, "request_id", None) if request is not None else None
    return AcademicsService(db, principal, request_id)


def _attendance_roster(service: AcademicsService, lesson_id: int, changed: int | None = None):
    lesson, rows, counts = service.attendance(lesson_id)
    return AttendanceRoster(
        lesson=LessonView.model_validate(lesson),
        summary=AttendanceSummary(**counts),
        items=[
            AttendanceRow(
                enrollment_id=row.Enrollment.id,
                student_id=row.Student.id,
                student_name=row.Student.name,
                school_name=row.Student.school_name,
                eligible=bool(row.eligible),
                record=None
                if row.LessonResult is None
                else AttendanceRecord(
                    status=row.LessonResult.attendance_status,
                    memo=row.LessonResult.memo,
                    version=row.LessonResult.version,
                    updated_at=row.LessonResult.updated_at,
                ),
            )
            for row in rows
        ],
        changed=changed,
    )


def _grade_roster(service: AcademicsService, assessment_id: int, changed: int | None = None):
    assessment, rows, counts = service.grades(assessment_id)
    return GradeRoster(
        assessment=AssessmentView.model_validate(assessment),
        summary=GradeSummary(**counts),
        items=[
            GradeRow(
                enrollment_id=row.Enrollment.id,
                student_id=row.Student.id,
                student_name=row.Student.name,
                school_name=row.Student.school_name,
                eligible=bool(row.eligible),
                record=None
                if row.AssessmentResult is None
                else GradeRecord(
                    result_status=row.AssessmentResult.result_status,
                    score=row.AssessmentResult.score,
                    memo=row.AssessmentResult.memo,
                    version=row.AssessmentResult.version,
                    updated_at=row.AssessmentResult.updated_at,
                ),
            )
            for row in rows
        ],
        changed=changed,
    )


# ---------------------------------------------------------------- lessons
@router.get(
    "/classrooms/{classroom_id}/lessons", summary="수업 회차 목록", response_model=LessonPage
)
def list_lessons(
    classroom_id: int,
    principal: Reader,
    db: Db,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
):
    rows = _service(db, principal).lessons(classroom_id, date_from, date_to, limit, offset)
    return LessonPage(
        items=[
            LessonListItem(
                **LessonView.model_validate(lesson).model_dump(), attendance_recorded=recorded
            )
            for lesson, recorded in rows
        ],
        limit=limit,
        offset=offset,
    )


@router.post(
    "/classrooms/{classroom_id}/lessons",
    summary="수업 회차 생성",
    response_model=LessonView,
    status_code=status.HTTP_201_CREATED,
)
def create_lesson(
    classroom_id: int, payload: LessonCreate, principal: Writer, db: Db, request: Request
):
    return _service(db, principal, request).create_lesson(classroom_id, payload)


@router.post(
    "/classrooms/{classroom_id}/lessons/today",
    summary="오늘 수업 시작(없으면 생성)",
    response_model=TodayLesson,
)
def start_today_lesson(classroom_id: int, principal: Writer, db: Db, request: Request):
    lesson, created = _service(db, principal, request).start_today_lesson(classroom_id)
    return TodayLesson(lesson=LessonView.model_validate(lesson), created=created)


@router.get("/lessons/{lesson_id}", summary="수업 회차 상세", response_model=LessonDetail)
def get_lesson(lesson_id: int, principal: Reader, db: Db):
    lesson, counts = _service(db, principal).lesson_detail(lesson_id)
    return LessonDetail(
        **LessonView.model_validate(lesson).model_dump(),
        attendance=AttendanceSummary(**counts),
    )


@router.patch("/lessons/{lesson_id}", summary="수업 회차 수정", response_model=LessonView)
def update_lesson(
    lesson_id: int, payload: LessonUpdate, principal: Writer, db: Db, request: Request
):
    return _service(db, principal, request).update_lesson(lesson_id, payload)


# ------------------------------------------------------------- attendance
@router.get("/lessons/{lesson_id}/attendance", summary="출결 조회", response_model=AttendanceRoster)
def get_attendance(lesson_id: int, principal: Reader, db: Db):
    return _attendance_roster(_service(db, principal), lesson_id)


@router.put("/lessons/{lesson_id}/attendance", summary="출결 저장", response_model=AttendanceRoster)
def save_attendance(
    lesson_id: int, payload: AttendanceBulk, principal: Writer, db: Db, request: Request
):
    service = _service(db, principal, request)
    changed = service.save_attendance(lesson_id, payload)
    return _attendance_roster(service, lesson_id, changed)


# ------------------------------------------------------------ assessments
@router.get(
    "/classrooms/{classroom_id}/assessments", summary="평가 목록", response_model=AssessmentPage
)
def list_assessments(
    classroom_id: int, principal: Reader, db: Db, limit: Limit = 50, offset: Offset = 0
):
    rows = _service(db, principal).assessments(classroom_id, limit, offset)
    return AssessmentPage(
        items=[
            AssessmentListItem(
                **AssessmentView.model_validate(assessment).model_dump(),
                scored=scored,
                not_taken=not_taken,
            )
            for assessment, scored, not_taken in rows
        ],
        limit=limit,
        offset=offset,
    )


@router.post(
    "/classrooms/{classroom_id}/assessments",
    summary="평가 생성",
    response_model=AssessmentView,
    status_code=status.HTTP_201_CREATED,
)
def create_assessment(
    classroom_id: int, payload: AssessmentCreate, principal: Writer, db: Db, request: Request
):
    return _service(db, principal, request).create_assessment(classroom_id, payload)


@router.get("/assessments/{assessment_id}", summary="평가 상세", response_model=AssessmentDetail)
def get_assessment(assessment_id: int, principal: Reader, db: Db):
    assessment, counts = _service(db, principal).assessment_detail(assessment_id)
    return AssessmentDetail(
        **AssessmentView.model_validate(assessment).model_dump(),
        grades=GradeSummary(**counts),
    )


@router.patch("/assessments/{assessment_id}", summary="평가 수정", response_model=AssessmentView)
def update_assessment(
    assessment_id: int, payload: AssessmentUpdate, principal: Writer, db: Db, request: Request
):
    return _service(db, principal, request).update_assessment(assessment_id, payload)


@router.get("/assessments/{assessment_id}/grades", summary="점수 조회", response_model=GradeRoster)
def get_grades(assessment_id: int, principal: Reader, db: Db):
    return _grade_roster(_service(db, principal), assessment_id)


@router.put("/assessments/{assessment_id}/grades", summary="점수 저장", response_model=GradeRoster)
def save_grades(
    assessment_id: int, payload: GradeBulk, principal: Writer, db: Db, request: Request
):
    service = _service(db, principal, request)
    changed = service.save_grades(assessment_id, payload)
    return _grade_roster(service, assessment_id, changed)


# ------------------------------------------------ class progress grid (8.1)
@router.get(
    "/classrooms/{classroom_id}/progress",
    summary="진도표(기간별 출결·과제·점수)",
    response_model=ClassProgress,
)
def class_progress(classroom_id: int, date_from: date, date_to: date, principal: Reader, db: Db):
    return ClassProgress(**_service(db, principal).progress(classroom_id, date_from, date_to))


@router.put(
    "/lessons/{lesson_id}/records/{enrollment_id}",
    summary="학생 한 명의 수업 기록 수정",
    response_model=RecordSaved,
)
def update_record(
    lesson_id: int,
    enrollment_id: int,
    payload: RecordUpdate,
    principal: Writer,
    db: Db,
    request: Request,
):
    changed = _service(db, principal, request).update_record(lesson_id, enrollment_id, payload)
    return RecordSaved(changed=changed)


# -------------------------------------------------------- student history
@router.get(
    "/classrooms/{classroom_id}/students/{student_id}/records",
    summary="학생별 수업·평가 기록",
    response_model=StudentRecords,
)
def student_records(
    classroom_id: int,
    student_id: int,
    principal: Reader,
    db: Db,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
):
    enrollment, student, lessons, assessments = _service(db, principal).student_records(
        classroom_id, student_id, limit
    )
    return StudentRecords(
        student_id=student.id,
        student_name=student.name,
        enrollment_id=enrollment.id,
        enrollment_status=enrollment.status,
        enrolled_at=enrollment.enrolled_at,
        ended_at=enrollment.ended_at,
        lessons=[
            StudentLessonRecord(
                lesson_id=lesson.id,
                lesson_date=lesson.lesson_date,
                session_no=lesson.session_no,
                exam_round=lesson.exam_round,
                topic=lesson.topic,
                lesson_status=lesson.status,
                attendance_status=None if result is None else result.attendance_status,
                prework_grade=None if result is None else result.prework_grade,
                weekly_grade=None if result is None else result.weekly_assignment_grade,
                memo=None if result is None else result.memo,
                updated_at=None if result is None else result.updated_at,
            )
            for lesson, result in lessons
        ],
        assessments=[
            StudentGradeRecord(
                assessment_id=assessment.id,
                title=assessment.title,
                assessment_date=assessment.assessment_date,
                max_score=assessment.max_score,
                result_status=None if result is None else result.result_status,
                score=None if result is None else result.score,
                memo=None if result is None else result.memo,
                updated_at=None if result is None else result.updated_at,
            )
            for assessment, result in assessments
        ],
    )


# --------------------------------------------------- enrollment pauses (7.1)
@router.get(
    "/classrooms/{classroom_id}/enrollments/{enrollment_id}/pauses",
    summary="휴원 이력",
    response_model=PausePage,
)
def list_pauses(classroom_id: int, enrollment_id: int, principal: Reader, db: Db):
    enrollment, pauses = _service(db, principal).pauses(classroom_id, enrollment_id)
    return PausePage(
        enrollment_id=enrollment.id,
        enrollment_status=enrollment.status,
        items=[PauseView.model_validate(pause) for pause in pauses],
    )


@router.post(
    "/classrooms/{classroom_id}/enrollments/{enrollment_id}/pauses",
    summary="휴원 처리",
    response_model=PauseView,
    status_code=status.HTTP_201_CREATED,
)
def create_pause(
    classroom_id: int,
    enrollment_id: int,
    payload: PauseCreate,
    principal: Writer,
    db: Db,
    request: Request,
):
    return _service(db, principal, request).create_pause(classroom_id, enrollment_id, payload)


@router.post(
    "/classrooms/{classroom_id}/enrollments/{enrollment_id}/pauses/{pause_id}/resume",
    summary="휴원 학생 복귀",
    response_model=PauseView,
)
def resume_pause(
    classroom_id: int,
    enrollment_id: int,
    pause_id: int,
    payload: PauseResume,
    principal: Writer,
    db: Db,
    request: Request,
):
    return _service(db, principal, request).resume(classroom_id, enrollment_id, pause_id, payload)
