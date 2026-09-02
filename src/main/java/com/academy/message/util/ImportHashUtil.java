package com.academy.message.util;

import com.academy.message.model.ImportRow;
import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

public final class ImportHashUtil {
    private ImportHashUtil() {}

    public static String fileHash(File file) throws IOException { return sha256(Files.readAllBytes(file.toPath())); }

    public static String rowHash(ImportRow row) {
        String canonical = String.join("\u001f", safe(row.getClassName()), safe(row.getClassType()),
                String.valueOf(row.getSessionDate()), safe(row.getTestRound()), safe(row.getStudentName()),
                safe(row.getSchoolName()), safe(row.getEnrollmentStatus()), safe(row.getAttendance()),
                safe(row.getParentName()), safe(row.getParentEmail()), safe(row.getPreGrade()),
                safe(row.getWeeklyGrade()), safe(row.getTestResult()));
        return sha256(canonical.getBytes(StandardCharsets.UTF_8));
    }

    private static String sha256(byte[] bytes) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(bytes);
            StringBuilder result = new StringBuilder(64);
            for (byte value : digest) result.append(String.format("%02x", value));
            return result.toString();
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256을 사용할 수 없습니다.", ex);
        }
    }

    private static String safe(String value) { return value == null ? "" : value; }
}
