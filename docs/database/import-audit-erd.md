# Import Audit ERD source

> **(2026-11-22) 이전 기록**: 이 문서가 설명하는 `import_job`·`import_row`·`import_error`는 Alembic `010_drop_legacy_import_tables`로 삭제되었다(구 CSV/XLSX 가져오기 제거, Phase 9.6).
> 현재 스키마는 [`ERD.md`](ERD.md)를 본다. 아래 내용은 Java v1.2 시절의 기록으로 남겨 둔다.

이 문서는 `sql/schema_postgresql.sql`의 Import Audit 영역을 표현합니다. 공개 API는 건수·상태·시각만 반환하며 파일명, 해시, 요청 키와 행 데이터는 반환하지 않습니다.

```mermaid
erDiagram
    IMPORT_JOB {
        BIGINT id PK
        VARCHAR source_type
        VARCHAR source_file_name
        CHAR file_hash
        INTEGER total_rows
        INTEGER success_rows
        INTEGER failed_rows
        UUID request_id
        UUID idempotency_key UK
        INTEGER insert_count
        INTEGER update_count
        INTEGER skip_count
        VARCHAR status
        TIMESTAMPTZ started_at
        TIMESTAMPTZ finished_at
        TIMESTAMPTZ created_at
    }
    IMPORT_ROW {
        BIGINT id PK
        BIGINT import_job_id FK
        BIGINT lesson_result_id FK
        INTEGER row_number
        CHAR row_hash
        VARCHAR processing_result
        VARCHAR enrollment_action
        TIMESTAMPTZ created_at
    }
    IMPORT_ERROR {
        BIGINT id PK
        BIGINT import_row_id FK
        VARCHAR field_name
        VARCHAR error_code
        TEXT error_message
        TIMESTAMPTZ created_at
    }
    LESSON_RESULT ||--o{ IMPORT_ROW : mapped_from
    IMPORT_JOB ||--o{ IMPORT_ROW : contains
    IMPORT_ROW ||--o{ IMPORT_ERROR : has
```
