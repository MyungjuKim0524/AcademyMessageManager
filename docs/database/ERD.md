# Database ERD (현재 스키마)

> **자동 생성 문서**: `backend/scripts/generate_erd.py`가 SQLAlchemy 모델(`backend/app/db/models/tables.py`)에서 만든다. 직접 고치지 말고, Migration 뒤에 스크립트를 다시 실행한다.
> 기준: 테이블 20개, Alembic head와 일치하는 모델(`alembic check` 차이 없음 확인 대상).

- 표기: `PK` 기본키, `FK` 외래키, `UK` 단일 열 UNIQUE, `"nullable"` NULL 허용 열.
- 관계선: `||` 반드시 1, `o|` 0 또는 1(외래키 NULL 허용), `}o` 0개 이상.
- 여러 열 UNIQUE, 부분 UNIQUE, CHECK, EXCLUDE, 트리거는 그림에 나오지 않는다. 정의는 `tables.py`와 `backend/alembic/versions/`에 있다.
- 이전 ERD(`AMM_PostgreSQL_ERD_v1.3.*`, `PostgreSQL ERD v1.2.drawio`, `import-audit-erd.md`)는 Java v1.2 시절 스키마 기록이다.

## 전체 관계 개요

```mermaid
erDiagram
    assessment ||--}o assessment_result : "assessment_id, classroom_id, max_score"
    classroom ||--}o assessment : "classroom_id"
    classroom ||--}o classroom_staff_assignment : "classroom_id"
    classroom ||--}o enrollment : "classroom_id"
    classroom ||--}o lesson : "classroom_id"
    delivery_job ||--}o delivery_attempt : "delivery_job_id"
    enrollment ||--}o assessment_result : "enrollment_id, classroom_id"
    enrollment ||--}o enrollment_pause : "enrollment_id"
    enrollment ||--}o lesson_result : "enrollment_id"
    enrollment ||--}o parent_notification : "enrollment_id, classroom_id"
    lesson o|--}o assessment : "lesson_id, classroom_id"
    lesson o|--}o makeup_request : "target_lesson_id"
    lesson ||--}o lesson_result : "lesson_id"
    lesson ||--}o parent_notification : "lesson_id, classroom_id"
    lesson_result ||--}o makeup_request : "lesson_result_id"
    lesson_result ||--}o message_draft : "lesson_result_id"
    message_draft ||--}o delivery_job : "message_draft_id"
    message_template ||--}o message_draft : "template_id"
    notification_template ||--}o parent_notification : "template_id"
    parent_notification ||--}o notification_send_attempt : "notification_id"
    staff_user o|--}o audit_log : "actor_staff_user_id"
    staff_user o|--}o notification_send_attempt : "requested_by_staff_user_id"
    staff_user o|--}o notification_template : "created_by_staff_user_id"
    staff_user o|--}o parent_notification : "approved_by_staff_user_id"
    staff_user o|--}o parent_notification : "created_by_staff_user_id"
    staff_user o|--}o parent_notification : "updated_by_staff_user_id"
    staff_user ||--}o auth_session : "staff_user_id"
    staff_user ||--}o classroom_staff_assignment : "staff_user_id"
    student ||--}o enrollment : "student_id"
```

## 학사: 학생·반·수강·수업·출결·성적

학원 운영의 기본 데이터. 출결은 `lesson_result`, 평가 점수는 `assessment_result`에 저장한다. `makeup_request`는 Java 버전의 보강 관리용 테이블로, 웹 버전에는 화면·API가 없다.

```mermaid
erDiagram
    student {
        bigint id PK
        varchar name
        varchar school_name "nullable"
        varchar parent_name "nullable"
        varchar parent_email "nullable"
        timestamptz created_at
        timestamptz updated_at
    }
    classroom {
        bigint id PK
        varchar name
        varchar class_type
        boolean is_active
        timestamptz created_at
        timestamptz updated_at
    }
    enrollment {
        bigint id PK
        bigint student_id FK
        bigint classroom_id FK
        varchar status
        date enrolled_at
        date ended_at "nullable"
        timestamptz created_at
        timestamptz updated_at
    }
    enrollment_pause {
        bigint id PK
        bigint enrollment_id FK
        date paused_from
        date resumed_on "nullable"
        varchar source
        timestamptz created_at
        timestamptz updated_at
    }
    lesson {
        bigint id PK
        bigint classroom_id FK
        date lesson_date
        varchar exam_round "nullable"
        varchar topic "nullable"
        varchar memo "nullable"
        varchar status
        integer version
        smallint session_no
        timestamptz created_at
        timestamptz updated_at
    }
    lesson_result {
        bigint id PK
        bigint lesson_id FK
        bigint enrollment_id FK
        varchar attendance_status
        varchar prework_grade "nullable"
        varchar weekly_assignment_grade "nullable"
        smallint correct_count "nullable"
        smallint total_count "nullable"
        varchar memo "nullable"
        integer version
        timestamptz created_at
        timestamptz updated_at
    }
    assessment {
        bigint id PK
        bigint classroom_id FK
        bigint lesson_id FK "nullable"
        varchar title
        date assessment_date
        numeric max_score
        integer version
        timestamptz created_at
        timestamptz updated_at
    }
    assessment_result {
        bigint id PK
        bigint assessment_id FK
        bigint classroom_id FK
        numeric max_score FK
        bigint enrollment_id FK
        varchar result_status
        numeric score "nullable"
        varchar memo "nullable"
        integer version
        timestamptz created_at
        timestamptz updated_at
    }
    makeup_request {
        bigint id PK
        bigint lesson_result_id FK
        bigint target_lesson_id FK "nullable"
        varchar status
        timestamptz requested_at
        timestamptz completed_at "nullable"
        varchar cancel_reason "nullable"
        timestamptz created_at
        timestamptz updated_at
    }
    assessment ||--}o assessment_result : "assessment_id, classroom_id, max_score"
    classroom ||--}o assessment : "classroom_id"
    classroom ||--}o enrollment : "classroom_id"
    classroom ||--}o lesson : "classroom_id"
    enrollment ||--}o assessment_result : "enrollment_id, classroom_id"
    enrollment ||--}o enrollment_pause : "enrollment_id"
    enrollment ||--}o lesson_result : "enrollment_id"
    lesson o|--}o assessment : "lesson_id, classroom_id"
    lesson o|--}o makeup_request : "target_lesson_id"
    lesson ||--}o lesson_result : "lesson_id"
    lesson_result ||--}o makeup_request : "lesson_result_id"
    student ||--}o enrollment : "student_id"
```

## 직원·인증·감사

직원 계정(역할 ADMIN/TEACHER/ASSISTANT, 상태 ACTIVE/INACTIVE/DELETED), 서버 세션, 담당 반 배정, 변경 감사 기록.

```mermaid
erDiagram
    staff_user {
        bigint id PK
        varchar email
        varchar display_name "nullable"
        varchar password_hash
        varchar role
        varchar status
        timestamptz created_at
        timestamptz updated_at
    }
    auth_session {
        uuid id PK
        bigint staff_user_id FK
        char token_hash UK
        char csrf_token_hash
        timestamptz expires_at
        timestamptz revoked_at "nullable"
        timestamptz created_at
        timestamptz last_seen_at
    }
    classroom_staff_assignment {
        bigint id PK
        bigint classroom_id FK
        bigint staff_user_id FK
        varchar assignment_role
        date valid_from
        date valid_to "nullable"
        timestamptz created_at
    }
    audit_log {
        bigint id PK
        bigint actor_staff_user_id FK "nullable"
        varchar event_type
        varchar target_type "nullable"
        varchar target_id "nullable"
        uuid request_id "nullable"
        json details "nullable"
        timestamptz created_at
    }
    staff_user o|--}o audit_log : "actor_staff_user_id"
    staff_user ||--}o auth_session : "staff_user_id"
    staff_user ||--}o classroom_staff_assignment : "staff_user_id"
```

## 학부모 안내 메시지(웹 버전)

템플릿 → 메시지(초안·검토·확정·모의 발송) → 발송 시도 원장. 발송 채널은 CHECK로 `MOCK`만 허용하며, `Idempotency-Key` UNIQUE와 메시지당 성공 1회 부분 UNIQUE로 중복 발송을 막는다.

```mermaid
erDiagram
    notification_template {
        bigint id PK
        varchar name UK
        text body
        boolean is_active
        integer version
        bigint created_by_staff_user_id FK "nullable"
        varchar default_for_class_type "nullable"
        timestamptz created_at
        timestamptz updated_at
    }
    parent_notification {
        bigint id PK
        bigint classroom_id FK
        bigint lesson_id FK
        bigint enrollment_id FK
        bigint template_id FK
        integer template_version
        text template_body
        varchar recipient_email
        text body
        char source_hash
        varchar status
        integer version
        bigint created_by_staff_user_id FK "nullable"
        bigint updated_by_staff_user_id FK "nullable"
        bigint approved_by_staff_user_id FK "nullable"
        timestamptz approved_at "nullable"
        timestamptz created_at
        timestamptz updated_at
    }
    notification_send_attempt {
        bigint id PK
        bigint notification_id FK
        uuid idempotency_key UK
        varchar channel
        varchar result
        varchar error_code "nullable"
        varchar error_message "nullable"
        bigint requested_by_staff_user_id FK "nullable"
        timestamptz attempted_at
    }
    notification_template ||--}o parent_notification : "template_id"
    parent_notification ||--}o notification_send_attempt : "notification_id"
```

## Java 레거시 메시지(웹 버전 미사용)

Java v1.2의 실제 발송 기록용 테이블. 기준선 Migration 001에서 넘어왔고 웹 서비스는 읽거나 쓰지 않는다.

```mermaid
erDiagram
    message_template {
        bigint id PK
        varchar class_type UK
        text subject_template
        text body_template
        boolean is_active
        timestamptz created_at
        timestamptz updated_at
    }
    message_draft {
        bigint id PK
        bigint lesson_result_id FK
        bigint template_id FK
        text subject
        text body
        varchar draft_status
        timestamptz generated_at
        timestamptz created_at
        timestamptz updated_at
    }
    delivery_job {
        bigint id PK
        bigint message_draft_id FK
        varchar recipient_email
        varchar status
        timestamptz requested_at
        timestamptz processed_at "nullable"
        timestamptz created_at
        timestamptz updated_at
    }
    delivery_attempt {
        bigint id PK
        bigint delivery_job_id FK
        integer attempt_no
        varchar attempt_status
        text error_message "nullable"
        timestamptz attempted_at
    }
    delivery_job ||--}o delivery_attempt : "delivery_job_id"
    message_draft ||--}o delivery_job : "message_draft_id"
    message_template ||--}o message_draft : "template_id"
```
