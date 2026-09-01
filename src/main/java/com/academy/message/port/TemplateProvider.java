package com.academy.message.port;

import java.sql.SQLException;

public interface TemplateProvider {
    String findOrCreateActiveTemplate(String classType) throws SQLException;
    String defaultTemplate(String classType);
}
