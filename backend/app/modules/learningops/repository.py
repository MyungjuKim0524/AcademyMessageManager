from datetime import date

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.db.models.tables import (
    AuditLog,
    Classroom,
    ClassroomStaffAssignment,
    Enrollment,
    NotificationSendAttempt,
    NotificationTemplate,
    ParentNotification,
    StaffUser,
    Student,
)


class LearningOpsRepository:
    def __init__(self, db: Session):
        self.db = db

    def classroom(self, row_id: int):
        return self.db.get(Classroom, row_id)

    def student(self, row_id: int):
        return self.db.get(Student, row_id)

    def staff(self, row_id: int):
        return self.db.get(StaffUser, row_id)

    def staff_page(self, limit: int, offset: int):
        """Staff list without deleted accounts (they stay in the table only for history)."""
        return self.db.scalars(
            select(StaffUser)
            .where(StaffUser.status != "DELETED")
            .order_by(StaffUser.id)
            .limit(limit)
            .offset(offset)
        ).all()

    def staff_has_history(self, staff_id: int) -> bool:
        """Whether any record names this account as the one who acted (log-in, change, message
        created / confirmed / sent, template). Such an account is never removed for real."""
        checks = (
            select(AuditLog.id).where(AuditLog.actor_staff_user_id == staff_id),
            select(NotificationTemplate.id).where(
                NotificationTemplate.created_by_staff_user_id == staff_id
            ),
            select(ParentNotification.id).where(
                or_(
                    ParentNotification.created_by_staff_user_id == staff_id,
                    ParentNotification.updated_by_staff_user_id == staff_id,
                    ParentNotification.approved_by_staff_user_id == staff_id,
                )
            ),
            select(NotificationSendAttempt.id).where(
                NotificationSendAttempt.requested_by_staff_user_id == staff_id
            ),
        )
        return any(self.db.scalar(select(query.exists())) for query in checks)

    def staff_by_email(self, email: str):
        return self.db.scalar(select(StaffUser).where(StaffUser.email.ilike(email)))

    def active_admins_for_update(self):
        return self.db.scalars(
            select(StaffUser)
            .where(StaffUser.role == "ADMIN", StaffUser.status == "ACTIVE")
            .order_by(StaffUser.id)
            .with_for_update()
        ).all()

    def revoke_sessions(self, staff_user_id: int, revoked_at):
        from app.db.models.tables import AuthSession

        sessions = self.db.scalars(
            select(AuthSession).where(
                AuthSession.staff_user_id == staff_user_id,
                AuthSession.revoked_at.is_(None),
            )
        ).all()
        for session in sessions:
            session.revoked_at = revoked_at
        return len(sessions)

    def staff_assignments(self, staff_user_id: int, limit: int, offset: int):
        return self.db.execute(
            select(ClassroomStaffAssignment, Classroom)
            .join(Classroom, Classroom.id == ClassroomStaffAssignment.classroom_id)
            .where(ClassroomStaffAssignment.staff_user_id == staff_user_id)
            .order_by(ClassroomStaffAssignment.id)
            .limit(limit)
            .offset(offset)
        ).all()

    def classroom_assignments(self, classroom_id: int, limit: int, offset: int):
        return self.db.execute(
            select(ClassroomStaffAssignment, StaffUser)
            .join(StaffUser, StaffUser.id == ClassroomStaffAssignment.staff_user_id)
            .where(
                ClassroomStaffAssignment.classroom_id == classroom_id,
                StaffUser.status != "DELETED",
            )
            .order_by(ClassroomStaffAssignment.id)
            .limit(limit)
            .offset(offset)
        ).all()

    def assignment(self, assignment_id: int):
        return self.db.get(ClassroomStaffAssignment, assignment_id)

    def all_classrooms(self, limit: int, offset: int):
        """Every class including ended ones (administrators' class management)."""
        query = select(Classroom).order_by(Classroom.is_active.desc(), Classroom.id)
        return self.db.scalars(query.limit(limit).offset(offset)).all()

    def classrooms_for_principal(self, user_id: int, role: str, limit: int, offset: int):
        query = select(Classroom).where(Classroom.is_active.is_(True))
        if role != "ADMIN":
            today = date.today()
            query = query.join(
                ClassroomStaffAssignment,
                and_(
                    ClassroomStaffAssignment.classroom_id == Classroom.id,
                    ClassroomStaffAssignment.staff_user_id == user_id,
                    ClassroomStaffAssignment.assignment_role == role,
                    ClassroomStaffAssignment.valid_from <= today,
                    or_(
                        ClassroomStaffAssignment.valid_to.is_(None),
                        ClassroomStaffAssignment.valid_to >= today,
                    ),
                ),
            )
        return self.db.scalars(query.order_by(Classroom.id).limit(limit).offset(offset)).all()

    def can_access_classroom(self, classroom_id: int, user_id: int, role: str) -> bool:
        if role == "ADMIN":
            return True
        today = date.today()
        return (
            self.db.scalar(
                select(ClassroomStaffAssignment.id).where(
                    ClassroomStaffAssignment.classroom_id == classroom_id,
                    ClassroomStaffAssignment.staff_user_id == user_id,
                    ClassroomStaffAssignment.assignment_role == role,
                    ClassroomStaffAssignment.valid_from <= today,
                    or_(
                        ClassroomStaffAssignment.valid_to.is_(None),
                        ClassroomStaffAssignment.valid_to >= today,
                    ),
                )
            )
            is not None
        )

    def students_page(self, query: str | None, limit: int, offset: int):
        """All students, optionally filtered by a name substring (LIKE wildcards are literal)."""
        condition = []
        if query:
            escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            condition.append(Student.name.ilike(f"%{escaped}%", escape="\\"))
        total = self.db.scalar(select(func.count()).select_from(Student).where(*condition))
        rows = self.db.scalars(
            select(Student)
            .where(*condition)
            .order_by(Student.name, Student.id)
            .limit(limit)
            .offset(offset)
        ).all()
        return rows, total or 0

    def enrollments_for_students(self, student_ids: list[int]):
        if not student_ids:
            return []
        return self.db.execute(
            select(Enrollment, Classroom)
            .join(Classroom, Classroom.id == Enrollment.classroom_id)
            .where(Enrollment.student_id.in_(student_ids))
            .order_by(Classroom.name, Enrollment.id)
        ).all()

    def students_for_classroom(self, classroom_id: int, limit: int, offset: int):
        return self.db.execute(
            select(Student, Enrollment)
            .join(Enrollment, Enrollment.student_id == Student.id)
            .where(Enrollment.classroom_id == classroom_id)
            .order_by(Student.id)
            .limit(limit)
            .offset(offset)
        ).all()
