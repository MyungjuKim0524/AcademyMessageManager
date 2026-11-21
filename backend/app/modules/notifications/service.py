"""Parent notification workflow: preview -> draft -> review -> approval -> mock send.

Transaction rules: every state change, its audit_log row and (for sends) the attempt ledger row
are committed together. State changes lock the notification row and compare ``version``.
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models.tables import (
    AuditLog,
    Lesson,
    NotificationSendAttempt,
    NotificationTemplate,
    ParentNotification,
)
from app.errors import CompatibilityError, FieldError
from app.modules.auth.dependencies import Principal

from .engine import VARIABLES, GradeLine, MessageContext, TemplateError, parse_template, render
from .repository import NotificationRepository
from .schemas import MAX_BATCH, BodyUpdate, GenerateRequest, TemplateCreate, TemplateUpdate
from .sender import MockSender

ALL_STAFF = frozenset({"ADMIN", "TEACHER", "ASSISTANT"})
# Academy policy (2026-11-18, user decision): assistants confirm ("approve") and send messages
# themselves; teachers and admins may do the same. Classroom assignment still limits every action.
APPROVERS = ALL_STAFF
CONFLICT = "다른 사용자가 먼저 변경했습니다. 새로고침 후 다시 시도해주세요."
EDITABLE = frozenset({"DRAFT", "READY_FOR_REVIEW"})
# Confirmed messages that a (re)send may still go out for.
SENDABLE = frozenset({"APPROVED", "MOCK_FAILED"})
# Messages handled by one class batch request (a class lesson has a handful; this bounds a request,
# same bound as draft generation's schemas.MAX_BATCH).
BATCH_LIMIT = MAX_BATCH
NOT_IN_LESSON = ("NOT_IN_LESSON", "이 수업의 메시지가 아닙니다.")


def mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}" if domain else "***"


def _fail(status: int, code: str, message: str, fields: list[FieldError] | None = None):
    raise CompatibilityError(status, code, message, tuple(fields or ()))


class NotificationService:
    def __init__(self, db: Session, principal: Principal, request_id: str | None = None):
        self.db = db
        self.principal = principal
        self.request_id = request_id
        self.repo = NotificationRepository(db)
        self.sender = MockSender()

    # ---------------------------------------------------------------- helpers
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

    def _commit(self, code: str, message: str) -> None:
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise CompatibilityError(409, code, message) from exc

    def _require_role(self, roles: frozenset[str]) -> None:
        if self.principal.role not in roles:
            self._abort(403, "FORBIDDEN", "요청한 작업을 수행할 권한이 없습니다.")

    def _require_classroom(self, classroom_id: int) -> None:
        classroom = self.repo.classroom(classroom_id)
        if classroom is None or not classroom.is_active:
            self._abort(404, "CLASSROOM_NOT_FOUND", "반을 찾을 수 없습니다.")
        if not self.repo.can_access(classroom_id, self.principal.user_id, self.principal.role):
            self._abort(403, "CLASSROOM_ACCESS_DENIED", "담당 반에만 접근할 수 있습니다.")

    def _lesson(self, lesson_id: int) -> Lesson:
        lesson = self.repo.lesson(lesson_id)
        if lesson is None:
            _fail(404, "LESSON_NOT_FOUND", "수업을 찾을 수 없습니다.")
        self._require_classroom(lesson.classroom_id)
        return lesson

    def _notification(self, notification_id: int, *, lock: bool = False) -> ParentNotification:
        row = self.repo.notification(notification_id, lock=lock)
        if row is None:
            self._abort(404, "NOTIFICATION_NOT_FOUND", "메시지를 찾을 수 없습니다.")
        self._require_classroom(row.classroom_id)
        return row

    # -------------------------------------------------------------- templates
    def variables(self):
        return [{"name": name, "description": text} for name, text in VARIABLES.items()]

    def templates(self):
        return self.repo.templates(active_only=self.principal.role != "ADMIN")

    @staticmethod
    def _check_template(body: str) -> None:
        try:
            parse_template(body)
        except TemplateError as error:
            _fail(
                400,
                "INVALID_TEMPLATE",
                "템플릿을 확인해주세요.",
                [FieldError(field="body", message=m) for m in error.messages],
            )

    def validate_template(self, body: str) -> dict:
        self._require_role(frozenset({"ADMIN"}))
        from .engine import SAMPLE_CONTEXT

        try:
            names = parse_template(body)
        except TemplateError as error:
            return {
                "ok": False,
                "errors": error.messages,
                "variables": [],
                "sample_body": None,
                "sample_issues": [],
            }
        sample = render(body, SAMPLE_CONTEXT)
        return {
            "ok": True,
            "errors": [],
            "variables": names,
            "sample_body": sample.body,
            "sample_issues": sample.issues,
        }

    def create_template(self, data: TemplateCreate) -> NotificationTemplate:
        self._require_role(frozenset({"ADMIN"}))
        self._check_template(data.body)
        row = NotificationTemplate(
            name=data.name, body=data.body, created_by_staff_user_id=self.principal.user_id
        )
        self.db.add(row)
        try:
            self.db.flush()
        except IntegrityError as exc:
            self.db.rollback()
            raise CompatibilityError(
                409, "TEMPLATE_NAME_EXISTS", "같은 이름의 템플릿이 있습니다."
            ) from exc
        self._audit(
            "NOTIFICATION_TEMPLATE_CREATED",
            "NOTIFICATION_TEMPLATE",
            row.id,
            {"name": row.name, "length": len(row.body)},
        )
        self._commit("TEMPLATE_NAME_EXISTS", "같은 이름의 템플릿이 있습니다.")
        self.db.refresh(row)
        return row

    def update_template(self, template_id: int, data: TemplateUpdate) -> NotificationTemplate:
        self._require_role(frozenset({"ADMIN"}))
        row = self.repo.template(template_id, lock=True)
        if row is None:
            self._abort(404, "TEMPLATE_NOT_FOUND", "템플릿을 찾을 수 없습니다.")
        if row.version != data.version:
            self._abort(409, "VERSION_CONFLICT", CONFLICT)
        changes = {
            name: getattr(data, name)
            for name in data.model_fields_set - {"version", "default_for_class_type"}
            if getattr(data, name) is not None and getattr(data, name) != getattr(row, name)
        }
        if data.default_for_class_type is not None:
            target = None if data.default_for_class_type == "NONE" else data.default_for_class_type
            if target != row.default_for_class_type:
                if target is not None:
                    if not changes.get("is_active", row.is_active):
                        self._abort(
                            400,
                            "TEMPLATE_INACTIVE",
                            "사용 중인 템플릿만 기본으로 지정할 수 있습니다.",
                        )
                    # One default per class type (unique index): release the previous one first.
                    self.db.execute(
                        update(NotificationTemplate)
                        .where(
                            NotificationTemplate.default_for_class_type == target,
                            NotificationTemplate.id != row.id,
                        )
                        .values(default_for_class_type=None)
                    )
                changes["default_for_class_type"] = target
        if changes.get("is_active") is False and row.default_for_class_type:
            changes["default_for_class_type"] = None  # an inactive template cannot stay default
        if "body" in changes:
            try:
                self._check_template(changes["body"])
            except CompatibilityError:
                self.db.rollback()
                raise
        if not changes:
            self.db.rollback()
            return row
        before_version = row.version
        for name, value in changes.items():
            setattr(row, name, value)
        try:
            self.db.flush()
        except IntegrityError as exc:
            self.db.rollback()
            raise CompatibilityError(
                409, "TEMPLATE_NAME_EXISTS", "같은 이름의 템플릿이 있습니다."
            ) from exc
        # Existing notifications keep their own body/template snapshot; nothing else changes.
        self._audit(
            "NOTIFICATION_TEMPLATE_UPDATED",
            "NOTIFICATION_TEMPLATE",
            row.id,
            {"changed": sorted(changes), "version_before": before_version},
        )
        self._commit("TEMPLATE_NAME_EXISTS", "같은 이름의 템플릿이 있습니다.")
        self.db.refresh(row)
        return row

    # ----------------------------------------------------- preview / drafts
    def _active_template(self, template_id: int) -> NotificationTemplate:
        template = self.repo.template(template_id)
        if template is None or not template.is_active:
            _fail(
                400,
                "TEMPLATE_NOT_AVAILABLE",
                "사용할 수 있는 템플릿이 아닙니다.",
                [FieldError(field="template_id", message="활성 템플릿을 선택해주세요.")],
            )
        return template

    def _contexts(self, lesson: Lesson, enrollment_ids: list[int] | None):
        """Build one render context per requested student, with no per-student queries."""
        if enrollment_ids is not None and len(set(enrollment_ids)) != len(enrollment_ids):
            _fail(400, "DUPLICATE_ENROLLMENT", "같은 학생이 중복되었습니다.")
        rows = self.repo.roster(lesson, enrollment_ids)
        found = {row.Enrollment.id: row for row in rows}
        ids = list(found) if enrollment_ids is None else enrollment_ids
        assessments, results = self.repo.linked_grades(lesson, list(found))
        classroom = self.repo.classroom(lesson.classroom_id)
        contexts = []
        for enrollment_id in ids:
            row = found.get(enrollment_id)
            if row is None:  # not a student of this lesson's classroom (no data disclosed)
                contexts.append((enrollment_id, None, None))
                continue
            result = row.LessonResult
            grades = tuple(
                GradeLine(
                    title=a.title,
                    result_status=(r := results.get((a.id, enrollment_id))) and r.result_status,
                    score=r.score if r else None,
                    max_score=a.max_score,
                )
                for a in assessments
            )
            contexts.append(
                (
                    enrollment_id,
                    row.Student,
                    MessageContext(
                        student_name=row.Student.name,
                        classroom_name=classroom.name,
                        lesson_date=lesson.lesson_date.isoformat(),
                        session_no=lesson.session_no,
                        exam_round=lesson.exam_round,
                        topic=lesson.topic,
                        lesson_status=lesson.status,
                        eligible=bool(row.eligible),
                        recipient_email=row.Student.parent_email,
                        attendance=result.attendance_status if result else None,
                        prework_grade=result.prework_grade if result else None,
                        weekly_grade=result.weekly_assignment_grade if result else None,
                        correct_count=result.correct_count if result else None,
                        total_count=result.total_count if result else None,
                        grades=grades,
                    ),
                )
            )
        return contexts

    def preview(self, lesson_id: int, data: GenerateRequest):
        """Pure computation: no rows are written."""
        self._require_role(ALL_STAFF)
        lesson = self._lesson(lesson_id)
        template = self._active_template(data.template_id)
        contexts = self._contexts(lesson, data.enrollment_ids)
        existing = self.repo.active_notifications(
            lesson.id, template.id, [eid for eid, student, _ in contexts if student]
        )
        items = []
        for enrollment_id, student, ctx in contexts:
            if ctx is None:
                items.append(
                    {
                        "enrollment_id": enrollment_id,
                        "student_id": None,
                        "student_name": None,
                        "ok": False,
                        "body": None,
                        "issues": ["이 수업의 반 학생이 아닙니다"],
                        "warnings": [],
                        "existing_notification_id": None,
                    }
                )
                continue
            result = render(template.body, ctx)
            items.append(
                {
                    "enrollment_id": enrollment_id,
                    "student_id": student.id,
                    "student_name": student.name,
                    "ok": result.ok,
                    "body": result.body,
                    "issues": result.issues,
                    "warnings": result.warnings,
                    "existing_notification_id": existing.get(enrollment_id),
                }
            )
        return lesson, template, items

    def create_drafts(self, lesson_id: int, data: GenerateRequest):
        lesson, template, items = self.preview(lesson_id, data)
        contexts = {eid: ctx for eid, _, ctx in self._contexts(lesson, data.enrollment_ids)}
        created, skipped = [], []
        for item in items:
            reasons = list(item["issues"])
            if item["existing_notification_id"]:
                reasons.append("이미 이 수업·템플릿의 메시지가 있습니다")
            if reasons:
                skipped.append(
                    {
                        "enrollment_id": item["enrollment_id"],
                        "student_name": item["student_name"],
                        "reasons": reasons,
                        "existing_notification_id": item["existing_notification_id"],
                    }
                )
                continue
            ctx = contexts[item["enrollment_id"]]
            result = render(template.body, ctx)
            row = ParentNotification(
                classroom_id=lesson.classroom_id,
                lesson_id=lesson.id,
                enrollment_id=item["enrollment_id"],
                template_id=template.id,
                template_version=template.version,
                template_body=template.body,
                recipient_email=ctx.recipient_email,
                body=result.body,
                source_hash=result.source_hash,
                status="DRAFT",
                created_by_staff_user_id=self.principal.user_id,
                updated_by_staff_user_id=self.principal.user_id,
            )
            self.db.add(row)
            created.append(row)
        try:
            self.db.flush()
        except IntegrityError as exc:  # a concurrent request created the same drafts first
            self.db.rollback()
            raise CompatibilityError(
                409,
                "NOTIFICATION_CONFLICT",
                "동시에 같은 메시지가 생성되었습니다. 다시 시도하면 이미 만든 메시지는 건너뜁니다.",
            ) from exc
        for row in created:
            self._audit(
                "NOTIFICATION_CREATED",
                "PARENT_NOTIFICATION",
                row.id,
                {
                    "lesson_id": row.lesson_id,
                    "enrollment_id": row.enrollment_id,
                    "template_id": row.template_id,
                    "template_version": row.template_version,
                    "status": "DRAFT",
                    "length": len(row.body),
                },
            )
        self._commit("NOTIFICATION_CONFLICT", "동시에 같은 메시지가 생성되었습니다.")
        return [row.id for row in created], skipped

    # -------------------------------------------------- review / approval
    def listing(self, classroom_id: int, lesson_id, status, limit: int, offset: int):
        self._require_classroom(classroom_id)
        return self.repo.notification_rows(classroom_id, lesson_id, status, limit, offset)

    def source_changed(self, row: ParentNotification) -> bool:
        lesson = self.repo.lesson(row.lesson_id)
        [(_, _, ctx)] = self._contexts(lesson, [row.enrollment_id])
        return self._changed_against(row, ctx)

    @staticmethod
    def _changed_against(row: ParentNotification, ctx: MessageContext | None) -> bool:
        """The one "source changed" rule: the message re-rendered from today's data differs."""
        if ctx is None:
            return True
        current = render(row.template_body, ctx)
        return not current.ok or current.source_hash != row.source_hash

    # ------------------------------------------------ class batch (2026-11-20)
    # One class lesson at a time: the bodies are reviewed together on one screen, the chosen ones
    # are confirmed, then the confirmed ones are mock-sent. Every message still goes through the
    # single-message approve / mock_send / retry_mock_send (own transaction, version check,
    # source check, idempotency key, audit row), so one failure never stops or undoes the rest.

    def batch_view(self, lesson_id: int) -> dict:
        self._require_role(ALL_STAFF)
        lesson = self._lesson(lesson_id)
        rows = [
            row
            for row in self.repo.notification_rows(
                lesson.classroom_id, lesson.id, None, BATCH_LIMIT, 0
            )
            if row[0].status != "CANCELLED"
        ]
        enrollment_ids = list(dict.fromkeys(n.enrollment_id for n, *_ in rows))
        contexts = (
            {eid: ctx for eid, _, ctx in self._contexts(lesson, enrollment_ids)}
            if enrollment_ids
            else {}
        )
        items = []
        for notification, row_lesson, student, template in rows:
            ctx = contexts.get(notification.enrollment_id)
            check = notification.status in EDITABLE | SENDABLE
            items.append(
                {
                    **self.list_item(notification, row_lesson, student, template),
                    "body": notification.body,
                    "source_changed": self._changed_against(notification, ctx) if check else False,
                    "attention": self._attention(ctx),
                }
            )
        return {"lesson_id": lesson.id, "classroom_id": lesson.classroom_id, "items": items}

    @staticmethod
    def _attention(ctx: MessageContext | None) -> list[str]:
        """Facts worth a second look before confirming (shown, never blocking)."""
        if ctx is None:
            return []
        notes = []
        if ctx.attendance in ("ABSENT", "EXCUSED"):
            notes.append("결석" if ctx.attendance == "ABSENT" else "인정결석")
        if any(g.result_status == "NOT_TAKEN" for g in ctx.grades):
            notes.append("미응시")
        if any(g.result_status == "SCORED" and g.score == 0 for g in ctx.grades):
            notes.append("0점")
        return notes

    def _batch_rows(self, lesson_id: int, ids: list[int]) -> dict[int, tuple]:
        """The lesson's messages among ``ids`` (others are reported, never touched)."""
        self._lesson(lesson_id)
        if len(ids) > BATCH_LIMIT:
            _fail(400, "BATCH_TOO_LARGE", f"한 번에 {BATCH_LIMIT}건까지 처리할 수 있습니다.")
        if len(set(ids)) != len(ids):
            _fail(400, "DUPLICATE_NOTIFICATION", "같은 메시지가 중복되었습니다.")
        rows = self.repo.notification_rows_by_ids(lesson_id, ids)
        self.db.rollback()  # read only; each message is then processed in its own transaction
        return {row[0].id: row for row in rows}

    @staticmethod
    def _skip(notification_id: int, name: str | None, code: str, message: str) -> dict:
        return {
            "id": notification_id,
            "student_name": name,
            "outcome": "SKIPPED",
            "code": code,
            "message": message,
        }

    def batch_approve(self, lesson_id: int, items: list[tuple[int, int]]) -> list[dict]:
        self._require_role(APPROVERS)
        found = self._batch_rows(lesson_id, [i for i, _ in items])
        results = []
        for notification_id, version in items:
            row = found.get(notification_id)
            if row is None:
                results.append(self._skip(notification_id, None, *NOT_IN_LESSON))
                continue
            name = row[2].name
            try:
                self.approve(notification_id, version, batch=True)
            except CompatibilityError as error:
                self.db.rollback()
                results.append(self._skip(notification_id, name, error.code, error.message))
                continue
            results.append(
                {
                    "id": notification_id,
                    "student_name": name,
                    "outcome": "APPROVED",
                    "code": None,
                    "message": None,
                }
            )
        return results

    def batch_mock_send(self, lesson_id: int, items: list[tuple[int, UUID]]) -> list[dict]:
        """Confirmed messages are sent, failed ones retried (same idempotency rules as one by
        one: the client keeps each message's key until it gets an answer)."""
        self._require_role(APPROVERS)
        found = self._batch_rows(lesson_id, [i for i, _ in items])
        results = []
        for notification_id, key in items:
            row = found.get(notification_id)
            if row is None:
                results.append(self._skip(notification_id, None, *NOT_IN_LESSON))
                continue
            name = row[2].name
            send = self.retry_mock_send if row[0].status == "MOCK_FAILED" else self.mock_send
            try:
                detail, attempt, replayed = send(notification_id, key, batch=True)
            except CompatibilityError as error:
                self.db.rollback()
                results.append(self._skip(notification_id, name, error.code, error.message))
                continue
            results.append(
                {
                    "id": notification_id,
                    "student_name": name,
                    "outcome": detail["status"],  # MOCK_SENT or MOCK_FAILED
                    "code": attempt["error_code"],
                    "message": attempt["error_message"],
                    "replayed": replayed,
                }
            )
        return results

    def detail(self, notification_id: int):
        row = self._notification(notification_id)
        return self._detail(row)

    def _detail(self, row: ParentNotification) -> dict:
        found = self.repo.notification_row(row.id)
        notification, lesson, student, template = found
        attempts = self.repo.attempts(row.id)
        history = self.repo.history(row.id)
        names = self.repo.staff_names(
            [notification.created_by_staff_user_id, notification.approved_by_staff_user_id]
            + [a.requested_by_staff_user_id for a in attempts]
            + [h.actor_staff_user_id for h in history]
        )
        # Every status that can still be confirmed or (re)sent shows the warning — the same
        # statuses that refuse to proceed when the source changed (see _reject_changed_source).
        check_source = notification.status in EDITABLE | SENDABLE
        return {
            **self.list_item(notification, lesson, student, template),
            # Full address for the assigned staff who confirm / send (policy 2026-11-18,
            # re-confirmed 2026-11-20); list rows use mask_email.
            "recipient_email": notification.recipient_email,
            "body": notification.body,
            "template_version": notification.template_version,
            "created_by": names.get(notification.created_by_staff_user_id),
            "approved_by": names.get(notification.approved_by_staff_user_id),
            "approved_at": notification.approved_at,
            "source_changed": self.source_changed(notification) if check_source else False,
            "attempts": [self.attempt_view(a, names) for a in attempts],
            "history": [
                {
                    "event_type": h.event_type,
                    "actor": names.get(h.actor_staff_user_id),
                    "created_at": h.created_at,
                    "details": h.details or {},
                }
                for h in history
            ],
        }

    @staticmethod
    def list_item(notification, lesson, student, template) -> dict:
        return {
            "id": notification.id,
            "classroom_id": notification.classroom_id,
            "lesson_id": notification.lesson_id,
            "lesson_date": lesson.lesson_date,
            "session_no": lesson.session_no,
            "enrollment_id": notification.enrollment_id,
            "student_name": student.name,
            "template_id": notification.template_id,
            "template_name": template.name,
            "status": notification.status,
            "recipient": mask_email(notification.recipient_email),
            "version": notification.version,
            "updated_at": notification.updated_at,
        }

    @staticmethod
    def attempt_view(attempt: NotificationSendAttempt, names: dict) -> dict:
        return {
            "id": attempt.id,
            "channel": attempt.channel,
            "result": attempt.result,
            "error_code": attempt.error_code,
            "error_message": attempt.error_message,
            "requested_by": names.get(attempt.requested_by_staff_user_id),
            "attempted_at": attempt.attempted_at,
        }

    def _locked(self, notification_id: int, version: int) -> ParentNotification:
        row = self._notification(notification_id, lock=True)
        if row.version != version:
            self._abort(409, "VERSION_CONFLICT", CONFLICT)
        return row

    def _invalid(self, row: ParentNotification, action: str):
        self._abort(
            409,
            "INVALID_TRANSITION",
            f"현재 상태({row.status})에서는 '{action}'을(를) 할 수 없습니다.",
        )

    def _finish(
        self, row: ParentNotification, event: str, details: dict, *, detail: bool = True
    ) -> dict:
        row.updated_by_staff_user_id = self.principal.user_id
        self.db.flush()
        self._audit(event, "PARENT_NOTIFICATION", row.id, details)
        self._commit("NOTIFICATION_CONFLICT", CONFLICT)
        if not detail:
            # Class batch (Phase 11-4-A): the batch answer only reports the outcome, so the full
            # detail view (≈11 more queries incl. a second source check) is not built.
            return {"status": row.status}
        self.db.refresh(row)
        return self._detail(row)

    def edit(self, notification_id: int, data: BodyUpdate) -> dict:
        self._require_role(ALL_STAFF)
        row = self._locked(notification_id, data.version)
        if row.status not in EDITABLE:
            self._abort(
                409,
                "NOTIFICATION_LOCKED",
                "확정된 메시지는 수정할 수 없습니다. 확정을 취소한 뒤 수정하세요.",
            )
        body = data.body.replace("\r\n", "\n").strip()
        if not body:
            self._abort(
                400,
                "VALIDATION_ERROR",
                "본문을 입력해주세요.",
                [FieldError(field="body", message="본문을 입력해주세요.")],
            )
        if body == row.body:
            self.db.rollback()
            return self._detail(row)
        before = len(row.body)
        row.body = body
        return self._finish(
            row,
            "NOTIFICATION_EDITED",
            {"status": row.status, "length_before": before, "length_after": len(body)},
        )

    def submit(self, notification_id: int, version: int) -> dict:
        self._require_role(ALL_STAFF)
        row = self._locked(notification_id, version)
        if row.status != "DRAFT":
            self._invalid(row, "검토 요청")
        row.status = "READY_FOR_REVIEW"
        return self._finish(row, "NOTIFICATION_SUBMITTED", {"from": "DRAFT", "to": row.status})

    def approve(self, notification_id: int, version: int, *, batch: bool = False) -> dict:
        self._require_role(APPROVERS)
        row = self._locked(notification_id, version)
        if row.status not in EDITABLE:
            self._invalid(row, "내용 확정")
        if self.source_changed(row):
            self._abort(
                409,
                "SOURCE_CHANGED",
                "메시지 생성 후 수업·출결·성적 또는 연락처가 바뀌었습니다. "
                "이 메시지를 취소하고 다시 생성해주세요.",
            )
        before = row.status
        row.status = "APPROVED"
        row.approved_by_staff_user_id = self.principal.user_id
        row.approved_at = datetime.now(UTC)
        details = {"from": before, "to": row.status}
        if batch:
            details["batch"] = True  # confirmed from the class batch screen
        return self._finish(row, "NOTIFICATION_APPROVED", details, detail=not batch)

    def revoke(self, notification_id: int, version: int) -> dict:
        self._require_role(APPROVERS)
        row = self._locked(notification_id, version)
        if row.status != "APPROVED":
            self._invalid(row, "확정 취소")
        approver = row.approved_by_staff_user_id
        row.status = "DRAFT"
        row.approved_by_staff_user_id = None
        row.approved_at = None
        return self._finish(
            row,
            "NOTIFICATION_APPROVAL_REVOKED",
            {"from": "APPROVED", "to": "DRAFT", "previous_approver_id": approver},
        )

    def cancel(self, notification_id: int, version: int) -> dict:
        self._require_role(ALL_STAFF)
        row = self._locked(notification_id, version)
        if row.status not in EDITABLE | {"APPROVED", "MOCK_FAILED"}:
            self._invalid(row, "취소")
        before = row.status
        row.status = "CANCELLED"
        return self._finish(row, "NOTIFICATION_CANCELLED", {"from": before, "to": "CANCELLED"})

    # ------------------------------------------------------------- mock send
    def _locked_for_send(self, notification_id: int, idempotency_key: UUID):
        """Lock the message, then resolve an idempotent replay. Returns (row, replay|None)."""
        self._require_role(APPROVERS)
        # The row lock serialises concurrent sends; the key is checked only after locking.
        row = self._notification(notification_id, lock=True)
        previous = self.repo.attempt_by_key(idempotency_key)
        if previous is not None:
            if previous.notification_id != row.id:
                self._abort(
                    409, "IDEMPOTENCY_KEY_REUSED", "이미 다른 메시지에 사용된 요청 키입니다."
                )
            self.db.rollback()
            names = self.repo.staff_names([previous.requested_by_staff_user_id])
            return row, (self._detail(row), self.attempt_view(previous, names), True)
        if row.status == "MOCK_SENT":
            self._abort(409, "ALREADY_MOCK_SENT", "이미 모의 발송에 성공한 메시지입니다.")
        return row, None

    def mock_send(self, notification_id: int, idempotency_key: UUID, *, batch: bool = False):
        row, replay = self._locked_for_send(notification_id, idempotency_key)
        if replay is not None:
            return replay
        if row.status != "APPROVED":
            self._abort(409, "NOT_APPROVED", "내용을 확정한 메시지만 모의 발송할 수 있습니다.")
        self._reject_changed_source(row, "모의 발송할")
        return self._deliver(row, idempotency_key, retry=False, batch=batch)

    def _reject_changed_source(self, row: ParentNotification, action: str) -> None:
        """Phase 10.5 (H1): one rule for the first send and the retry — a confirmed body whose
        source (lesson, attendance, grades used by the template, guardian e-mail) changed since
        generation is never sent; it must be cancelled and generated again. Checked under the
        message row lock, before any attempt row or status change is written.

        Phase 11-3-B (INT-01): the source rows are locked first and stay locked until the send
        commits (see NotificationRepository.lock_sources), so a source write cannot commit
        between this check and the MOCK_SENT record."""
        self.repo.lock_sources(row)
        if self.source_changed(row):
            self._abort(
                409,
                "SOURCE_CHANGED",
                "메시지 생성 후 수업·출결·성적 또는 연락처가 바뀌어 "
                f"{action} 수 없습니다. 이 메시지를 취소하고 다시 생성·확정해주세요.",
            )

    def retry_mock_send(self, notification_id: int, idempotency_key: UUID, *, batch: bool = False):
        """Phase 9: an explicit staff action to re-send a message whose mock send failed.

        The confirmed body and recipient are reused unchanged; earlier failed attempts stay in
        the ledger. If the source data changed since the message was generated (lesson,
        attendance, grades or guardian contact), the message needs a new confirmation instead.
        """
        row, replay = self._locked_for_send(notification_id, idempotency_key)
        if replay is not None:
            return replay
        if row.status != "MOCK_FAILED":
            self._abort(
                409,
                "NOT_FAILED",
                "모의 발송에 실패한 메시지만 재시도할 수 있습니다. "
                "확정 전이면 검토·확정을, 확정된 메시지는 모의 발송을 사용하세요.",
            )
        self._reject_changed_source(row, "재시도할")
        return self._deliver(row, idempotency_key, retry=True, batch=batch)

    def _deliver(
        self, row: ParentNotification, idempotency_key: UUID, *, retry: bool, batch: bool = False
    ):
        before = row.status
        attempt_no = self.repo.attempt_count(row.id) + 1
        result = self.sender.send(row.recipient_email, row.body, attempt_no)
        attempt = NotificationSendAttempt(
            notification_id=row.id,
            idempotency_key=idempotency_key,
            channel=self.sender.channel,
            result="MOCK_SUCCESS" if result.success else "MOCK_FAILURE",
            error_code=result.error_code,
            error_message=result.error_message,
            requested_by_staff_user_id=self.principal.user_id,
        )
        self.db.add(attempt)
        row.status = "MOCK_SENT" if result.success else "MOCK_FAILED"
        row.updated_by_staff_user_id = self.principal.user_id
        try:
            self.db.flush()
        except IntegrityError as exc:
            self.db.rollback()
            raise CompatibilityError(409, "MOCK_SEND_CONFLICT", CONFLICT) from exc
        details = {
            "from": before,
            "to": row.status,
            "attempt_id": attempt.id,
            "result": attempt.result,
            "error_code": attempt.error_code,
        }
        if retry:
            details["retry"] = True
            details["attempt_no"] = attempt_no
        if batch:
            details["batch"] = True  # sent from the class batch screen
        self._audit("NOTIFICATION_MOCK_SEND", "PARENT_NOTIFICATION", row.id, details)
        self._commit("MOCK_SEND_CONFLICT", CONFLICT)
        if batch:
            # Same as _finish: the batch answer needs only the outcome and the error, not the
            # detail view (Phase 11-4-A).
            outcome = {"error_code": attempt.error_code, "error_message": attempt.error_message}
            return {"status": row.status}, outcome, False
        self.db.refresh(row)
        self.db.refresh(attempt)
        names = self.repo.staff_names([attempt.requested_by_staff_user_id])
        return self._detail(row), self.attempt_view(attempt, names), False
