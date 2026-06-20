package com.academy.message.model;

public class MailCredentials {
    private final String username;
    private final String password;

    public MailCredentials(String username, String password) {
        this.username = username;
        this.password = password;
    }

    public String getUsername() {
        return username;
    }

    public String getPassword() {
        return password;
    }

}
