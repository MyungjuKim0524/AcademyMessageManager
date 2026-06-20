package com.academy.message.util;

public final class ClassTypeUtil {
    private ClassTypeUtil() {
    }

    public static String toDisplayName(String classType) {
        if ("REGULAR".equalsIgnoreCase(classType)) {
            return "정규";
        }
        if ("EXAM_PREP".equalsIgnoreCase(classType)) {
            return "내신 대비";
        }
        return classType == null ? "" : classType;
    }

    public static String toCode(String displayName) {
        if ("정규".equals(displayName)) {
            return "REGULAR";
        }
        if ("내신 대비".equals(displayName)) {
            return "EXAM_PREP";
        }
        return displayName;
    }
}
