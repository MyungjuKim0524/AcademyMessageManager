from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.dependencies import (
    Principal,
    require_admin,
    require_admin_csrf,
    require_authenticated,
)

from .schemas import (
    AssignmentCreate,
    AssignmentDetailView,
    AssignmentPage,
    AssignmentView,
    ClassroomCreate,
    ClassroomPage,
    ClassroomStaffAssignmentPage,
    ClassroomStaffAssignmentView,
    ClassroomStudentPage,
    ClassroomStudentView,
    ClassroomUpdate,
    ClassroomView,
    EnrollmentCreate,
    EnrollmentView,
    PasswordResetCodeIssued,
    StaffCreate,
    StaffDeletion,
    StaffPage,
    StaffProfileUpdate,
    StaffStatusUpdate,
    StaffView,
    StudentContactUpdate,
    StudentContactView,
    StudentCreate,
    StudentEnrollmentSummary,
    StudentListItem,
    StudentPage,
    StudentView,
)
from .service import LearningOpsService

router = APIRouter(prefix="/api")


def _request_id(request: Request) -> str | None:
    """Request id stamped by the middleware, kept on audit rows (as the other modules do)."""
    return getattr(request.state, "request_id", None)


@router.get("/classrooms", response_model=ClassroomPage)
def list_classrooms(
    principal: Annotated[Principal, Depends(require_authenticated)],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    include_inactive: bool = False,  # administrators' class management: ended classes too
):
    rows = LearningOpsService(db).classrooms(principal, limit, offset, include_inactive)
    return ClassroomPage(
        items=[ClassroomView.model_validate(row) for row in rows], limit=limit, offset=offset
    )


@router.get("/staff", response_model=StaffPage)
def list_staff(
    _: Annotated[Principal, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    rows = LearningOpsService(db).staff_page(limit, offset)
    return StaffPage(
        items=[StaffView.model_validate(row) for row in rows], limit=limit, offset=offset
    )


@router.post("/staff", response_model=StaffView, status_code=status.HTTP_201_CREATED)
def create_staff(
    payload: StaffCreate,
    principal: Annotated[Principal, Depends(require_admin_csrf)],
    db: Annotated[Session, Depends(get_db)],
    request: Request,
):
    return LearningOpsService(db).create_staff(payload, principal, _request_id(request))


@router.get("/staff/{staff_id}", response_model=StaffView)
def get_staff(
    staff_id: int,
    _: Annotated[Principal, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    return LearningOpsService(db).staff_detail(staff_id)


@router.patch("/staff/{staff_id}", response_model=StaffView)
def update_staff_profile(
    staff_id: int,
    payload: StaffProfileUpdate,
    principal: Annotated[Principal, Depends(require_admin_csrf)],
    db: Annotated[Session, Depends(get_db)],
    request: Request,
):
    return LearningOpsService(db).update_staff_profile(
        staff_id, payload, principal, _request_id(request)
    )


@router.patch("/staff/{staff_id}/status", response_model=StaffView)
def update_staff_status(
    staff_id: int,
    payload: StaffStatusUpdate,
    principal: Annotated[Principal, Depends(require_admin_csrf)],
    db: Annotated[Session, Depends(get_db)],
    request: Request,
):
    return LearningOpsService(db).update_staff_status(
        staff_id, payload, principal, _request_id(request)
    )


@router.post("/staff/{staff_id}/password-reset-code", response_model=PasswordResetCodeIssued)
def issue_password_reset_code(
    staff_id: int,
    principal: Annotated[Principal, Depends(require_admin_csrf)],
    db: Annotated[Session, Depends(get_db)],
    request: Request,
):
    """SEC-10-B: one-time code for a member who forgot the password (shown once; deliver in
    person). The member then sets a new password at POST /api/auth/password-reset."""
    code, expires_at = LearningOpsService(db).issue_password_reset_code(
        staff_id, principal, _request_id(request)
    )
    return PasswordResetCodeIssued(staff_id=staff_id, code=code, expires_at=expires_at)


@router.delete("/staff/{staff_id}", response_model=StaffDeletion)
def delete_staff(
    staff_id: int,
    principal: Annotated[Principal, Depends(require_admin_csrf)],
    db: Annotated[Session, Depends(get_db)],
    request: Request,
):
    """Removes an account without history; an account with history is marked deleted (cannot
    log in, hidden from lists) so its name stays on the records it made."""
    request_id = getattr(request.state, "request_id", None)
    mode = LearningOpsService(db).delete_staff(staff_id, principal, request_id)
    return StaffDeletion(staff_id=staff_id, mode=mode)


@router.get("/staff/{staff_id}/assignments", response_model=AssignmentPage)
def list_staff_assignments(
    staff_id: int,
    principal: Annotated[Principal, Depends(require_authenticated)],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    rows = LearningOpsService(db).staff_assignments(staff_id, principal, limit, offset)
    return AssignmentPage(
        items=[
            AssignmentDetailView(
                id=assignment.id,
                classroom_id=assignment.classroom_id,
                staff_user_id=assignment.staff_user_id,
                assignment_role=assignment.assignment_role,
                valid_from=assignment.valid_from,
                valid_to=assignment.valid_to,
                classroom_name=classroom.name,
            )
            for assignment, classroom in rows
        ],
        limit=limit,
        offset=offset,
    )


@router.get("/classrooms/{classroom_id}/staff", response_model=ClassroomStaffAssignmentPage)
def list_classroom_staff(
    classroom_id: int,
    _: Annotated[Principal, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    rows = LearningOpsService(db).classroom_assignments(classroom_id, limit, offset)
    return ClassroomStaffAssignmentPage(
        items=[
            ClassroomStaffAssignmentView(
                id=assignment.id,
                classroom_id=assignment.classroom_id,
                staff_user_id=assignment.staff_user_id,
                assignment_role=assignment.assignment_role,
                valid_from=assignment.valid_from,
                valid_to=assignment.valid_to,
                email=staff.email,
                display_name=staff.display_name,
                staff_status=staff.status,
            )
            for assignment, staff in rows
        ],
        limit=limit,
        offset=offset,
    )


@router.delete(
    "/classrooms/{classroom_id}/assignments/{assignment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_assignment(
    classroom_id: int,
    assignment_id: int,
    principal: Annotated[Principal, Depends(require_admin_csrf)],
    db: Annotated[Session, Depends(get_db)],
    request: Request,
) -> Response:
    LearningOpsService(db).remove_assignment(
        classroom_id, assignment_id, principal, _request_id(request)
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/classrooms", response_model=ClassroomView, status_code=status.HTTP_201_CREATED)
def create_classroom(
    payload: ClassroomCreate,
    principal: Annotated[Principal, Depends(require_admin_csrf)],
    db: Annotated[Session, Depends(get_db)],
    request: Request,
):
    return LearningOpsService(db).create_classroom(payload, principal, _request_id(request))


@router.patch("/classrooms/{classroom_id}", response_model=ClassroomView)
def update_classroom(
    classroom_id: int,
    payload: ClassroomUpdate,
    principal: Annotated[Principal, Depends(require_admin_csrf)],
    db: Annotated[Session, Depends(get_db)],
    request: Request,
):
    """Rename a class or end / resume its operation (records are always kept)."""
    request_id = getattr(request.state, "request_id", None)
    return LearningOpsService(db).update_classroom(classroom_id, payload, principal, request_id)


@router.delete("/classrooms/{classroom_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_classroom(
    classroom_id: int,
    principal: Annotated[Principal, Depends(require_admin_csrf)],
    db: Annotated[Session, Depends(get_db)],
    request: Request,
) -> Response:
    """Deletes a class with no records only; otherwise 409 CLASSROOM_HAS_RECORDS."""
    request_id = getattr(request.state, "request_id", None)
    LearningOpsService(db).delete_classroom(classroom_id, principal, request_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/students", response_model=StudentPage)
def list_all_students(
    _: Annotated[Principal, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """All students with their classes — administrators only (includes guardian contact)."""
    query = " ".join(q.split()) if q else None
    rows, total = LearningOpsService(db).students_page(query, limit, offset)
    return StudentPage(
        items=[
            StudentListItem(
                id=s.id,
                name=s.name,
                school_name=s.school_name,
                parent_name=s.parent_name,
                parent_email=s.parent_email,
                enrollments=[
                    StudentEnrollmentSummary(
                        enrollment_id=e.id,
                        classroom_id=c.id,
                        classroom_name=c.name,
                        status=e.status,
                        enrolled_at=e.enrolled_at,
                        classroom_active=c.is_active,
                    )
                    for e, c in enrollments
                ],
            )
            for s, enrollments in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/students/{student_id}/contact", response_model=StudentContactView)
def get_student_contact(
    student_id: int,
    _: Annotated[Principal, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    return LearningOpsService(db).student_contact(student_id)


@router.patch("/students/{student_id}/contact", response_model=StudentContactView)
def update_student_contact(
    student_id: int,
    payload: StudentContactUpdate,
    principal: Annotated[Principal, Depends(require_admin_csrf)],
    db: Annotated[Session, Depends(get_db)],
    request: Request,
):
    request_id = getattr(request.state, "request_id", None)
    return LearningOpsService(db).update_student_contact(student_id, payload, principal, request_id)


@router.post("/students", response_model=StudentView, status_code=status.HTTP_201_CREATED)
def create_student(
    payload: StudentCreate,
    principal: Annotated[Principal, Depends(require_admin_csrf)],
    db: Annotated[Session, Depends(get_db)],
    request: Request,
):
    return LearningOpsService(db).create_student(payload, principal, _request_id(request))


@router.post(
    "/classrooms/{classroom_id}/enrollments",
    response_model=EnrollmentView,
    status_code=status.HTTP_201_CREATED,
)
def create_enrollment(
    classroom_id: int,
    payload: EnrollmentCreate,
    principal: Annotated[Principal, Depends(require_admin_csrf)],
    db: Annotated[Session, Depends(get_db)],
    request: Request,
):
    return LearningOpsService(db).enroll(classroom_id, payload, principal, _request_id(request))


@router.post(
    "/classrooms/{classroom_id}/assignments",
    response_model=AssignmentView,
    status_code=status.HTTP_201_CREATED,
)
def create_assignment(
    classroom_id: int,
    payload: AssignmentCreate,
    principal: Annotated[Principal, Depends(require_admin_csrf)],
    db: Annotated[Session, Depends(get_db)],
    request: Request,
):
    return LearningOpsService(db).assign(classroom_id, payload, principal, _request_id(request))


@router.get(
    "/classrooms/{classroom_id}/students",
    response_model=ClassroomStudentPage,
    # Guardian fields are only *set* for administrators, so for everyone else the keys are
    # absent from the response entirely (not just null).
    response_model_exclude_unset=True,
)
def list_students(
    classroom_id: int,
    principal: Annotated[Principal, Depends(require_authenticated)],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    rows = LearningOpsService(db).classroom_students(classroom_id, principal, limit, offset)
    # Guardian contact in student lists: administrators only. (Policy 2026-11-18, re-confirmed
    # 2026-11-20: a message's detail also shows the full recipient address to the assigned staff
    # who confirm and send it; message lists stay masked — see notifications/service.py.)
    show_contact = principal.role == "ADMIN"
    return ClassroomStudentPage(
        items=[
            ClassroomStudentView(
                id=s.id,
                name=s.name,
                school_name=s.school_name,
                enrollment_id=e.id,
                enrollment_status=e.status,
                enrolled_at=e.enrolled_at,
                **(
                    {"parent_name": s.parent_name, "parent_email": s.parent_email}
                    if show_contact
                    else {}
                ),
            )
            for s, e in rows
        ],
        limit=limit,
        offset=offset,
    )
