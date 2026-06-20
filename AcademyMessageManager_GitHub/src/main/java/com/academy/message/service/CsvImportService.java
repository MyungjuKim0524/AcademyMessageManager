package com.academy.message.service;

import com.academy.message.model.ImportRow;
import com.academy.message.util.ClassTypeUtil;
import com.academy.message.util.EnrollmentStatusUtil;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.ByteBuffer;
import java.nio.charset.Charset;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class CsvImportService {
    private static final String[] REQUIRED_HEADERS = {
            "분반명", "수업유형", "수업일자", "시험회차", "이름", "학교명", "수강상태", "출석 여부",
            "보호자명", "보호자 이메일", "예습 과제 등급", "주간 과제 등급", "test 결과"
    };

    public List<ImportRow> importCsv(File file) throws IOException {
        Charset charset = detectCharset(file);
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(new FileInputStream(file), charset))) {
            String headerLine = reader.readLine();
            if (headerLine == null) {
                throw new IOException("CSV 파일이 비어 있습니다.");
            }

            List<String> headers = parseCsvLine(headerLine);
            Map<String, Integer> index = buildHeaderIndex(headers);
            List<ImportRow> rows = new ArrayList<>();

            String line;
            while ((line = reader.readLine()) != null) {
                if (line.trim().isEmpty()) {
                    continue;
                }
                List<String> values = parseCsvLine(line);
                rows.add(new ImportRow(
                        value(values, index, "분반명"),
                        ClassTypeUtil.toCode(value(values, index, "수업유형")),
                        LocalDate.parse(value(values, index, "수업일자")),
                        value(values, index, "시험회차"),
                        value(values, index, "이름"),
                        value(values, index, "학교명"),
                        EnrollmentStatusUtil.toCode(value(values, index, "수강상태")),
                        value(values, index, "출석 여부"),
                        value(values, index, "보호자명"),
                        value(values, index, "보호자 이메일"),
                        value(values, index, "예습 과제 등급"),
                        value(values, index, "주간 과제 등급"),
                        value(values, index, "test 결과")));
            }
            return rows;
        }
    }

    private Map<String, Integer> buildHeaderIndex(List<String> headers) throws IOException {
        Map<String, Integer> index = new HashMap<>();
        for (int i = 0; i < headers.size(); i++) {
            index.put(headers.get(i).trim(), i);
        }
        for (String required : REQUIRED_HEADERS) {
            if (!index.containsKey(required)) {
                throw new IOException("필수 컬럼 누락: " + required);
            }
        }
        return index;
    }

    private String value(List<String> values, Map<String, Integer> index, String key) {
        int valueIndex = index.get(key);
        if (valueIndex >= values.size()) {
            return "";
        }
        return values.get(valueIndex).trim();
    }

    private Charset detectCharset(File file) throws IOException {
        try (FileInputStream input = new FileInputStream(file)) {
            byte[] bytes = input.readAllBytes();
            if (bytes.length >= 3 && (bytes[0] & 0xff) == 0xef && (bytes[1] & 0xff) == 0xbb && (bytes[2] & 0xff) == 0xbf) {
                return StandardCharsets.UTF_8;
            }
            try {
                StandardCharsets.UTF_8.newDecoder()
                        .onMalformedInput(CodingErrorAction.REPORT)
                        .onUnmappableCharacter(CodingErrorAction.REPORT)
                        .decode(ByteBuffer.wrap(bytes));
                return StandardCharsets.UTF_8;
            } catch (CharacterCodingException ignored) {
                return Charset.forName("MS949");
            }
        }
    }

    private List<String> parseCsvLine(String line) {
        List<String> values = new ArrayList<>();
        StringBuilder current = new StringBuilder();
        boolean quoted = false;
        for (int i = 0; i < line.length(); i++) {
            char ch = line.charAt(i);
            if (ch == '"') {
                if (quoted && i + 1 < line.length() && line.charAt(i + 1) == '"') {
                    current.append('"');
                    i++;
                } else {
                    quoted = !quoted;
                }
            } else if (ch == ',' && !quoted) {
                values.add(current.toString());
                current.setLength(0);
            } else {
                current.append(ch);
            }
        }
        values.add(current.toString());
        return values;
    }
}
