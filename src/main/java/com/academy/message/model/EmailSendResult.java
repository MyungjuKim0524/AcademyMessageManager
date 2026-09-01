package com.academy.message.model;

public class EmailSendResult {
    private final boolean success;
    private final String errorMessage;

    private EmailSendResult(boolean success, String errorMessage) {
        this.success = success;
        this.errorMessage = errorMessage;
    }

    public static EmailSendResult success() {
        return new EmailSendResult(true, "");
    }

    public static EmailSendResult failure(String errorMessage) {
        return new EmailSendResult(false, errorMessage);
    }

    public boolean isSuccess() {
        return success;
    }

    public String getErrorMessage() {
        return errorMessage;
    }
}
