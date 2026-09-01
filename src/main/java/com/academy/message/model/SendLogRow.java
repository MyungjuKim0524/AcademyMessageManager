package com.academy.message.model;

import java.time.LocalDateTime;

public class SendLogRow {
    private final int logId;
    private final String studentName;
    private final String schoolName;
    private final String parentEmail;
    private final String messageContent;
    private final String status;
    private final LocalDateTime sentAt;
    private final String errorMessage;

    public SendLogRow(int logId, String studentName, String schoolName, String parentEmail, String messageContent, String status,
            LocalDateTime sentAt, String errorMessage) {
        this.logId = logId;
        this.studentName = studentName;
        this.schoolName = schoolName;
        this.parentEmail = parentEmail;
        this.messageContent = messageContent;
        this.status = status;
        this.sentAt = sentAt;
        this.errorMessage = errorMessage;
    }

    public int getLogId() {
        return logId;
    }

    public String getStudentName() {
        return studentName;
    }

    public String getSchoolName() {
        return schoolName;
    }

    public String getParentEmail() {
        return parentEmail;
    }

    public String getMessageContent() {
        return messageContent;
    }

    public String getStatus() {
        return status;
    }

    public LocalDateTime getSentAt() {
        return sentAt;
    }

    public String getErrorMessage() {
        return errorMessage;
    }
}
