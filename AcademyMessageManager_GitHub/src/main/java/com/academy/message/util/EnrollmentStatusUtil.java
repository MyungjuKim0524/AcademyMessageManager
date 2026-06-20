package com.academy.message.util;

public final class EnrollmentStatusUtil {
    private EnrollmentStatusUtil() {
    }

    public static String toDisplayName(String status) {
        if ("ACTIVE".equalsIgnoreCase(status)) {
            return "재원";
        }
        if ("PAUSED".equalsIgnoreCase(status)) {
            return "휴원";
        }
        if ("WITHDRAWN".equalsIgnoreCase(status)) {
            return "퇴원";
        }
        return status == null ? "" : status;
    }

    public static String toCode(String displayName) {
        if ("재원".equals(displayName)) {
            return "ACTIVE";
        }
        if ("휴원".equals(displayName)) {
            return "PAUSED";
        }
        if ("퇴원".equals(displayName)) {
            return "WITHDRAWN";
        }
        return displayName == null ? "" : displayName.trim().toUpperCase();
    }
}
