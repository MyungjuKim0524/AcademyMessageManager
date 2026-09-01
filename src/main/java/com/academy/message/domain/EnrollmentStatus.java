package com.academy.message.domain;

import java.util.Locale;

public enum EnrollmentStatus {
    ACTIVE("재원"), PAUSED("휴원"), WITHDRAWN("퇴원");

    private final String displayName;

    EnrollmentStatus(String displayName) { this.displayName = displayName; }
    public String displayName() { return displayName; }

    public boolean canRequestMakeup() { return this == ACTIVE; }

    public static EnrollmentStatus from(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("수강상태는 필수입니다.");
        }
        String normalized = value.trim().toUpperCase(Locale.ROOT);
        for (EnrollmentStatus status : values()) {
            if (status.name().equals(normalized) || status.displayName.equals(value.trim())) return status;
        }
        throw new IllegalArgumentException("지원하지 않는 수강상태입니다: " + value);
    }
}
