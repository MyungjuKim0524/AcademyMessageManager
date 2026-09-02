package com.academy.message.dao;

import com.academy.message.model.AbsentStudentRow;
import com.academy.message.model.MakeupRequestRow;
import com.academy.message.model.SessionOptionRow;

import java.sql.Connection;
import java.sql.Date;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import java.time.LocalDate;
import com.academy.message.port.MakeupStatusProvider;
import com.academy.message.port.ConnectionProvider;
import com.academy.message.domain.MakeupStatus;

public class MakeupDAO implements MakeupStatusProvider {
    private static final boolean EXCLUDE_PAUSED_STUDENTS_FROM_MAKEUP = true;
    private final ConnectionProvider connectionProvider;
    public MakeupDAO() { this(new DBConnection()); }
    public MakeupDAO(ConnectionProvider connectionProvider) { this.connectionProvider = connectionProvider; }

    public List<AbsentStudentRow> findAbsentStudents() throws SQLException {
        List<AbsentStudentRow> rows = new ArrayList<>();
        try (Connection connection = connectionProvider.getConnection();
                PreparedStatement statement = connection.prepareStatement(
                        "SELECT s.id AS student_id, cs.id AS session_id, s.name AS student_name, s.school_name, ac.name AS class_name, "
                                + "cs.lesson_date AS session_date, cs.exam_round AS test_round, "
                                + "(SELECT MAX(m.status) FROM makeup_request m "
                                + " WHERE m.lesson_result_id = gr.id) AS makeup_status "
                                + "FROM lesson_result gr "
                                + "JOIN enrollment ce ON gr.enrollment_id = ce.id "
                                + "JOIN student s ON ce.student_id = s.id "
                                + "JOIN lesson cs ON gr.lesson_id = cs.id "
                                + "JOIN classroom ac ON cs.classroom_id = ac.id "
                                + "WHERE gr.attendance_status = 'ABSENT' "
                                + "AND ce.status NOT IN (" + excludedMakeupStatusesSql() + ") "
                                + "ORDER BY cs.lesson_date DESC, s.name")) {
            try (ResultSet resultSet = statement.executeQuery()) {
                while (resultSet.next()) {
                    rows.add(new AbsentStudentRow(
                            resultSet.getInt("student_id"),
                            resultSet.getInt("session_id"),
                            resultSet.getString("student_name"),
                            resultSet.getString("school_name"),
                            resultSet.getString("class_name"),
                            resultSet.getDate("session_date").toLocalDate(),
                            resultSet.getString("test_round"),
                            resultSet.getString("makeup_status")));
                }
            }
        }
        return rows;
    }

    public List<SessionOptionRow> findAvailableSessions(int originalSessionId) throws SQLException {
        return findAvailableSessions(originalSessionId, null, null);
    }

    public List<SessionOptionRow> findAvailableSessions(int originalSessionId, LocalDate from, LocalDate to) throws SQLException {
        List<SessionOptionRow> rows = new ArrayList<>();
        String sql = "SELECT cs.id AS session_id, ac.name AS class_name, ac.class_type, cs.lesson_date AS session_date, cs.exam_round AS test_round "
                + "FROM lesson cs "
                + "JOIN classroom ac ON cs.classroom_id = ac.id "
                + "WHERE cs.id <> ? ";
        if (from != null) {
            sql += "AND cs.lesson_date >= ? ";
        }
        if (to != null) {
            sql += "AND cs.lesson_date <= ? ";
        }
        sql += "ORDER BY cs.lesson_date DESC, ac.name";
        try (Connection connection = connectionProvider.getConnection();
                PreparedStatement statement = connection.prepareStatement(sql)) {
            int index = 1;
            statement.setInt(index++, originalSessionId);
            if (from != null) {
                statement.setDate(index++, Date.valueOf(from));
            }
            if (to != null) {
                statement.setDate(index, Date.valueOf(to));
            }
            try (ResultSet resultSet = statement.executeQuery()) {
                while (resultSet.next()) {
                    rows.add(new SessionOptionRow(
                            resultSet.getInt("session_id"),
                            resultSet.getString("class_name"),
                            resultSet.getString("class_type"),
                            resultSet.getDate("session_date").toLocalDate(),
                            resultSet.getString("test_round")));
                }
            }
        }
        return rows;
    }

    public void requestMakeup(int studentId, int originalSessionId, int targetSessionId) throws SQLException {
        try (Connection connection = connectionProvider.getConnection()) {
            if (!isEligibleForMakeup(connection, studentId, originalSessionId)) {
                throw new SQLException("퇴원 또는 휴원 상태 학생은 보강 신청 대상이 아닙니다.");
            }
            try (PreparedStatement statement = connection.prepareStatement(
                        "INSERT INTO makeup_request (lesson_result_id, target_lesson_id, status) "
                                + "SELECT lr.id, ?, 'REQUESTED' FROM lesson_result lr "
                                + "JOIN enrollment e ON e.id = lr.enrollment_id "
                                + "WHERE e.student_id = ? AND lr.lesson_id = ?")) {
                statement.setInt(1, targetSessionId);
                statement.setInt(2, studentId);
                statement.setInt(3, originalSessionId);
                if (statement.executeUpdate() != 1) {
                    throw new SQLException("보강 요청과 연결할 원래 수업 결과를 찾지 못했습니다.");
                }
            }
        }
    }

    public void updateStatus(int makeupId, String status) throws SQLException {
        MakeupStatus target = requireMakeupStatus(status);
        try (Connection connection = connectionProvider.getConnection()) {
            MakeupStatus current = findStatus(connection, makeupId);
            if (!current.canTransitionTo(target)) {
                throw new SQLException("허용되지 않는 보강 상태 변경입니다: " + current + " -> " + target);
            }
            try (PreparedStatement statement = connection.prepareStatement(
                    "UPDATE makeup_request SET status = ?, completed_at = CASE WHEN ? = 'COMPLETED' THEN CURRENT_TIMESTAMP ELSE completed_at END WHERE id = ? AND status = ?")) {
                statement.setString(1, target.name());
                statement.setString(2, target.name());
                statement.setInt(3, makeupId);
                statement.setString(4, current.name());
                if (statement.executeUpdate() != 1) throw new SQLException("보강 신청 상태가 다른 사용자에 의해 변경되었습니다.");
            }
        }
    }

    public List<MakeupRequestRow> findRequests() throws SQLException {
        List<MakeupRequestRow> rows = new ArrayList<>();
        try (Connection connection = connectionProvider.getConnection();
                PreparedStatement statement = connection.prepareStatement(
                        "SELECT m.id AS makeup_id, s.name AS student_name, s.school_name, "
                                + "oc.name AS original_class_name, os.lesson_date AS original_date, "
                                + "tc.name AS target_class_name, ts.lesson_date AS target_date, m.status "
                                + "FROM makeup_request m "
                                + "JOIN lesson_result lr ON m.lesson_result_id = lr.id "
                                + "JOIN enrollment ce ON lr.enrollment_id = ce.id "
                                + "JOIN student s ON ce.student_id = s.id "
                                + "JOIN lesson os ON lr.lesson_id = os.id "
                                + "JOIN classroom oc ON os.classroom_id = oc.id "
                                + "LEFT JOIN lesson ts ON m.target_lesson_id = ts.id "
                                + "LEFT JOIN classroom tc ON ts.classroom_id = tc.id "
                                + "WHERE ce.status NOT IN (" + excludedMakeupStatusesSql() + ") "
                                + "ORDER BY m.id DESC")) {
            try (ResultSet resultSet = statement.executeQuery()) {
                while (resultSet.next()) {
                    Date targetDate = resultSet.getDate("target_date");
                    rows.add(new MakeupRequestRow(
                            resultSet.getInt("makeup_id"),
                            resultSet.getString("student_name"),
                            resultSet.getString("school_name"),
                            resultSet.getString("original_class_name"),
                            resultSet.getDate("original_date").toLocalDate(),
                            resultSet.getString("target_class_name"),
                            targetDate == null ? null : targetDate.toLocalDate(),
                            resultSet.getString("status")));
                }
            }
        }
        return rows;
    }

    public String findLatestStatus(String studentName, String schoolName, String className,
            java.time.LocalDate sessionDate, String testRound) throws SQLException {
        try (Connection connection = connectionProvider.getConnection();
                PreparedStatement statement = connection.prepareStatement(
                        "SELECT m.status "
                                + "FROM makeup_request m "
                                + "JOIN lesson_result lr ON m.lesson_result_id = lr.id "
                                + "JOIN enrollment e ON lr.enrollment_id = e.id "
                                + "JOIN student s ON e.student_id = s.id "
                                + "JOIN lesson cs ON lr.lesson_id = cs.id "
                                + "JOIN classroom ac ON cs.classroom_id = ac.id "
                                + "WHERE s.name = ? AND s.school_name = ? "
                                + "AND ac.name = ? AND cs.lesson_date = ? AND cs.exam_round IS NOT DISTINCT FROM ? "
                                + "ORDER BY m.id DESC LIMIT 1")) {
            statement.setString(1, studentName);
            statement.setString(2, schoolName);
            statement.setString(3, className);
            statement.setDate(4, Date.valueOf(sessionDate));
            statement.setString(5, testRound);
            try (ResultSet resultSet = statement.executeQuery()) {
                return resultSet.next() ? resultSet.getString(1) : null;
            }
        }
    }

    private boolean isEligibleForMakeup(Connection connection, int studentId, int originalSessionId) throws SQLException {
        try (PreparedStatement statement = connection.prepareStatement(
                "SELECT ce.status FROM enrollment ce "
                        + "JOIN lesson_result lr ON lr.enrollment_id = ce.id "
                        + "WHERE ce.student_id = ? AND lr.lesson_id = ?")) {
            statement.setInt(1, studentId);
            statement.setInt(2, originalSessionId);
            try (ResultSet resultSet = statement.executeQuery()) {
                if (!resultSet.next()) {
                    return false;
                }
                String status = normalize(resultSet.getString(1));
                if ("WITHDRAWN".equals(status)) {
                    return false;
                }
                return !(EXCLUDE_PAUSED_STUDENTS_FROM_MAKEUP && "PAUSED".equals(status));
            }
        }
    }

    private String excludedMakeupStatusesSql() {
        return EXCLUDE_PAUSED_STUDENTS_FROM_MAKEUP ? "'WITHDRAWN', 'PAUSED'" : "'WITHDRAWN'";
    }

    private String normalize(String value) {
        return value == null ? "" : value.trim().toUpperCase();
    }

    private MakeupStatus findStatus(Connection connection, int makeupId) throws SQLException {
        try (PreparedStatement statement = connection.prepareStatement(
                "SELECT status FROM makeup_request WHERE id = ?")) {
            statement.setInt(1, makeupId);
            try (ResultSet resultSet = statement.executeQuery()) {
                if (!resultSet.next()) throw new SQLException("보강 신청을 찾을 수 없습니다: " + makeupId);
                return requireMakeupStatus(resultSet.getString(1));
            }
        }
    }

    private MakeupStatus requireMakeupStatus(String value) throws SQLException {
        MakeupStatus status = MakeupStatus.fromNullable(value);
        if (status == null) throw new SQLException("지원하지 않는 보강 상태입니다: " + value);
        return status;
    }
}
