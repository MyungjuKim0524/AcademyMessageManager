package com.academy.message.dao;

import com.academy.message.model.EnrollmentStatusRow;

import java.sql.Connection;
import java.sql.Date;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import com.academy.message.port.ConnectionProvider;

public class EnrollmentDAO {
    private final ConnectionProvider connectionProvider;
    public EnrollmentDAO() { this(new DBConnection()); }
    public EnrollmentDAO(ConnectionProvider connectionProvider) { this.connectionProvider = connectionProvider; }

    public List<EnrollmentStatusRow> search(String status, String className) throws SQLException {
        List<EnrollmentStatusRow> rows = new ArrayList<>();
        String sql = "SELECT ce.id AS enrollment_id, s.id AS student_id, ac.name AS class_name, ac.class_type, s.name AS student_name, s.school_name, s.parent_email, "
                + "ce.status, ce.enrolled_at AS start_date, ce.ended_at AS end_date "
                + "FROM enrollment ce "
                + "JOIN classroom ac ON ce.classroom_id = ac.id "
                + "JOIN student s ON ce.student_id = s.id "
                + "WHERE 1 = 1 ";
        if (status != null && !status.isBlank() && !"ALL".equals(status)) {
            sql += "AND ce.status = ? ";
        }
        if (className != null && !className.isBlank()) {
            sql += "AND ac.name LIKE ? ";
        }
        sql += "ORDER BY ac.name, s.name";

        try (Connection connection = connectionProvider.getConnection();
                PreparedStatement statement = connection.prepareStatement(sql)) {
            int index = 1;
            if (status != null && !status.isBlank() && !"ALL".equals(status)) {
                statement.setString(index++, status);
            }
            if (className != null && !className.isBlank()) {
                statement.setString(index, "%" + className.trim() + "%");
            }
            try (ResultSet resultSet = statement.executeQuery()) {
                while (resultSet.next()) {
                    Date startDate = resultSet.getDate("start_date");
                    Date endDate = resultSet.getDate("end_date");
                    rows.add(new EnrollmentStatusRow(
                            resultSet.getInt("enrollment_id"),
                            resultSet.getInt("student_id"),
                            resultSet.getString("class_name"),
                            resultSet.getString("class_type"),
                            resultSet.getString("student_name"),
                            resultSet.getString("school_name"),
                            resultSet.getString("parent_email"),
                            resultSet.getString("status"),
                            startDate == null ? null : startDate.toLocalDate(),
                            endDate == null ? null : endDate.toLocalDate()));
                }
            }
        }
        return rows;
    }

    public List<String> findClassNames() throws SQLException {
        List<String> classNames = new ArrayList<>();
        try (Connection connection = connectionProvider.getConnection();
                PreparedStatement statement = connection.prepareStatement(
                        "SELECT name AS class_name FROM classroom WHERE is_active = TRUE ORDER BY name");
                ResultSet resultSet = statement.executeQuery()) {
            while (resultSet.next()) {
                classNames.add(resultSet.getString("class_name"));
            }
        }
        return classNames;
    }

    public String findEnrollmentStatus(String studentName, String schoolName, String className) throws SQLException {
        try (Connection connection = connectionProvider.getConnection();
                PreparedStatement statement = connection.prepareStatement(
                        "SELECT ce.status "
                                + "FROM enrollment ce "
                                + "JOIN classroom ac ON ce.classroom_id = ac.id "
                                + "JOIN student s ON ce.student_id = s.id "
                                + "WHERE s.name = ? AND s.school_name = ? AND ac.name = ?")) {
            statement.setString(1, studentName);
            statement.setString(2, schoolName);
            statement.setString(3, className);
            try (ResultSet resultSet = statement.executeQuery()) {
                return resultSet.next() ? resultSet.getString(1) : null;
            }
        }
    }

    public String findParentEmail(String studentName, String schoolName) throws SQLException {
        try (Connection connection = connectionProvider.getConnection();
                PreparedStatement statement = connection.prepareStatement(
                        "SELECT parent_email FROM student WHERE name = ? AND school_name = ?")) {
            statement.setString(1, studentName);
            statement.setString(2, schoolName);
            try (ResultSet resultSet = statement.executeQuery()) {
                return resultSet.next() ? resultSet.getString(1) : null;
            }
        }
    }

    public void updateStudentManagement(int enrollmentId, int studentId, String email, String status) throws SQLException {
        try (Connection connection = connectionProvider.getConnection()) {
            connection.setAutoCommit(false);
            try {
                try (PreparedStatement statement = connection.prepareStatement(
                        "UPDATE student SET parent_email = ? WHERE id = ?")) {
                    statement.setString(1, normalizeBlank(email));
                    statement.setInt(2, studentId);
                    statement.executeUpdate();
                }
                try (PreparedStatement statement = connection.prepareStatement(
                        "UPDATE enrollment "
                                + "SET status = ?, ended_at = CASE WHEN ? = 'ACTIVE' THEN NULL ELSE CURRENT_DATE END "
                                + "WHERE id = ?")) {
                    statement.setString(1, status);
                    statement.setString(2, status);
                    statement.setInt(3, enrollmentId);
                    statement.executeUpdate();
                }
                if ("WITHDRAWN".equals(status)) {
                    try (PreparedStatement statement = connection.prepareStatement(
                            "UPDATE makeup_request m SET status = 'CANCELLED', cancel_reason = '수강 종료' "
                                    + "FROM lesson_result lr JOIN enrollment e ON e.id = lr.enrollment_id "
                                    + "WHERE m.lesson_result_id = lr.id AND e.student_id = ? "
                                    + "AND m.status IN ('REQUESTED', 'APPROVED')")) {
                        statement.setInt(1, studentId);
                        statement.executeUpdate();
                    }
                }
                connection.commit();
            } catch (SQLException ex) {
                connection.rollback();
                throw ex;
            }
        }
    }

    private String normalizeBlank(String value) {
        return value == null || value.isBlank() ? null : value.trim();
    }
}
