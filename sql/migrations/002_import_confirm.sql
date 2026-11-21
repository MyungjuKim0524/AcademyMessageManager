-- Import Confirm audit/idempotency migration.
-- Apply only after reviewing the duplicate preflight result on the intended database.
BEGIN;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM student
        GROUP BY name, COALESCE(school_name, '')
        HAVING COUNT(*) > 1
    ) THEN
        RAISE EXCEPTION 'student business-key duplicates must be resolved before migration';
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_student_business_key
    ON student(name, COALESCE(school_name, ''));

ALTER TABLE import_job
    ADD COLUMN IF NOT EXISTS request_id UUID,
    ADD COLUMN IF NOT EXISTS idempotency_key UUID,
    ADD COLUMN IF NOT EXISTS insert_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS update_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS skip_count INTEGER NOT NULL DEFAULT 0;

ALTER TABLE import_job DROP CONSTRAINT IF EXISTS chk_import_job_status;
ALTER TABLE import_job ADD CONSTRAINT chk_import_job_status
    CHECK (status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'SUCCESS', 'FAILED'));

ALTER TABLE import_job DROP CONSTRAINT IF EXISTS chk_import_job_counts;
ALTER TABLE import_job ADD CONSTRAINT chk_import_job_counts CHECK (
    total_rows >= 0 AND success_rows >= 0 AND failed_rows >= 0
    AND insert_count >= 0 AND update_count >= 0 AND skip_count >= 0
    AND success_rows + failed_rows <= total_rows
    AND insert_count + update_count + skip_count <= total_rows
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_import_job_idempotency_key
    ON import_job(idempotency_key);

COMMIT;
