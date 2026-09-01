package com.academy.message.util;

import com.academy.message.domain.SendStatus;

public final class SendStatusUtil {
    private SendStatusUtil() {
    }

    public static String toDisplayName(String status) {
        if (status == null || status.isBlank()) return "";
        try { return SendStatus.from(status).displayName(); }
        catch (IllegalArgumentException ex) { return status; }
    }

    public static String toCode(String displayName) {
        if ("전체".equals(displayName)) {
            return "ALL";
        }
        return SendStatus.from(displayName).name();
    }
}
