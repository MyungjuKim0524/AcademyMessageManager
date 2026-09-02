package com.academy.message.dao;

import java.io.IOException;
import java.io.InputStream;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.util.Properties;
import com.academy.message.port.ConnectionProvider;

public class DBConnection implements ConnectionProvider {
    private static final String CONFIG_FILE = "config.properties";

    public Connection getConnection() throws SQLException {
        Properties properties = loadProperties();
        return DriverManager.getConnection(
                required(properties, "db.url", "DB_URL"),
                required(properties, "db.username", "DB_USER"),
                required(properties, "db.password", "DB_PASSWORD"));
    }

    private Properties loadProperties() {
        Properties properties = new Properties();
        try (InputStream input = Thread.currentThread().getContextClassLoader().getResourceAsStream(CONFIG_FILE)) {
            if (input != null) {
                properties.load(input);
            }
            return properties;
        } catch (IOException ex) {
            throw new IllegalStateException("DB 설정 파일을 읽지 못했습니다.", ex);
        }
    }

    private String required(Properties properties, String key, String environmentKey) {
        String environmentValue = System.getenv(environmentKey);
        String value = environmentValue == null || environmentValue.isBlank() ? properties.getProperty(key) : environmentValue;
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("필수 DB 설정이 없습니다: " + key + " 또는 " + environmentKey);
        }
        return value.trim();
    }
}
