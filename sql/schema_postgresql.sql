
-- ============================================================
-- Academy Message Manager
-- PostgreSQL Schema v1.1
--
-- Database Redesign
-- Legacy Oracle schema -> PostgreSQL project-specific schema
-- ============================================================

BEGIN;


-- ============================================================
-- updated_at 자동 갱신 함수
-- ============================================================

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- ============================================================
-- 1. STUDENT
-- ============================================================

CREATE TABLE student (
    id BIGSERIAL PRIMARY KEY,

    name VARCHAR(100) NOT NULL,
    school_name VARCHAR(120),

    parent_name VARCHAR(100),
    parent_email VARCHAR(255),

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_student_name
    ON student(name);

CREATE INDEX idx_student_parent_email
    ON student(parent_email);


-- ============================================================
-- 2. CLASSROOM
-- ============================================================

CREATE TABLE classroom (
    id BIGSERIAL PRIMARY KEY,

    name VARCHAR(100) NOT NULL,
    class_type VARCHAR(20) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_classroom_class_type
        CHECK (
            class_type IN (
                'REGULAR',
                'EXAM_PREP'
            )
        ),

    CONSTRAINT uq_classroom_name_class_type
        UNIQUE (name, class_type)
);


-- ============================================================
-- 3. ENROLLMENT
-- ============================================================

CREATE TABLE enrollment (
    id BIGSERIAL PRIMARY KEY,

    student_id BIGINT NOT NULL,
    classroom_id BIGINT NOT NULL,

    status VARCHAR(20) NOT NULL,

    enrolled_at DATE NOT NULL,
    ended_at DATE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_enrollment_student
        FOREIGN KEY (student_id)
        REFERENCES student(id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_enrollment_classroom
        FOREIGN KEY (classroom_id)
        REFERENCES classroom(id)
        ON DELETE RESTRICT,

    CONSTRAINT chk_enrollment_status
        CHECK (
            status IN (
                'ACTIVE',
                'PAUSED',
                'WITHDRAWN'
            )
        ),

    CONSTRAINT chk_enrollment_dates
        CHECK (
            ended_at IS NULL
            OR ended_at >= enrolled_at
        ),

    CONSTRAINT uq_enrollment
        UNIQUE (
            student_id,
            classroom_id,
            enrolled_at
        )
);

CREATE INDEX idx_enrollment_student
    ON enrollment(student_id);

CREATE INDEX idx_enrollment_classroom
    ON enrollment(classroom_id);

CREATE INDEX idx_enrollment_status
    ON enrollment(status);


-- ============================================================
-- 4. LESSON
-- ============================================================

CREATE TABLE lesson (
    id BIGSERIAL PRIMARY KEY,

    classroom_id BIGINT NOT NULL,

    lesson_date DATE NOT NULL,
    exam_round VARCHAR(50),

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_lesson_classroom
        FOREIGN KEY (classroom_id)
        REFERENCES classroom(id)
        ON DELETE RESTRICT
);

CREATE INDEX idx_lesson_classroom
    ON lesson(classroom_id);

CREATE INDEX idx_lesson_date
    ON lesson(lesson_date);

-- exam_round가 존재하는 경우
CREATE UNIQUE INDEX uq_lesson_with_exam_round
    ON lesson (
        classroom_id,
        lesson_date,
        exam_round
    )
    WHERE exam_round IS NOT NULL;

-- exam_round가 NULL인 일반 수업도 중복 생성 방지
CREATE UNIQUE INDEX uq_lesson_without_exam_round
    ON lesson (
        classroom_id,
        lesson_date
    )
    WHERE exam_round IS NULL;


-- ============================================================
-- 5. LESSON_RESULT
-- ============================================================

CREATE TABLE lesson_result (
    id BIGSERIAL PRIMARY KEY,

    lesson_id BIGINT NOT NULL,
    enrollment_id BIGINT NOT NULL,

    attendance_status VARCHAR(20) NOT NULL,

    prework_grade VARCHAR(20),
    weekly_assignment_grade VARCHAR(20),

    correct_count SMALLINT,
    total_count SMALLINT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_lesson_result_lesson
        FOREIGN KEY (lesson_id)
        REFERENCES lesson(id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_lesson_result_enrollment
        FOREIGN KEY (enrollment_id)
        REFERENCES enrollment(id)
        ON DELETE RESTRICT,

    CONSTRAINT chk_lesson_result_attendance
        CHECK (
            attendance_status IN (
                'PRESENT',
                'ABSENT',
                'LATE'
            )
        ),

    CONSTRAINT chk_lesson_result_prework_grade
        CHECK (
            prework_grade IS NULL
            OR prework_grade IN ('A', 'B', 'C')
        ),

    CONSTRAINT chk_lesson_result_weekly_grade
        CHECK (
            weekly_assignment_grade IS NULL
            OR weekly_assignment_grade IN ('A', 'B', 'C')
        ),

    CONSTRAINT chk_lesson_result_test_counts
        CHECK (
            (
                correct_count IS NULL
                AND total_count IS NULL
            )
            OR
            (
                correct_count IS NOT NULL
                AND total_count IS NOT NULL
                AND correct_count >= 0
                AND total_count > 0
                AND correct_count <= total_count
            )
        ),

    CONSTRAINT uq_lesson_result
        UNIQUE (
            lesson_id,
            enrollment_id
        )
);

CREATE INDEX idx_lesson_result_lesson
    ON lesson_result(lesson_id);

CREATE INDEX idx_lesson_result_enrollment
    ON lesson_result(enrollment_id);

CREATE INDEX idx_lesson_result_attendance
    ON lesson_result(attendance_status);


-- ============================================================
-- 6. MAKEUP_REQUEST
-- ============================================================

CREATE TABLE makeup_request (
    id BIGSERIAL PRIMARY KEY,

    lesson_result_id BIGINT NOT NULL,
    target_lesson_id BIGINT,

    status VARCHAR(20) NOT NULL,

    requested_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,

    cancel_reason VARCHAR(255),

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_makeup_request_lesson_result
        FOREIGN KEY (lesson_result_id)
        REFERENCES lesson_result(id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_makeup_request_target_lesson
        FOREIGN KEY (target_lesson_id)
        REFERENCES lesson(id)
        ON DELETE RESTRICT,

    CONSTRAINT chk_makeup_request_status
        CHECK (
            status IN (
                'REQUESTED',
                'APPROVED',
                'COMPLETED',
                'CANCELLED'
            )
        ),

    CONSTRAINT chk_makeup_request_completed_at
        CHECK (
            completed_at IS NULL
            OR completed_at >= requested_at
        )
);

CREATE INDEX idx_makeup_request_lesson_result
    ON makeup_request(lesson_result_id);

CREATE INDEX idx_makeup_request_target_lesson
    ON makeup_request(target_lesson_id);

CREATE INDEX idx_makeup_request_status
    ON makeup_request(status);


-- ============================================================
-- 7. MESSAGE_TEMPLATE
-- ============================================================

CREATE TABLE message_template (
    id BIGSERIAL PRIMARY KEY,

    class_type VARCHAR(20) NOT NULL,

    subject_template TEXT NOT NULL,
    body_template TEXT NOT NULL,

    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_message_template_class_type
        CHECK (
            class_type IN (
                'REGULAR',
                'EXAM_PREP'
            )
        ),

    CONSTRAINT uq_message_template_class_type
        UNIQUE (class_type)
);


-- ============================================================
-- 8. MESSAGE_DRAFT
-- ============================================================

CREATE TABLE message_draft (
    id BIGSERIAL PRIMARY KEY,

    lesson_result_id BIGINT NOT NULL,
    template_id BIGINT NOT NULL,

    subject TEXT NOT NULL,
    body TEXT NOT NULL,

    draft_status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',

    generated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_message_draft_lesson_result
        FOREIGN KEY (lesson_result_id)
        REFERENCES lesson_result(id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_message_draft_template
        FOREIGN KEY (template_id)
        REFERENCES message_template(id)
        ON DELETE RESTRICT,

    CONSTRAINT chk_message_draft_status
        CHECK (
            draft_status IN (
                'DRAFT',
                'READY',
                'CANCELLED'
            )
        )
);

CREATE INDEX idx_message_draft_lesson_result
    ON message_draft(lesson_result_id);

CREATE INDEX idx_message_draft_template
    ON message_draft(template_id);

CREATE INDEX idx_message_draft_status
    ON message_draft(draft_status);


-- ============================================================
-- 9. DELIVERY_JOB
-- ============================================================

CREATE TABLE delivery_job (
    id BIGSERIAL PRIMARY KEY,

    message_draft_id BIGINT NOT NULL,

    recipient_email VARCHAR(255) NOT NULL,

    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',

    requested_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_delivery_job_message_draft
        FOREIGN KEY (message_draft_id)
        REFERENCES message_draft(id)
        ON DELETE RESTRICT,

    CONSTRAINT chk_delivery_job_status
        CHECK (
            status IN (
                'PENDING',
                'PROCESSING',
                'SUCCESS',
                'FAILED',
                'SKIPPED'
            )
        ),

    CONSTRAINT chk_delivery_job_processed_at
        CHECK (
            processed_at IS NULL
            OR processed_at >= requested_at
        )
);

CREATE INDEX idx_delivery_job_message_draft
    ON delivery_job(message_draft_id);

CREATE INDEX idx_delivery_job_status
    ON delivery_job(status);

CREATE INDEX idx_delivery_job_recipient_email
    ON delivery_job(recipient_email);


-- ============================================================
-- 10. DELIVERY_ATTEMPT
-- ============================================================

CREATE TABLE delivery_attempt (
    id BIGSERIAL PRIMARY KEY,

    delivery_job_id BIGINT NOT NULL,

    attempt_no INTEGER NOT NULL,
    attempt_status VARCHAR(20) NOT NULL,

    error_message TEXT,

    attempted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_delivery_attempt_job
        FOREIGN KEY (delivery_job_id)
        REFERENCES delivery_job(id)
        ON DELETE CASCADE,

    CONSTRAINT chk_delivery_attempt_no
        CHECK (attempt_no > 0),

    CONSTRAINT chk_delivery_attempt_status
        CHECK (
            attempt_status IN (
                'SUCCESS',
                'FAILED'
            )
        ),

    CONSTRAINT uq_delivery_attempt
        UNIQUE (
            delivery_job_id,
            attempt_no
        )
);

CREATE INDEX idx_delivery_attempt_job
    ON delivery_attempt(delivery_job_id);


-- ============================================================
-- 11. IMPORT_JOB
-- ============================================================

CREATE TABLE import_job (
    id BIGSERIAL PRIMARY KEY,

    source_type VARCHAR(20) NOT NULL,
    source_file_name VARCHAR(255) NOT NULL,

    -- SHA-256 hexadecimal hash
    file_hash CHAR(64),

    total_rows INTEGER NOT NULL DEFAULT 0,
    success_rows INTEGER NOT NULL DEFAULT 0,
    failed_rows INTEGER NOT NULL DEFAULT 0,

    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',

    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_import_job_source_type
        CHECK (
            source_type IN (
                'CSV',
                'XLSX'
            )
        ),

    CONSTRAINT chk_import_job_status
        CHECK (
            status IN (
                'PENDING',
                'PROCESSING',
                'COMPLETED',
                'FAILED'
            )
        ),

    CONSTRAINT chk_import_job_counts
        CHECK (
            total_rows >= 0
            AND success_rows >= 0
            AND failed_rows >= 0
            AND success_rows + failed_rows <= total_rows
        ),

    CONSTRAINT chk_import_job_finished_at
        CHECK (
            finished_at IS NULL
            OR finished_at >= started_at
        )
);

CREATE INDEX idx_import_job_status
    ON import_job(status);

CREATE INDEX idx_import_job_started_at
    ON import_job(started_at);

CREATE INDEX idx_import_job_file_hash
    ON import_job(file_hash);


-- ============================================================
-- 12. IMPORT_ROW
-- ============================================================

CREATE TABLE import_row (
    id BIGSERIAL PRIMARY KEY,

    import_job_id BIGINT NOT NULL,

    -- 정상적으로 처리된 행은 생성/갱신된 수업 결과와 연결
    lesson_result_id BIGINT,

    row_number INTEGER NOT NULL,

    -- 원본 개인정보를 저장하지 않고 행 식별용 hash만 저장
    row_hash CHAR(64),

    processing_result VARCHAR(20) NOT NULL,
    enrollment_action VARCHAR(20),

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_import_row_job
        FOREIGN KEY (import_job_id)
        REFERENCES import_job(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_import_row_lesson_result
        FOREIGN KEY (lesson_result_id)
        REFERENCES lesson_result(id)
        ON DELETE SET NULL,

    CONSTRAINT chk_import_row_number
        CHECK (row_number > 0),

    CONSTRAINT chk_import_row_processing_result
        CHECK (
            processing_result IN (
                'INSERT',
                'UPDATE',
                'SKIP',
                'ERROR'
            )
        ),

    CONSTRAINT chk_import_row_enrollment_action
        CHECK (
            enrollment_action IS NULL
            OR enrollment_action IN (
                'INSERT',
                'UPDATE',
                'SKIP'
            )
        ),

    CONSTRAINT uq_import_row
        UNIQUE (
            import_job_id,
            row_number
        )
);

CREATE INDEX idx_import_row_job
    ON import_row(import_job_id);

CREATE INDEX idx_import_row_lesson_result
    ON import_row(lesson_result_id);

CREATE INDEX idx_import_row_processing_result
    ON import_row(processing_result);

CREATE INDEX idx_import_row_hash
    ON import_row(row_hash);


-- ============================================================
-- 13. IMPORT_ERROR
-- ============================================================

CREATE TABLE import_error (
    id BIGSERIAL PRIMARY KEY,

    import_row_id BIGINT NOT NULL,

    field_name VARCHAR(100),
    error_code VARCHAR(50) NOT NULL,
    error_message TEXT NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_import_error_row
        FOREIGN KEY (import_row_id)
        REFERENCES import_row(id)
        ON DELETE CASCADE
);

CREATE INDEX idx_import_error_row
    ON import_error(import_row_id);

CREATE INDEX idx_import_error_code
    ON import_error(error_code);


-- ============================================================
-- updated_at Triggers
-- ============================================================

CREATE TRIGGER trg_student_updated_at
BEFORE UPDATE ON student
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_classroom_updated_at
BEFORE UPDATE ON classroom
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_enrollment_updated_at
BEFORE UPDATE ON enrollment
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_lesson_updated_at
BEFORE UPDATE ON lesson
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_lesson_result_updated_at
BEFORE UPDATE ON lesson_result
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_makeup_request_updated_at
BEFORE UPDATE ON makeup_request
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_message_template_updated_at
BEFORE UPDATE ON message_template
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_message_draft_updated_at
BEFORE UPDATE ON message_draft
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_delivery_job_updated_at
BEFORE UPDATE ON delivery_job
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();


COMMIT;

