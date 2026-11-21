from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CHAR,
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )


class Student(TimestampMixin, Base):
    __tablename__ = "student"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    school_name: Mapped[str | None] = mapped_column(String(120))
    parent_name: Mapped[str | None] = mapped_column(String(100))
    parent_email: Mapped[str | None] = mapped_column(String(255))
    __table_args__ = (
        Index("idx_student_name", "name"),
        Index("idx_student_parent_email", "parent_email"),
        Index("uq_student_business_key", "name", func.coalesce(school_name, ""), unique=True),
    )


class Classroom(TimestampMixin, Base):
    __tablename__ = "classroom"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    class_type: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    __table_args__ = (
        CheckConstraint("class_type IN ('REGULAR','EXAM_PREP')", name="chk_classroom_class_type"),
        UniqueConstraint("name", "class_type", name="uq_classroom_name_class_type"),
    )


class Enrollment(TimestampMixin, Base):
    __tablename__ = "enrollment"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("student.id", ondelete="RESTRICT"))
    classroom_id: Mapped[int] = mapped_column(ForeignKey("classroom.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    enrolled_at: Mapped[date] = mapped_column(Date, nullable=False)
    ended_at: Mapped[date | None] = mapped_column(Date)
    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE','PAUSED','WITHDRAWN')", name="chk_enrollment_status"),
        CheckConstraint("ended_at IS NULL OR ended_at >= enrolled_at", name="chk_enrollment_dates"),
        UniqueConstraint("student_id", "classroom_id", "enrolled_at", name="uq_enrollment"),
        UniqueConstraint("id", "classroom_id", name="uq_enrollment_id_classroom"),
        Index("uq_enrollment_student_classroom", "student_id", "classroom_id", unique=True),
        Index("idx_enrollment_student", "student_id"),
        Index("idx_enrollment_classroom", "classroom_id"),
        Index("idx_enrollment_status", "status"),
    )


class EnrollmentPause(TimestampMixin, Base):
    """Dated pause (휴원) history. Overlapping pauses are rejected by an EXCLUDE constraint."""

    __tablename__ = "enrollment_pause"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    enrollment_id: Mapped[int] = mapped_column(
        ForeignKey("enrollment.id", ondelete="RESTRICT"), nullable=False
    )
    paused_from: Mapped[date] = mapped_column(Date, nullable=False)
    resumed_on: Mapped[date | None] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'MANUAL'"))
    __table_args__ = (
        CheckConstraint(
            "resumed_on IS NULL OR resumed_on > paused_from", name="chk_enrollment_pause_dates"
        ),
        CheckConstraint("source IN ('MANUAL','STATUS_CHANGE')", name="chk_enrollment_pause_source"),
        ExcludeConstraint(
            ("enrollment_id", "="),
            (text("daterange(paused_from, resumed_on, '[)')"), "&&"),
            name="ex_enrollment_pause_overlap",
            using="gist",
        ),
    )


class Lesson(TimestampMixin, Base):
    __tablename__ = "lesson"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    classroom_id: Mapped[int] = mapped_column(ForeignKey("classroom.id", ondelete="RESTRICT"))
    lesson_date: Mapped[date] = mapped_column(Date, nullable=False)
    exam_round: Mapped[str | None] = mapped_column(String(50))
    topic: Mapped[str | None] = mapped_column(String(200))
    memo: Mapped[str | None] = mapped_column(String(2000))
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'COMPLETED'")
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    # Same-day sessions (Phase 7.1). The Java import always targets session 1.
    session_no: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("1"))
    __table_args__ = (
        CheckConstraint(
            "status IN ('SCHEDULED','COMPLETED','CANCELLED')", name="chk_lesson_status"
        ),
        CheckConstraint("session_no BETWEEN 1 AND 9", name="chk_lesson_session_no"),
        UniqueConstraint("id", "classroom_id", name="uq_lesson_id_classroom"),
        Index("idx_lesson_classroom", "classroom_id"),
        Index("idx_lesson_date", "lesson_date"),
        Index(
            "uq_lesson_session_with_exam_round",
            "classroom_id",
            "lesson_date",
            "exam_round",
            "session_no",
            unique=True,
            postgresql_where=text("exam_round IS NOT NULL"),
        ),
        Index(
            "uq_lesson_session_without_exam_round",
            "classroom_id",
            "lesson_date",
            "session_no",
            unique=True,
            postgresql_where=text("exam_round IS NULL"),
        ),
    )


class LessonResult(TimestampMixin, Base):
    __tablename__ = "lesson_result"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lesson.id", ondelete="RESTRICT"))
    enrollment_id: Mapped[int] = mapped_column(ForeignKey("enrollment.id", ondelete="RESTRICT"))
    attendance_status: Mapped[str] = mapped_column(String(20), nullable=False)
    prework_grade: Mapped[str | None] = mapped_column(String(20))
    weekly_assignment_grade: Mapped[str | None] = mapped_column(String(20))
    correct_count: Mapped[int | None] = mapped_column(SmallInteger)
    total_count: Mapped[int | None] = mapped_column(SmallInteger)
    memo: Mapped[str | None] = mapped_column(String(500))
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    __table_args__ = (
        CheckConstraint(
            "attendance_status IN ('PRESENT','ABSENT','LATE','EXCUSED')",
            name="chk_lesson_result_attendance",
        ),
        CheckConstraint(
            "prework_grade IS NULL OR prework_grade IN ('A','B','C')",
            name="chk_lesson_result_prework_grade",
        ),
        CheckConstraint(
            "weekly_assignment_grade IS NULL OR weekly_assignment_grade IN ('A','B','C')",
            name="chk_lesson_result_weekly_grade",
        ),
        CheckConstraint(
            "(correct_count IS NULL AND total_count IS NULL) OR "
            "(correct_count IS NOT NULL AND total_count IS NOT NULL "
            "AND correct_count >= 0 AND total_count > 0 "
            "AND correct_count <= total_count)",
            name="chk_lesson_result_test_counts",
        ),
        UniqueConstraint("lesson_id", "enrollment_id", name="uq_lesson_result"),
        Index("idx_lesson_result_lesson", "lesson_id"),
        Index("idx_lesson_result_enrollment", "enrollment_id"),
        Index("idx_lesson_result_attendance", "attendance_status"),
    )


class Assessment(TimestampMixin, Base):
    __tablename__ = "assessment"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    classroom_id: Mapped[int] = mapped_column(
        ForeignKey("classroom.id", ondelete="RESTRICT"), nullable=False
    )
    lesson_id: Mapped[int | None] = mapped_column(BigInteger)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    assessment_date: Mapped[date] = mapped_column(Date, nullable=False)
    max_score: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    __table_args__ = (
        CheckConstraint("max_score > 0", name="chk_assessment_max_score"),
        CheckConstraint("btrim(title) <> ''", name="chk_assessment_title"),
        ForeignKeyConstraint(
            ["lesson_id", "classroom_id"],
            ["lesson.id", "lesson.classroom_id"],
            name="fk_assessment_lesson_classroom",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("id", "classroom_id", "max_score", name="uq_assessment_scope"),
        Index("idx_assessment_classroom_date", "classroom_id", "assessment_date"),
        Index(
            "uq_assessment_lesson_title",
            "lesson_id",
            "title",
            unique=True,
            postgresql_where=text("lesson_id IS NOT NULL"),
        ),
    )


class AssessmentResult(TimestampMixin, Base):
    __tablename__ = "assessment_result"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    assessment_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    classroom_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    max_score: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    enrollment_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    result_status: Mapped[str] = mapped_column(String(20), nullable=False)
    score: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    memo: Mapped[str | None] = mapped_column(String(500))
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    __table_args__ = (
        CheckConstraint(
            "result_status IN ('SCORED','NOT_TAKEN')", name="chk_assessment_result_status"
        ),
        CheckConstraint(
            "(result_status = 'SCORED' AND score IS NOT NULL AND score >= 0 "
            "AND score <= max_score) OR (result_status = 'NOT_TAKEN' AND score IS NULL)",
            name="chk_assessment_result_score",
        ),
        ForeignKeyConstraint(
            ["assessment_id", "classroom_id", "max_score"],
            ["assessment.id", "assessment.classroom_id", "assessment.max_score"],
            name="fk_assessment_result_assessment",
            onupdate="CASCADE",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["enrollment_id", "classroom_id"],
            ["enrollment.id", "enrollment.classroom_id"],
            name="fk_assessment_result_enrollment",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("assessment_id", "enrollment_id", name="uq_assessment_result"),
        Index("idx_assessment_result_enrollment", "enrollment_id"),
    )


class MakeupRequest(TimestampMixin, Base):
    __tablename__ = "makeup_request"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    lesson_result_id: Mapped[int] = mapped_column(
        ForeignKey("lesson_result.id", ondelete="RESTRICT")
    )
    target_lesson_id: Mapped[int | None] = mapped_column(
        ForeignKey("lesson.id", ondelete="RESTRICT")
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(String(255))
    __table_args__ = (
        CheckConstraint(
            "status IN ('REQUESTED','APPROVED','COMPLETED','CANCELLED')",
            name="chk_makeup_request_status",
        ),
        CheckConstraint(
            "completed_at IS NULL OR completed_at >= requested_at",
            name="chk_makeup_request_completed_at",
        ),
        Index("idx_makeup_request_lesson_result", "lesson_result_id"),
        Index("idx_makeup_request_target_lesson", "target_lesson_id"),
        Index("idx_makeup_request_status", "status"),
    )


class MessageTemplate(TimestampMixin, Base):
    __tablename__ = "message_template"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    class_type: Mapped[str] = mapped_column(String(20), nullable=False)
    subject_template: Mapped[str] = mapped_column(Text, nullable=False)
    body_template: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    __table_args__ = (
        CheckConstraint(
            "class_type IN ('REGULAR','EXAM_PREP')", name="chk_message_template_class_type"
        ),
        UniqueConstraint("class_type", name="uq_message_template_class_type"),
    )


class MessageDraft(TimestampMixin, Base):
    __tablename__ = "message_draft"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    lesson_result_id: Mapped[int] = mapped_column(
        ForeignKey("lesson_result.id", ondelete="RESTRICT")
    )
    template_id: Mapped[int] = mapped_column(ForeignKey("message_template.id", ondelete="RESTRICT"))
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    draft_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'DRAFT'")
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    __table_args__ = (
        CheckConstraint(
            "draft_status IN ('DRAFT','READY','CANCELLED')", name="chk_message_draft_status"
        ),
        Index("idx_message_draft_lesson_result", "lesson_result_id"),
        Index("idx_message_draft_template", "template_id"),
        Index("idx_message_draft_status", "draft_status"),
    )


class DeliveryJob(TimestampMixin, Base):
    __tablename__ = "delivery_job"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    message_draft_id: Mapped[int] = mapped_column(
        ForeignKey("message_draft.id", ondelete="RESTRICT")
    )
    recipient_email: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'PENDING'")
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING','PROCESSING','SUCCESS','FAILED','SKIPPED')",
            name="chk_delivery_job_status",
        ),
        CheckConstraint(
            "processed_at IS NULL OR processed_at >= requested_at",
            name="chk_delivery_job_processed_at",
        ),
        Index("idx_delivery_job_message_draft", "message_draft_id"),
        Index("idx_delivery_job_status", "status"),
        Index("idx_delivery_job_recipient_email", "recipient_email"),
    )


class DeliveryAttempt(Base):
    __tablename__ = "delivery_attempt"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    delivery_job_id: Mapped[int] = mapped_column(ForeignKey("delivery_job.id", ondelete="CASCADE"))
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    attempt_status: Mapped[str] = mapped_column(String(20), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    __table_args__ = (
        CheckConstraint("attempt_no > 0", name="chk_delivery_attempt_no"),
        CheckConstraint(
            "attempt_status IN ('SUCCESS','FAILED')", name="chk_delivery_attempt_status"
        ),
        UniqueConstraint("delivery_job_id", "attempt_no", name="uq_delivery_attempt"),
        Index("idx_delivery_attempt_job", "delivery_job_id"),
    )


# import_job / import_row / import_error (legacy CSV/XLSX import) were dropped by migration 010.


class StaffUser(TimestampMixin, Base):
    __tablename__ = "staff_user"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'ACTIVE'"))
    __table_args__ = (
        CheckConstraint("role IN ('ADMIN','TEACHER','ASSISTANT')", name="chk_staff_user_role"),
        # DELETED (migration 011): cannot log in, hidden from lists, history rows keep the id.
        CheckConstraint("status IN ('ACTIVE','INACTIVE','DELETED')", name="chk_staff_user_status"),
        Index("uq_staff_user_email_lower", func.lower(email), unique=True),
        Index("idx_staff_user_role_status", "role", "status"),
    )


class ClassroomStaffAssignment(Base):
    __tablename__ = "classroom_staff_assignment"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    classroom_id: Mapped[int] = mapped_column(ForeignKey("classroom.id", ondelete="CASCADE"))
    staff_user_id: Mapped[int] = mapped_column(ForeignKey("staff_user.id", ondelete="CASCADE"))
    assignment_role: Mapped[str] = mapped_column(String(20), nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    __table_args__ = (
        CheckConstraint(
            "assignment_role IN ('TEACHER','ASSISTANT')",
            name="chk_classroom_staff_assignment_role",
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from",
            name="chk_classroom_staff_assignment_dates",
        ),
        UniqueConstraint(
            "classroom_id",
            "staff_user_id",
            "valid_from",
            name="uq_classroom_staff_assignment",
        ),
        Index(
            "uq_assignment_open_staff_classroom",
            "classroom_id",
            "staff_user_id",
            unique=True,
            postgresql_where=text("valid_to IS NULL"),
        ),
        Index("idx_assignment_staff_dates", "staff_user_id", "valid_from", "valid_to"),
        Index("idx_assignment_classroom_dates", "classroom_id", "valid_from", "valid_to"),
    )


class AuthSession(Base):
    __tablename__ = "auth_session"
    id: Mapped[UUID] = mapped_column(PgUUID, primary_key=True)
    staff_user_id: Mapped[int] = mapped_column(
        ForeignKey("staff_user.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False, unique=True)
    csrf_token_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    __table_args__ = (
        CheckConstraint("expires_at > created_at", name="chk_auth_session_expiry"),
        Index("idx_auth_session_staff", "staff_user_id"),
        Index("idx_auth_session_expiry", "expires_at"),
    )


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    actor_staff_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("staff_user.id", ondelete="SET NULL")
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(50))
    target_id: Mapped[str | None] = mapped_column(String(100))
    request_id: Mapped[UUID | None] = mapped_column(PgUUID)
    details: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    __table_args__ = (
        Index("idx_audit_log_actor_created", "actor_staff_user_id", "created_at"),
        Index("idx_audit_log_event_created", "event_type", "created_at"),
    )


# ----------------------------------------------------------------- Phase 8
NOTIFICATION_STATUSES = (
    "('DRAFT','READY_FOR_REVIEW','APPROVED','MOCK_SENT','MOCK_FAILED','CANCELLED')"
)


class NotificationTemplate(TimestampMixin, Base):
    __tablename__ = "notification_template"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    created_by_staff_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("staff_user.id", ondelete="SET NULL")
    )
    # Phase 8.1: template used for drafts generated from workbook uploads, per class type.
    default_for_class_type: Mapped[str | None] = mapped_column(String(20))
    __table_args__ = (
        CheckConstraint("btrim(name) <> ''", name="chk_notification_template_name"),
        CheckConstraint(
            "default_for_class_type IS NULL OR default_for_class_type IN ('REGULAR','EXAM_PREP')",
            name="chk_notification_template_default_type",
        ),
        Index(
            "uq_notification_template_default_type",
            "default_for_class_type",
            unique=True,
            postgresql_where=text("default_for_class_type IS NOT NULL"),
        ),
        CheckConstraint(
            "btrim(body) <> '' AND char_length(body) <= 2000", name="chk_notification_template_body"
        ),
        UniqueConstraint("name", name="uq_notification_template_name"),
    )


class ParentNotification(TimestampMixin, Base):
    """One parent message: student (enrollment) x lesson x template, with a frozen body."""

    __tablename__ = "parent_notification"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    classroom_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    lesson_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    enrollment_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("notification_template.id", ondelete="RESTRICT"), nullable=False
    )
    template_version: Mapped[int] = mapped_column(Integer, nullable=False)
    template_body: Mapped[str] = mapped_column(Text, nullable=False)
    recipient_email: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    source_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'DRAFT'"))
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    created_by_staff_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("staff_user.id", ondelete="SET NULL")
    )
    updated_by_staff_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("staff_user.id", ondelete="SET NULL")
    )
    approved_by_staff_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("staff_user.id", ondelete="SET NULL")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint(
            f"status IN {NOTIFICATION_STATUSES}", name="chk_parent_notification_status"
        ),
        CheckConstraint(
            "btrim(body) <> '' AND char_length(body) <= 2000", name="chk_parent_notification_body"
        ),
        CheckConstraint(
            "status NOT IN ('APPROVED','MOCK_SENT','MOCK_FAILED') OR approved_at IS NOT NULL",
            name="chk_parent_notification_approved",
        ),
        ForeignKeyConstraint(
            ["lesson_id", "classroom_id"],
            ["lesson.id", "lesson.classroom_id"],
            name="fk_parent_notification_lesson",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["enrollment_id", "classroom_id"],
            ["enrollment.id", "enrollment.classroom_id"],
            name="fk_parent_notification_enrollment",
            ondelete="RESTRICT",
        ),
        Index(
            "uq_parent_notification_active",
            "lesson_id",
            "enrollment_id",
            "template_id",
            unique=True,
            postgresql_where=text("status <> 'CANCELLED'"),
        ),
        Index("idx_parent_notification_classroom_status", "classroom_id", "status"),
        Index("idx_parent_notification_lesson", "lesson_id"),
    )


class NotificationSendAttempt(Base):
    """Ledger of mock sends. Nothing is transmitted; channel is always MOCK."""

    __tablename__ = "notification_send_attempt"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    notification_id: Mapped[int] = mapped_column(
        ForeignKey("parent_notification.id", ondelete="RESTRICT"), nullable=False
    )
    idempotency_key: Mapped[UUID] = mapped_column(PgUUID, nullable=False)
    channel: Mapped[str] = mapped_column(String(10), nullable=False, server_default=text("'MOCK'"))
    result: Mapped[str] = mapped_column(String(20), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(50))
    error_message: Mapped[str | None] = mapped_column(String(255))
    requested_by_staff_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("staff_user.id", ondelete="SET NULL")
    )
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    __table_args__ = (
        CheckConstraint("channel = 'MOCK'", name="chk_notification_send_attempt_channel"),
        CheckConstraint(
            "(result = 'MOCK_SUCCESS' AND error_code IS NULL) OR "
            "(result = 'MOCK_FAILURE' AND error_code IS NOT NULL)",
            name="chk_notification_send_attempt_result",
        ),
        UniqueConstraint("idempotency_key", name="uq_notification_send_attempt_key"),
        Index(
            "uq_notification_send_attempt_success",
            "notification_id",
            unique=True,
            postgresql_where=text("result = 'MOCK_SUCCESS'"),
        ),
        Index("idx_notification_send_attempt_notification", "notification_id"),
    )
