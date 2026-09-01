package com.academy.message.util;

import com.academy.message.model.SendLogRow;

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.time.format.DateTimeFormatter;
import java.util.List;

public final class CsvExportUtil {
    private static final DateTimeFormatter DATE_TIME_FORMATTER = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");

    private CsvExportUtil() {
    }

    public static void exportSendLogs(File file, List<SendLogRow> logs) throws IOException {
        try (BufferedWriter writer = new BufferedWriter(
                new OutputStreamWriter(new FileOutputStream(file), StandardCharsets.UTF_8))) {
            writer.write('\ufeff');
            writer.write("학생명,학교,이메일,상태,발송 시간,실패 사유");
            writer.newLine();
            for (SendLogRow log : logs) {
                writer.write(csv(log.getStudentName()));
                writer.write(',');
                writer.write(csv(log.getSchoolName()));
                writer.write(',');
                writer.write(csv(log.getParentEmail()));
                writer.write(',');
                writer.write(csv(log.getStatus()));
                writer.write(',');
                writer.write(csv(log.getSentAt() == null ? "" : DATE_TIME_FORMATTER.format(log.getSentAt())));
                writer.write(',');
                writer.write(csv(log.getErrorMessage()));
                writer.newLine();
            }
        }
    }

    static String csv(String value) {
        String safe = value == null ? "" : value;
        if (startsWithFormulaCharacter(safe)) {
            safe = "'" + safe;
        }
        if (safe.contains(",") || safe.contains("\"") || safe.contains("\n") || safe.contains("\r")) {
            return "\"" + safe.replace("\"", "\"\"") + "\"";
        }
        return safe;
    }

    private static boolean startsWithFormulaCharacter(String value) {
        if (value.isEmpty()) {
            return false;
        }
        char first = value.charAt(0);
        return first == '=' || first == '+' || first == '-' || first == '@';
    }
}
