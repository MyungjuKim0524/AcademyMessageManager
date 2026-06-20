package com.academy.message.dao;

import com.academy.message.model.ImportRow;
import com.academy.message.model.MessagePreview;
import com.academy.message.model.SendLogRow;

import java.sql.Connection;
import java.sql.Date;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.LocalDateTime;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;

public class SendLogDAO {
    private final DBConnection dbConnection = new DBConnection();

    public void insertSendLog(MessagePreview preview, String status, String errorMessage) throws SQLException {
        insertSendLog(preview, preview.getRow().getParentEmail(), status, errorMessage);
    }

    public void insertSendLog(MessagePreview preview, String parentEmail, String status, String errorMessage) throws SQLException {
        ImportRow row = preview.getRow();
        try (Connection connection = dbConnection.getConnection()) {
            Integer studentId = findStudentId(connection, row);
            Integer sessionId = findSessionId(connection, row);
            try (PreparedStatement statement = connection.prepareStatement(
                    "INSERT INTO send_log "
                            + "(student_id, session_id, parent_email, message_content, status, sent_at, error_message) "
                            + "VALUES (?, ?, ?, ?, ?, ?, ?)")) {
                setNullableInt(statement, 1, studentId);
                setNullableInt(statement, 2, sessionId);
                statement.setString(3, parentEmail);
                statement.setString(4, preview.getContent());
                statement.setString(5, status);
                statement.setTimestamp(6, Timestamp.valueOf(LocalDateTime.now()));
                statement.setString(7, errorMessage == null || errorMessage.isBlank() ? null : errorMessage);
                statement.executeUpdate();
            }
        }
    }

    public List<SendLogRow> findAll() throws SQLException {
        return findByStatus(null);
    }

    public List<SendLogRow> findFailedLogs() throws SQLException {
        return findByStatus("FAILED");
    }

    public List<SendLogRow> searchLogs(String status, String className, LocalDate sentDate) throws SQLException {
        List<SendLogRow> logs = new ArrayList<>();
        String sql = "SELECT l.log_id, s.student_name, s.school_name, l.parent_email, l.message_content, l.status, l.sent_at, l.error_message "
                + "FROM send_log l "
                + "LEFT JOIN student s ON l.student_id = s.student_id "
                + "LEFT JOIN class_session cs ON l.session_id = cs.session_id "
                + "LEFT JOIN academy_class ac ON cs.class_id = ac.class_id "
                + "WHERE 1 = 1 ";
        if (status != null && !status.isBlank() && !"ALL".equals(status)) {
            sql += "AND l.status = ? ";
        }
        if (className != null && !className.isBlank()) {
            sql += "AND ac.class_name LIKE ? ";
        }
        if (sentDate != null) {
            sql += "AND TRUNC(l.sent_at) = ? ";
        }
        sql += "ORDER BY l.log_id DESC";

        try (Connection connection = dbConnection.getConnection();
                PreparedStatement statement = connection.prepareStatement(sql)) {
            int index = 1;
            if (status != null && !status.isBlank() && !"ALL".equals(status)) {
                statement.setString(index++, status);
            }
            if (className != null && !className.isBlank()) {
                statement.setString(index++, "%" + className.trim() + "%");
            }
            if (sentDate != null) {
                statement.setDate(index, Date.valueOf(sentDate));
            }
            try (ResultSet resultSet = statement.executeQuery()) {
                while (resultSet.next()) {
                    Timestamp sentAt = resultSet.getTimestamp("sent_at");
                    logs.add(new SendLogRow(
                            resultSet.getInt("log_id"),
                            resultSet.getString("student_name"),
                            resultSet.getString("school_name"),
                            resultSet.getString("parent_email"),
                            resultSet.getString("message_content"),
                            resultSet.getString("status"),
                            sentAt == null ? null : sentAt.toLocalDateTime(),
                            resultSet.getString("error_message")));
                }
            }
        }
        return logs;
    }

    public void markRetriedAsSent(int logId) throws SQLException {
        try (Connection connection = dbConnection.getConnection();
                PreparedStatement statement = connection.prepareStatement(
                        "UPDATE send_log SET status = 'SENT', sent_at = ?, error_message = NULL WHERE log_id = ?")) {
            statement.setTimestamp(1, Timestamp.valueOf(LocalDateTime.now()));
            statement.setInt(2, logId);
            statement.executeUpdate();
        }
    }

    public void markFailed(int logId, String errorMessage) throws SQLException {
        try (Connection connection = dbConnection.getConnection();
                PreparedStatement statement = connection.prepareStatement(
                        "UPDATE send_log SET status = 'FAILED', sent_at = ?, error_message = ? WHERE log_id = ?")) {
            statement.setTimestamp(1, Timestamp.valueOf(LocalDateTime.now()));
            statement.setString(2, errorMessage);
            statement.setInt(3, logId);
            statement.executeUpdate();
        }
    }

    private List<SendLogRow> findByStatus(String status) throws SQLException {
        List<SendLogRow> logs = new ArrayList<>();
        String sql = "SELECT l.log_id, s.student_name, s.school_name, l.parent_email, l.message_content, l.status, l.sent_at, l.error_message "
                + "FROM send_log l "
                + "LEFT JOIN student s ON l.student_id = s.student_id ";
        if (status != null) {
            sql += "WHERE l.status = ? ";
        }
        sql += "ORDER BY l.log_id DESC";
        try (Connection connection = dbConnection.getConnection();
                PreparedStatement statement = connection.prepareStatement(sql)) {
            if (status != null) {
                statement.setString(1, status);
            }
            try (ResultSet resultSet = statement.executeQuery()) {
                while (resultSet.next()) {
                    Timestamp sentAt = resultSet.getTimestamp("sent_at");
                    logs.add(new SendLogRow(
                            resultSet.getInt("log_id"),
                            resultSet.getString("student_name"),
                            resultSet.getString("school_name"),
                            resultSet.getString("parent_email"),
                            resultSet.getString("message_content"),
                            resultSet.getString("status"),
                            sentAt == null ? null : sentAt.toLocalDateTime(),
                            resultSet.getString("error_message")));
                }
            }
        }
        return logs;
    }

    private Integer findStudentId(Connection connection, ImportRow row) throws SQLException {
        try (PreparedStatement statement = connection.prepareStatement(
                "SELECT student_id FROM student WHERE student_name = ? AND school_name = ?")) {
            statement.setString(1, row.getStudentName());
            statement.setString(2, row.getSchoolName());
            try (ResultSet resultSet = statement.executeQuery()) {
                return resultSet.next() ? resultSet.getInt(1) : null;
            }
        }
    }

    private Integer findSessionId(Connection connection, ImportRow row) throws SQLException {
        try (PreparedStatement statement = connection.prepareStatement(
                "SELECT cs.session_id "
                        + "FROM class_session cs "
                        + "JOIN academy_class ac ON cs.class_id = ac.class_id "
                        + "WHERE ac.class_name = ? AND cs.session_date = ? AND cs.test_round = ?")) {
            statement.setString(1, row.getClassName());
            statement.setDate(2, Date.valueOf(row.getSessionDate()));
            statement.setString(3, row.getTestRound());
            try (ResultSet resultSet = statement.executeQuery()) {
                return resultSet.next() ? resultSet.getInt(1) : null;
            }
        }
    }

    private void setNullableInt(PreparedStatement statement, int index, Integer value) throws SQLException {
        if (value == null) {
            statement.setNull(index, java.sql.Types.INTEGER);
        } else {
            statement.setInt(index, value);
        }
    }
}
