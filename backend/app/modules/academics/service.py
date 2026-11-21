"""Business rules and transaction boundaries for lessons, attendance and grades.

Every write runs in one transaction together with its audit_log rows: either all of a bulk
request (data + history) is committed, or nothing is.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models.tables import (
    Assessment,
    AssessmentResult,
    AuditLog,
    EnrollmentPause,
    Lesson,
    LessonResult,
)
from app.errors import CompatibilityError, FieldError
from app.modules.auth.dependencies import Principal

from .repository import AcademicsRepository
from .schemas import (
    AssessmentCreate,
    AssessmentUpdate,
    AttendanceBulk,
    GradeBulk,
    LessonCreate,
    LessonUpdate,
    PauseCreate,
    PauseResume,
    RecordUpdate,
)

LESSON_WRITERS = frozenset({"ADMIN", "TEACHER"})
ATTENDANCE_WRITERS = frozenset({"ADMIN", "TEACHER", "ASSISTANT"})
# 2026-11-19 user decision: assistants may also record and correct scores and assignment grades
# (they already save both through the workbook upload, so they must be able to fix mistakes),
# and may create / edit assessments (name, max score) as well.
GRADE_WRITERS = frozenset({"ADMIN", "TEACHER", "ASSISTANT"})
ASSESSMENT_WRITERS = GRADE_WRITERS
ASSIGNMENT_GRADE_WRITERS = GRADE_WRITERS
ENROLLMENT_WRITERS = frozenset({"ADMIN"})
MAX_PROGRESS_DAYS = 93  # about three months per grid

CONFLICT_MESSAGE = "다른 사용자가 먼저 변경했습니다. 새로고침 후 다시 시도해주세요."
DUPLICATE_LESSON = "같은 날짜·회차 번호의 수업이 이미 있습니다. 다른 회차 번호를 지정하세요."


def _json(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    return value


def _fail(status: int, code: str, message: str, fields: list[FieldError] | None = None):
    raise CompatibilityError(status, code, message, tuple(fields or ()))


class AcademicsService:
    def __init__(self, db: Session, principal: Principal, request_id: str | None = None):
        self.db = db
        self.principal = principal
        self.request_id = request_id
        self.repo = AcademicsRepository(db)

    # ------------------------------------------------------------------ helpers
    def _audit(self, event: str, target_type: str, target_id: int, details: dict) -> None:
        self.db.add(
            AuditLog(
                actor_staff_user_id=self.principal.user_id,
                event_type=event,
                target_type=target_type,
                target_id=str(target_id),
                request_id=UUID(self.request_id) if self.request_id else None,
                details=details,
            )
        )

    def _abort(self, status: int, code: str, message: str, fields=None):
        self.db.rollback()  # release row locks before answering
        _fail(status, code, message, fields)

    def _flush_or_conflict(self, code: str, message: str) -> None:
        try:
            self.db.flush()
        except IntegrityError as exc:
            self.db.rollback()
            raise CompatibilityError(409, code, message) from exc

    def _commit_or_conflict(self, code: str, message: str) -> None:
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise CompatibilityError(409, code, message) from exc

    def _require_classroom(self, classroom_id: int, writers: frozenset[str] | None = None):
        classroom = self.repo.classroom(classroom_id)
        if classroom is None or not classroom.is_active:
            _fail(404, "CLASSROOM_NOT_FOUND", "반을 찾을 수 없습니다.")
        if not self.repo.can_access(classroom_id, self.principal.user_id, self.principal.role):
            _fail(403, "CLASSROOM_ACCESS_DENIED", "담당 반에만 접근할 수 있습니다.")
        if writers is not None and self.principal.role not in writers:
            _fail(403, "FORBIDDEN", "요청한 작업을 수행할 권한이 없습니다.")
        return classroom

    def _lesson(self, lesson_id: int, writers=None, lock: str | None = None) -> Lesson:
        lesson = self.repo.lesson(lesson_id, lock=lock)
        if lesson is None:
            self._abort(404, "LESSON_NOT_FOUND", "수업을 찾을 수 없습니다.")
        try:
            self._require_classroom(lesson.classroom_id, writers)
        except CompatibilityError:
            self.db.rollback()
            raise
        return lesson

    def _assessment(self, assessment_id: int, writers=None, lock: str | None = None) -> Assessment:
        assessment = self.repo.assessment(assessment_id, lock=lock)
        if assessment is None:
            self._abort(404, "ASSESSMENT_NOT_FOUND", "평가를 찾을 수 없습니다.")
        try:
            self._require_classroom(assessment.classroom_id, writers)
        except CompatibilityError:
            self.db.rollback()
            raise
        return assessment

    @staticmethod
    def _changes(data, current, required: tuple[str, ...]) -> dict:
        changes = {}
        for name in data.model_fields_set - {"version"}:
            value = getattr(data, name)
            if value is None and name in required:
                _fail(
                    400,
                    "VALIDATION_ERROR",
                    "입력값을 확인해주세요.",
                    [FieldError(field=name, message="값을 비울 수 없습니다.")],
                )
            if value != getattr(current, name):
                changes[name] = value
        return changes

    @staticmethod
    def _redact(values: dict) -> dict:
        """Audit values only; free-text memos may contain student details."""
        result = {k: _json(v) for k, v in values.items() if k != "memo"}
        if "memo" in values:
            result["memo_changed"] = True
        return result

    def _validate_items(self, items, classroom_id: int, day: date, existing: dict, eligibility):
        errors, conflicts = [], []
        seen: set[int] = set()
        for index, item in enumerate(items):
            field = f"items.{index}"
            if item.enrollment_id in seen:
                errors.append(
                    FieldError(
                        field=f"{field}.enrollment_id", message="같은 학생이 중복되었습니다."
                    )
                )
                continue
            seen.add(item.enrollment_id)
            if item.enrollment_id not in eligibility:
                errors.append(
                    FieldError(field=f"{field}.enrollment_id", message="이 반의 학생이 아닙니다.")
                )
                continue
            if not eligibility[item.enrollment_id]:
                errors.append(
                    FieldError(
                        field=f"{field}.enrollment_id", message="해당 날짜의 수강 대상이 아닙니다."
                    )
                )
                continue
            current = existing.get(item.enrollment_id)
            if current is None and item.version is not None:
                conflicts.append(FieldError(field=f"{field}.version", message=CONFLICT_MESSAGE))
            elif current is not None and item.version is None:
                conflicts.append(
                    FieldError(
                        field=f"{field}.version",
                        message="이미 기록이 있습니다. 새로고침 후 수정해주세요.",
                    )
                )
            elif current is not None and current.version != item.version:
                conflicts.append(FieldError(field=f"{field}.version", message=CONFLICT_MESSAGE))
        return errors, conflicts

    # ------------------------------------------------------------------ lessons
    def lessons(self, classroom_id: int, date_from, date_to, limit: int, offset: int):
        self._require_classroom(classroom_id)
        if date_from and date_to and date_from > date_to:
            _fail(400, "INVALID_DATE_RANGE", "조회 기간을 확인해주세요.")
        return self.repo.lesson_page(classroom_id, date_from, date_to, limit, offset)

    def create_lesson(self, classroom_id: int, data: LessonCreate) -> Lesson:
        self._require_classroom(classroom_id, LESSON_WRITERS)
        if data.status == "COMPLETED" and data.lesson_date > date.today():
            _fail(400, "INVALID_LESSON_STATUS", "미래 수업은 완료 처리할 수 없습니다.")
        lesson = Lesson(classroom_id=classroom_id, **data.model_dump())
        self.db.add(lesson)
        self._flush_or_conflict("LESSON_ALREADY_EXISTS", DUPLICATE_LESSON)
        self._audit(
            "LESSON_CREATED",
            "LESSON",
            lesson.id,
            {"classroom_id": classroom_id, "after": self._redact(data.model_dump())},
        )
        self._commit_or_conflict("LESSON_ALREADY_EXISTS", DUPLICATE_LESSON)
        self.db.refresh(lesson)
        return lesson

    def start_today_lesson(self, classroom_id: int) -> tuple[Lesson, bool]:
        """ "오늘 수업 시작" on the attendance tab: find or create today's 1st-session lesson.

        Attendance is taken first at the start of class (often by an assistant), so anyone who
        may record attendance may call this. It is idempotent: an existing lesson is returned
        unchanged. Editing topic / date and cancelling stay with lesson writers.
        """
        self._require_classroom(classroom_id, ATTENDANCE_WRITERS)
        today = date.today()

        def existing() -> Lesson | None:
            return self.db.scalar(
                select(Lesson)
                .where(
                    Lesson.classroom_id == classroom_id,
                    Lesson.lesson_date == today,
                    Lesson.session_no == 1,
                    Lesson.exam_round.is_(None),
                )
                .execution_options(populate_existing=True)
            )

        found = existing()
        if found is None:
            lesson = Lesson(classroom_id=classroom_id, lesson_date=today, status="COMPLETED")
            self.db.add(lesson)
            try:
                self.db.flush()
            except IntegrityError:
                self.db.rollback()  # someone else started it at the same moment
                found = existing()
                if found is None:
                    raise
            else:
                self._audit(
                    "LESSON_CREATED",
                    "LESSON",
                    lesson.id,
                    {
                        "classroom_id": classroom_id,
                        "after": {"lesson_date": today.isoformat(), "session_no": 1},
                        "source": "ATTENDANCE_START",
                    },
                )
                self._commit_or_conflict("LESSON_ALREADY_EXISTS", DUPLICATE_LESSON)
                self.db.refresh(lesson)
                return lesson, True
        if found.status == "CANCELLED":
            _fail(409, "LESSON_CANCELLED", "오늘 수업이 취소 상태입니다. 선생님께 확인해주세요.")
        self.db.rollback()
        return found, False

    def lesson_detail(self, lesson_id: int):
        lesson = self._lesson(lesson_id)
        rows = self.repo.attendance_roster(lesson)
        return lesson, self.repo.attendance_counts(rows)

    def update_lesson(self, lesson_id: int, data: LessonUpdate) -> Lesson:
        lesson = self._lesson(lesson_id, LESSON_WRITERS, lock="update")
        if lesson.version != data.version:
            self._abort(409, "VERSION_CONFLICT", CONFLICT_MESSAGE)
        try:
            changes = self._changes(data, lesson, ("lesson_date", "status"))
        except CompatibilityError:
            self.db.rollback()
            raise
        if not changes:
            self.db.rollback()
            return lesson
        moves_key = bool({"lesson_date", "exam_round", "session_no"} & changes.keys())
        cancels = changes.get("status") == "CANCELLED"
        if (moves_key or cancels) and self.repo.lesson_has_records(lesson.id):
            self._abort(
                409,
                "LESSON_HAS_RECORDS",
                "출결이나 평가가 연결된 수업은 날짜·회차를 바꾸거나 취소할 수 없습니다.",
            )
        new_date = changes.get("lesson_date", lesson.lesson_date)
        if changes.get("status", lesson.status) == "COMPLETED" and new_date > date.today():
            self._abort(400, "INVALID_LESSON_STATUS", "미래 수업은 완료 처리할 수 없습니다.")
        before = self._redact({name: getattr(lesson, name) for name in changes})
        before["version"] = lesson.version
        for name, value in changes.items():
            setattr(lesson, name, value)
        self._flush_or_conflict("LESSON_ALREADY_EXISTS", DUPLICATE_LESSON)
        self._audit(
            "LESSON_UPDATED",
            "LESSON",
            lesson.id,
            {"classroom_id": lesson.classroom_id, "before": before, "after": self._redact(changes)},
        )
        self._commit_or_conflict("LESSON_ALREADY_EXISTS", DUPLICATE_LESSON)
        self.db.refresh(lesson)
        return lesson

    # --------------------------------------------------------------- attendance
    def attendance(self, lesson_id: int):
        lesson = self._lesson(lesson_id)
        rows = self.repo.attendance_roster(lesson)
        return lesson, rows, self.repo.attendance_counts(rows)

    def save_attendance(self, lesson_id: int, data: AttendanceBulk) -> int:
        # FOR SHARE: a concurrent lesson PATCH (cancel / date change) waits for this batch.
        lesson = self._lesson(lesson_id, ATTENDANCE_WRITERS, lock="share")
        if lesson.status == "CANCELLED":
            self._abort(409, "LESSON_CANCELLED", "취소된 수업에는 출결을 기록할 수 없습니다.")
        if lesson.lesson_date > date.today():
            self._abort(400, "LESSON_IN_FUTURE", "아직 진행되지 않은 수업입니다.")
        ids = {item.enrollment_id for item in data.items}
        eligibility = self.repo.enrollments_in_classroom(
            lesson.classroom_id, ids, lesson.lesson_date
        )
        existing = self.repo.attendance_for_update(lesson.id, ids)
        errors, conflicts = self._validate_items(
            data.items, lesson.classroom_id, lesson.lesson_date, existing, eligibility
        )
        if errors:
            self._abort(400, "INVALID_ATTENDANCE_ITEMS", "출결 입력을 확인해주세요.", errors)
        if conflicts:
            self._abort(409, "VERSION_CONFLICT", CONFLICT_MESSAGE, conflicts)

        created: list[tuple[LessonResult, object]] = []
        changed = 0
        for item in data.items:
            current = existing.get(item.enrollment_id)
            if current is None:
                row = LessonResult(
                    lesson_id=lesson.id,
                    enrollment_id=item.enrollment_id,
                    attendance_status=item.status,
                    memo=item.memo,
                )
                self.db.add(row)
                created.append((row, item))
                changed += 1
                continue
            if current.attendance_status == item.status and current.memo == item.memo:
                continue
            self._audit(
                "ATTENDANCE_UPDATED",
                "LESSON_RESULT",
                current.id,
                {
                    "lesson_id": lesson.id,
                    "enrollment_id": item.enrollment_id,
                    "before": {"status": current.attendance_status, "version": current.version},
                    "after": {"status": item.status, "version": current.version + 1},
                    "memo_changed": current.memo != item.memo,
                },
            )
            current.attendance_status = item.status
            current.memo = item.memo
            changed += 1
        self._flush_or_conflict("ATTENDANCE_CONFLICT", CONFLICT_MESSAGE)
        for row, item in created:
            self._audit(
                "ATTENDANCE_RECORDED",
                "LESSON_RESULT",
                row.id,
                {
                    "lesson_id": lesson.id,
                    "enrollment_id": item.enrollment_id,
                    "after": {"status": item.status, "version": 1},
                    "memo_set": item.memo is not None,
                },
            )
        self._commit_or_conflict("ATTENDANCE_CONFLICT", CONFLICT_MESSAGE)
        return changed

    # -------------------------------------------------------------- assessments
    def assessments(self, classroom_id: int, limit: int, offset: int):
        self._require_classroom(classroom_id)
        return self.repo.assessment_page(classroom_id, limit, offset)

    def _check_lesson_link(self, classroom_id: int, lesson_id: int) -> None:
        # FOR SHARE until commit (Phase 11-3-B, INT-03): a cancel (FOR UPDATE) either waits for
        # this assessment and then refuses (LESSON_HAS_RECORDS), or commits first and this
        # read — taken after the wait — sees CANCELLED. Same lock the attendance writers use.
        lesson = self.repo.lesson(lesson_id, lock="share")
        if lesson is None or lesson.classroom_id != classroom_id or lesson.status == "CANCELLED":
            self._abort(
                400,
                "INVALID_LESSON_LINK",
                "같은 반의 취소되지 않은 수업만 연결할 수 있습니다.",
                [FieldError(field="lesson_id", message="연결할 수 없는 수업입니다.")],
            )

    def create_assessment(self, classroom_id: int, data: AssessmentCreate) -> Assessment:
        self._require_classroom(classroom_id, ASSESSMENT_WRITERS)
        if data.lesson_id is not None:
            self._check_lesson_link(classroom_id, data.lesson_id)
        assessment = Assessment(classroom_id=classroom_id, **data.model_dump())
        self.db.add(assessment)
        self._flush_or_conflict("ASSESSMENT_CONFLICT", "평가를 저장할 수 없습니다.")
        self._audit(
            "ASSESSMENT_CREATED",
            "ASSESSMENT",
            assessment.id,
            {"classroom_id": classroom_id, "after": self._redact(data.model_dump())},
        )
        self._commit_or_conflict("ASSESSMENT_CONFLICT", "평가를 저장할 수 없습니다.")
        self.db.refresh(assessment)
        return assessment

    def assessment_detail(self, assessment_id: int):
        assessment = self._assessment(assessment_id)
        rows = self.repo.grade_roster(assessment)
        return assessment, self._grade_counts(rows)

    def update_assessment(self, assessment_id: int, data: AssessmentUpdate) -> Assessment:
        assessment = self._assessment(assessment_id, ASSESSMENT_WRITERS, lock="update")
        if assessment.version != data.version:
            self._abort(409, "VERSION_CONFLICT", CONFLICT_MESSAGE)
        try:
            changes = self._changes(data, assessment, ("title", "assessment_date", "max_score"))
        except CompatibilityError:
            self.db.rollback()
            raise
        if not changes:
            self.db.rollback()
            return assessment
        result_count, highest = self.repo.assessment_result_stats(assessment.id)
        if "assessment_date" in changes and result_count:
            self._abort(
                409, "ASSESSMENT_HAS_RESULTS", "점수가 입력된 평가는 평가일을 바꿀 수 없습니다."
            )
        if "max_score" in changes and highest is not None and highest > changes["max_score"]:
            self._abort(
                409,
                "MAX_SCORE_BELOW_EXISTING",
                "이미 입력된 점수보다 낮은 만점으로 바꿀 수 없습니다.",
                [FieldError(field="max_score", message=f"현재 최고 점수: {highest}")],
            )
        if changes.get("lesson_id") is not None:
            self._check_lesson_link(assessment.classroom_id, changes["lesson_id"])
        before = self._redact({name: getattr(assessment, name) for name in changes})
        before["version"] = assessment.version
        for name, value in changes.items():
            setattr(assessment, name, value)
        # max_score cascades to assessment_result; the DB CHECK rejects any exceeding score.
        self._flush_or_conflict(
            "MAX_SCORE_BELOW_EXISTING", "이미 입력된 점수와 맞지 않는 만점입니다."
        )
        self._audit(
            "ASSESSMENT_UPDATED",
            "ASSESSMENT",
            assessment.id,
            {
                "classroom_id": assessment.classroom_id,
                "before": before,
                "after": self._redact(changes),
            },
        )
        self._commit_or_conflict("ASSESSMENT_CONFLICT", CONFLICT_MESSAGE)
        self.db.refresh(assessment)
        return assessment

    # ------------------------------------------------------------------- grades
    @staticmethod
    def _grade_counts(rows) -> dict[str, int]:
        counts = {"eligible": 0, "scored": 0, "not_taken": 0, "unrecorded": 0}
        for row in rows:
            result = row.AssessmentResult
            if row.eligible:
                counts["eligible"] += 1
                if result is None:
                    counts["unrecorded"] += 1
            if result is not None:
                counts["scored" if result.result_status == "SCORED" else "not_taken"] += 1
        return counts

    def grades(self, assessment_id: int):
        assessment = self._assessment(assessment_id)
        rows = self.repo.grade_roster(assessment)
        return assessment, rows, self._grade_counts(rows)

    @staticmethod
    def _score_errors(items, max_score: Decimal) -> list[FieldError]:
        errors = []
        for index, item in enumerate(items):
            field = f"items.{index}.score"
            if item.result_status == "NOT_TAKEN":
                if item.score is not None:
                    errors.append(
                        FieldError(field=field, message="미응시는 점수를 입력하지 않습니다.")
                    )
                continue
            if item.score is None:
                errors.append(FieldError(field=field, message="점수를 입력해주세요."))
            elif not item.score.is_finite() or item.score < 0:
                errors.append(FieldError(field=field, message="0 이상의 점수를 입력해주세요."))
            elif item.score.as_tuple().exponent < -2:
                errors.append(
                    FieldError(field=field, message="소수점 둘째 자리까지 입력할 수 있습니다.")
                )
            elif item.score > max_score:
                errors.append(
                    FieldError(field=field, message=f"만점({max_score})을 넘을 수 없습니다.")
                )
        return errors

    def save_grades(self, assessment_id: int, data: GradeBulk) -> int:
        # FOR SHARE: a concurrent max_score / date change waits for this batch.
        assessment = self._assessment(assessment_id, GRADE_WRITERS, lock="share")
        if assessment.assessment_date > date.today():
            self._abort(400, "ASSESSMENT_IN_FUTURE", "아직 시행되지 않은 평가입니다.")
        ids = {item.enrollment_id for item in data.items}
        eligibility = self.repo.enrollments_in_classroom(
            assessment.classroom_id, ids, assessment.assessment_date
        )
        existing = self.repo.grades_for_update(assessment.id, ids)
        errors, conflicts = self._validate_items(
            data.items, assessment.classroom_id, assessment.assessment_date, existing, eligibility
        )
        errors += self._score_errors(data.items, assessment.max_score)
        if errors:
            self._abort(400, "INVALID_GRADE_ITEMS", "점수 입력을 확인해주세요.", errors)
        if conflicts:
            self._abort(409, "VERSION_CONFLICT", CONFLICT_MESSAGE, conflicts)

        created: list[tuple[AssessmentResult, object]] = []
        changed = 0
        for item in data.items:
            current = existing.get(item.enrollment_id)
            if current is None:
                row = AssessmentResult(
                    assessment_id=assessment.id,
                    classroom_id=assessment.classroom_id,
                    max_score=assessment.max_score,
                    enrollment_id=item.enrollment_id,
                    result_status=item.result_status,
                    score=item.score,
                    memo=item.memo,
                )
                self.db.add(row)
                created.append((row, item))
                changed += 1
                continue
            if (
                current.result_status == item.result_status
                and current.score == item.score
                and current.memo == item.memo
            ):
                continue
            self._audit(
                "GRADE_UPDATED",
                "ASSESSMENT_RESULT",
                current.id,
                {
                    "assessment_id": assessment.id,
                    "enrollment_id": item.enrollment_id,
                    "before": {
                        "result_status": current.result_status,
                        "score": _json(current.score),
                        "version": current.version,
                    },
                    "after": {
                        "result_status": item.result_status,
                        "score": _json(item.score),
                        "version": current.version + 1,
                    },
                    "memo_changed": current.memo != item.memo,
                },
            )
            current.result_status = item.result_status
            current.score = item.score
            current.memo = item.memo
            changed += 1
        self._flush_or_conflict("GRADE_CONFLICT", CONFLICT_MESSAGE)
        for row, item in created:
            self._audit(
                "GRADE_RECORDED",
                "ASSESSMENT_RESULT",
                row.id,
                {
                    "assessment_id": assessment.id,
                    "enrollment_id": item.enrollment_id,
                    "after": {
                        "result_status": item.result_status,
                        "score": _json(item.score),
                        "version": 1,
                    },
                    "memo_set": item.memo is not None,
                },
            )
        self._commit_or_conflict("GRADE_CONFLICT", CONFLICT_MESSAGE)
        return changed

    # ------------------------------------------------------ enrollment pauses
    def pauses(self, classroom_id: int, enrollment_id: int):
        self._require_classroom(classroom_id)
        enrollment = self.repo.enrollment_in_classroom(classroom_id, enrollment_id)
        if enrollment is None:
            _fail(404, "ENROLLMENT_NOT_FOUND", "이 반의 수강 정보를 찾을 수 없습니다.")
        return enrollment, self.repo.pauses(enrollment.id)

    def _locked_enrollment(self, classroom_id: int, enrollment_id: int):
        self._require_classroom(classroom_id, ENROLLMENT_WRITERS)
        enrollment = self.repo.enrollment_in_classroom(classroom_id, enrollment_id, lock=True)
        if enrollment is None:
            self._abort(404, "ENROLLMENT_NOT_FOUND", "이 반의 수강 정보를 찾을 수 없습니다.")
        return enrollment

    def create_pause(self, classroom_id: int, enrollment_id: int, data: PauseCreate):
        enrollment = self._locked_enrollment(classroom_id, enrollment_id)
        today = date.today()
        if enrollment.status == "WITHDRAWN":
            self._abort(409, "ENROLLMENT_WITHDRAWN", "퇴원한 수강에는 휴원을 기록할 수 없습니다.")
        if data.paused_from > today or (data.resumed_on is not None and data.resumed_on > today):
            self._abort(400, "PAUSE_IN_FUTURE", "오늘 이후 날짜로는 휴원을 기록할 수 없습니다.")
        if data.resumed_on is not None and data.resumed_on <= data.paused_from:
            self._abort(400, "INVALID_PAUSE_DATES", "복귀일은 휴원 시작일 다음 날 이후여야 합니다.")
        if data.paused_from < enrollment.enrolled_at or (
            enrollment.ended_at is not None and data.paused_from > enrollment.ended_at
        ):
            self._abort(400, "PAUSE_OUTSIDE_ENROLLMENT", "수강 기간 안의 날짜를 입력해주세요.")
        if data.resumed_on is None and enrollment.status == "PAUSED":
            self._abort(409, "ALREADY_PAUSED", "이미 휴원 중입니다. 먼저 복귀 처리하세요.")
        status_before = enrollment.status
        pause = EnrollmentPause(
            enrollment_id=enrollment.id,
            paused_from=data.paused_from,
            resumed_on=data.resumed_on,
            source="MANUAL",
        )
        self.db.add(pause)
        # The pause row is written first, so the status trigger does not add a second one.
        self._flush_or_conflict("PAUSE_OVERLAP", "기존 휴원 기간과 겹칩니다.")
        if data.resumed_on is None:
            enrollment.status = "PAUSED"
            self._flush_or_conflict("PAUSE_OVERLAP", "기존 휴원 기간과 겹칩니다.")
        self._audit(
            "ENROLLMENT_PAUSE_RECORDED",
            "ENROLLMENT_PAUSE",
            pause.id,
            {
                "enrollment_id": enrollment.id,
                "paused_from": _json(data.paused_from),
                "resumed_on": _json(data.resumed_on),
                "status_before": status_before,
                "status_after": enrollment.status,
            },
        )
        self._commit_or_conflict("PAUSE_OVERLAP", "기존 휴원 기간과 겹칩니다.")
        self.db.refresh(pause)
        return pause

    def resume(self, classroom_id: int, enrollment_id: int, pause_id: int, data: PauseResume):
        enrollment = self._locked_enrollment(classroom_id, enrollment_id)
        pause = self.repo.open_pause(enrollment.id)
        if pause is None or pause.id != pause_id:
            self._abort(409, "PAUSE_NOT_OPEN", "진행 중인 휴원이 아닙니다.")
        if data.resumed_on <= pause.paused_from:
            self._abort(400, "INVALID_PAUSE_DATES", "복귀일은 휴원 시작일 다음 날 이후여야 합니다.")
        if data.resumed_on > date.today():
            self._abort(400, "PAUSE_IN_FUTURE", "오늘 이후 날짜로는 복귀를 기록할 수 없습니다.")
        status_before = enrollment.status
        pause.resumed_on = data.resumed_on
        self._flush_or_conflict("PAUSE_OVERLAP", "기존 휴원 기간과 겹칩니다.")
        if enrollment.status == "PAUSED":
            enrollment.status = "ACTIVE"  # trigger finds no open pause left, so it changes nothing
        self._audit(
            "ENROLLMENT_RESUMED",
            "ENROLLMENT_PAUSE",
            pause.id,
            {
                "enrollment_id": enrollment.id,
                "paused_from": _json(pause.paused_from),
                "resumed_on": _json(data.resumed_on),
                "status_before": status_before,
                "status_after": enrollment.status,
            },
        )
        self._commit_or_conflict("PAUSE_OVERLAP", "기존 휴원 기간과 겹칩니다.")
        self.db.refresh(pause)
        return pause

    # ------------------------------------------------------- class progress grid
    def progress(self, classroom_id: int, date_from: date, date_to: date) -> dict:
        """Student × lesson grid: attendance, assignment grades and linked test scores."""
        self._require_classroom(classroom_id)
        if date_from > date_to:
            _fail(400, "INVALID_DATE_RANGE", "조회 기간을 확인해주세요.")
        if (date_to - date_from).days >= MAX_PROGRESS_DAYS:
            _fail(400, "DATE_RANGE_TOO_LONG", "한 번에 최대 3개월까지 조회할 수 있습니다.")
        lessons = self.repo.progress_lessons(classroom_id, date_from, date_to)
        assessments = self.repo.progress_assessments(
            classroom_id, [lesson.id for lesson in lessons], date_from, date_to
        )
        linked: dict[int, list[Assessment]] = {}
        standalone: list[Assessment] = []
        for assessment in assessments:
            if assessment.lesson_id is None:
                standalone.append(assessment)
            else:
                linked.setdefault(assessment.lesson_id, []).append(assessment)

        def assessment_view(a: Assessment) -> dict:
            return {"id": a.id, "title": a.title, "max_score": a.max_score, "version": a.version}

        columns = [
            {
                "key": f"lesson:{lesson.id}",
                "kind": "LESSON",
                "lesson_id": lesson.id,
                "day": lesson.lesson_date,
                "session_no": lesson.session_no,
                "exam_round": lesson.exam_round,
                "topic": lesson.topic,
                "lesson_status": lesson.status,
                "assessments": [assessment_view(a) for a in linked.get(lesson.id, [])],
            }
            for lesson in lessons
        ] + [
            {
                "key": f"assessment:{a.id}",
                "kind": "ASSESSMENT",
                "lesson_id": None,
                "day": a.assessment_date,
                "session_no": None,
                "exam_round": None,
                "topic": None,
                "lesson_status": None,
                "assessments": [assessment_view(a)],
            }
            for a in standalone
        ]
        columns.sort(key=lambda c: (c["day"], c["kind"] != "LESSON", c["session_no"] or 0))

        results = {
            (r.lesson_id, r.enrollment_id): r
            for r in self.repo.lesson_results([lesson.id for lesson in lessons])
        }
        scores = {
            (r.assessment_id, r.enrollment_id): r
            for r in self.repo.assessment_results([a.id for a in assessments])
        }
        eligible = self.repo.eligibility_by_day(classroom_id, {c["day"] for c in columns})

        students = []
        for enrollment, student in self.repo.classroom_enrollments(classroom_id):
            cells, relevant = [], False
            for column in columns:
                result = (
                    results.get((column["lesson_id"], enrollment.id))
                    if column["kind"] == "LESSON"
                    else None
                )
                cell_scores = [
                    {
                        "assessment_id": a["id"],
                        "result_status": s.result_status,
                        "score": s.score,
                        "memo": s.memo,
                        "version": s.version,
                    }
                    for a in column["assessments"]
                    if (s := scores.get((a["id"], enrollment.id))) is not None
                ]
                is_eligible = (enrollment.id, column["day"]) in eligible
                relevant = relevant or is_eligible or result is not None or bool(cell_scores)
                cells.append(
                    {
                        "key": column["key"],
                        "eligible": is_eligible,
                        "attendance_status": result.attendance_status if result else None,
                        "prework_grade": result.prework_grade if result else None,
                        "weekly_grade": result.weekly_assignment_grade if result else None,
                        "result_version": result.version if result else None,
                        "scores": cell_scores,
                    }
                )
            # Students outside the period (and without records in it) are not listed.
            if relevant:
                students.append(
                    {
                        "enrollment_id": enrollment.id,
                        "student_id": student.id,
                        "student_name": student.name,
                        "enrollment_status": enrollment.status,
                        "cells": cells,
                    }
                )
        return {
            "classroom_id": classroom_id,
            "date_from": date_from,
            "date_to": date_to,
            "columns": columns,
            "students": students,
        }

    def update_record(self, lesson_id: int, enrollment_id: int, data: RecordUpdate) -> int:
        """Correct one student's attendance, assignment grades and lesson-linked scores at once."""
        touches_result = bool(
            {"attendance_status", "prework_grade", "weekly_grade"} & data.model_fields_set
        )
        if not touches_result and not data.scores:
            _fail(400, "NOTHING_TO_SAVE", "변경할 내용이 없습니다.")
        if "attendance_status" in data.model_fields_set and data.attendance_status is None:
            _fail(400, "VALIDATION_ERROR", "출결은 비울 수 없습니다. 출결 상태를 선택해주세요.")
        lesson = self._lesson(lesson_id, lock="share")
        role = self.principal.role
        needs = []
        if "attendance_status" in data.model_fields_set:
            needs.append(ATTENDANCE_WRITERS)
        if {"prework_grade", "weekly_grade"} & data.model_fields_set:
            needs.append(ASSIGNMENT_GRADE_WRITERS)
        if data.scores:
            needs.append(GRADE_WRITERS)
        if any(role not in writers for writers in needs):
            self._abort(403, "FORBIDDEN", "요청한 작업을 수행할 권한이 없습니다.")
        if lesson.status == "CANCELLED":
            self._abort(409, "LESSON_CANCELLED", "취소된 수업에는 기록할 수 없습니다.")
        if lesson.lesson_date > date.today():
            self._abort(400, "LESSON_IN_FUTURE", "아직 진행되지 않은 수업입니다.")
        eligibility = self.repo.enrollments_in_classroom(
            lesson.classroom_id, {enrollment_id}, lesson.lesson_date
        )
        if enrollment_id not in eligibility:
            self._abort(404, "ENROLLMENT_NOT_FOUND", "이 반의 학생이 아닙니다.")
        if not eligibility[enrollment_id]:
            self._abort(400, "NOT_ELIGIBLE", "해당 날짜의 수강 대상이 아닙니다.")

        changed = 0
        if touches_result:
            changed += self._update_lesson_result(lesson, enrollment_id, data)
        if data.scores:
            changed += self._update_linked_scores(lesson, enrollment_id, data)
        self._commit_or_conflict("RECORD_CONFLICT", CONFLICT_MESSAGE)
        return changed

    def _update_lesson_result(self, lesson: Lesson, enrollment_id: int, data: RecordUpdate) -> int:
        current = self.repo.attendance_for_update(lesson.id, {enrollment_id}).get(enrollment_id)
        if (current is None) != (data.result_version is None) or (
            current is not None and current.version != data.result_version
        ):
            self._abort(409, "VERSION_CONFLICT", CONFLICT_MESSAGE)
        fields = data.model_fields_set
        wanted = {
            "attendance_status": data.attendance_status
            if "attendance_status" in fields
            else (current.attendance_status if current else None),
            "prework_grade": data.prework_grade
            if "prework_grade" in fields
            else (current.prework_grade if current else None),
            "weekly_assignment_grade": data.weekly_grade
            if "weekly_grade" in fields
            else (current.weekly_assignment_grade if current else None),
        }
        if current is None:
            if wanted["attendance_status"] is None:
                self._abort(
                    400,
                    "ATTENDANCE_REQUIRED",
                    "출결을 먼저 입력해야 과제 등급을 기록할 수 있습니다.",
                )
            row = LessonResult(lesson_id=lesson.id, enrollment_id=enrollment_id, **wanted)
            self.db.add(row)
            self._flush_or_conflict("RECORD_CONFLICT", CONFLICT_MESSAGE)
            self._audit(
                "ATTENDANCE_RECORDED",
                "LESSON_RESULT",
                row.id,
                {
                    "lesson_id": lesson.id,
                    "enrollment_id": enrollment_id,
                    "after": {"status": wanted["attendance_status"], "version": 1},
                    "memo_set": False,
                },
            )
            if wanted["prework_grade"] or wanted["weekly_assignment_grade"]:
                self._audit(
                    "ASSIGNMENT_GRADES_UPDATED",
                    "LESSON_RESULT",
                    row.id,
                    {
                        "lesson_id": lesson.id,
                        "enrollment_id": enrollment_id,
                        "before": {"prework": None, "weekly": None},
                        "after": {
                            "prework": wanted["prework_grade"],
                            "weekly": wanted["weekly_assignment_grade"],
                        },
                    },
                )
            return 1
        changed = 0
        if wanted["attendance_status"] != current.attendance_status:
            self._audit(
                "ATTENDANCE_UPDATED",
                "LESSON_RESULT",
                current.id,
                {
                    "lesson_id": lesson.id,
                    "enrollment_id": enrollment_id,
                    "before": {"status": current.attendance_status, "version": current.version},
                    "after": {
                        "status": wanted["attendance_status"],
                        "version": current.version + 1,
                    },
                    "memo_changed": False,
                },
            )
            changed = 1
        before_grades = (current.prework_grade, current.weekly_assignment_grade)
        after_grades = (wanted["prework_grade"], wanted["weekly_assignment_grade"])
        if before_grades != after_grades:
            self._audit(
                "ASSIGNMENT_GRADES_UPDATED",
                "LESSON_RESULT",
                current.id,
                {
                    "lesson_id": lesson.id,
                    "enrollment_id": enrollment_id,
                    "before": {"prework": before_grades[0], "weekly": before_grades[1]},
                    "after": {"prework": after_grades[0], "weekly": after_grades[1]},
                },
            )
            changed = 1
        for name, value in wanted.items():
            setattr(current, name, value)
        self._flush_or_conflict("RECORD_CONFLICT", CONFLICT_MESSAGE)
        return changed

    def _update_linked_scores(self, lesson: Lesson, enrollment_id: int, data: RecordUpdate) -> int:
        changed = 0
        seen: set[int] = set()
        for index, item in enumerate(data.scores):
            if item.assessment_id in seen:
                self._abort(400, "INVALID_GRADE_ITEMS", "같은 평가가 중복되었습니다.")
            seen.add(item.assessment_id)
            assessment = self.repo.assessment(item.assessment_id, lock="share")
            if assessment is None or assessment.lesson_id != lesson.id:
                self._abort(400, "INVALID_GRADE_ITEMS", "이 수업에 연결된 평가가 아닙니다.")
            errors = self._score_errors([item], assessment.max_score)
            if errors:
                field = FieldError(field=f"scores.{index}.score", message=errors[0].message)
                self._abort(400, "INVALID_GRADE_ITEMS", "점수 입력을 확인해주세요.", [field])
            current = self.repo.grades_for_update(assessment.id, {enrollment_id}).get(enrollment_id)
            if (current is None) != (item.version is None) or (
                current is not None and current.version != item.version
            ):
                self._abort(409, "VERSION_CONFLICT", CONFLICT_MESSAGE)
            after = {"result_status": item.result_status, "score": _json(item.score)}
            if current is None:
                row = AssessmentResult(
                    assessment_id=assessment.id,
                    classroom_id=assessment.classroom_id,
                    max_score=assessment.max_score,
                    enrollment_id=enrollment_id,
                    result_status=item.result_status,
                    score=item.score,
                )
                self.db.add(row)
                self._flush_or_conflict("GRADE_CONFLICT", CONFLICT_MESSAGE)
                self._audit(
                    "GRADE_RECORDED",
                    "ASSESSMENT_RESULT",
                    row.id,
                    {
                        "assessment_id": assessment.id,
                        "enrollment_id": enrollment_id,
                        "after": {**after, "version": 1},
                        "memo_set": False,
                    },
                )
                changed += 1
                continue
            if current.result_status == item.result_status and current.score == item.score:
                continue
            self._audit(
                "GRADE_UPDATED",
                "ASSESSMENT_RESULT",
                current.id,
                {
                    "assessment_id": assessment.id,
                    "enrollment_id": enrollment_id,
                    "before": {
                        "result_status": current.result_status,
                        "score": _json(current.score),
                        "version": current.version,
                    },
                    "after": {**after, "version": current.version + 1},
                    "memo_changed": False,
                },
            )
            current.result_status = item.result_status
            current.score = item.score
            changed += 1
        self._flush_or_conflict("GRADE_CONFLICT", CONFLICT_MESSAGE)
        return changed

    # ---------------------------------------------------------- student history
    def student_records(self, classroom_id: int, student_id: int, limit: int):
        self._require_classroom(classroom_id)
        found = self.repo.enrollment_for_student(classroom_id, student_id)
        if found is None:
            _fail(404, "STUDENT_NOT_IN_CLASSROOM", "이 반의 학생이 아닙니다.")
        enrollment, student = found
        return (
            enrollment,
            student,
            self.repo.student_lessons(enrollment, limit),
            self.repo.student_assessments(enrollment, limit),
        )
