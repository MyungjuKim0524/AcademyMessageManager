package com.academy.message.dao;

import com.academy.message.model.EnrollmentStatusRow;

import java.sql.Connection;
import java.sql.Date;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;

public class EnrollmentDAO {
    private final DBConnection dbConnection = new DBConnection();

    public List<EnrollmentStatusRow> search(String status, String className) throws SQLException {
        List<EnrollmentStatusRow> rows = new ArrayList<>();
        String sql = "SELECT ce.enrollment_id, s.student_id, ac.class_name, ac.class_type, s.student_name, s.school_name, s.parent_email, "
                + "ce.status, ce.start_date, ce.end_date "
                + "FROM class_enrollment ce "
                + "JOIN academy_class ac ON ce.class_id = ac.class_id "
                + "JOIN student s ON ce.student_id = s.student_id "
                + "WHERE 1 = 1 ";
        if (status != null && !status.isBlank() && !"ALL".equals(status)) {
            sql += "AND ce.status = ? ";
        }
        if (className != null && !className.isBlank()) {
            sql += "AND ac.class_name LIKE ? ";
        }
        sql += "ORDER BY ac.class_name, s.student_name";

        try (Connection connection = dbConnection.getConnection();
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
        try (Connection connection = dbConnection.getConnection();
                PreparedStatement statement = connection.prepareStatement(
                        "SELECT class_name FROM academy_class WHERE active_yn = 'Y' ORDER BY class_name");
                ResultSet resultSet = statement.executeQuery()) {
            while (resultSet.next()) {
                classNames.add(resultSet.getString("class_name"));
            }
        }
        return classNames;
    }

    public String findEnrollmentStatus(String studentName, String schoolName, String className) throws SQLException {
        try (Connection connection = dbConnection.getConnection();
                PreparedStatement statement = connection.prepareStatement(
                        "SELECT ce.status "
                                + "FROM class_enrollment ce "
                                + "JOIN academy_class ac ON ce.class_id = ac.class_id "
                                + "JOIN student s ON ce.student_id = s.student_id "
                                + "WHERE s.student_name = ? AND s.school_name = ? AND ac.class_name = ?")) {
            statement.setString(1, studentName);
            statement.setString(2, schoolName);
            statement.setString(3, className);
            try (ResultSet resultSet = statement.executeQuery()) {
                return resultSet.next() ? resultSet.getString(1) : null;
            }
        }
    }

    public String findParentEmail(String studentName, String schoolName) throws SQLException {
        try (Connection connection = dbConnection.getConnection();
                PreparedStatement statement = connection.prepareStatement(
                        "SELECT parent_email FROM student WHERE student_name = ? AND school_name = ?")) {
            statement.setString(1, studentName);
            statement.setString(2, schoolName);
            try (ResultSet resultSet = statement.executeQuery()) {
                return resultSet.next() ? resultSet.getString(1) : null;
            }
        }
    }

    public void updateStudentManagement(int enrollmentId, int studentId, String email, String status) throws SQLException {
        try (Connection connection = dbConnection.getConnection()) {
            connection.setAutoCommit(false);
            try {
                try (PreparedStatement statement = connection.prepareStatement(
                        "UPDATE student SET parent_email = ? WHERE student_id = ?")) {
                    statement.setString(1, normalizeBlank(email));
                    statement.setInt(2, studentId);
                    statement.executeUpdate();
                }
                try (PreparedStatement statement = connection.prepareStatement(
                        "UPDATE class_enrollment "
                                + "SET status = ?, end_date = CASE WHEN ? = 'ACTIVE' THEN NULL ELSE SYSDATE END "
                                + "WHERE enrollment_id = ?")) {
                    statement.setString(1, status);
                    statement.setString(2, status);
                    statement.setInt(3, enrollmentId);
                    statement.executeUpdate();
                }
                if ("WITHDRAWN".equals(status)) {
                    try (PreparedStatement statement = connection.prepareStatement(
                            "UPDATE makeup_request SET status = 'CANCELED' "
                                    + "WHERE student_id = ? AND status IN ('REQUESTED', 'APPROVED')")) {
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
