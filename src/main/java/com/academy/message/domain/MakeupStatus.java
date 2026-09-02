package com.academy.message.domain;

public enum MakeupStatus {
    REQUESTED, APPROVED, COMPLETED, CANCELLED;

    public static MakeupStatus fromNullable(String value) {
        if (value == null || value.isBlank()) return null;
        try { return valueOf(value.trim().toUpperCase()); }
        catch (IllegalArgumentException ex) { return null; }
    }

    public boolean canTransitionTo(MakeupStatus target) {
        if (target == null || this == target) return false;
        return switch (this) {
            case REQUESTED -> target == APPROVED || target == COMPLETED || target == CANCELLED;
            case APPROVED -> target == COMPLETED || target == CANCELLED;
            case COMPLETED, CANCELLED -> false;
        };
    }
}
