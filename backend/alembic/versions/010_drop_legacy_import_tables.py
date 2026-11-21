"""Remove the legacy CSV/XLSX import tables (import_job, import_row, import_error).

The legacy import (``/api/imports``) was removed from the FastAPI/React product on 2026-11-20;
the weekly workbook upload (``/api/lesson-uploads``) replaces it and records to audit_log.
Nothing in the Python application reads or writes these tables any more.

Safety: the upgrade refuses to run while any of the three tables holds a row, so no import
record is ever deleted silently. Downgrade recreates the tables exactly as the baseline DDL
(``sql/schema_postgresql.sql``) defined them — empty, since their rows were never kept.
"""

from alembic import op

revision = "010_drop_legacy_import_tables"
down_revision = "009_phase81_lesson_upload"
branch_labels = None
depends_on = None

TABLES = ("import_error", "import_row", "import_job")


def upgrade() -> None:
    bind = op.get_bind()
    counts = {
        table: bind.exec_driver_sql(f"SELECT count(*) FROM {table}").scalar_one()
        for table in TABLES
    }
    if any(counts.values()):
        raise RuntimeError(
            "구 가져오기 테이블에 기록이 있어 삭제하지 않습니다: "
            + ", ".join(f"{table}={count}" for table, count in counts.items())
            + ". 보관 여부를 결정한 뒤 다시 실행하세요."
        )
    op.execute("DROP TABLE import_error")
    op.execute("DROP TABLE import_row")
    op.execute("DROP TABLE import_job")


def downgrade() -> None:
    op.execute(
        """
        CREATE TABLE import_job (
            id BIGSERIAL PRIMARY KEY,
            source_type VARCHAR(20) NOT NULL,
            source_file_name VARCHAR(255) NOT NULL,
            file_hash CHAR(64),
            total_rows INTEGER NOT NULL DEFAULT 0,
            success_rows INTEGER NOT NULL DEFAULT 0,
            failed_rows INTEGER NOT NULL DEFAULT 0,
            request_id UUID,
            idempotency_key UUID,
            insert_count INTEGER NOT NULL DEFAULT 0,
            update_count INTEGER NOT NULL DEFAULT 0,
            skip_count INTEGER NOT NULL DEFAULT 0,
            status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
            started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            finished_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT chk_import_job_source_type CHECK (source_type IN ('CSV', 'XLSX')),
            CONSTRAINT chk_import_job_status
                CHECK (status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'SUCCESS', 'FAILED')),
            CONSTRAINT chk_import_job_counts CHECK (
                total_rows >= 0 AND success_rows >= 0 AND failed_rows >= 0
                AND insert_count >= 0 AND update_count >= 0 AND skip_count >= 0
                AND success_rows + failed_rows <= total_rows
                AND insert_count + update_count + skip_count <= total_rows
            ),
            CONSTRAINT chk_import_job_finished_at
                CHECK (finished_at IS NULL OR finished_at >= started_at)
        );
        CREATE INDEX idx_import_job_status ON import_job(status);
        CREATE INDEX idx_import_job_started_at ON import_job(started_at);
        CREATE INDEX idx_import_job_file_hash ON import_job(file_hash);
        CREATE UNIQUE INDEX uq_import_job_idempotency_key ON import_job(idempotency_key);

        CREATE TABLE import_row (
            id BIGSERIAL PRIMARY KEY,
            import_job_id BIGINT NOT NULL,
            lesson_result_id BIGINT,
            row_number INTEGER NOT NULL,
            row_hash CHAR(64),
            processing_result VARCHAR(20) NOT NULL,
            enrollment_action VARCHAR(20),
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_import_row_job
                FOREIGN KEY (import_job_id) REFERENCES import_job(id) ON DELETE CASCADE,
            CONSTRAINT fk_import_row_lesson_result
                FOREIGN KEY (lesson_result_id) REFERENCES lesson_result(id) ON DELETE SET NULL,
            CONSTRAINT chk_import_row_number CHECK (row_number > 0),
            CONSTRAINT chk_import_row_processing_result
                CHECK (processing_result IN ('INSERT', 'UPDATE', 'SKIP', 'ERROR')),
            CONSTRAINT chk_import_row_enrollment_action CHECK (
                enrollment_action IS NULL OR enrollment_action IN ('INSERT', 'UPDATE', 'SKIP')
            ),
            CONSTRAINT uq_import_row UNIQUE (import_job_id, row_number)
        );
        CREATE INDEX idx_import_row_job ON import_row(import_job_id);
        CREATE INDEX idx_import_row_lesson_result ON import_row(lesson_result_id);
        CREATE INDEX idx_import_row_processing_result ON import_row(processing_result);
        CREATE INDEX idx_import_row_hash ON import_row(row_hash);

        CREATE TABLE import_error (
            id BIGSERIAL PRIMARY KEY,
            import_row_id BIGINT NOT NULL,
            field_name VARCHAR(100),
            error_code VARCHAR(50) NOT NULL,
            error_message TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_import_error_row
                FOREIGN KEY (import_row_id) REFERENCES import_row(id) ON DELETE CASCADE
        );
        CREATE INDEX idx_import_error_row ON import_error(import_row_id);
        CREATE INDEX idx_import_error_code ON import_error(error_code);
        """
    )
