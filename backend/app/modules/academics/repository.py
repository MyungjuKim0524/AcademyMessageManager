from datetime import date

from sqlalchemy import ColumnElement, Date, and_, func, literal, not_, or_, select, true
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Session, aliased

from app.db.models.tables import (
    Assessment,
    AssessmentResult,
    Classroom,
    Enrollment,
    EnrollmentPause,
    Lesson,
    LessonResult,
    Student,
)
from app.modules.learningops.repository import LearningOpsRepository


def eligible_on(day) -> ColumnElement[bool]:
    """Whether the (joined) ``Enrollment`` row is a roster member on ``day``.

    * ``enrolled_at <= day <= ended_at`` (no end date = still enrolled);
    * not inside a dated pause: ``paused_from <= day < resumed_on`` (open pause = until now);
    * periods that cannot be known are never guessed: WITHDRAWN without ``ended_at``, and legacy
      PAUSED rows that have no open pause record (paused before Phase 7.1 pause history existed).
    """
    pause = aliased(EnrollmentPause)
    paused_on_day = (
        select(pause.id)
        .where(
            pause.enrollment_id == Enrollment.id,
            pause.paused_from <= day,
            or_(pause.resumed_on.is_(None), pause.resumed_on > day),
        )
        .exists()
    )
    open_pause = (
        select(pause.id)
        .where(pause.enrollment_id == Enrollment.id, pause.resumed_on.is_(None))
        .exists()
    )
    return and_(
        Enrollment.enrolled_at <= day,
        or_(Enrollment.ended_at.is_(None), Enrollment.ended_at >= day),
        not_(and_(Enrollment.status == "WITHDRAWN", Enrollment.ended_at.is_(None))),
        not_(and_(Enrollment.status == "PAUSED", not_(open_pause))),
        not_(paused_on_day),
    )


def held_lesson(today: date) -> ColumnElement[bool]:
    """Whether the (selected) ``Lesson`` row counts as *held* (진행된 수업).

    Not cancelled, not in the future, and COMPLETED or with at least one attendance row — a past
    SCHEDULED lesson without attendance is "not held". Single definition shared by 메시지 처리
    현황 (message_operations) and 출결 분석 (analytics);
    see docs/analytics/phase10-metric-definitions.md.
    """
    any_result = aliased(LessonResult)
    has_attendance = select(any_result.id).where(any_result.lesson_id == Lesson.id).exists()
    return and_(
        Lesson.status != "CANCELLED",
        Lesson.lesson_date <= today,
        or_(Lesson.status == "COMPLETED", has_attendance),
    )


class AcademicsRepository:
    def __init__(self, db: Session):
        self.db = db
        self.access = LearningOpsRepository(db)

    # ----- classroom / access -----
    def classroom(self, classroom_id: int) -> Classroom | None:
        return self.db.get(Classroom, classroom_id)

    def can_access(self, classroom_id: int, user_id: int, role: str) -> bool:
        return self.access.can_access_classroom(classroom_id, user_id, role)

    # ----- lessons -----
    def lesson(self, lesson_id: int, *, lock: str | None = None) -> Lesson | None:
        query = select(Lesson).where(Lesson.id == lesson_id)
        if lock == "update":
            query = query.with_for_update()
        elif lock == "share":
            query = query.with_for_update(read=True)
        return self.db.scalar(query.execution_options(populate_existing=True))

    def lesson_page(
        self,
        classroom_id: int,
        date_from: date | None,
        date_to: date | None,
        limit: int,
        offset: int,
    ):
        recorded = (
            select(func.count(LessonResult.id))
            .where(LessonResult.lesson_id == Lesson.id)
            .scalar_subquery()
        )
        query = select(Lesson, recorded).where(Lesson.classroom_id == classroom_id)
        if date_from:
            query = query.where(Lesson.lesson_date >= date_from)
        if date_to:
            query = query.where(Lesson.lesson_date <= date_to)
        query = (
            query.order_by(Lesson.lesson_date.desc(), Lesson.session_no.desc(), Lesson.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return self.db.execute(query.execution_options(populate_existing=True)).all()

    def lesson_has_records(self, lesson_id: int) -> bool:
        attendance = select(LessonResult.id).where(LessonResult.lesson_id == lesson_id).limit(1)
        linked = select(Assessment.id).where(Assessment.lesson_id == lesson_id).limit(1)
        return self.db.scalar(attendance) is not None or self.db.scalar(linked) is not None

    # ----- attendance -----
    def attendance_roster(self, lesson: Lesson):
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
            .where(
                Enrollment.classroom_id == lesson.classroom_id,
                or_(eligible, LessonResult.id.is_not(None)),
            )
            .order_by(Student.name, Student.id)
        )
        return self.db.execute(query.execution_options(populate_existing=True)).all()

    def enrollments_in_classroom(self, classroom_id: int, ids: set[int], day: date):
        query = select(Enrollment, eligible_on(day).label("eligible")).where(
            Enrollment.classroom_id == classroom_id, Enrollment.id.in_(ids)
        )
        return {row.Enrollment.id: bool(row.eligible) for row in self.db.execute(query)}

    def attendance_for_update(self, lesson_id: int, enrollment_ids: set[int]):
        rows = self.db.scalars(
            select(LessonResult)
            .where(
                LessonResult.lesson_id == lesson_id, LessonResult.enrollment_id.in_(enrollment_ids)
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return {row.enrollment_id: row for row in rows}

    # ----- assessments -----
    def assessment(self, assessment_id: int, *, lock: str | None = None) -> Assessment | None:
        query = select(Assessment).where(Assessment.id == assessment_id)
        if lock == "update":
            query = query.with_for_update()
        elif lock == "share":
            query = query.with_for_update(read=True)
        return self.db.scalar(query.execution_options(populate_existing=True))

    def assessment_page(self, classroom_id: int, limit: int, offset: int):
        # Correlated per page row; uses the uq_assessment_result (assessment_id, ...) index
        # instead of aggregating every result in the table.
        def count_of(status: str):
            return (
                select(func.count(AssessmentResult.id))
                .where(
                    AssessmentResult.assessment_id == Assessment.id,
                    AssessmentResult.result_status == status,
                )
                .scalar_subquery()
            )

        query = (
            select(Assessment, count_of("SCORED"), count_of("NOT_TAKEN"))
            .where(Assessment.classroom_id == classroom_id)
            .order_by(Assessment.assessment_date.desc(), Assessment.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return self.db.execute(query.execution_options(populate_existing=True)).all()

    def assessment_result_stats(self, assessment_id: int):
        return self.db.execute(
            select(func.count(AssessmentResult.id), func.max(AssessmentResult.score)).where(
                AssessmentResult.assessment_id == assessment_id
            )
        ).one()

    def grade_roster(self, assessment: Assessment):
        eligible = eligible_on(assessment.assessment_date)
        query = (
            select(Enrollment, Student, AssessmentResult, eligible.label("eligible"))
            .join(Student, Student.id == Enrollment.student_id)
            .outerjoin(
                AssessmentResult,
                and_(
                    AssessmentResult.assessment_id == assessment.id,
                    AssessmentResult.enrollment_id == Enrollment.id,
                ),
            )
            .where(
                Enrollment.classroom_id == assessment.classroom_id,
                or_(eligible, AssessmentResult.id.is_not(None)),
            )
            .order_by(Student.name, Student.id)
        )
        return self.db.execute(query.execution_options(populate_existing=True)).all()

    def grades_for_update(self, assessment_id: int, enrollment_ids: set[int]):
        rows = self.db.scalars(
            select(AssessmentResult)
            .where(
                AssessmentResult.assessment_id == assessment_id,
                AssessmentResult.enrollment_id.in_(enrollment_ids),
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return {row.enrollment_id: row for row in rows}

    # ----- student history -----
    def enrollment_for_student(self, classroom_id: int, student_id: int):
        return self.db.execute(
            select(Enrollment, Student)
            .join(Student, Student.id == Enrollment.student_id)
            .where(Enrollment.classroom_id == classroom_id, Enrollment.student_id == student_id)
        ).one_or_none()

    def student_lessons(self, enrollment: Enrollment, limit: int):
        # Lessons inside the enrollment period, plus any lesson that already has a record.
        in_period = eligible_on(Lesson.lesson_date)
        query = (
            select(Lesson, LessonResult)
            .select_from(Lesson)
            .join(Enrollment, Enrollment.id == enrollment.id)
            .outerjoin(
                LessonResult,
                and_(
                    LessonResult.lesson_id == Lesson.id, LessonResult.enrollment_id == enrollment.id
                ),
            )
            .where(
                Lesson.classroom_id == enrollment.classroom_id,
                or_(and_(in_period, Lesson.status != "CANCELLED"), LessonResult.id.is_not(None)),
            )
            .order_by(Lesson.lesson_date.desc(), Lesson.session_no.desc(), Lesson.id.desc())
            .limit(limit)
        )
        return self.db.execute(query.execution_options(populate_existing=True)).all()

    def student_assessments(self, enrollment: Enrollment, limit: int):
        in_period = eligible_on(Assessment.assessment_date)
        query = (
            select(Assessment, AssessmentResult)
            .select_from(Assessment)
            .join(Enrollment, Enrollment.id == enrollment.id)
            .outerjoin(
                AssessmentResult,
                and_(
                    AssessmentResult.assessment_id == Assessment.id,
                    AssessmentResult.enrollment_id == enrollment.id,
                ),
            )
            .where(
                Assessment.classroom_id == enrollment.classroom_id,
                or_(in_period, AssessmentResult.id.is_not(None)),
            )
            .order_by(Assessment.assessment_date.desc(), Assessment.id.desc())
            .limit(limit)
        )
        return self.db.execute(query.execution_options(populate_existing=True)).all()

    # ----- class progress grid -----
    def progress_lessons(self, classroom_id: int, date_from: date, date_to: date):
        return list(
            self.db.scalars(
                select(Lesson)
                .where(
                    Lesson.classroom_id == classroom_id,
                    Lesson.lesson_date >= date_from,
                    Lesson.lesson_date <= date_to,
                )
                .order_by(Lesson.lesson_date, Lesson.session_no, Lesson.id)
                .execution_options(populate_existing=True)
            )
        )

    def progress_assessments(
        self, classroom_id: int, lesson_ids: list[int], date_from: date, date_to: date
    ):
        """Assessments linked to the lessons, plus unlinked ones dated inside the period."""
        return list(
            self.db.scalars(
                select(Assessment)
                .where(
                    Assessment.classroom_id == classroom_id,
                    or_(
                        Assessment.lesson_id.in_(lesson_ids),
                        and_(
                            Assessment.lesson_id.is_(None),
                            Assessment.assessment_date >= date_from,
                            Assessment.assessment_date <= date_to,
                        ),
                    ),
                )
                .order_by(Assessment.assessment_date, Assessment.title, Assessment.id)
                .execution_options(populate_existing=True)
            )
        )

    def classroom_enrollments(self, classroom_id: int):
        return self.db.execute(
            select(Enrollment, Student)
            .join(Student, Student.id == Enrollment.student_id)
            .where(Enrollment.classroom_id == classroom_id)
            .order_by(Student.name, Student.id)
        ).all()

    def eligibility_by_day(self, classroom_id: int, days: set[date]) -> set[tuple[int, date]]:
        """(enrollment_id, day) pairs that are roster members on that day.

        One query for every day (Phase 11-4-A): the days are unnested and the same
        ``eligible_on`` rule is applied per (enrollment, day). Before: one query per day — 24
        lesson days took ~165ms of a ~270ms progress grid request."""
        if not days:
            return set()
        day_list = (
            func.unnest(literal(sorted(days), type_=ARRAY(Date)))
            .table_valued("day")
            .render_derived(name="d")
        )
        rows = self.db.execute(
            select(Enrollment.id, day_list.c.day)
            .select_from(Enrollment)
            .join(day_list, true())
            .where(Enrollment.classroom_id == classroom_id, eligible_on(day_list.c.day))
        )
        return {(enrollment_id, day) for enrollment_id, day in rows}

    def lesson_results(self, lesson_ids: list[int]):
        if not lesson_ids:
            return []
        return list(
            self.db.scalars(
                select(LessonResult)
                .where(LessonResult.lesson_id.in_(lesson_ids))
                .execution_options(populate_existing=True)
            )
        )

    def assessment_results(self, assessment_ids: list[int]):
        if not assessment_ids:
            return []
        return list(
            self.db.scalars(
                select(AssessmentResult)
                .where(AssessmentResult.assessment_id.in_(assessment_ids))
                .execution_options(populate_existing=True)
            )
        )

    # ----- enrollment pauses -----
    def enrollment_in_classroom(self, classroom_id: int, enrollment_id: int, *, lock=False):
        query = select(Enrollment).where(
            Enrollment.id == enrollment_id, Enrollment.classroom_id == classroom_id
        )
        if lock:
            query = query.with_for_update()
        return self.db.scalar(query.execution_options(populate_existing=True))

    def pauses(self, enrollment_id: int):
        return list(
            self.db.scalars(
                select(EnrollmentPause)
                .where(EnrollmentPause.enrollment_id == enrollment_id)
                .order_by(EnrollmentPause.paused_from.desc())
                .execution_options(populate_existing=True)
            )
        )

    def open_pause(self, enrollment_id: int) -> EnrollmentPause | None:
        return self.db.scalar(
            select(EnrollmentPause)
            .where(
                EnrollmentPause.enrollment_id == enrollment_id,
                EnrollmentPause.resumed_on.is_(None),
            )
            .execution_options(populate_existing=True)
        )

    @staticmethod
    def attendance_counts(rows) -> dict[str, int]:
        counts = {"eligible": 0, "recorded": 0, "present": 0, "absent": 0, "late": 0, "excused": 0}
        for row in rows:
            if row.eligible:
                counts["eligible"] += 1
            if row.LessonResult is not None:
                counts["recorded"] += 1
                counts[row.LessonResult.attendance_status.lower()] += 1
        counts["unrecorded"] = sum(1 for row in rows if row.eligible and row.LessonResult is None)
        return counts
