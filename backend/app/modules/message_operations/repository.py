"""Set-based reads for the obligation model: a handful of queries per request, bounded by the
requested period (max 93 days) and the classrooms the staff member may see — no N+1."""

from datetime import date

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.db.models.tables import (
    Classroom,
    Enrollment,
    Lesson,
    LessonResult,
    NotificationSendAttempt,
    NotificationTemplate,
    ParentNotification,
    Student,
)
from app.modules.academics.repository import eligible_on, held_lesson
from app.modules.learningops.repository import LearningOpsRepository


class OperationsRepository:
    def __init__(self, db: Session):
        self.db = db
        self.access = LearningOpsRepository(db)

    def classroom(self, classroom_id: int) -> Classroom | None:
        return self.db.get(Classroom, classroom_id)

    def can_access(self, classroom_id: int, user_id: int, role: str) -> bool:
        return self.access.can_access_classroom(classroom_id, user_id, role)

    def visible_classrooms(self, user_id: int, role: str) -> list[Classroom]:
        """Active classrooms: all for administrators, currently assigned ones otherwise."""
        return list(self.access.classrooms_for_principal(user_id, role, limit=10_000, offset=0))

    def lessons(self, classroom_ids: list[int], date_from: date, date_to: date) -> list[Lesson]:
        if not classroom_ids:
            return []
        return list(
            self.db.scalars(
                select(Lesson)
                .where(
                    Lesson.classroom_id.in_(classroom_ids),
                    Lesson.lesson_date >= date_from,
                    Lesson.lesson_date <= date_to,
                )
                .order_by(Lesson.lesson_date.desc(), Lesson.session_no.desc(), Lesson.id.desc())
            )
        )

    def roster(self, lesson_ids: list[int]):
        """(lesson × enrollment) pairs inside the enrollment period, or with an attendance row.

        ``eligible`` is evaluated on each lesson's own date (dated pauses, end date), so a past
        lesson keeps the same answer after a later pause or withdrawal.
        """
        if not lesson_ids:
            return []
        in_period = and_(
            Enrollment.enrolled_at <= Lesson.lesson_date,
            or_(Enrollment.ended_at.is_(None), Enrollment.ended_at >= Lesson.lesson_date),
        )
        query = (
            select(
                Lesson.id.label("lesson_id"),
                Enrollment,
                Student,
                eligible_on(Lesson.lesson_date).label("eligible"),
                LessonResult.id.label("result_id"),
            )
            .select_from(Lesson)
            .join(Enrollment, Enrollment.classroom_id == Lesson.classroom_id)
            .join(Student, Student.id == Enrollment.student_id)
            .outerjoin(
                LessonResult,
                and_(
                    LessonResult.lesson_id == Lesson.id,
                    LessonResult.enrollment_id == Enrollment.id,
                ),
            )
            .where(Lesson.id.in_(lesson_ids), or_(in_period, LessonResult.id.is_not(None)))
        )
        return self.db.execute(query).all()

    def held_lessons(self, lesson_ids: list[int], today: date) -> set[int]:
        """Ids of the given lessons that are *held* (shared ``held_lesson`` rule)."""
        if not lesson_ids:
            return set()
        return set(
            self.db.scalars(select(Lesson.id).where(Lesson.id.in_(lesson_ids), held_lesson(today)))
        )

    def notifications(self, lesson_ids: list[int], *, active_only: bool = True):
        if not lesson_ids:
            return []
        query = (
            select(ParentNotification, NotificationTemplate.name)
            .join(NotificationTemplate, NotificationTemplate.id == ParentNotification.template_id)
            .where(ParentNotification.lesson_id.in_(lesson_ids))
            .order_by(ParentNotification.id)
        )
        if active_only:
            query = query.where(ParentNotification.status != "CANCELLED")
        return self.db.execute(query).all()

    def attempts(self, notification_ids: list[int]) -> list[NotificationSendAttempt]:
        if not notification_ids:
            return []
        return list(
            self.db.scalars(
                select(NotificationSendAttempt)
                .where(NotificationSendAttempt.notification_id.in_(notification_ids))
                .order_by(NotificationSendAttempt.attempted_at, NotificationSendAttempt.id)
            )
        )
