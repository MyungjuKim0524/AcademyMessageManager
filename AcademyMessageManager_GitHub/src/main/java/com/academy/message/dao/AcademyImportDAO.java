package com.academy.message.dao;

import com.academy.message.model.ImportRow;
import com.academy.message.model.ImportSummary;

import java.sql.Connection;
import java.sql.Date;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Objects;

public class AcademyImportDAO {
    private final DBConnection dbConnection = new DBConnection();

    public ImportSummary importRows(Iterable<ImportRow> rows) throws SQLException {
        ImportSummary summary = new ImportSummary();
        try (Connection connection = dbConnection.getConnection()) {
            connection.setAutoCommit(false);
            try {
                for (ImportRow row : rows) {
                    int classId = findOrCreateClass(connection, row, summary);
                    int studentId = findOrCreateStudent(connection, row, summary);
                    ensureEnrollment(connection, classId, studentId, row, summary);
                    int sessionId = findOrCreateSession(connection, classId, row, summary);
                    upsertGrade(connection, sessionId, studentId, row, summary);
                }
                connection.commit();
                return summary;
            } catch (SQLException ex) {
                connection.rollback();
                throw ex;
            }
        }
    }

    private int findOrCreateClass(Connection connection, ImportRow row, ImportSummary summary) throws SQLException {
        Integer existingId = queryId(connection, "SELECT class_id FROM academy_class WHERE class_name = ?", row.getClassName());
        if (existingId != null) {
            return existingId;
        }
        try (PreparedStatement statement = connection.prepareStatement(
                "INSERT INTO academy_class (class_name, class_type, subject) VALUES (?, ?, 'JAVA')")) {
            statement.setString(1, row.getClassName());
            statement.setString(2, row.getClassType());
            statement.executeUpdate();
            summary.incrementInsertedClasses();
        }
        return queryRequiredId(connection, "SELECT class_id FROM academy_class WHERE class_name = ?", row.getClassName());
    }

    private int findOrCreateStudent(Connection connection, ImportRow row, ImportSummary summary) throws SQLException {
        Integer existingId = queryId(connection,
                "SELECT student_id FROM student WHERE student_name = ? AND school_name = ?",
                row.getStudentName(), row.getSchoolName());
        if (existingId == null) {
            try (PreparedStatement statement = connection.prepareStatement(
                    "INSERT INTO student (student_name, school_name, parent_name, parent_email) VALUES (?, ?, ?, ?)")) {
                statement.setString(1, row.getStudentName());
                statement.setString(2, row.getSchoolName());
                statement.setString(3, row.getParentName());
                statement.setString(4, row.getParentEmail());
                statement.executeUpdate();
                summary.incrementInsertedStudents();
            }
            return queryRequiredId(connection,
                    "SELECT student_id FROM student WHERE student_name = ? AND school_name = ?",
                    row.getStudentName(), row.getSchoolName());
        }

        try (PreparedStatement statement = connection.prepareStatement(
                "UPDATE student SET parent_name = ?, parent_email = ? WHERE student_id = ?")) {
            statement.setString(1, row.getParentName());
            statement.setString(2, row.getParentEmail());
            statement.setInt(3, existingId);
            int updated = statement.executeUpdate();
            if (updated > 0) {
                summary.incrementUpdatedStudents();
            }
        }
        return existingId;
    }

    private void ensureEnrollment(Connection connection, int classId, int studentId, ImportRow row, ImportSummary summary)
            throws SQLException {
        Integer existingId = queryId(connection,
                "SELECT enrollment_id FROM class_enrollment WHERE class_id = ? AND student_id = ?",
                classId, studentId);
        if (existingId != null) {
            return;
        }
        try (PreparedStatement statement = connection.prepareStatement(
                "INSERT INTO class_enrollment (class_id, student_id, status, start_date) VALUES (?, ?, ?, ?)")) {
            statement.setInt(1, classId);
            statement.setInt(2, studentId);
            statement.setString(3, blankToDefault(row.getEnrollmentStatus(), "ACTIVE"));
            statement.setDate(4, Date.valueOf(row.getSessionDate()));
            statement.executeUpdate();
            summary.incrementInsertedEnrollments();
        }
    }

    private int findOrCreateSession(Connection connection, int classId, ImportRow row, ImportSummary summary)
            throws SQLException {
        Integer existingId = queryId(connection,
                "SELECT session_id FROM class_session WHERE class_id = ? AND session_date = ? AND test_round = ?",
                classId, Date.valueOf(row.getSessionDate()), row.getTestRound());
        if (existingId != null) {
            return existingId;
        }
        try (PreparedStatement statement = connection.prepareStatement(
                "INSERT INTO class_session (class_id, session_date, test_round) VALUES (?, ?, ?)")) {
            statement.setInt(1, classId);
            statement.setDate(2, Date.valueOf(row.getSessionDate()));
            statement.setString(3, row.getTestRound());
            statement.executeUpdate();
            summary.incrementInsertedSessions();
        }
        return queryRequiredId(connection,
                "SELECT session_id FROM class_session WHERE class_id = ? AND session_date = ? AND test_round = ?",
                classId, Date.valueOf(row.getSessionDate()), row.getTestRound());
    }

    private void upsertGrade(Connection connection, int sessionId, int studentId, ImportRow row, ImportSummary summary)
            throws SQLException {
        try (PreparedStatement statement = connection.prepareStatement(
                "SELECT grade_id, attendance, pre_grade, weekly_grade, test_result "
                        + "FROM grade_record WHERE session_id = ? AND student_id = ?")) {
            statement.setInt(1, sessionId);
            statement.setInt(2, studentId);
            try (ResultSet resultSet = statement.executeQuery()) {
                if (!resultSet.next()) {
                    insertGrade(connection, sessionId, studentId, row);
                    summary.incrementInsertedGrades();
                    return;
                }
                int gradeId = resultSet.getInt("grade_id");
                boolean changed = !Objects.equals(resultSet.getString("attendance"), row.getAttendance())
                        || !Objects.equals(nullToBlank(resultSet.getString("pre_grade")), row.getPreGrade())
                        || !Objects.equals(nullToBlank(resultSet.getString("weekly_grade")), row.getWeeklyGrade())
                        || !Objects.equals(nullToBlank(resultSet.getString("test_result")), row.getTestResult());
                if (changed) {
                    updateGrade(connection, gradeId, row);
                    summary.incrementUpdatedGrades();
                } else {
                    summary.incrementSkippedGrades();
                }
            }
        }
    }

    private void insertGrade(Connection connection, int sessionId, int studentId, ImportRow row) throws SQLException {
        try (PreparedStatement statement = connection.prepareStatement(
                "INSERT INTO grade_record (session_id, student_id, attendance, pre_grade, weekly_grade, test_result) "
                        + "VALUES (?, ?, ?, ?, ?, ?)")) {
            statement.setInt(1, sessionId);
            statement.setInt(2, studentId);
            statement.setString(3, row.getAttendance());
            statement.setString(4, blankToNull(row.getPreGrade()));
            statement.setString(5, blankToNull(row.getWeeklyGrade()));
            statement.setString(6, blankToNull(row.getTestResult()));
            statement.executeUpdate();
        }
    }

    private void updateGrade(Connection connection, int gradeId, ImportRow row) throws SQLException {
        try (PreparedStatement statement = connection.prepareStatement(
                "UPDATE grade_record SET attendance = ?, pre_grade = ?, weekly_grade = ?, test_result = ? WHERE grade_id = ?")) {
            statement.setString(1, row.getAttendance());
            statement.setString(2, blankToNull(row.getPreGrade()));
            statement.setString(3, blankToNull(row.getWeeklyGrade()));
            statement.setString(4, blankToNull(row.getTestResult()));
            statement.setInt(5, gradeId);
            statement.executeUpdate();
        }
    }

    private Integer queryId(Connection connection, String sql, Object... parameters) throws SQLException {
        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            for (int i = 0; i < parameters.length; i++) {
                statement.setObject(i + 1, parameters[i]);
            }
            try (ResultSet resultSet = statement.executeQuery()) {
                if (resultSet.next()) {
                    return resultSet.getInt(1);
                }
                return null;
            }
        }
    }

    private int queryRequiredId(Connection connection, String sql, Object... parameters) throws SQLException {
        Integer id = queryId(connection, sql, parameters);
        if (id == null) {
            throw new SQLException("생성된 ID를 다시 조회하지 못했습니다.");
        }
        return id;
    }

    private String blankToDefault(String value, String defaultValue) {
        return value == null || value.isBlank() ? defaultValue : value;
    }

    private String blankToNull(String value) {
        return value == null || value.isBlank() ? null : value;
    }

    private String nullToBlank(String value) {
        return value == null ? "" : value;
    }
}
