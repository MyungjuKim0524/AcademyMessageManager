package com.academy.message.dao;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

import com.academy.message.port.TemplateProvider;
import com.academy.message.port.ConnectionProvider;

public class TemplateDAO implements TemplateProvider {
    private static final String REGULAR_DEFAULT = "안녕하세요, JAVA 학원입니다.\n"
            + "{학생명} 학생의 이번 주 정규 수업 학습 현황 안내드립니다.\n\n"
            + "{예습메시지}\n"
            + "{주간메시지}\n"
            + "{테스트메시지}\n"
            + "{보강메시지}\n\n"
            + "오늘도 감사드립니다.";

    private static final String EXAM_PREP_DEFAULT = "안녕하세요, JAVA 학원입니다.\n"
            + "{학생명} 학생의 내신 대비 학습 현황 안내드립니다.\n\n"
            + "{예습메시지}\n"
            + "{주간메시지}\n"
            + "{테스트메시지}\n"
            + "{보강메시지}\n\n"
            + "시험 대비 기간 동안 꾸준히 학습할 수 있도록 지도하겠습니다.\n"
            + "감사합니다.";

    private final ConnectionProvider connectionProvider;
    public TemplateDAO() { this(new DBConnection()); }
    public TemplateDAO(ConnectionProvider connectionProvider) { this.connectionProvider = connectionProvider; }

    public String findOrCreateActiveTemplate(String classType) throws SQLException {
        try (Connection connection = connectionProvider.getConnection()) {
            String template = findActiveTemplate(connection, classType);
            if (template != null) {
                return template;
            }
            insertDefaultTemplate(connection, classType);
            return findActiveTemplate(connection, classType);
        }
    }

    public void saveTemplate(String classType, String content) throws SQLException {
        try (Connection connection = connectionProvider.getConnection()) {
            String existing = findActiveTemplate(connection, classType);
            if (existing == null) {
                try (PreparedStatement statement = connection.prepareStatement(
                        "INSERT INTO message_template (class_type, template_name, template_content, active_yn) "
                                + "VALUES (?, ?, ?, 'Y')")) {
                    statement.setString(1, classType);
                    statement.setString(2, defaultName(classType));
                    statement.setString(3, content);
                    statement.executeUpdate();
                }
                return;
            }

            try (PreparedStatement statement = connection.prepareStatement(
                    "UPDATE message_template SET template_content = ? WHERE class_type = ? AND active_yn = 'Y'")) {
                statement.setString(1, content);
                statement.setString(2, classType);
                statement.executeUpdate();
            }
        }
    }

    public String defaultTemplate(String classType) {
        return "EXAM_PREP".equals(classType) ? EXAM_PREP_DEFAULT : REGULAR_DEFAULT;
    }

    private String findActiveTemplate(Connection connection, String classType) throws SQLException {
        try (PreparedStatement statement = connection.prepareStatement(
                "SELECT template_content FROM message_template WHERE class_type = ? AND active_yn = 'Y'")) {
            statement.setString(1, classType);
            try (ResultSet resultSet = statement.executeQuery()) {
                if (resultSet.next()) {
                    return resultSet.getString(1);
                }
                return null;
            }
        }
    }

    private void insertDefaultTemplate(Connection connection, String classType) throws SQLException {
        try (PreparedStatement statement = connection.prepareStatement(
                "INSERT INTO message_template (class_type, template_name, template_content, active_yn) "
                        + "VALUES (?, ?, ?, 'Y')")) {
            statement.setString(1, classType);
            statement.setString(2, defaultName(classType));
            statement.setString(3, defaultTemplate(classType));
            statement.executeUpdate();
        }
    }

    private String defaultName(String classType) {
        return "EXAM_PREP".equals(classType) ? "내신 대비 기본 템플릿" : "정규 수업 기본 템플릿";
    }
}
