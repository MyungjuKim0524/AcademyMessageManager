"""Read-only analytics: authorisation, period rules and the rate formulas.

Formulas (docs/phase10-metric-definitions.md):
* record_rate     = recorded / target
* attendance_rate = (present + late) / (recorded - excused)   — user decision 2026-11-20:
  late counts as attended, excused absences are left out; unrecorded is never an absence.
* entry_rate      = (scored + not_taken) / target             — not for upcoming assessments
A zero denominator gives ``None`` (shown as "N/A"), never 0%. Rates are computed from integer
counts with Decimal and rounded half-up to one decimal place.
"""

from collections import defaultdict
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from app.errors import CompatibilityError
from app.modules.academics.repository import AcademicsRepository
from app.modules.auth.dependencies import Principal

from .repository import ATTENDANCE_STATUSES, AnalyticsRepository

MAX_PERIOD_DAYS = 366

# 관심 필요 학생 (user decision 2026-11-20, revised the same day): judged on each student's most
# recent sessions instead of calendar weeks, so classes held once or twice a week mean the same.
WATCH_LOOKBACK_DAYS = 92  # only records of the last 3 months are considered
WATCH_RECENT = 4  # the last 4 scored sessions per 평가 항목 / the last 4 lessons
WATCH_MIN_SCORED = 3  # score rules need at least 3 scored sessions
WATCH_GAP = Decimal(15)  # %p below the class average of the same session
WATCH_LOW_MIN = 3  # … in 3 of the last 4 sessions
WATCH_DROP = Decimal(10)  # last 3 sessions kept falling, by 10%p or more in total
WATCH_LESSON_MIN = 2  # homework C / absence in 2 of the last 4 lessons
WATCH_RULES = (
    "학생별 최근 기록으로 판단합니다"
    "(평가 항목별 최근 4회차, 최근 4회 수업, 최근 3개월 기록 안에서).",
    "점수: 같은 평가 항목의 최근 4회 중 3회 이상 같은 회차 반 평균보다 15%p 이상 낮음"
    " (점수가 3회 이상 있을 때만 판단)",
    "점수 흐름: 같은 평가 항목의 최근 3회 동안 반 평균 대비 위치가 계속 낮아졌고"
    " 합쳐서 10%p 이상 하락",
    "과제: 최근 4회 수업 중 예습 또는 주간 과제 C 등급이 2회 이상",
    "출결: 최근 4회 수업 중 결석 또는 (출석했지만) 미응시가 2회 이상 (인정결석은 세지 않음)",
)
HELD_LESSON_RULE = "취소되지 않았고 미래가 아니며, 완료 상태이거나 출결이 1건 이상 있는 수업"
ATTENDANCE_RATE_RULE = "(출석 + 지각) ÷ (입력된 출결 − 인정결석). 미입력은 제외(결석 아님)"
COUNT_KEYS = (
    "target",
    "recorded",
    "unrecorded",
    *(s.lower() for s in ATTENDANCE_STATUSES),
    "outside_records",
)


def rate(numerator: int, denominator: int) -> Decimal | None:
    if denominator <= 0:
        return None
    return (Decimal(numerator) * 100 / Decimal(denominator)).quantize(
        Decimal("0.1"), rounding=ROUND_HALF_UP
    )


def with_rates(counts: dict) -> dict:
    counts = {key: int(counts[key]) for key in COUNT_KEYS}
    counts["record_rate"] = rate(counts["recorded"], counts["target"])
    counts["attendance_rate"] = rate(
        counts["present"] + counts["late"], counts["recorded"] - counts["excused"]
    )
    return counts


def _fail(status: int, code: str, message: str):
    raise CompatibilityError(status, code, message)


class AnalyticsService:
    def __init__(self, db: Session, principal: Principal):
        self.db = db
        self.principal = principal
        self.repo = AnalyticsRepository(db)
        self.academics = AcademicsRepository(db)

    # ------------------------------------------------------------------ guards
    def _require_classroom(self, classroom_id: int) -> None:
        """Same rule and answers as the 수업·출결·성적 screens (AcademicsService)."""
        classroom = self.academics.classroom(classroom_id)
        if classroom is None or not classroom.is_active:
            _fail(404, "CLASSROOM_NOT_FOUND", "반을 찾을 수 없습니다.")
        if not self.academics.can_access(classroom_id, self.principal.user_id, self.principal.role):
            _fail(403, "CLASSROOM_ACCESS_DENIED", "담당 반에만 접근할 수 있습니다.")

    def _student(self, classroom_id: int, student_id: int):
        # Checked after the classroom: a student of another class is "not found" here, so an
        # id from a class the user cannot see reveals nothing.
        found = self.repo.enrollment_of_student(classroom_id, student_id)
        if found is None:
            _fail(404, "STUDENT_NOT_IN_CLASSROOM", "이 반의 학생이 아닙니다.")
        return found

    @staticmethod
    def _period(date_from: date, date_to: date) -> None:
        if date_from > date_to:
            _fail(400, "INVALID_DATE_RANGE", "조회 기간을 확인해주세요.")
        if (date_to - date_from).days >= MAX_PERIOD_DAYS:
            _fail(400, "DATE_RANGE_TOO_LONG", "한 번에 최대 1년까지 조회할 수 있습니다.")

    # -------------------------------------------------------------- attendance
    def attendance(self, classroom_id: int, date_from: date, date_to: date) -> dict:
        self._require_classroom(classroom_id)
        self._period(date_from, date_to)
        today = date.today()
        until = min(date_to, today)  # attendance cannot be taken for future lessons
        students = [
            {
                "enrollment_id": row["enrollment_id"],
                "student_id": row["student_id"],
                "student_name": row["student_name"],
                "enrollment_status": row["enrollment_status"],
                **with_rates(row),
            }
            for row in self.repo.attendance_by_student(classroom_id, date_from, until, today)
        ]
        totals = {key: sum(s[key] for s in students) for key in COUNT_KEYS}
        held, not_held = self.repo.lesson_counts(classroom_id, date_from, until, today)
        return {
            "classroom_id": classroom_id,
            "date_from": date_from,
            "date_to": date_to,
            "counted_until": until if until >= date_from else date_from - timedelta(days=1),
            "policy": {"held_lesson": HELD_LESSON_RULE, "attendance_rate": ATTENDANCE_RATE_RULE},
            "summary": with_rates(totals),
            "held_lessons": held,
            "not_held_lessons": not_held,
            "students": students,
            "lessons": [
                dict(row)
                for row in self.repo.attendance_by_lesson(classroom_id, date_from, until, today)
            ],
        }

    def student_attendance(
        self, classroom_id: int, student_id: int, date_from: date, date_to: date
    ) -> dict:
        self._require_classroom(classroom_id)
        self._period(date_from, date_to)
        enrollment = self._student(classroom_id, student_id)
        today = date.today()
        until = min(date_to, today)
        rows = self.repo.attendance_history(classroom_id, enrollment.id, date_from, until, today)
        counts = {key: 0 for key in COUNT_KEYS}
        for row in rows:
            if row["eligible"]:
                counts["target"] += 1
                if row["status"] is None:
                    counts["unrecorded"] += 1
                else:
                    counts["recorded"] += 1
                    counts[row["status"].lower()] += 1
            elif row["status"] is not None:
                counts["outside_records"] += 1
        return {
            "classroom_id": classroom_id,
            "student_id": enrollment.student_id,
            "student_name": enrollment.name,
            "enrollment_id": enrollment.id,
            "date_from": date_from,
            "date_to": date_to,
            "counted_until": until if until >= date_from else date_from - timedelta(days=1),
            "summary": with_rates(counts),
            "rows": [
                {
                    "lesson_id": row["lesson_id"],
                    "lesson_date": row["lesson_date"],
                    "session_no": row["session_no"],
                    "topic": row["topic"],
                    "eligible": bool(row["eligible"]),
                    "status": row["status"],
                    "prework": row["prework"],
                    "weekly": row["weekly"],
                }
                for row in rows
            ],
        }

    # ------------------------------------------------------------------ grades
    @staticmethod
    def _stats(row, today: date) -> dict:
        upcoming = row["assessment_date"] > today
        target, scored, not_taken = int(row["target"]), int(row["scored"]), int(row["not_taken"])
        return {
            "assessment_id": row["assessment_id"],
            "title": row["title"],
            "assessment_date": row["assessment_date"],
            "max_score": row["max_score"],
            "lesson_id": row["lesson_id"],
            "upcoming": upcoming,
            "target": target,
            "scored": scored,
            "not_taken": not_taken,
            "missing": int(row["missing"]),
            "outside_records": int(row["outside_records"]),
            # Scores cannot be entered before the assessment date: no completion rate yet.
            "entry_rate": None if upcoming else rate(scored + not_taken, target),
            "average": row["average"],
            "average_count": int(row["average_count"]),
            "average_percent": row["average_percent"],
        }

    @staticmethod
    def _grade_status(row, today: date) -> str:
        if row["status"] is not None:
            return row["status"]
        return "UPCOMING" if row["assessment_date"] > today else "MISSING"

    def grades(self, classroom_id: int, date_from: date, date_to: date) -> dict:
        self._require_classroom(classroom_id)
        self._period(date_from, date_to)
        today = date.today()
        return {
            "classroom_id": classroom_id,
            "date_from": date_from,
            "date_to": date_to,
            "assessments": [
                self._stats(row, today)
                for row in self.repo.grade_stats(classroom_id, date_from, date_to)
            ],
        }

    def assessment_detail(self, assessment_id: int) -> dict:
        found = self.repo.assessment_classroom(assessment_id)
        if found is None:
            _fail(404, "ASSESSMENT_NOT_FOUND", "평가를 찾을 수 없습니다.")
        classroom_id = found.classroom_id
        self._require_classroom(classroom_id)
        today = date.today()
        stats = self.repo.grade_stats(classroom_id, date.min, date.max, assessment_id)[0]
        rows = self.repo.grade_rows(classroom_id, assessment_id=assessment_id)
        return {
            "classroom_id": classroom_id,
            "stats": self._stats(stats, today),
            "rows": [
                {
                    "enrollment_id": row["enrollment_id"],
                    "student_id": row["student_id"],
                    "student_name": row["student_name"],
                    "eligible": bool(row["eligible"]),
                    "status": self._grade_status(row, today),
                    "score": row["score"],
                    "percent": row["percent"],
                }
                for row in rows
            ],
        }

    def student_grades(
        self, classroom_id: int, student_id: int, date_from: date, date_to: date
    ) -> dict:
        self._require_classroom(classroom_id)
        self._period(date_from, date_to)
        enrollment = self._student(classroom_id, student_id)
        today = date.today()
        rows = self.repo.grade_rows(
            classroom_id, enrollment_id=enrollment.id, date_from=date_from, date_to=date_to
        )
        return {
            "classroom_id": classroom_id,
            "student_id": enrollment.student_id,
            "student_name": enrollment.name,
            "enrollment_id": enrollment.id,
            "date_from": date_from,
            "date_to": date_to,
            "rows": [
                {
                    "assessment_id": row["assessment_id"],
                    "title": row["title"],
                    "assessment_date": row["assessment_date"],
                    "max_score": row["max_score"],
                    "lesson_id": row["lesson_id"],
                    "eligible": bool(row["eligible"]),
                    "status": self._grade_status(row, today),
                    "score": row["score"],
                    "percent": row["percent"],
                }
                for row in rows
            ],
        }

    # ----------------------------------------------- watch list & student report (2026-11-20)
    @staticmethod
    def _diff(percent, average) -> Decimal | None:
        """Position against the class: student % minus the same session's class average %.
        Comparing with the class on the same session removes most of the difficulty difference
        between sessions, so a series of these is a fair picture of growth."""
        if percent is None or average is None:
            return None
        return (Decimal(percent) - Decimal(average)).quantize(Decimal("0.1"), ROUND_HALF_UP)

    def _signals(self, classroom_id: int, today: date) -> tuple[date, date, dict[int, list]]:
        """Watch-list reasons per enrolment from each student's most recent records (WATCH_RULES):
        the last WATCH_RECENT scored sessions of every 평가 항목 and the last WATCH_RECENT lessons,
        within the last WATCH_LOOKBACK_DAYS days."""
        start = today - timedelta(days=WATCH_LOOKBACK_DAYS - 1)
        averages = {
            row["assessment_id"]: row["average_percent"]
            for row in self.repo.grade_stats(classroom_id, start, today)
        }
        series: dict[tuple[int, str], list[Decimal]] = defaultdict(list)  # date order
        skipped_test = set()  # (enrolment, lesson) with a 미응시 test linked to that lesson
        for row in self.repo.grade_rows(classroom_id, date_from=start, date_to=today):
            if not row["eligible"]:
                continue
            if row["status"] == "NOT_TAKEN" and row["lesson_id"] is not None:
                skipped_test.add((row["enrollment_id"], row["lesson_id"]))
            diff = self._diff(row["percent"], averages.get(row["assessment_id"]))
            if row["status"] == "SCORED" and diff is not None:
                series[(row["enrollment_id"], row["title"])].append(diff)
        recent_lessons: dict[int, list] = defaultdict(list)  # date order
        for row in self.repo.lesson_rows(classroom_id, start, today, today):
            if row["eligible"]:
                recent_lessons[row["enrollment_id"]].append(row)

        reasons: dict[int, list] = defaultdict(list)
        for (enrollment, title), diffs in sorted(series.items(), key=lambda item: item[0][1]):
            recent = diffs[-WATCH_RECENT:]
            if len(recent) < WATCH_MIN_SCORED:
                continue  # too few scores to judge
            low = sum(1 for d in recent if d <= -WATCH_GAP)
            if low >= WATCH_LOW_MIN:
                reasons[enrollment].append(
                    {
                        "code": "LOW_SCORE",
                        "title": title,
                        "count": low,
                        "text": f"{title}: 최근 {len(recent)}회 중 {low}회 "
                        "반 평균보다 15%p 이상 낮음",
                    }
                )
            first, middle, last = recent[-3:]
            if first > middle > last and first - last >= WATCH_DROP:
                reasons[enrollment].append(
                    {
                        "code": "DECLINING",
                        "title": title,
                        "count": 3,
                        "text": f"{title}: 최근 3회 반 대비 위치가 계속 낮아짐 "
                        f"({first:+.1f} → {middle:+.1f} → {last:+.1f}%p, "
                        f"{first - last:.1f}%p 하락)",
                    }
                )
        for enrollment, rows in recent_lessons.items():
            recent = rows[-WATCH_RECENT:]
            for kind, key in (("예습", "prework"), ("주간", "weekly")):
                count = sum(1 for r in recent if r[key] == "C")
                if count >= WATCH_LESSON_MIN:
                    reasons[enrollment].append(
                        {
                            "code": "HOMEWORK_C",
                            "title": None,
                            "count": count,
                            "text": f"최근 {len(recent)}회 수업 중 {kind} 과제 C 등급 {count}회",
                        }
                    )
            # One count per lesson: absent, or present but skipped a test of that lesson.
            # 인정결석 is never counted (nor its tests).
            absent = sum(1 for r in recent if r["status"] == "ABSENT")
            skipped = sum(
                1
                for r in recent
                if r["status"] in ("PRESENT", "LATE")
                and (enrollment, r["lesson_id"]) in skipped_test
            )
            if absent + skipped >= WATCH_LESSON_MIN:
                reasons[enrollment].append(
                    {
                        "code": "ABSENCE",
                        "title": None,
                        "count": absent + skipped,
                        "text": f"최근 {len(recent)}회 수업 중 결석·미응시 {absent + skipped}회 "
                        f"(결석 {absent}, 미응시 {skipped})",
                    }
                )
        return start, today, reasons

    def watchlist(self, classroom_id: int) -> dict:
        """관심 필요 학생: students whose last 4 weeks meet a rule, each with the reasons."""
        self._require_classroom(classroom_id)
        start, until, reasons = self._signals(classroom_id, date.today())
        students = [
            {
                "enrollment_id": row.id,
                "student_id": row.student_id,
                "student_name": row.name,
                "reasons": reasons[row.id],
            }
            for row in self.repo.roster(classroom_id)
            if row.status != "WITHDRAWN" and reasons.get(row.id)
        ]
        students.sort(key=lambda s: (-len(s["reasons"]), s["student_name"], s["student_id"]))
        return {
            "classroom_id": classroom_id,
            "window_from": start,
            "window_to": until,
            "rules": list(WATCH_RULES),
            "students": students,
        }

    def student_report(
        self, classroom_id: int, student_id: int, date_from: date, date_to: date
    ) -> dict:
        """학생 학습 리포트: per 평가 항목, each session's score next to the class average of the
        same session; homework grades and attendance per lesson; the watch-list reasons."""
        grades = self.student_grades(classroom_id, student_id, date_from, date_to)
        attendance = self.student_attendance(classroom_id, student_id, date_from, date_to)
        averages = {
            row["assessment_id"]: row["average_percent"]
            for row in self.repo.grade_stats(classroom_id, date_from, date_to)
        }
        items: dict[str, list] = {}
        for row in grades["rows"]:
            average = averages.get(row["assessment_id"])
            items.setdefault(row["title"], []).append(
                {
                    **row,
                    "class_average_percent": average,
                    "diff": self._diff(row["percent"], average)
                    if row["status"] == "SCORED"
                    else None,
                }
            )
        categories = []
        for title, points in items.items():
            diffs = [p["diff"] for p in points if p["diff"] is not None]
            categories.append(
                {
                    "title": title,
                    "points": points,
                    "scored_count": len(diffs),
                    "average_diff": (sum(diffs) / len(diffs)).quantize(
                        Decimal("0.1"), ROUND_HALF_UP
                    )
                    if diffs
                    else None,
                }
            )
        _, _, reasons = self._signals(classroom_id, date.today())
        return {
            "classroom_id": classroom_id,
            "student_id": grades["student_id"],
            "student_name": grades["student_name"],
            "enrollment_id": grades["enrollment_id"],
            "date_from": date_from,
            "date_to": date_to,
            "categories": categories,
            "attendance": attendance["summary"],
            "lessons": attendance["rows"],
            "watch_reasons": reasons.get(grades["enrollment_id"], []),
        }
