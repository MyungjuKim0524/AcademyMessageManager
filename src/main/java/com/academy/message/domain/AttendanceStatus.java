package com.academy.message.domain;

public enum AttendanceStatus {
    PRESENT("출석"), ABSENT("결석"), LATE("지각");

    private final String displayName;
    AttendanceStatus(String displayName) { this.displayName = displayName; }
    public String displayName() { return displayName; }
    public boolean requiresMakeupGuidance() { return this == ABSENT; }

    public static AttendanceStatus from(String value) {
        if (value != null) {
            for (AttendanceStatus status : values()) {
                if (status.displayName.equals(value.trim()) || status.name().equalsIgnoreCase(value.trim())) return status;
            }
        }
        throw new IllegalArgumentException("출석 여부는 출석, 결석 또는 지각이어야 합니다.");
    }
}
