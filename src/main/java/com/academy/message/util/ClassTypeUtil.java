package com.academy.message.util;

import com.academy.message.domain.ClassType;

public final class ClassTypeUtil {
    private ClassTypeUtil() {
    }

    public static String toDisplayName(String classType) {
        if (classType == null || classType.isBlank()) return "";
        try { return ClassType.from(classType).displayName(); }
        catch (IllegalArgumentException ex) { return classType; }
    }

    public static String toCode(String displayName) {
        if (displayName == null || displayName.isBlank()) return "";
        try { return ClassType.from(displayName).name(); }
        catch (IllegalArgumentException ex) { return displayName.trim(); }
    }
}
