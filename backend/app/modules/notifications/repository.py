from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.db.models.tables import (
    Assessment,
    AssessmentResult,
    AuditLog,
    Classroom,
    Enrollment,
    Lesson,
    LessonResult,
    NotificationSendAttempt,
    NotificationTemplate,
    ParentNotification,
    StaffUser,
    Student,
)
from app.modules.academics.repository import eligible_on
from app.modules.learningops.repository import LearningOpsRepository


class NotificationRepository:
    def __init__(self, db: Session):
        self.db = db
        self.access = LearningOpsRepository(db)

    def _one(self, query):
        return self.db.scalar(query.execution_options(populate_existing=True))

    # ------------------------------------------------------- access / scope
    def classroom(self, classroom_id: int) -> Classroom | None:
        return self.db.get(Classroom, classroom_id)

    def can_access(self, classroom_id: int, user_id: int, role: str) -> bool:
        return self.access.can_access_classroom(classroom_id, user_id, role)

    def lesson(self, lesson_id: int) -> Lesson | None:
        return self._one(select(Lesson).where(Lesson.id == lesson_id))

    # ------------------------------------------------------------ templates
    def templates(self, active_only: bool):
        query = select(NotificationTemplate).order_by(NotificationTemplate.name)
        if active_only:
            query = query.where(NotificationTemplate.is_active.is_(True))
        return list(self.db.scalars(query.execution_options(populate_existing=True)))

    def template(self, template_id: int, *, lock: bool = False) -> NotificationTemplate | None:
        query = select(NotificationTemplate).where(NotificationTemplate.id == template_id)
        return self._one(query.with_for_update() if lock else query)

    # -------------------------------------------------- generation sources
    def roster(self, lesson: Lesson, enrollment_ids: list[int] | None):
        """Students for the lesson with their attendance row and eligibility, one query."""
        eligible = eligible_on(lesson.lesson_date)
        query = (
            select(Enrollment, Student, LessonResult, eligible.label("eligible"))
            .join(Student, Student.id == Enrollment.student_id)
            .outerjoin(
                LessonResult,
                and_(
                    LessonResult.lesson_id == lesson.id,
                    LessonResult.enrollment_id == Enrollment.id,
                ),
            )
            .where(Enrollment.classroom_id == lesson.classroom_id)
            .order_by(Student.name, Student.id)
        )
        if enrollment_ids is None:
            query = query.where(or_(eligible, LessonResult.id.is_not(None)))
        else:
            query = query.where(Enrollment.id.in_(enrollment_ids))
        return self.db.execute(query.execution_options(populate_existing=True)).all()

    def linked_grades(self, lesson: Lesson, enrollment_ids: list[int]):
        # populate_existing like lesson()/roster(): the source check must read the stored values,
        # never attributes of an Assessment / result object still held by this session's identity
        # map from an earlier message of the same batch (Phase 11-3-B, INT-02).
        assessments = list(
            self.db.scalars(
                select(Assessment)
                .where(Assessment.lesson_id == lesson.id)
                .order_by(Assessment.assessment_date, Assessment.id)
                .execution_options(populate_existing=True)
            )
        )
        results = {}
        if assessments and enrollment_ids:
            for row in self.db.scalars(
                select(AssessmentResult)
                .where(
                    AssessmentResult.assessment_id.in_([a.id for a in assessments]),
                    AssessmentResult.enrollment_id.in_(enrollment_ids),
                )
                .execution_options(populate_existing=True)
            ):
                results[(row.assessment_id, row.enrollment_id)] = row
        return assessments, results

    def active_notifications(self, lesson_id: int, template_id: int, enrollment_ids: list[int]):
        rows = self.db.execute(
            select(ParentNotification.enrollment_id, ParentNotification.id).where(
                ParentNotification.lesson_id == lesson_id,
                ParentNotification.template_id == template_id,
                ParentNotification.enrollment_id.in_(enrollment_ids),
                ParentNotification.status != "CANCELLED",
            )
        )
        return dict(rows.all())

    def lock_sources(self, row: ParentNotification) -> None:
        """Phase 11-3-B (INT-01): lock what a message is rendered from, in one fixed order,
        before its source is checked for a (re)send. Held until the send commits, so a source
        write either commits before the check (then seen and refused) or waits until after the
        send. Every lock re-reads the row (populate_existing), so nothing cached is used.

        Which writer each lock stops (all writers lock these parents before writing children):
        * classroom FOR SHARE   — class rename (FOR UPDATE)
        * lesson FOR UPDATE     — lesson edit (FOR UPDATE); attendance / record edits (FOR SHARE
          first); new attendance rows and newly linked tests (their FK check takes KEY SHARE on
          the lesson, which FOR UPDATE — unlike FOR NO KEY UPDATE — also blocks); uploads
        * linked tests FOR UPDATE, by id — test edits (FOR UPDATE); score saves (FOR SHARE first);
          new score rows (FK KEY SHARE on the test)
        * enrollment FOR SHARE  — pause / resume (FOR UPDATE)
        * student FOR SHARE     — guardian contact edit (FOR UPDATE)
        Order classroom -> lesson -> tests -> enrollment -> student matches the upload's
        lesson -> tests -> enrollment, and no writer takes a message row lock, so no cycle."""

        def lock(query):
            return self.db.execute(query.execution_options(populate_existing=True)).scalars().all()

        lock(select(Classroom).where(Classroom.id == row.classroom_id).with_for_update(read=True))
        lock(select(Lesson).where(Lesson.id == row.lesson_id).with_for_update())
        lock(
            select(Assessment)
            .where(Assessment.lesson_id == row.lesson_id)
            .order_by(Assessment.id)
            .with_for_update()
        )
        [enrollment] = lock(
            select(Enrollment).where(Enrollment.id == row.enrollment_id).with_for_update(read=True)
        )
        lock(select(Student).where(Student.id == enrollment.student_id).with_for_update(read=True))

    # -------------------------------------------------------- notifications
    def notification(self, notification_id: int, *, lock: bool = False):
        query = select(ParentNotification).where(ParentNotification.id == notification_id)
        return self._one(query.with_for_update() if lock else query)

    def _listing(self):
        return (
            select(ParentNotification, Lesson, Student, NotificationTemplate)
            .join(Lesson, Lesson.id == ParentNotification.lesson_id)
            .join(Enrollment, Enrollment.id == ParentNotification.enrollment_id)
            .join(Student, Student.id == Enrollment.student_id)
            .join(NotificationTemplate, NotificationTemplate.id == ParentNotification.template_id)
        )

    def notification_rows(self, classroom_id, lesson_id, status, limit, offset):
        query = self._listing().where(ParentNotification.classroom_id == classroom_id)
        if lesson_id is not None:
            query = query.where(ParentNotification.lesson_id == lesson_id)
        if status is not None:
            query = query.where(ParentNotification.status == status)
        query = query.order_by(Lesson.lesson_date.desc(), Student.name, ParentNotification.id)
        return self.db.execute(
            query.limit(limit).offset(offset).execution_options(populate_existing=True)
        ).all()

    def notification_rows_by_ids(self, lesson_id: int, ids: list[int]):
        """Messages of one lesson among ``ids`` (a class batch); others are simply not returned."""
        if not ids:
            return []
        return self.db.execute(
            self._listing().where(
                ParentNotification.lesson_id == lesson_id, ParentNotification.id.in_(ids)
            )
        ).all()

    def notification_row(self, notification_id: int):
        return self.db.execute(
            self._listing()
            .where(ParentNotification.id == notification_id)
            .execution_options(populate_existing=True)
        ).one_or_none()

    def staff_names(self, ids) -> dict[int, str]:
        wanted = {i for i in ids if i is not None}
        if not wanted:
            return {}
        rows = self.db.execute(
            select(StaffUser.id, StaffUser.display_name, StaffUser.email, StaffUser.status).where(
                StaffUser.id.in_(wanted)
            )
        )
        # A deleted account keeps its name in history, marked so it is not mistaken for a
        # current staff member (staff deletion option B, 2026-11-20).
        return {
            row.id: (row.display_name or row.email)
            + (" (삭제된 직원)" if row.status == "DELETED" else "")
            for row in rows
        }

    def attempts(self, notification_id: int):
        return list(
            self.db.scalars(
                select(NotificationSendAttempt)
                .where(NotificationSendAttempt.notification_id == notification_id)
                .order_by(NotificationSendAttempt.attempted_at, NotificationSendAttempt.id)
            )
        )

    def attempt_count(self, notification_id: int) -> int:
        return self.db.scalar(
            select(func.count(NotificationSendAttempt.id)).where(
                NotificationSendAttempt.notification_id == notification_id
            )
        )

    def attempt_by_key(self, key: UUID):
        return self.db.scalar(
            select(NotificationSendAttempt).where(NotificationSendAttempt.idempotency_key == key)
        )

    def history(self, notification_id: int):
        return list(
            self.db.scalars(
                select(AuditLog)
                .where(
                    AuditLog.target_type == "PARENT_NOTIFICATION",
                    AuditLog.target_id == str(notification_id),
                )
                .order_by(AuditLog.created_at, AuditLog.id)
            )
        )
