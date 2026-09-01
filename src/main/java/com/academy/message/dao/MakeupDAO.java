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
                        "SELECT s.student_id, cs.session_id, s.student_name, s.school_name, ac.class_name, "
                                + "cs.session_date, cs.test_round, "
                                + "(SELECT MAX(m.status) FROM makeup_request m "
                                + " WHERE m.student_id = s.student_id AND m.original_session_id = cs.session_id) AS makeup_status "
                                + "FROM grade_record gr "
                                + "JOIN student s ON gr.student_id = s.student_id "
                                + "JOIN class_session cs ON gr.session_id = cs.session_id "
                                + "JOIN academy_class ac ON cs.class_id = ac.class_id "
                                + "JOIN class_enrollment ce ON ce.student_id = s.student_id AND ce.class_id = ac.class_id "
                                + "WHERE TRIM(gr.attendance) = '결석' "
                                + "AND ce.status NOT IN (" + excludedMakeupStatusesSql() + ") "
                                + "ORDER BY cs.session_date DESC, s.student_name")) {
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
        String sql = "SELECT cs.session_id, ac.class_name, ac.class_type, cs.session_date, cs.test_round "
                + "FROM class_session cs "
                + "JOIN academy_class ac ON cs.class_id = ac.class_id "
                + "WHERE cs.session_id <> ? ";
        if (from != null) {
            sql += "AND cs.session_date >= ? ";
        }
        if (to != null) {
            sql += "AND cs.session_date <= ? ";
        }
        sql += "ORDER BY cs.session_date DESC, ac.class_name";
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
                        "INSERT INTO makeup_request (student_id, original_session_id, target_session_id, status) "
                                + "VALUES (?, ?, ?, 'REQUESTED')")) {
                statement.setInt(1, studentId);
                statement.setInt(2, originalSessionId);
                statement.setInt(3, targetSessionId);
                statement.executeUpdate();
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
                    "UPDATE makeup_request SET status = ? WHERE makeup_id = ? AND status = ?")) {
                statement.setString(1, target.name());
                statement.setInt(2, makeupId);
                statement.setString(3, current.name());
                if (statement.executeUpdate() != 1) throw new SQLException("보강 신청 상태가 다른 사용자에 의해 변경되었습니다.");
            }
        }
    }

    public List<MakeupRequestRow> findRequests() throws SQLException {
        List<MakeupRequestRow> rows = new ArrayList<>();
        try (Connection connection = connectionProvider.getConnection();
                PreparedStatement statement = connection.prepareStatement(
                        "SELECT m.makeup_id, s.student_name, s.school_name, "
                                + "oc.class_name AS original_class_name, os.session_date AS original_date, "
                                + "tc.class_name AS target_class_name, ts.session_date AS target_date, m.status "
                                + "FROM makeup_request m "
                                + "JOIN student s ON m.student_id = s.student_id "
                                + "JOIN class_session os ON m.original_session_id = os.session_id "
                                + "JOIN academy_class oc ON os.class_id = oc.class_id "
                                + "JOIN class_enrollment ce ON ce.student_id = s.student_id AND ce.class_id = oc.class_id "
                                + "LEFT JOIN class_session ts ON m.target_session_id = ts.session_id "
                                + "LEFT JOIN academy_class tc ON ts.class_id = tc.class_id "
                                + "WHERE ce.status NOT IN (" + excludedMakeupStatusesSql() + ") "
                                + "ORDER BY m.makeup_id DESC")) {
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
                                + "JOIN student s ON m.student_id = s.student_id "
                                + "JOIN class_session cs ON m.original_session_id = cs.session_id "
                                + "JOIN academy_class ac ON cs.class_id = ac.class_id "
                                + "WHERE s.student_name = ? AND s.school_name = ? "
                                + "AND ac.class_name = ? AND cs.session_date = ? AND cs.test_round = ? "
                                + "ORDER BY m.makeup_id DESC")) {
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
                "SELECT ce.status "
                        + "FROM class_enrollment ce "
                        + "JOIN class_session cs ON ce.class_id = cs.class_id "
                        + "WHERE ce.student_id = ? AND cs.session_id = ?")) {
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
                "SELECT status FROM makeup_request WHERE makeup_id = ?")) {
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
