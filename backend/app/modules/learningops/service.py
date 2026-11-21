from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models.tables import (
    AuditLog,
    Classroom,
    ClassroomStaffAssignment,
    Enrollment,
    StaffUser,
    Student,
)
from app.errors import CompatibilityError
from app.modules.auth.dependencies import Principal
from app.modules.auth.service import hash_password

from .repository import LearningOpsRepository
from .schemas import (
    AssignmentCreate,
    ClassroomCreate,
    ClassroomUpdate,
    EnrollmentCreate,
    StaffCreate,
    StaffProfileUpdate,
    StaffStatusUpdate,
    StudentContactUpdate,
    StudentCreate,
)


class LearningOpsService:
    def __init__(self, db: Session):
        self.db, self.repo = db, LearningOpsRepository(db)

    def _commit(self, code: str, message: str):
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise CompatibilityError(409, code, message) from exc

    def _audit(
        self,
        principal: Principal,
        request_id: str | None,
        event: str,
        target,
        details,
        target_type: str = "CLASSROOM",
    ):
        self.db.add(
            AuditLog(
                actor_staff_user_id=principal.user_id,
                event_type=event,
                target_type=target_type,
                target_id=str(target),
                request_id=UUID(request_id) if request_id else None,
                details=details,
            )
        )

    def _flush(self, code: str, message: str):
        """Write pending rows (to get their ids for the audit row) and map a constraint
        violation to a 409; nothing of the request is kept."""
        try:
            self.db.flush()
        except IntegrityError as exc:
            self.db.rollback()
            raise CompatibilityError(409, code, message) from exc

    @staticmethod
    def _assignment_snapshot(row: ClassroomStaffAssignment) -> dict:
        """Who held which class and when — kept in the audit log because a removed assignment
        row is physically deleted (SEC-02). Ids, role and dates only."""
        return {
            "assignment_id": row.id,
            "classroom_id": row.classroom_id,
            "staff_user_id": row.staff_user_id,
            "assignment_role": row.assignment_role,
            "valid_from": row.valid_from.isoformat(),
            "valid_to": row.valid_to.isoformat() if row.valid_to else None,
        }

    def _assignments_of(self, *, classroom_id: int | None = None, staff_id: int | None = None):
        query = select(ClassroomStaffAssignment).order_by(ClassroomStaffAssignment.id)
        if classroom_id is not None:
            query = query.where(ClassroomStaffAssignment.classroom_id == classroom_id)
        if staff_id is not None:
            query = query.where(ClassroomStaffAssignment.staff_user_id == staff_id)
        return [self._assignment_snapshot(row) for row in self.db.scalars(query)]

    def _name_taken(self, name: str, class_type: str) -> str:
        """Conflict message for (name, type): an ended class with that name can be resumed."""
        existing = self.db.scalar(
            select(Classroom).where(Classroom.name == name, Classroom.class_type == class_type)
        )
        if existing is not None and not existing.is_active:
            return "같은 이름의 운영 종료된 반이 있습니다. 반 관리에서 '다시 운영'을 사용하세요."
        return "동일한 반이 이미 등록되어 있습니다."

    def create_classroom(self, data: ClassroomCreate, principal: Principal, request_id):
        row = Classroom(name=data.name.strip(), class_type=data.class_type)
        self.db.add(row)
        try:
            self.db.flush()
        except IntegrityError as exc:
            self.db.rollback()
            message = self._name_taken(row.name, row.class_type)
            raise CompatibilityError(409, "CLASSROOM_ALREADY_EXISTS", message) from exc
        self._audit(
            principal,
            request_id,
            "CLASSROOM_CREATED",
            row.id,
            {"name": row.name, "class_type": row.class_type},
        )
        self.db.commit()
        self.db.refresh(row)
        return row

    def update_classroom(
        self, classroom_id: int, data: ClassroomUpdate, principal: Principal, request_id
    ):
        """Rename or end / resume a class. Ending keeps all records (lessons, scores, messages)
        and only hides the class from daily screens, uploads and access checks."""
        row = self.db.scalar(
            select(Classroom).where(Classroom.id == classroom_id).with_for_update()
        )
        if row is None:
            raise CompatibilityError(404, "CLASSROOM_NOT_FOUND", "반을 찾을 수 없습니다.")
        changes = {}
        if data.name is not None and data.name.strip() != row.name:
            if not data.name.strip():
                raise CompatibilityError(400, "VALIDATION_ERROR", "반 이름을 입력해주세요.")
            changes["name"] = {"before": row.name, "after": data.name.strip()}
            row.name = data.name.strip()
        if data.is_active is not None and data.is_active != row.is_active:
            changes["is_active"] = {"before": row.is_active, "after": data.is_active}
            row.is_active = data.is_active
        if not changes:
            self.db.rollback()
            return row
        self._audit(principal, request_id, "CLASSROOM_UPDATED", row.id, {"changed": changes})
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            message = self._name_taken(data.name.strip(), row.class_type)
            raise CompatibilityError(409, "CLASSROOM_ALREADY_EXISTS", message) from exc
        self.db.refresh(row)
        return row

    def delete_classroom(self, classroom_id: int, principal: Principal, request_id) -> None:
        """Only a class with no records can be deleted (e.g. registered by mistake). The DB's
        RESTRICT foreign keys refuse it once students, lessons or assessments exist."""
        row = self.db.scalar(
            select(Classroom).where(Classroom.id == classroom_id).with_for_update()
        )
        if row is None:
            raise CompatibilityError(404, "CLASSROOM_NOT_FOUND", "반을 찾을 수 없습니다.")
        details = {
            "name": row.name,
            "class_type": row.class_type,
            # Assignment rows go with the class (ON DELETE CASCADE); keep who held it.
            "assignments_removed": self._assignments_of(classroom_id=row.id),
        }
        self.db.delete(row)
        try:
            self.db.flush()
        except IntegrityError as exc:
            self.db.rollback()
            raise CompatibilityError(
                409,
                "CLASSROOM_HAS_RECORDS",
                "수강생·수업·평가 기록이 있는 반은 삭제할 수 없습니다. "
                "대신 '운영 종료'를 사용하세요.",
            ) from exc
        self._audit(principal, request_id, "CLASSROOM_DELETED", classroom_id, details)
        self.db.commit()

    def create_student(self, data: StudentCreate, principal: Principal, request_id):
        """Register a student, and enrol them in a class in the same transaction when given
        (nothing is saved if the enrolment fails). Both are audited in that transaction; the
        audit holds ids and whether contact fields were given, never their values."""
        classroom = None
        if data.classroom_id is not None:
            classroom = self.repo.classroom(data.classroom_id)
            if classroom is None or not classroom.is_active:
                raise CompatibilityError(404, "CLASSROOM_NOT_FOUND", "활성 반을 찾을 수 없습니다.")
        row = Student(
            name=data.name.strip(),
            school_name=data.school_name.strip() if data.school_name else None,
            parent_name=data.parent_name.strip() if data.parent_name else None,
            parent_email=data.parent_email.strip().lower() if data.parent_email else None,
        )
        self.db.add(row)
        conflict = ("STUDENT_BUSINESS_KEY_CONFLICT", "동일한 이름과 학교의 학생이 이미 있습니다.")
        self._flush(*conflict)  # student id for the audit / enrolment; a duplicate fails here
        enrollment = None
        if classroom is not None:
            enrollment = Enrollment(
                classroom_id=classroom.id,
                student_id=row.id,
                status="ACTIVE",
                enrolled_at=data.enrolled_at,
            )
            self.db.add(enrollment)
            self._flush(*conflict)
        self._audit(
            principal,
            request_id,
            "STUDENT_CREATED",
            row.id,
            {
                "school_present": row.school_name is not None,
                "parent_name_present": row.parent_name is not None,
                "parent_email_present": row.parent_email is not None,
                "enrollment_id": enrollment.id if enrollment else None,
            },
            target_type="STUDENT",
        )
        if enrollment is not None:
            self._audit_enrollment(principal, request_id, enrollment, "STUDENT_REGISTRATION")
        self._commit(*conflict)
        self.db.refresh(row)
        return row

    def _audit_enrollment(self, principal, request_id, enrollment: Enrollment, source: str):
        self._audit(
            principal,
            request_id,
            "ENROLLMENT_CREATED",
            enrollment.id,
            {
                "classroom_id": enrollment.classroom_id,
                "student_id": enrollment.student_id,
                "enrolled_at": enrollment.enrolled_at.isoformat(),
                "status": enrollment.status,
                "source": source,
            },
            target_type="ENROLLMENT",
        )

    def students_page(self, query: str | None, limit: int, offset: int):
        rows, total = self.repo.students_page(query, limit, offset)
        by_student: dict[int, list] = {row.id: [] for row in rows}
        for enrollment, classroom in self.repo.enrollments_for_students(list(by_student)):
            by_student[enrollment.student_id].append((enrollment, classroom))
        return [(row, by_student[row.id]) for row in rows], total

    def student_contact(self, student_id: int):
        row = self.repo.student(student_id)
        if row is None:
            raise CompatibilityError(404, "STUDENT_NOT_FOUND", "학생을 찾을 수 없습니다.")
        return row

    def update_student_contact(
        self,
        student_id: int,
        data: StudentContactUpdate,
        principal: Principal,
        request_id: str | None,
    ):
        row = self.db.scalar(select(Student).where(Student.id == student_id).with_for_update())
        if row is None:
            raise CompatibilityError(404, "STUDENT_NOT_FOUND", "학생을 찾을 수 없습니다.")
        changes = {}
        for name in data.model_fields_set:
            value = getattr(data, name)
            if name == "parent_email" and value is not None:
                value = value.lower()
            if value != getattr(row, name):
                changes[name] = value
        if not changes:
            self.db.rollback()
            return row
        for name, value in changes.items():
            setattr(row, name, value)
        # Contact values are personal data: the audit log records which fields changed only.
        self.db.add(
            AuditLog(
                actor_staff_user_id=principal.user_id,
                event_type="STUDENT_CONTACT_UPDATED",
                target_type="STUDENT",
                target_id=str(row.id),
                request_id=UUID(request_id) if request_id else None,
                details={
                    "changed": sorted(changes),
                    "parent_email_present": row.parent_email is not None,
                },
            )
        )
        self.db.commit()
        self.db.refresh(row)
        return row

    def enroll(self, classroom_id: int, data: EnrollmentCreate, principal: Principal, request_id):
        classroom = self.repo.classroom(classroom_id)
        if classroom is None or not classroom.is_active:
            raise CompatibilityError(404, "CLASSROOM_NOT_FOUND", "활성 반을 찾을 수 없습니다.")
        if self.repo.student(data.student_id) is None:
            raise CompatibilityError(404, "STUDENT_NOT_FOUND", "학생을 찾을 수 없습니다.")
        row = Enrollment(
            classroom_id=classroom_id,
            student_id=data.student_id,
            status="ACTIVE",
            enrolled_at=data.enrolled_at,
        )
        self.db.add(row)
        conflict = ("ENROLLMENT_ALREADY_EXISTS", "학생은 해당 반에 이미 등록되어 있습니다.")
        self._flush(*conflict)
        self._audit_enrollment(principal, request_id, row, "MANUAL")
        self._commit(*conflict)
        self.db.refresh(row)
        return row

    def assign(self, classroom_id: int, data: AssignmentCreate, principal: Principal, request_id):
        if data.valid_to is not None and data.valid_to < data.valid_from:
            raise CompatibilityError(400, "INVALID_ASSIGNMENT_DATES", "배정 종료일을 확인해주세요.")
        if self.repo.classroom(classroom_id) is None:
            raise CompatibilityError(404, "CLASSROOM_NOT_FOUND", "반을 찾을 수 없습니다.")
        staff = self.repo.staff(data.staff_user_id)
        if staff is None or staff.status != "ACTIVE":
            raise CompatibilityError(400, "STAFF_NOT_ASSIGNABLE", "활성 직원을 선택해주세요.")
        if staff.role != data.assignment_role:
            raise CompatibilityError(
                400, "ASSIGNMENT_ROLE_MISMATCH", "직원 역할과 배정 역할이 다릅니다."
            )
        row = ClassroomStaffAssignment(classroom_id=classroom_id, **data.model_dump())
        self.db.add(row)
        conflict = ("ASSIGNMENT_ALREADY_EXISTS", "동일한 직원 배정이 이미 있습니다.")
        self._flush(*conflict)
        self._audit(
            principal,
            request_id,
            "ASSIGNMENT_CREATED",
            row.id,
            self._assignment_snapshot(row),
            target_type="CLASSROOM_STAFF_ASSIGNMENT",
        )
        self._commit(*conflict)
        self.db.refresh(row)
        return row

    def create_staff(self, data: StaffCreate, principal: Principal, request_id):
        row = StaffUser(
            email=data.email.strip().lower(),
            display_name=data.display_name,
            password_hash=hash_password(data.password),
            role=data.role,
            status="ACTIVE",
        )
        self.db.add(row)
        try:
            self.db.flush()
        except IntegrityError as exc:
            self.db.rollback()
            existing = self.repo.staff_by_email(row.email)
            message = (
                "삭제된 직원 계정이 사용하던 이메일입니다. 다른 이메일을 사용하세요."
                if existing is not None and existing.status == "DELETED"
                else "동일한 이메일의 직원이 이미 있습니다."
            )
            raise CompatibilityError(409, "STAFF_EMAIL_ALREADY_EXISTS", message) from exc
        # Role only: no e-mail, name or password (hash) in the audit log.
        self._audit(
            principal,
            request_id,
            "STAFF_CREATED",
            row.id,
            {"role": row.role, "status": row.status},
            target_type="STAFF_USER",
        )
        self.db.commit()
        self.db.refresh(row)
        return row

    def delete_staff(self, staff_id: int, principal: Principal, request_id: str | None) -> str:
        """Delete a staff account (option B, 2026-11-20). Returns "HARD" or "SOFT".

        * No history: the account is removed (sessions and class assignments go with it).
        * With history (log-ins, changes, messages): marked DELETED — cannot log in, hidden from
          lists — so every record keeps saying who did it.
        The signed-in account and the last active administrator cannot be deleted.
        """
        row = self.db.scalar(select(StaffUser).where(StaffUser.id == staff_id).with_for_update())
        if row is None or row.status == "DELETED":
            raise CompatibilityError(404, "STAFF_NOT_FOUND", "직원을 찾을 수 없습니다.")
        if row.id == principal.user_id:
            raise CompatibilityError(
                409, "SELF_DELETION_FORBIDDEN", "현재 로그인한 계정은 삭제할 수 없습니다."
            )
        if row.role == "ADMIN" and row.status == "ACTIVE":
            if len(self.repo.active_admins_for_update()) <= 1:
                raise CompatibilityError(
                    409, "LAST_ACTIVE_ADMIN", "마지막 활성 관리자 계정은 삭제할 수 없습니다."
                )
        mode = "SOFT" if self.repo.staff_has_history(row.id) else "HARD"
        # A hard delete takes the account's assignment rows with it (ON DELETE CASCADE).
        removed = self._assignments_of(staff_id=row.id) if mode == "HARD" else []
        if mode == "SOFT":
            row.status = "DELETED"
            self.repo.revoke_sessions(row.id, datetime.now(UTC))
        else:
            self.db.delete(row)
        self.db.flush()
        self._audit(
            principal,
            request_id,
            "STAFF_DELETED",
            staff_id,
            {"mode": mode, "role": row.role, "assignments_removed": removed},
            target_type="STAFF_USER",
        )
        self.db.commit()
        return mode

    def issue_password_reset_code(
        self, staff_id: int, principal: Principal, request_id: str | None
    ) -> tuple[str, datetime]:
        """SEC-10-B (Phase 11-4-B): an administrator issues a one-time code for a member who
        cannot log in, and hands it over in person (no e-mail / SMS). The code is shown once in
        this answer, kept only as a digest in memory, and never written to the database or log.
        Own account: use password change instead (an admin who forgot it asks another admin)."""
        from app.modules.auth.service import RESET_CODE_MINUTES, password_reset_codes, utc_now

        row = self.repo.staff(staff_id)
        if row is None or row.status == "DELETED":
            raise CompatibilityError(404, "STAFF_NOT_FOUND", "직원을 찾을 수 없습니다.")
        if row.id == principal.user_id:
            raise CompatibilityError(
                409,
                "SELF_RESET_FORBIDDEN",
                "본인 계정은 '비밀번호 변경'을 사용하세요.",
            )
        if row.status != "ACTIVE":
            raise CompatibilityError(
                409, "STAFF_NOT_ACTIVE", "비활성 계정입니다. 먼저 활성화하세요."
            )
        self._audit(
            principal,
            request_id,
            "STAFF_PASSWORD_RESET_ISSUED",
            row.id,
            {"role": row.role, "expires_in_minutes": RESET_CODE_MINUTES},
            target_type="STAFF_USER",
        )
        self.db.commit()
        # Issued only after the audit row is stored: no code exists without its record.
        return password_reset_codes.issue(row.id, utc_now(), RESET_CODE_MINUTES)

    def staff_page(self, limit: int, offset: int):
        return self.repo.staff_page(limit, offset)

    def staff_detail(self, staff_id: int):
        row = self.repo.staff(staff_id)
        if row is None or row.status == "DELETED":  # deleted accounts exist only for history
            raise CompatibilityError(404, "STAFF_NOT_FOUND", "직원을 찾을 수 없습니다.")
        return row

    def update_staff_profile(
        self, staff_id: int, data: StaffProfileUpdate, principal: Principal, request_id
    ):
        row = self.staff_detail(staff_id)
        if row.display_name == data.display_name:
            self.db.rollback()
            return row
        row.display_name = data.display_name
        # Which field changed, not the names themselves (as for guardian contact changes).
        self._audit(
            principal,
            request_id,
            "STAFF_RENAMED",
            row.id,
            {"changed": ["display_name"]},
            target_type="STAFF_USER",
        )
        self.db.commit()
        self.db.refresh(row)
        return row

    def update_staff_status(
        self, staff_id: int, data: StaffStatusUpdate, principal: Principal, request_id=None
    ):
        row = self.repo.staff(staff_id)
        if row is None or row.status == "DELETED":  # a deleted account is never reactivated
            raise CompatibilityError(404, "STAFF_NOT_FOUND", "직원을 찾을 수 없습니다.")
        if row.status == data.status:
            return row
        if data.status == "INACTIVE" and row.role == "ADMIN":
            admins = self.repo.active_admins_for_update()
            if row.id == principal.user_id:
                raise CompatibilityError(
                    409,
                    "SELF_ADMIN_DEACTIVATION_FORBIDDEN",
                    "현재 관리자 계정은 비활성화할 수 없습니다.",
                )
            if len(admins) <= 1:
                raise CompatibilityError(
                    409, "LAST_ACTIVE_ADMIN", "마지막 활성 관리자 계정은 비활성화할 수 없습니다."
                )
        before = row.status
        row.status = data.status
        revoked = 0
        if data.status == "INACTIVE":
            revoked = self.repo.revoke_sessions(row.id, datetime.now(UTC))
        self._audit(
            principal,
            request_id,
            "STAFF_STATUS_CHANGED",
            row.id,
            {"before": before, "after": row.status, "role": row.role, "sessions_revoked": revoked},
            target_type="STAFF_USER",
        )
        self.db.commit()
        self.db.refresh(row)
        return row

    def staff_assignments(self, staff_id: int, principal: Principal, limit: int, offset: int):
        if principal.role != "ADMIN" and principal.user_id != staff_id:
            raise CompatibilityError(403, "FORBIDDEN", "다른 직원의 배정은 조회할 수 없습니다.")
        self.staff_detail(staff_id)
        return self.repo.staff_assignments(staff_id, limit, offset)

    def classroom_assignments(self, classroom_id: int, limit: int, offset: int):
        if self.repo.classroom(classroom_id) is None:
            raise CompatibilityError(404, "CLASSROOM_NOT_FOUND", "반을 찾을 수 없습니다.")
        return self.repo.classroom_assignments(classroom_id, limit, offset)

    def remove_assignment(
        self, classroom_id: int, assignment_id: int, principal: Principal, request_id
    ):
        """Access is revoked at once by deleting the row (kept as before); the audit row keeps
        a snapshot of it, so who held the class and when stays traceable (SEC-02)."""
        row = self.db.scalar(
            select(ClassroomStaffAssignment)
            .where(ClassroomStaffAssignment.id == assignment_id)
            .with_for_update()
        )
        if row is None or row.classroom_id != classroom_id:
            raise CompatibilityError(404, "ASSIGNMENT_NOT_FOUND", "배정을 찾을 수 없습니다.")
        snapshot = self._assignment_snapshot(row)
        self.db.delete(row)
        self.db.flush()
        self._audit(
            principal,
            request_id,
            "ASSIGNMENT_REMOVED",
            assignment_id,
            snapshot,
            target_type="CLASSROOM_STAFF_ASSIGNMENT",
        )
        self.db.commit()

    def classrooms(
        self, principal: Principal, limit: int, offset: int, include_inactive: bool = False
    ):
        if include_inactive and principal.role == "ADMIN":  # class management screen only
            return self.repo.all_classrooms(limit, offset)
        return self.repo.classrooms_for_principal(principal.user_id, principal.role, limit, offset)

    def classroom_students(self, classroom_id: int, principal: Principal, limit: int, offset: int):
        classroom = self.repo.classroom(classroom_id)
        if classroom is None or not classroom.is_active:
            raise CompatibilityError(404, "CLASSROOM_NOT_FOUND", "활성 반을 찾을 수 없습니다.")
        if not self.repo.can_access_classroom(classroom_id, principal.user_id, principal.role):
            raise CompatibilityError(
                403, "CLASSROOM_ACCESS_DENIED", "담당 반에만 접근할 수 있습니다."
            )
        return self.repo.students_for_classroom(classroom_id, limit, offset)
