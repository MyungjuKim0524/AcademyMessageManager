# Oracle to PostgreSQL Migration Strategy

## 1. Background

기존 Oracle DB는 학습용 환경으로 프로젝트 외 테이블이 함께 존재한다. 신규 PostgreSQL DB는 AcademyMessageManager 전용 13개 테이블과 import audit 구조를 사용한다. 따라서 이 작업은 스키마 복제가 아니라 검증된 데이터만 변환하는 ETL이다.

## 2. Migration Scope

이전 대상은 학생, 반, 수강 상태, 수업, 학생별 수업 결과, 보강 요청, 활성 메시지 템플릿과 필요한 발송 이력이다. 프로젝트와 무관한 training table, credential, 임시 데이터, 오래되거나 민감한 테스트 데이터는 제외한다. 실제 이전 전에는 개인정보 처리 근거와 보존 기간을 확인한다.

## 3. Data Mapping

| Oracle | PostgreSQL | 변환 |
| --- | --- | --- |
| `student(student_id, student_name, ...)` | `student(id, name, ...)` | 이름과 보호자 정보 정규화 |
| `academy_class` | `classroom` | `active_yn`을 `is_active` boolean으로 변환 |
| `class_enrollment` | `enrollment` | `start_date/end_date`를 `enrolled_at/ended_at`으로 변환 |
| `class_session` | `lesson` | `session_date/test_round`를 `lesson_date/exam_round`으로 변환 |
| `grade_record` | `lesson_result` | 학생·반을 enrollment로 연결하고 출석값을 영문 코드로 변환 |
| `pre_grade/weekly_grade` | `prework_grade/weekly_assignment_grade` | A/B/C/NULL만 허용 |
| `test_result = '13/39'` | `correct_count = 13`, `total_count = 39` | 정규식 검증 후 두 정수로 분리 |
| `makeup_request` | `makeup_request` | 원본 학생/수업을 `lesson_result_id`, 대상 수업을 `target_lesson_id`로 연결 |
| `message_template` | `message_template` | 제목은 기본 제목으로 보완하고 본문을 이전 |
| `send_log` | `message_draft` → `delivery_job` → `delivery_attempt` | 메시지와 시도 이력을 분리하고 상태 매핑 |

출석은 `출석 → PRESENT`, `결석 → ABSENT`로 변환한다. `test_result`는 `^\d+/\d+$`에 맞고 `0 <= correct <= total`, `total > 0`인 값만 이전한다. 빈 값은 두 컬럼 모두 NULL로 저장하며 파싱 실패는 import error로 분리한다.

## 4. Migration Order

`student → classroom → enrollment → lesson → lesson_result → makeup_request → message_template → message_draft → delivery_job → delivery_attempt → import_job → import_row → import_error` 순서로 적재한다.

## 5. Validation

- 원본/대상별 row count와 제외 건수 대조
- FK orphan 0건 확인
- 필수값 NULL, 중복 학생·반·수업 확인
- 상태 및 A/B/C 코드 분포 확인
- 모든 점수 문자열의 파싱 성공/실패 집계
- enrollment와 lesson의 classroom 일치 확인
- 샘플 메시지 및 발송 상태 매핑 검토

## 6. Rollback

Oracle은 읽기 전용 원본으로 유지하고 수정하지 않는다. PostgreSQL은 별도 빈 DB 또는 별도 schema에서 전체 적재·검증한 뒤 전환한다. 실패 시 PostgreSQL 대상 DB를 폐기하고 Oracle 연결 설정으로 복귀한다. 운영 전환 시점, 백업, 검증 결과와 연결 설정 롤백 절차를 기록한다.

## Approved ERD Deviation

기존 보강 대상 수업 지정 기능을 보존하기 위해 ERD v1.1의 `makeup_request`에 nullable `target_lesson_id → lesson(id)`를 추가했다. 요청 시 미배정 상태를 허용하고 이후 승인·완료 정책 강화는 별도 결정한다.

최종 설계 산출물은 **PostgreSQL ERD v1.2**로 확정했다. DDL에는 `fk_makeup_request_target_lesson`과 `idx_makeup_request_target_lesson`이 반영되어 있으며, 실제 PostgreSQL 통합 테스트에서 대상 수업 지정과 조회를 검증한다.

## Actual PostgreSQL Validation

- PostgreSQL 17에 `schema_postgresql.sql`과 `seed_postgresql.sql` 적용 성공
- CSV/XLSX import 및 학생·분반·수강·수업·성적 관계 저장 확인
- DB 템플릿 기반 메시지 생성 확인
- 보강 요청의 `target_lesson_id` 저장, 조회 및 완료 상태 전이 확인
- 발송 작업과 발송 시도 이력 저장 확인
- FK 위반 거부와 명시적 트랜잭션 롤백 확인

재현 가능한 테스트 코드는 `PostgreSqlDaoIntegrationTest`에 있으며, 운영 DB가 아닌 전용 테스트 DB에서만 실행한다.
