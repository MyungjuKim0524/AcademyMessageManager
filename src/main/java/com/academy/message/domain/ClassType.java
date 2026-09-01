package com.academy.message.domain;

import java.util.Locale;

public enum ClassType {
    REGULAR("정규"),
    EXAM_PREP("내신 대비");

    private final String displayName;

    ClassType(String displayName) {
        this.displayName = displayName;
    }

    public String displayName() {
        return displayName;
    }

    public static ClassType from(String value) {
        String normalized = requireValue(value).toUpperCase(Locale.ROOT);
        for (ClassType type : values()) {
            if (type.name().equals(normalized) || type.displayName.equals(value.trim())) {
                return type;
            }
        }
        throw new IllegalArgumentException("지원하지 않는 수업유형입니다: " + value);
    }

    private static String requireValue(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("수업유형은 필수입니다.");
        }
        return value.trim();
    }
}
