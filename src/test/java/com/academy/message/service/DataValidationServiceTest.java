package com.academy.message.service;

import com.academy.message.model.ImportRow;
import org.junit.jupiter.api.Test;
import java.time.LocalDate;
import java.util.List;
import static org.junit.jupiter.api.Assertions.*;

class DataValidationServiceTest {
    @Test void reportsBusinessErrorsWithSourceRowNumber() {
        ImportRow invalid = new ImportRow("A반", "UNKNOWN", LocalDate.of(2026, 8, 8), "1회",
                "김학생", "코덱스중", "WITHDRAWN", "조퇴", "김보호", "not-an-email", "D", "", "");

        List<String> errors = new DataValidationService().validate(List.of(invalid));

        assertTrue(errors.stream().allMatch(error -> error.startsWith("2행:")));
        assertTrue(errors.stream().anyMatch(error -> error.contains("수업유형")));
        assertTrue(errors.stream().anyMatch(error -> error.contains("출석 여부")));
        assertTrue(errors.stream().anyMatch(error -> error.contains("이메일")));
    }
}
