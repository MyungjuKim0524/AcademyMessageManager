"""Set-based, read-only aggregation queries for Phase 10 analytics.

The *target set* is built first — (held lesson × enrolment) for attendance, (assessment ×
enrolment) for grades — and results are LEFT JOINed onto it, so a missing record is counted as
"not entered" instead of disappearing. Unique constraints make every join one-to-one per pair:
``uq_enrollment_student_classroom`` (one enrolment per student and class), ``uq_lesson_result``
(lesson, enrolment) and ``uq_assessment_result`` (assessment, enrolment). Eligibility on a day is
the existing ``eligible_on`` rule (enrolment period + dated pauses), as in the entry screens.

Every method issues a fixed number of queries regardless of class size (no N+1).
"""

from datetime import date

from sqlalchemy import and_, false, func, not_, or_, select
from sqlalchemy.orm import Session, aliased

from app.db.models.tables import (
    Assessment,
    AssessmentResult,
    Enrollment,
    Lesson,
    LessonResult,
    Student,
)
from app.modules.academics.repository import eligible_on, held_lesson

ATTENDANCE_STATUSES = ("PRESENT", "LATE", "ABSENT", "EXCUSED")


class AnalyticsRepository:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------ attendance
    @staticmethod
    def _attendance_pairs(
        classroom_id: int, date_from: date, until: date, today: date, enrollment_id=None
    ):
        eligible = eligible_on(Lesson.lesson_date)
        # One student: filter inside the (materialized) CTE so only that student's rows are built.
        student = [Enrollment.id == enrollment_id] if enrollment_id is not None else []
        return (
            select(
                Lesson.id.label("lesson_id"),
                Lesson.lesson_date.label("lesson_date"),
                Lesson.session_no.label("session_no"),
                Lesson.topic.label("topic"),
                Enrollment.id.label("enrollment_id"),
                eligible.label("eligible"),
                LessonResult.attendance_status.label("status"),
                # Homework grades of the same lesson row (student report / watch list).
                LessonResult.prework_grade.label("prework"),
                LessonResult.weekly_assignment_grade.label("weekly"),
            )
            .select_from(Lesson)
            .join(Enrollment, Enrollment.classroom_id == Lesson.classroom_id)
            .outerjoin(
                LessonResult,
                and_(
                    LessonResult.lesson_id == Lesson.id,
                    LessonResult.enrollment_id == Enrollment.id,
                ),
            )
            .where(
                Lesson.classroom_id == classroom_id,
                Lesson.lesson_date >= date_from,
                Lesson.lesson_date <= until,
                held_lesson(today),
                *student,
            )
            # MATERIALIZED: compute eligibility once per pair. Inlined, PostgreSQL re-evaluated the
            # eligible_on subqueries in every FILTER aggregate (measured: 370 ms → see Stage 6).
            .cte("attendance_pairs")
            .prefix_with("MATERIALIZED", dialect="postgresql")
        )

    @staticmethod
    def _attendance_counts(pairs):
        eligible, status = pairs.c.eligible, pairs.c.status
        return [
            func.count().filter(eligible).label("target"),
            func.count().filter(and_(eligible, status.is_not(None))).label("recorded"),
            func.count().filter(and_(eligible, status.is_(None))).label("unrecorded"),
            *[
                func.count().filter(and_(eligible, status == value)).label(value.lower())
                for value in ATTENDANCE_STATUSES
            ],
            func.count().filter(and_(not_(eligible), status.is_not(None))).label("outside_records"),
        ]

    def attendance_by_student(self, classroom_id: int, date_from: date, until: date, today: date):
        pairs = self._attendance_pairs(classroom_id, date_from, until, today)
        counts = self._attendance_counts(pairs)
        query = (
            select(
                pairs.c.enrollment_id,
                Student.id.label("student_id"),
                Student.name.label("student_name"),
                Enrollment.status.label("enrollment_status"),
                *counts,
            )
            .select_from(pairs)
            .join(Enrollment, Enrollment.id == pairs.c.enrollment_id)
            .join(Student, Student.id == Enrollment.student_id)
            .group_by(pairs.c.enrollment_id, Student.id, Student.name, Enrollment.status)
            # Students with neither a target lesson nor a record in the period are not listed.
            .having(or_(counts[0] > 0, counts[-1] > 0))
            .order_by(Student.name, Student.id)
        )
        return self.db.execute(query).mappings().all()

    def attendance_by_lesson(self, classroom_id: int, date_from: date, until: date, today: date):
        pairs = self._attendance_pairs(classroom_id, date_from, until, today)
        eligible, status = pairs.c.eligible, pairs.c.status
        query = (
            select(
                pairs.c.lesson_id,
                pairs.c.lesson_date,
                pairs.c.session_no,
                pairs.c.topic,
                func.count().filter(eligible).label("target"),
                func.count().filter(and_(eligible, status.is_not(None))).label("recorded"),
                func.count().filter(and_(eligible, status.is_(None))).label("unrecorded"),
            )
            .group_by(pairs.c.lesson_id, pairs.c.lesson_date, pairs.c.session_no, pairs.c.topic)
            .order_by(pairs.c.lesson_date, pairs.c.session_no, pairs.c.lesson_id)
        )
        return self.db.execute(query).mappings().all()

    def lesson_counts(self, classroom_id: int, date_from: date, until: date, today: date):
        """(held lessons, past SCHEDULED lessons without any attendance) in the period."""
        any_result = aliased(LessonResult)
        has_attendance = select(any_result.id).where(any_result.lesson_id == Lesson.id).exists()
        in_period = and_(
            Lesson.classroom_id == classroom_id,
            Lesson.lesson_date >= date_from,
            Lesson.lesson_date <= until,
        )
        held = func.count().filter(held_lesson(today))
        not_held = func.count().filter(and_(Lesson.status == "SCHEDULED", not_(has_attendance)))
        row = self.db.execute(select(held, not_held).select_from(Lesson).where(in_period)).one()
        return int(row[0]), int(row[1])

    def attendance_history(
        self, classroom_id: int, enrollment_id: int, date_from: date, until: date, today: date
    ):
        pairs = self._attendance_pairs(classroom_id, date_from, until, today, enrollment_id)
        query = (
            select(pairs)
            .where(or_(pairs.c.eligible, pairs.c.status.is_not(None)))
            .order_by(pairs.c.lesson_date, pairs.c.session_no, pairs.c.lesson_id)
        )
        return self.db.execute(query).mappings().all()

    # ---------------------------------------------------------------------- grades
    @staticmethod
    def _grade_pairs(
        classroom_id: int, date_from: date, date_to: date, assessment_id=None, enrollment_id=None
    ):
        linked = aliased(Lesson)
        # Outer join: an assessment of a class without students still appears (target 0).
        eligible = func.coalesce(eligible_on(Assessment.assessment_date), false())
        query = (
            select(
                Assessment.id.label("assessment_id"),
                Assessment.title.label("title"),
                Assessment.assessment_date.label("assessment_date"),
                Assessment.max_score.label("max_score"),
                Assessment.lesson_id.label("lesson_id"),
                linked.session_no.label("session_no"),
                Enrollment.id.label("enrollment_id"),
                eligible.label("eligible"),
                AssessmentResult.result_status.label("status"),
                AssessmentResult.score.label("score"),
            )
            .select_from(Assessment)
            .outerjoin(linked, linked.id == Assessment.lesson_id)
            .outerjoin(Enrollment, Enrollment.classroom_id == Assessment.classroom_id)
            .outerjoin(
                AssessmentResult,
                and_(
                    AssessmentResult.assessment_id == Assessment.id,
                    AssessmentResult.enrollment_id == Enrollment.id,
                ),
            )
            .where(Assessment.classroom_id == classroom_id)
        )
        if enrollment_id is not None:  # inside the CTE, see _attendance_pairs
            query = query.where(Enrollment.id == enrollment_id)
        if assessment_id is not None:
            query = query.where(Assessment.id == assessment_id)
        else:
            query = query.where(
                Assessment.assessment_date >= date_from, Assessment.assessment_date <= date_to
            )
        return query.cte("grade_pairs").prefix_with("MATERIALIZED", dialect="postgresql")

    @staticmethod
    def _order(pairs):
        # Stable: date, then the linked lesson's session (unlinked last), then id.
        return (
            pairs.c.assessment_date,
            pairs.c.session_no.asc().nulls_last(),
            pairs.c.assessment_id,
        )

    def grade_stats(
        self, classroom_id: int, date_from: date, date_to: date, assessment_id: int | None = None
    ):
        pairs = self._grade_pairs(classroom_id, date_from, date_to, assessment_id)
        eligible, status, score = pairs.c.eligible, pairs.c.status, pairs.c.score
        scored = status == "SCORED"
        average = func.avg(score).filter(scored)  # numeric AVG: no integer truncation
        query = (
            select(
                pairs.c.assessment_id,
                pairs.c.title,
                pairs.c.assessment_date,
                pairs.c.max_score,
                pairs.c.lesson_id,
                pairs.c.session_no,
                func.count().filter(eligible).label("target"),
                func.count().filter(and_(eligible, scored)).label("scored"),
                func.count().filter(and_(eligible, status == "NOT_TAKEN")).label("not_taken"),
                func.count().filter(and_(eligible, status.is_(None))).label("missing"),
                func.count()
                .filter(and_(not_(eligible), status.is_not(None)))
                .label("outside_records"),
                func.round(average, 2).label("average"),
                func.count().filter(scored).label("average_count"),
                # max_score > 0 is a CHECK constraint; NULL average stays NULL.
                func.round(average * 100 / pairs.c.max_score, 1).label("average_percent"),
            )
            .group_by(
                pairs.c.assessment_id,
                pairs.c.title,
                pairs.c.assessment_date,
                pairs.c.max_score,
                pairs.c.lesson_id,
                pairs.c.session_no,
            )
            .order_by(*self._order(pairs))
        )
        return self.db.execute(query).mappings().all()

    def grade_rows(
        self,
        classroom_id: int,
        *,
        assessment_id: int | None = None,
        enrollment_id: int | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ):
        """Per (assessment, student) rows where the student is a target or has a result."""
        pairs = self._grade_pairs(
            classroom_id, date_from or date.min, date_to or date.max, assessment_id, enrollment_id
        )
        percent = func.round(pairs.c.score * 100 / pairs.c.max_score, 1)
        query = (
            select(
                pairs,
                Student.id.label("student_id"),
                Student.name.label("student_name"),
                percent.label("percent"),
            )
            .join(Enrollment, Enrollment.id == pairs.c.enrollment_id)
            .join(Student, Student.id == Enrollment.student_id)
            .where(or_(pairs.c.eligible, pairs.c.status.is_not(None)))
        )
        if assessment_id is not None:
            query = query.order_by(Student.name, Student.id)
        else:
            query = query.order_by(*self._order(pairs))
        return self.db.execute(query).mappings().all()

    def lesson_rows(self, classroom_id: int, date_from: date, until: date, today: date):
        """Every student's held-lesson rows (attendance + homework grades), date order."""
        pairs = self._attendance_pairs(classroom_id, date_from, until, today)
        query = (
            select(pairs)
            .where(or_(pairs.c.eligible, pairs.c.status.is_not(None)))
            .order_by(pairs.c.lesson_date, pairs.c.session_no, pairs.c.lesson_id)
        )
        return self.db.execute(query).mappings().all()

    def roster(self, classroom_id: int):
        """Enrolments of the class with the student's name and enrolment status."""
        return self.db.execute(
            select(Enrollment.id, Enrollment.status, Student.id.label("student_id"), Student.name)
            .join(Student, Student.id == Enrollment.student_id)
            .where(Enrollment.classroom_id == classroom_id)
        ).all()

    # ----------------------------------------------------------------- lookups
    def enrollment_of_student(self, classroom_id: int, student_id: int):
        """The student's enrolment in this class (one per class), or None — IDOR guard."""
        return self.db.execute(
            select(Enrollment.id, Student.id.label("student_id"), Student.name)
            .join(Student, Student.id == Enrollment.student_id)
            .where(Enrollment.classroom_id == classroom_id, Enrollment.student_id == student_id)
        ).one_or_none()

    def assessment_classroom(self, assessment_id: int):
        return self.db.execute(
            select(Assessment.classroom_id, Assessment.assessment_date).where(
                Assessment.id == assessment_id
            )
        ).one_or_none()
