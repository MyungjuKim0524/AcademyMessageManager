package com.academy.message.util;

public final class SendStatusUtil {
    private SendStatusUtil() {
    }

    public static String toDisplayName(String status) {
        if ("SENT".equalsIgnoreCase(status)) {
            return "발송 성공";
        }
        if ("FAILED".equalsIgnoreCase(status)) {
            return "발송 실패";
        }
        if ("SKIPPED".equalsIgnoreCase(status)) {
            return "발송 제외";
        }
        if ("READY".equalsIgnoreCase(status)) {
            return "발송 대기";
        }
        return status == null ? "" : status;
    }

    public static String toCode(String displayName) {
        if ("전체".equals(displayName)) {
            return "ALL";
        }
        if ("발송 성공".equals(displayName)) {
            return "SENT";
        }
        if ("발송 실패".equals(displayName)) {
            return "FAILED";
        }
        if ("발송 제외".equals(displayName)) {
            return "SKIPPED";
        }
        if ("발송 대기".equals(displayName)) {
            return "READY";
        }
        return displayName == null ? "" : displayName.trim().toUpperCase();
    }
}
