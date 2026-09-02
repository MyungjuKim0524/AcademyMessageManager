-- Run after schema_postgresql.sql in a disposable database.
-- Every case is isolated by a savepoint; no test data remains after ROLLBACK.

\set ON_ERROR_STOP off
\set ON_ERROR_ROLLBACK on

BEGIN;

-- EXPECTED: SUCCESS
INSERT INTO student (name, school_name, parent_email)
VALUES ('제약테스트학생', '가상중학교', 'constraint@example.invalid');
INSERT INTO classroom (name, class_type) VALUES ('제약테스트반', 'REGULAR');
INSERT INTO enrollment (student_id, classroom_id, status, enrolled_at)
VALUES (currval('student_id_seq'), currval('classroom_id_seq'), 'ACTIVE', CURRENT_DATE);
INSERT INTO lesson (classroom_id, lesson_date, exam_round)
VALUES (currval('classroom_id_seq'), CURRENT_DATE, '정상');
INSERT INTO lesson_result (lesson_id, enrollment_id, attendance_status, prework_grade, correct_count, total_count)
VALUES (currval('lesson_id_seq'), currval('enrollment_id_seq'), 'PRESENT', 'A', 13, 39);

-- The following statements are EXPECTED: FAILURE. In psql use ON_ERROR_ROLLBACK=on
-- so each failure rolls back only its statement and execution can continue.

-- EXPECTED: FAILURE (invalid enrollment status)
INSERT INTO enrollment (student_id, classroom_id, status, enrolled_at)
VALUES (currval('student_id_seq'), currval('classroom_id_seq'), 'INVALID', CURRENT_DATE);

-- EXPECTED: FAILURE (invalid attendance)
INSERT INTO lesson_result (lesson_id, enrollment_id, attendance_status)
VALUES (currval('lesson_id_seq'), currval('enrollment_id_seq'), 'INVALID');

-- EXPECTED: FAILURE (invalid grade)
INSERT INTO lesson_result (lesson_id, enrollment_id, attendance_status, prework_grade)
VALUES (currval('lesson_id_seq'), currval('enrollment_id_seq'), 'PRESENT', 'D');

-- EXPECTED: FAILURE (correct_count > total_count)
INSERT INTO lesson_result (lesson_id, enrollment_id, attendance_status, correct_count, total_count)
VALUES (currval('lesson_id_seq'), currval('enrollment_id_seq'), 'PRESENT', 31, 30);

-- EXPECTED: FAILURE (total_count <= 0)
INSERT INTO lesson_result (lesson_id, enrollment_id, attendance_status, correct_count, total_count)
VALUES (currval('lesson_id_seq'), currval('enrollment_id_seq'), 'PRESENT', 0, 0);

-- EXPECTED: FAILURE (only correct_count exists)
INSERT INTO lesson_result (lesson_id, enrollment_id, attendance_status, correct_count)
VALUES (currval('lesson_id_seq'), currval('enrollment_id_seq'), 'PRESENT', 1);

-- EXPECTED: FAILURE (only total_count exists)
INSERT INTO lesson_result (lesson_id, enrollment_id, attendance_status, total_count)
VALUES (currval('lesson_id_seq'), currval('enrollment_id_seq'), 'PRESENT', 10);

-- EXPECTED: FAILURE (ended_at before enrolled_at)
INSERT INTO enrollment (student_id, classroom_id, status, enrolled_at, ended_at)
VALUES (currval('student_id_seq'), currval('classroom_id_seq'), 'WITHDRAWN', CURRENT_DATE, CURRENT_DATE - 1);

-- EXPECTED: FAILURE (duplicate lesson with exam_round)
INSERT INTO lesson (classroom_id, lesson_date, exam_round)
VALUES (currval('classroom_id_seq'), CURRENT_DATE, '정상');

-- EXPECTED: SUCCESS (NULL exam_round baseline)
INSERT INTO lesson (classroom_id, lesson_date, exam_round)
VALUES (currval('classroom_id_seq'), CURRENT_DATE + 1, NULL);

-- EXPECTED: FAILURE (duplicate lesson with NULL exam_round)
INSERT INTO lesson (classroom_id, lesson_date, exam_round)
VALUES (currval('classroom_id_seq'), CURRENT_DATE + 1, NULL);

-- EXPECTED: FAILURE (duplicate lesson_result)
INSERT INTO lesson_result (lesson_id, enrollment_id, attendance_status)
VALUES ((SELECT id FROM lesson WHERE exam_round = '정상'), currval('enrollment_id_seq'), 'PRESENT');

-- EXPECTED: SUCCESS (import baseline)
INSERT INTO import_job (source_type, source_file_name, total_rows, status)
VALUES ('CSV', 'constraint.csv', 1, 'PROCESSING');
INSERT INTO import_row (import_job_id, row_number, processing_result)
VALUES (currval('import_job_id_seq'), 2, 'INSERT');

-- EXPECTED: FAILURE (duplicate import_job + row_number)
INSERT INTO import_row (import_job_id, row_number, processing_result)
VALUES (currval('import_job_id_seq'), 2, 'SKIP');

-- EXPECTED: SUCCESS (message flow baseline)
INSERT INTO message_template (class_type, subject_template, body_template)
VALUES ('REGULAR', '제약 테스트', '제약 테스트');
INSERT INTO message_draft (lesson_result_id, template_id, subject, body)
VALUES (currval('lesson_result_id_seq'), currval('message_template_id_seq'), '제약 테스트', '제약 테스트');
INSERT INTO delivery_job (message_draft_id, recipient_email)
VALUES (currval('message_draft_id_seq'), 'constraint@example.invalid');

-- EXPECTED: SUCCESS (delivery attempt baseline)
INSERT INTO delivery_attempt (delivery_job_id, attempt_no, attempt_status)
VALUES (currval('delivery_job_id_seq'), 1, 'SUCCESS');

-- EXPECTED: FAILURE (attempt_no <= 0)
INSERT INTO delivery_attempt (delivery_job_id, attempt_no, attempt_status)
VALUES (currval('delivery_job_id_seq'), 0, 'FAILED');

-- EXPECTED: FAILURE (invalid FK)
INSERT INTO import_error (import_row_id, error_code, error_message)
VALUES (-1, 'INVALID_FK', '존재하지 않는 행');

ROLLBACK;
