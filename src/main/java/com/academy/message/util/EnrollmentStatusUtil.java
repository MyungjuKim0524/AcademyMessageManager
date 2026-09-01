package com.academy.message.util;

import com.academy.message.domain.EnrollmentStatus;

public final class EnrollmentStatusUtil {
    private EnrollmentStatusUtil() {
    }

    public static String toDisplayName(String status) {
        if (status == null || status.isBlank()) return "";
        try { return EnrollmentStatus.from(status).displayName(); }
        catch (IllegalArgumentException ex) { return status; }
    }

    public static String toCode(String displayName) {
        if (displayName == null || displayName.isBlank()) return "";
        return EnrollmentStatus.from(displayName).name();
    }
}
