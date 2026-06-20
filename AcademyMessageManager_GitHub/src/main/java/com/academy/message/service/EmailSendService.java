package com.academy.message.service;

import com.academy.message.model.EmailSendResult;
import com.academy.message.model.MailCredentials;

import jakarta.mail.Authenticator;
import jakarta.mail.Message;
import jakarta.mail.MessagingException;
import jakarta.mail.PasswordAuthentication;
import jakarta.mail.Session;
import jakarta.mail.Transport;
import jakarta.mail.internet.InternetAddress;
import jakarta.mail.internet.MimeMessage;

import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

public class EmailSendService {
    private static final String CONFIG_FILE = "config.properties";
    private final MailCredentialStore credentialStore = new MailCredentialStore();

    public EmailSendResult sendEmail(String to, String subject, String content, char[] masterPassword) {
        try {
            Properties appProperties = loadProperties();
            MailCredentials credentials = credentialStore.load(masterPassword);
            String username = credentials.getUsername();
            String password = credentials.getPassword();
            String from = credentials.getUsername();

            Properties mailProperties = new Properties();
            mailProperties.put("mail.smtp.auth", "true");
            mailProperties.put("mail.smtp.starttls.enable", "true");
            mailProperties.put("mail.smtp.host", required(appProperties, "mail.smtp.host"));
            mailProperties.put("mail.smtp.port", required(appProperties, "mail.smtp.port"));

            Session session = Session.getInstance(mailProperties, new Authenticator() {
                @Override
                protected PasswordAuthentication getPasswordAuthentication() {
                    return new PasswordAuthentication(username, password);
                }
            });

            Message message = new MimeMessage(session);
            message.setFrom(new InternetAddress(from));
            message.setRecipients(Message.RecipientType.TO, InternetAddress.parse(to));
            message.setSubject(subject);
            message.setText(content);
            Transport.send(message);
            return EmailSendResult.success();
        } catch (Exception ex) {
            return EmailSendResult.failure(ex.getMessage());
        }
    }

    private Properties loadProperties() throws IOException {
        Properties properties = new Properties();
        try (InputStream input = Thread.currentThread().getContextClassLoader().getResourceAsStream(CONFIG_FILE)) {
            if (input == null) {
                throw new IOException("config.properties 파일이 필요합니다.");
            }
            properties.load(input);
            return properties;
        }
    }

    private String required(Properties properties, String key) throws MessagingException {
        String value = properties.getProperty(key);
        if (value == null || value.isBlank()) {
            throw new MessagingException("메일 설정이 필요합니다: " + key);
        }
        return value.trim();
    }
}
