"""Workbook upload: preview (no writes) and confirm (one transaction, then drafts).

Rules agreed with the academy (Phase 8.1):
* Attendance is normally entered in the app. The workbook value is stored only when the app has
  no record; when both exist and differ, the app value is kept, the row is flagged, and no
  parent message draft is created for that student until it is resolved.
* Homework grades and test scores from the workbook are stored/updated per class and student.
  A blank test cell is "not entered", except for absent/excused students where it is NOT_TAKEN.
  Re-uploading therefore replaces values corrected in the app (decision 2026-11-20: keep the rule,
  but the preview lists each replaced value as ``app_changes`` and the audit keeps before/after).
* Students not active in the class need a decision: NEW (enrol), RETURNING (pause -> active)
  or EXCLUDE (nothing stored, no message).
* NEW always creates a new student; it never links an existing one (SEC-01, Phase 11-2-B-1).
  A name and school say nothing reliable about who a child is, and linking would let class staff
  pull a student of another class (and that guardian's address) into their own class. When the
  student key (name + school) is already taken, the row is flagged in the preview and NEW is
  refused; an administrator enrols an existing student under student / class management.
* Staff upload the same day's workbook several times (after each time slot) or one class at a
  time (decision 2026-11-20). Only the selected sheets (= time slots) are checked and saved, and a
  row that would write nothing is neither updated nor audited, so the stored data and audit trail
  are the same however the day's workbook is split into uploads.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import BigInteger, and_, cast, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models.tables import (
    Assessment,
    AssessmentResult,
    AuditLog,
    Classroom,
    Enrollment,
    EnrollmentPause,
    Lesson,
    LessonResult,
    NotificationTemplate,
    Student,
)
from app.errors import CompatibilityError
from app.modules.academics.repository import eligible_on
from app.modules.auth.dependencies import Principal
from app.modules.learningops.repository import LearningOpsRepository
from app.modules.notifications.schemas import GenerateRequest
from app.modules.notifications.service import NotificationService

from .workbook import ClassBlock, StudentRow, parse_workbook, school_of

ABSENCE = frozenset({"ABSENT", "EXCUSED"})
LABEL = {"PRESENT": "출석", "LATE": "지각", "ABSENT": "결석", "EXCUSED": "인정결석"}
GRADE_FIELDS = (
    ("prework", "prework_grade", "예습 과제"),
    ("weekly", "weekly_assignment_grade", "주간 과제"),
)
CHECK_VIOLATION = "23514"  # PostgreSQL SQLSTATE
STUDENT_KEY_INDEX = "uq_student_business_key"  # name + coalesce(school_name, '')
UPLOAD_LOCK_NAMESPACE = 11_303  # advisory-lock key prefix for "upload confirm of class N"
# Shown for a NEW row whose student key is taken. Says nothing about that student (class,
# contact): only that the upload cannot register this name and what to do instead.
EXISTING_STUDENT_TEXT = (
    "같은 이름(·학교)의 학생이 이미 등록되어 있어 업로드에서 신규로 등록할 수 없습니다 — "
    "관리자가 학생·반 관리에서 수강 등록하거나, 다른 학생이면 학교 정보로 구분해 등록해야 합니다. "
    "이번 업로드에서는 '제외'를 선택하세요."
)


def planned_scores(attendance: str, scores: dict) -> dict[str, tuple[str, Decimal | None]]:
    """What confirming stores per test column — the one place this rule lives (preview and
    confirm both use it): a number is SCORED; a blank is NOT_TAKEN for an absent / excused
    student and is otherwise "not entered", which leaves the app's value alone."""
    planned = {}
    for title, score in scores.items():
        if score is None and attendance not in ABSENCE:
            continue
        planned[title] = ("SCORED", Decimal(score)) if score is not None else ("NOT_TAKEN", None)
    return planned


def score_text(status: str, score) -> str:
    if status == "NOT_TAKEN":
        return "미응시"
    return format(Decimal(score).normalize(), "f")


class LessonUploadService:
    def __init__(self, db: Session, principal: Principal, request_id: str | None = None):
        self.db = db
        self.principal = principal
        self.request_id = request_id
        self.access = LearningOpsRepository(db)

    # ------------------------------------------------------------- helpers
    def _audit(self, event: str, target_type: str, target_id, details: dict) -> None:
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

    def _classroom(self, name: str, class_type: str | None) -> tuple[Classroom | None, str | None]:
        rows = list(
            self.db.scalars(
                select(Classroom).where(Classroom.name == name, Classroom.is_active.is_(True))
            )
        )
        exact = [row for row in rows if row.class_type == class_type]
        if exact:
            return exact[0], None
        if rows:
            return None, "같은 이름의 반이 있지만 수업유형(정규/내신 대비)이 다릅니다"
        return None, None

    def _lesson(self, classroom_id: int, day: date, *, lock: bool = False) -> Lesson | None:
        query = select(Lesson).where(
            Lesson.classroom_id == classroom_id,
            Lesson.lesson_date == day,
            Lesson.exam_round.is_(None),
            Lesson.session_no == 1,  # uploads always target session 1 (Phase 7.1 rule)
        )
        return self.db.scalar(query.with_for_update() if lock else query)

    def _roster(self, classroom_id: int, day: date):
        rows = self.db.execute(
            select(Enrollment, Student, eligible_on(day).label("eligible"))
            .join(Student, Student.id == Enrollment.student_id)
            .where(Enrollment.classroom_id == classroom_id)
        ).all()
        by_name: dict[str, list] = {}
        for row in rows:
            by_name.setdefault(" ".join(row.Student.name.split()), []).append(row)
        return by_name

    def _taken_student_keys(self, names: list[str], school: str | None) -> set[str]:
        """Names whose student key (name + school, the DB's unique key) already exists. Only
        whether the key is taken is used — never which student or class holds it."""
        if not names:
            return set()
        return set(
            self.db.scalars(
                select(Student.name).where(
                    Student.name.in_(names),
                    func.coalesce(Student.school_name, "") == (school or ""),
                )
            )
        )

    # -------------------------------------------------------------- analysis
    @staticmethod
    def sheet_summaries(blocks: list[ClassBlock]) -> list[dict]:
        """Sheets (time slots) of the workbook that hold class blocks, in workbook order."""
        sheets: dict[str, dict] = {}
        for block in blocks:
            sheet = sheets.setdefault(
                block.sheet, {"name": block.sheet, "class_names": [], "student_rows": 0}
            )
            sheet["class_names"].append(block.class_name)
            sheet["student_rows"] += sum(1 for s in block.students if not s.empty)
        return list(sheets.values())

    @staticmethod
    def _selected(blocks: list[ClassBlock], sheets: list[str] | None) -> list[ClassBlock]:
        """Blocks of the chosen sheets; ``None`` = every sheet (API callers without a choice)."""
        if sheets is None:
            return blocks
        known = {block.sheet for block in blocks}
        unknown = [name for name in dict.fromkeys(sheets) if name not in known]
        if unknown:
            raise CompatibilityError(
                400,
                "UNKNOWN_SHEET",
                "엑셀에 반 블록이 있는 시트가 아닙니다: " + ", ".join(unknown),
            )
        chosen = set(sheets)
        return [block for block in blocks if block.sheet in chosen]

    def analyse(self, content: bytes, day: date, sheets: list[str] | None = None):
        """Parse and match the chosen sheets against the database. Writes nothing.

        Returns (every parsed block, views of the chosen sheets, blocking issues of those sheets).
        An error in a sheet that was not chosen never blocks the upload.
        """
        if day > date.today():
            raise CompatibilityError(400, "LESSON_IN_FUTURE", "수업일은 오늘 이후일 수 없습니다.")
        parsed = parse_workbook(content)
        views, blocking = self._match(parsed, day, sheets)
        return parsed, views, blocking

    def _match(self, parsed: list[ClassBlock], day: date, sheets: list[str] | None):
        """Views and blocking issues of the chosen sheets, read from the database now."""
        blocks = self._selected(parsed, sheets)
        views, blocking = [], []
        for block in blocks:
            view = self._analyse_block(block, day)
            views.append(view)
            label = f"[{block.sheet}] {block.class_name or '(이름 없음)'}"
            blocking += [f"{label}: {issue}" for issue in view["issues"]]
            undecided = [r for r in view["rows"] if r["status"] == "UNREGISTERED"]
            if undecided:
                view["needs_decision"] = [r["key"] for r in undecided]
        return views, blocking

    def _serialize_classes(self, views: list[dict]) -> None:
        """Phase 11-3-B (INT-04): one confirm at a time per class. A transaction-scoped advisory
        lock per classroom (sorted ids, so two uploads never wait on each other in a cycle;
        released at commit / rollback; no table or schema involved). A second confirm of the
        same workbook waits here and then analyses the committed result, so it answers like a
        sequential re-send (200, rows unchanged) instead of failing on a student it just
        registered itself."""
        for classroom_id in sorted({v["classroom_id"] for v in views if v["classroom_id"]}):
            key = (UPLOAD_LOCK_NAMESPACE << 32) + classroom_id
            self.db.execute(select(func.pg_advisory_xact_lock(cast(key, BigInteger))))

    def _analyse_block(self, block: ClassBlock, day: date) -> dict:
        issues = list(block.issues)
        classroom, type_issue = (
            self._classroom(block.class_name, block.class_type)
            if block.class_type
            else (None, None)
        )
        lesson = None
        roster: dict = {}
        accessible = False
        if type_issue:
            issues.append(type_issue)
        elif block.class_type and classroom is None:
            issues.append("프로그램에 등록되지 않은 반입니다 (관리자가 먼저 반을 등록해야 합니다)")
        if classroom is not None:
            if not self.access.can_access_classroom(
                classroom.id, self.principal.user_id, self.principal.role
            ):
                issues.append("담당 반이 아닙니다")
            else:
                accessible = True
                lesson = self._lesson(classroom.id, day)
                if lesson is not None and lesson.status == "CANCELLED":
                    issues.append("이 날짜 수업이 취소 상태입니다")
                roster = self._roster(classroom.id, day)
        results, assessments, stored_scores, max_changes = {}, {}, {}, []
        if lesson is not None:
            results = {
                r.enrollment_id: r
                for r in self.db.scalars(
                    select(LessonResult).where(LessonResult.lesson_id == lesson.id)
                )
            }
            # Values already in the app that this workbook would replace (shown, not blocked).
            linked = select(Assessment).where(Assessment.lesson_id == lesson.id)
            assessments = {a.title: a for a in self.db.scalars(linked)}
            if assessments:
                stored_scores = {
                    (r.assessment_id, r.enrollment_id): r
                    for r in self.db.scalars(
                        select(AssessmentResult).where(
                            AssessmentResult.assessment_id.in_([a.id for a in assessments.values()])
                        )
                    )
                }
            for test in block.tests:
                current = assessments.get(test.title)
                if current is None or current.max_score == Decimal(test.total):
                    continue
                max_changes.append(
                    {
                        "title": test.title,
                        "app": score_text("SCORED", current.max_score),
                        "upload": str(test.total),
                    }
                )
                highest = max(
                    (
                        r.score
                        for (assessment_id, _), r in stored_scores.items()
                        if assessment_id == current.id and r.score is not None
                    ),
                    default=None,
                )
                if highest is not None and highest > test.total:
                    issues.append(
                        f"'{test.title}' 만점이 {score_text('SCORED', current.max_score)} → "
                        f"{test.total}(으)로 바뀌는데, 이미 입력된 점수"
                        f"({score_text('SCORED', highest)})보다 낮습니다 — 머리글의 문항 수를 "
                        "확인하세요"
                    )
        rows = [
            self._analyse_row(student, roster, results, assessments, stored_scores)
            for student in block.students
        ]
        names = [r["name"] for r in rows if r["status"] != "SKIPPED"]
        for row in rows:
            if row["status"] != "SKIPPED" and names.count(row["name"]) > 1:
                row["status"] = "INVALID"
                row["issues"].append("같은 반에 같은 이름이 두 번 있습니다")
        # A student not in this class whose key is taken cannot be registered as NEW (SEC-01).
        # Checked only for the user's own classes; confirm runs this again, so a student added
        # after the preview is caught too.
        candidates = [r for r in rows if r["status"] == "UNREGISTERED" and r["_match"] is None]
        if accessible and candidates:
            taken = self._taken_student_keys(
                [r["name"] for r in candidates], school_of(classroom.name, classroom.class_type)
            )
            for row in candidates:
                if row["name"] in taken:
                    row["existing_student_conflict"] = True
                    row["warnings"].append(EXISTING_STUDENT_TEXT)
        return {
            "sheet": block.sheet,
            "row": block.row,
            "class_name": block.class_name,
            "class_type": block.class_type,
            "classroom_id": classroom.id if classroom else None,
            "tests": [{"title": t.title, "total": t.total} for t in block.tests],
            "issues": issues,
            "rows": rows,
            "max_score_changes": max_changes,
            "_classroom": classroom,
            "_roster": roster,
        }

    def _analyse_row(
        self,
        student: StudentRow,
        roster: dict,
        results: dict,
        assessments: dict | None = None,
        stored_scores: dict | None = None,
    ) -> dict:
        view = {
            "key": student.key,
            "row": student.row,
            "name": student.name,
            "attendance": student.attendance,
            "prework": student.prework,
            "weekly": student.weekly,
            "scores": dict(student.scores),
            "issues": list(student.issues),
            "warnings": [],
            "app_attendance": None,
            "attendance_mismatch": False,
            "returning_available": False,
            "app_changes": [],
            "unchanged": False,
            "existing_student_conflict": False,
            "_match": None,
        }
        if student.empty:
            view.update(
                status="SKIPPED", issues=[], warnings=["이름 칸 외에 내용이 없어 건너뜁니다"]
            )
            return view
        if view["issues"]:
            view["status"] = "INVALID"
            return view
        matches = roster.get(student.name, [])
        if len(matches) > 1:
            view["status"] = "INVALID"
            view["issues"].append("이 반에 같은 이름의 학생이 여러 명 등록되어 있습니다")
            return view
        match = matches[0] if matches else None
        if match is not None and match.eligible:
            view["status"] = "MATCHED"
            view["_match"] = match
            existing = results.get(match.Enrollment.id)
            if existing is not None:
                view["app_attendance"] = existing.attendance_status
                if existing.attendance_status != student.attendance:
                    view["attendance_mismatch"] = True
                    view["warnings"].append(
                        f"출결 불일치: 프로그램 '{LABEL[existing.attendance_status]}', "
                        f"엑셀 '{LABEL[student.attendance]}' — "
                        "프로그램 값을 유지하고 안내 초안은 만들지 않습니다"
                    )
            view["app_changes"] = self._app_changes(
                student, existing, match.Enrollment.id, assessments or {}, stored_scores or {}
            )
            view["unchanged"] = self._unchanged(
                student, existing, match.Enrollment.id, assessments or {}, stored_scores or {}
            )
            return view
        view["status"] = "UNREGISTERED"
        view["_match"] = match
        view["returning_available"] = match is not None and match.Enrollment.status == "PAUSED"
        if match is not None and match.Enrollment.status == "WITHDRAWN":
            view["warnings"].append("퇴원 처리된 학생입니다 — 신규·복귀로 처리할 수 없습니다")
        return view

    @staticmethod
    def _app_changes(
        student: StudentRow, existing, enrollment_id: int, assessments: dict, stored_scores: dict
    ) -> list[dict]:
        """App values this row would overwrite on confirm — same rules as ``_apply_row``."""
        changes = []
        if existing is not None:
            for field, attribute, label in GRADE_FIELDS:
                current, incoming = getattr(existing, attribute), getattr(student, field)
                if incoming is not None and current is not None and current != incoming:
                    changes.append(
                        {"field": field, "label": label, "app": current, "upload": incoming}
                    )
        # Absence is judged on the attendance that will be kept (the app's, when it has one).
        attendance = existing.attendance_status if existing is not None else student.attendance
        for title, (status, value) in planned_scores(attendance, student.scores).items():
            assessment = assessments.get(title)
            stored = stored_scores.get((assessment.id, enrollment_id)) if assessment else None
            if stored is not None and (stored.result_status, stored.score) != (status, value):
                changes.append(
                    {
                        "field": "score",
                        "label": title,
                        "app": score_text(stored.result_status, stored.score),
                        "upload": score_text(status, value),
                    }
                )
        return changes

    @staticmethod
    def _unchanged(
        student: StudentRow, existing, enrollment_id: int, assessments: dict, stored_scores: dict
    ) -> bool:
        """Confirming this row would write nothing — same rules as ``_apply_row``: the app
        already has this lesson's row, every non-blank grade and every planned score is equal."""
        if existing is None:
            return False
        for field, attribute, _ in GRADE_FIELDS:
            incoming = getattr(student, field)
            if incoming is not None and incoming != getattr(existing, attribute):
                return False
        for title, planned in planned_scores(existing.attendance_status, student.scores).items():
            assessment = assessments.get(title)
            stored = stored_scores.get((assessment.id, enrollment_id)) if assessment else None
            if stored is None or (stored.result_status, stored.score) != planned:
                return False
        return True

    @staticmethod
    def public_view(views: list[dict]) -> list[dict]:
        return [
            {
                **{
                    k: v
                    for k, v in block.items()
                    if not k.startswith("_") and k != "needs_decision"
                },
                "rows": [
                    {k: v for k, v in r.items() if not k.startswith("_")} for r in block["rows"]
                ],
            }
            for block in views
        ]

    # ---------------------------------------------------------------- confirm
    def confirm(
        self, content: bytes, day: date, decisions: dict[str, str], sheets: list[str] | None = None
    ):
        parsed, views, blocking = self.analyse(content, day, sheets)
        if views:
            # Serialise per class, then analyse again from what is committed now: everything
            # below (decisions, NEW / RETURNING checks, writes) uses data read under the lock.
            self._serialize_classes(views)
            views, blocking = self._match(parsed, day, sheets)
        if blocking:
            raise CompatibilityError(
                400,
                "UPLOAD_HAS_ERRORS",
                "엑셀의 오류를 고친 뒤 다시 올려주세요: " + " / ".join(blocking),
            )
        missing = [
            r["key"]
            for v in views
            for r in v["rows"]
            if r["status"] == "UNREGISTERED" and r["key"] not in decisions
        ]
        if missing:
            raise CompatibilityError(
                400,
                "DECISION_REQUIRED",
                "등록되지 않은 학생의 처리 방법을 선택해주세요: " + ", ".join(missing),
            )
        summary = {
            "saved_rows": 0,  # rows that wrote something
            "unchanged_rows": 0,  # rows equal to the app: nothing written, nothing audited
            "new_students": 0,
            "returned_students": 0,
            "excluded_rows": 0,
            "attendance_mismatches": [],
        }
        draft_targets: list[tuple[str, Lesson, list[int]]] = []
        try:
            for view in views:
                saved = self._apply_block(view, day, decisions, summary)
                if saved is not None:
                    draft_targets.append(saved)
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            diag = getattr(exc.orig, "diag", None)
            if getattr(diag, "constraint_name", None) == STUDENT_KEY_INDEX:
                # A same-key student was registered between the check and this insert.
                raise CompatibilityError(
                    409,
                    "EXISTING_STUDENT_ELSEWHERE",
                    f"저장하지 않았습니다. {EXISTING_STUDENT_TEXT} 다시 미리보기해 확인해주세요.",
                ) from exc
            if getattr(exc.orig, "sqlstate", None) == CHECK_VIOLATION:
                # e.g. a lowered max score below a stored score (preview normally blocks this;
                # here only if another user saved a higher score in between).
                raise CompatibilityError(
                    409,
                    "MAX_SCORE_BELOW_EXISTING",
                    "엑셀 머리글의 만점(문항 수)이 이미 입력된 점수보다 낮아 저장하지 않았습니다. "
                    "다시 미리보기해 확인해주세요.",
                ) from exc
            raise CompatibilityError(
                409,
                "UPLOAD_CONFLICT",
                "다른 사용자가 같은 수업을 동시에 저장했습니다. 다시 시도해주세요.",
            ) from exc
        except CompatibilityError:
            self.db.rollback()
            raise
        summary["drafts"] = [
            self._drafts(name, lesson, ids, view_type)
            for name, lesson, ids, view_type in draft_targets
        ]
        return summary

    def _apply_block(self, view: dict, day: date, decisions: dict, summary: dict):
        classroom: Classroom = view["_classroom"]
        rows = [r for r in view["rows"] if r["status"] in ("MATCHED", "UNREGISTERED")]
        if classroom is None or not rows:
            return None
        lesson = self._lesson(classroom.id, day, lock=True)
        block_wrote = lesson is None
        if lesson is None:
            lesson = Lesson(classroom_id=classroom.id, lesson_date=day, status="COMPLETED")
            self.db.add(lesson)
            self.db.flush()
        assessments, max_changes, created = self._assessments(lesson, classroom, view["tests"], day)
        block_wrote = block_wrote or created or bool(max_changes)
        draft_ids, written = [], 0
        for row in rows:
            enrollment = self._resolve(row, classroom, day, decisions, summary)
            if enrollment is None:
                continue
            mismatch, wrote = self._apply_row(lesson, enrollment, row, assessments)
            if wrote:
                summary["saved_rows"] += 1
                written += 1
            else:
                summary["unchanged_rows"] += 1
            if mismatch:
                summary["attendance_mismatches"].append(f"{view['class_name']} {row['key']}")
            else:
                # Unchanged rows stay draft targets: a student who had no draft (e.g. no
                # guardian e-mail then) gets one now; existing drafts are never duplicated.
                draft_ids.append(enrollment.id)
        if block_wrote or written:
            self._audit(
                "LESSON_UPLOAD_APPLIED",
                "LESSON",
                lesson.id,
                {
                    "classroom_id": classroom.id,
                    "rows": len(rows),
                    "rows_written": written,
                    "drafts_planned": len(draft_ids),
                    "max_score_changes": max_changes,
                },
            )
        return view["class_name"], lesson, draft_ids, classroom.class_type

    def _assessments(self, lesson: Lesson, classroom: Classroom, tests: list[dict], day: date):
        found, max_changes, created = {}, [], False
        for test in tests:
            row = self.db.scalar(
                select(Assessment)
                .where(Assessment.lesson_id == lesson.id, Assessment.title == test["title"])
                .with_for_update()
            )
            if row is None:
                row = Assessment(
                    classroom_id=classroom.id,
                    lesson_id=lesson.id,
                    title=test["title"],
                    assessment_date=day,
                    max_score=Decimal(test["total"]),
                )
                self.db.add(row)
                self.db.flush()
                created = True
            elif row.max_score != Decimal(test["total"]):
                max_changes.append(
                    {
                        "assessment_id": row.id,
                        "before": score_text("SCORED", row.max_score),
                        "after": str(test["total"]),
                    }
                )
                row.max_score = Decimal(test["total"])  # DB rejects it if a stored score exceeds it
                self.db.flush()
            found[test["title"]] = row
        return found, max_changes, created

    def _resolve(self, row: dict, classroom: Classroom, day: date, decisions: dict, summary: dict):
        if row["status"] == "MATCHED":
            return row["_match"].Enrollment
        decision = decisions[row["key"]]
        match = row["_match"]
        if decision == "EXCLUDE":
            summary["excluded_rows"] += 1
            return None
        if decision == "NEW":
            if match is not None:
                raise CompatibilityError(
                    400,
                    "NOT_A_NEW_STUDENT",
                    f"{row['key']}: 이미 이 반에 등록된 학생입니다. 복귀 학생으로 처리하세요.",
                )
            if row["existing_student_conflict"]:
                raise CompatibilityError(
                    400, "EXISTING_STUDENT_ELSEWHERE", f"{row['key']}: {EXISTING_STUDENT_TEXT}"
                )
            # The school follows the class: an exam-prep class is for one school ("00고2 토10"
            # -> "00고"); regular classes carry no school. (name, school) is the student key.
            # Always a new row — an existing student is never linked here (SEC-01). If another
            # request took the key since the check above, the unique index refuses this insert
            # and the whole upload is rolled back (see ``confirm``).
            school = school_of(classroom.name, classroom.class_type)
            student = Student(name=row["name"], school_name=school)
            self.db.add(student)
            self.db.flush()
            enrollment = Enrollment(
                student_id=student.id, classroom_id=classroom.id, status="ACTIVE", enrolled_at=day
            )
            self.db.add(enrollment)
            self.db.flush()
            self._audit(
                "ENROLLMENT_CREATED_FROM_UPLOAD",
                "ENROLLMENT",
                enrollment.id,
                {
                    "classroom_id": classroom.id,
                    "enrolled_at": day.isoformat(),
                    "school_assigned": school is not None,
                },
            )
            summary["new_students"] += 1
            return enrollment
        # RETURNING
        if match is None or match.Enrollment.status != "PAUSED":
            raise CompatibilityError(
                400,
                "NOT_A_RETURNING_STUDENT",
                f"{row['key']}: 휴원 중인 학생이 아니어서 복귀로 처리할 수 없습니다.",
            )
        enrollment = self.db.scalar(
            select(Enrollment).where(Enrollment.id == match.Enrollment.id).with_for_update()
        )
        pause = self.db.scalar(
            select(EnrollmentPause).where(
                and_(
                    EnrollmentPause.enrollment_id == enrollment.id,
                    EnrollmentPause.resumed_on.is_(None),
                )
            )
        )
        if pause is not None:
            if day <= pause.paused_from:
                raise CompatibilityError(
                    400,
                    "INVALID_PAUSE_DATES",
                    f"{row['key']}: 수업일이 휴원 시작일({pause.paused_from}) 이후여야 합니다.",
                )
            pause.resumed_on = day  # written first, so the status trigger has nothing to close
            self.db.flush()
        enrollment.status = "ACTIVE"
        self.db.flush()
        self._audit(
            "ENROLLMENT_RESUMED",
            "ENROLLMENT_PAUSE" if pause else "ENROLLMENT",
            pause.id if pause else enrollment.id,
            {"enrollment_id": enrollment.id, "resumed_on": day.isoformat(), "source": "UPLOAD"},
        )
        summary["returned_students"] += 1
        return enrollment

    def _apply_row(
        self, lesson: Lesson, enrollment: Enrollment, row: dict, assessments: dict
    ) -> tuple[bool, bool]:
        """Store one row. Returns (attendance mismatch, wrote anything). A row equal to the app
        writes nothing and leaves no audit row (re-uploads and split uploads stay quiet)."""
        result = self.db.scalar(
            select(LessonResult)
            .where(LessonResult.lesson_id == lesson.id, LessonResult.enrollment_id == enrollment.id)
            .with_for_update()
        )
        mismatch = wrote = False
        # App values replaced by the workbook (before → after), kept in the audit row so a
        # correction made in the app and undone by a re-upload can be traced.
        changed: list[dict] = []
        if result is None:
            result = LessonResult(
                lesson_id=lesson.id,
                enrollment_id=enrollment.id,
                attendance_status=row["attendance"],
            )
            self.db.add(result)
            wrote = True
        elif result.attendance_status != row["attendance"]:
            mismatch = True  # keep the attendance entered in the app
        for field, attribute, label in GRADE_FIELDS:
            incoming = row[field]
            current = getattr(result, attribute)
            if incoming is None or current == incoming:
                continue
            if current is not None:
                changed.append(
                    {"field": field, "label": label, "before": current, "after": incoming}
                )
            setattr(result, attribute, incoming)
            wrote = True
        self.db.flush()
        for title, (status, value) in planned_scores(
            result.attendance_status, row["scores"]
        ).items():
            assessment = assessments[title]
            existing = self.db.scalar(
                select(AssessmentResult)
                .where(
                    AssessmentResult.assessment_id == assessment.id,
                    AssessmentResult.enrollment_id == enrollment.id,
                )
                .with_for_update()
            )
            if existing is None:
                self.db.add(
                    AssessmentResult(
                        assessment_id=assessment.id,
                        classroom_id=assessment.classroom_id,
                        max_score=assessment.max_score,
                        enrollment_id=enrollment.id,
                        result_status=status,
                        score=value,
                    )
                )
                wrote = True
            elif (existing.result_status, existing.score) != (status, value):
                changed.append(
                    {
                        "field": "score",
                        "label": title,
                        "before": score_text(existing.result_status, existing.score),
                        "after": score_text(status, value),
                    }
                )
                existing.result_status, existing.score = status, value
                wrote = True
        self.db.flush()
        if not wrote:
            return mismatch, False
        self._audit(
            "UPLOAD_ROW_APPLIED",
            "LESSON_RESULT",
            result.id,
            {
                "lesson_id": lesson.id,
                "enrollment_id": enrollment.id,
                "attendance_kept_from_app": mismatch,
                "changed": changed,
            },
        )
        return mismatch, True

    def _drafts(self, class_name: str, lesson: Lesson, enrollment_ids: list[int], class_type: str):
        if not enrollment_ids:
            return {"class_name": class_name, "created": 0, "skipped": []}
        template = self.db.scalar(
            select(NotificationTemplate).where(
                NotificationTemplate.default_for_class_type == class_type,
                NotificationTemplate.is_active.is_(True),
            )
        )
        if template is None:
            return {
                "class_name": class_name,
                "created": 0,
                "skipped": ["이 수업유형의 기본 템플릿이 없습니다 (템플릿 탭에서 지정)"],
            }
        service = NotificationService(self.db, self.principal, self.request_id)
        created_total, notes = 0, []
        for start in range(0, len(enrollment_ids), 100):  # draft API batch limit
            batch = enrollment_ids[start : start + 100]
            try:
                created, skipped = service.create_drafts(
                    lesson.id, GenerateRequest(template_id=template.id, enrollment_ids=batch)
                )
            except CompatibilityError as error:
                # The workbook data is already committed; drafts can be generated again later.
                notes.append(f"초안 생성 실패: {error.message}")
                continue
            created_total += len(created)
            notes += [
                f"{s['student_name'] or s['enrollment_id']}: {', '.join(s['reasons'])}"
                for s in skipped
            ]
        return {"class_name": class_name, "created": created_total, "skipped": notes}
