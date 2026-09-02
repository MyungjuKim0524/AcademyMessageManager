-- Academy Message Manager PostgreSQL v1.2 sample data
-- Synthetic data only. Run once against an empty database after schema_postgresql.sql.

BEGIN;

INSERT INTO student (name, school_name, parent_name, parent_email) VALUES
    ('샘플학생1', '가상중학교', '샘플보호자1', 'parent1@example.invalid'),
    ('샘플학생2', '가상중학교', '샘플보호자2', 'parent2@example.invalid'),
    ('샘플학생3', '예시중학교', '샘플보호자3', 'parent3@example.invalid');

INSERT INTO classroom (name, class_type) VALUES
    ('JAVA-A', 'REGULAR'),
    ('중3내신-A', 'EXAM_PREP');

INSERT INTO enrollment (student_id, classroom_id, status, enrolled_at, ended_at) VALUES
    ((SELECT id FROM student WHERE name = '샘플학생1'), (SELECT id FROM classroom WHERE name = 'JAVA-A'), 'ACTIVE', DATE '2026-05-01', NULL),
    ((SELECT id FROM student WHERE name = '샘플학생2'), (SELECT id FROM classroom WHERE name = 'JAVA-A'), 'PAUSED', DATE '2026-05-01', NULL),
    ((SELECT id FROM student WHERE name = '샘플학생3'), (SELECT id FROM classroom WHERE name = '중3내신-A'), 'WITHDRAWN', DATE '2026-04-01', DATE '2026-06-01');

INSERT INTO lesson (classroom_id, lesson_date, exam_round) VALUES
    ((SELECT id FROM classroom WHERE name = 'JAVA-A'), DATE '2026-05-11', '3회차'),
    ((SELECT id FROM classroom WHERE name = 'JAVA-A'), DATE '2026-05-18', NULL),
    ((SELECT id FROM classroom WHERE name = '중3내신-A'), DATE '2026-05-11', '1회차');

INSERT INTO lesson_result
    (lesson_id, enrollment_id, attendance_status, prework_grade, weekly_assignment_grade, correct_count, total_count)
VALUES
    ((SELECT id FROM lesson WHERE lesson_date = DATE '2026-05-11' AND exam_round = '3회차'),
     (SELECT e.id FROM enrollment e JOIN student s ON s.id = e.student_id WHERE s.name = '샘플학생1'),
     'PRESENT', 'A', 'B', 13, 39),
    ((SELECT id FROM lesson WHERE lesson_date = DATE '2026-05-11' AND exam_round = '3회차'),
     (SELECT e.id FROM enrollment e JOIN student s ON s.id = e.student_id WHERE s.name = '샘플학생2'),
     'ABSENT', 'B', 'C', NULL, NULL),
    ((SELECT id FROM lesson WHERE lesson_date = DATE '2026-05-11' AND exam_round = '1회차'),
     (SELECT e.id FROM enrollment e JOIN student s ON s.id = e.student_id WHERE s.name = '샘플학생3'),
     'LATE', NULL, 'A', 39, 39);

INSERT INTO makeup_request (lesson_result_id, target_lesson_id, status)
SELECT lr.id,
       (SELECT id FROM lesson WHERE lesson_date = DATE '2026-05-18' AND exam_round IS NULL),
       'APPROVED'
FROM lesson_result lr
JOIN enrollment e ON e.id = lr.enrollment_id
JOIN student s ON s.id = e.student_id
WHERE s.name = '샘플학생2';

INSERT INTO message_template (class_type, subject_template, body_template) VALUES
    ('REGULAR', '[학습 안내] {학생명}', '{학생명} 학생의 학습 현황입니다.\n{테스트메시지}'),
    ('EXAM_PREP', '[내신 안내] {학생명}', '{학생명} 학생의 내신 대비 현황입니다.\n{테스트메시지}');

INSERT INTO message_draft (lesson_result_id, template_id, subject, body, draft_status)
SELECT lr.id, mt.id, '[학습 안내] 샘플학생1', '샘플학생1 학생의 테스트 결과는 13/39입니다.', 'READY'
FROM lesson_result lr
JOIN enrollment e ON e.id = lr.enrollment_id
JOIN student s ON s.id = e.student_id
JOIN message_template mt ON mt.class_type = 'REGULAR'
WHERE s.name = '샘플학생1';

INSERT INTO delivery_job (message_draft_id, recipient_email, status, processed_at)
SELECT id, 'parent1@example.invalid', 'SUCCESS', CURRENT_TIMESTAMP FROM message_draft;

INSERT INTO delivery_attempt (delivery_job_id, attempt_no, attempt_status)
SELECT id, 1, 'SUCCESS' FROM delivery_job;

INSERT INTO import_job
    (source_type, source_file_name, file_hash, total_rows, success_rows, failed_rows, status, finished_at)
VALUES
    ('CSV', 'sample_students.csv', repeat('a', 64), 3, 3, 0, 'COMPLETED', CURRENT_TIMESTAMP),
    ('XLSX', 'invalid_sample.xlsx', repeat('b', 64), 1, 0, 1, 'FAILED', CURRENT_TIMESTAMP);

INSERT INTO import_row (import_job_id, lesson_result_id, row_number, row_hash, processing_result, enrollment_action)
SELECT j.id, lr.id, 2, repeat('c', 64), 'INSERT', 'INSERT'
FROM import_job j
JOIN lesson_result lr ON TRUE
WHERE j.source_file_name = 'sample_students.csv'
ORDER BY lr.id
LIMIT 1;

INSERT INTO import_row (import_job_id, row_number, row_hash, processing_result)
SELECT id, 2, repeat('d', 64), 'ERROR' FROM import_job WHERE source_file_name = 'invalid_sample.xlsx';

INSERT INTO import_error (import_row_id, field_name, error_code, error_message)
SELECT r.id, 'attendance_status', 'INVALID_ATTENDANCE', '출석 상태가 허용 범위를 벗어났습니다.'
FROM import_row r
JOIN import_job j ON j.id = r.import_job_id
WHERE j.source_file_name = 'invalid_sample.xlsx';

COMMIT;
