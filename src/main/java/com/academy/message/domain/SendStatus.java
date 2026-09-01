package com.academy.message.domain;

public enum SendStatus {
    READY("발송 대기"), SENT("발송 성공"), FAILED("발송 실패"), SKIPPED("발송 제외");

    private final String displayName;
    SendStatus(String displayName) { this.displayName = displayName; }
    public String displayName() { return displayName; }

    public static SendStatus from(String value) {
        if (value != null) {
            for (SendStatus status : values()) {
                if (status.name().equalsIgnoreCase(value.trim()) || status.displayName.equals(value.trim())) return status;
            }
        }
        throw new IllegalArgumentException("지원하지 않는 발송 상태입니다: " + value);
    }
}
