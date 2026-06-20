package com.academy.message.dao;

import java.io.IOException;
import java.io.InputStream;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.util.Properties;

public class DBConnection {
    private static final String CONFIG_FILE = "config.properties";

    public Connection getConnection() throws SQLException {
        Properties properties = loadProperties();
        return DriverManager.getConnection(
                properties.getProperty("db.url"),
                properties.getProperty("db.username"),
                properties.getProperty("db.password"));
    }

    private Properties loadProperties() {
        Properties properties = new Properties();
        try (InputStream input = Thread.currentThread().getContextClassLoader().getResourceAsStream(CONFIG_FILE)) {
            if (input == null) {
                throw new IllegalStateException("src/main/resources/config.properties 파일이 필요합니다.");
            }
            properties.load(input);
            return properties;
        } catch (IOException ex) {
            throw new IllegalStateException("DB 설정 파일을 읽지 못했습니다.", ex);
        }
    }
}
