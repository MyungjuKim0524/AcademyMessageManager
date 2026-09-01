package com.academy.message.domain;

public enum AchievementGrade {
    A, B, C;

    public static AchievementGrade from(String value) {
        if (value == null || value.isBlank()) return null;
        try {
            return valueOf(value.trim().toUpperCase());
        } catch (IllegalArgumentException ex) {
            throw new IllegalArgumentException("성취도는 A, B, C 또는 공백이어야 합니다.");
        }
    }
}
