package com.academy.message.util;

import com.academy.message.model.ImportRow;
import org.junit.jupiter.api.Test;
import java.time.LocalDate;
import static org.junit.jupiter.api.Assertions.*;

class ImportHashUtilTest {
    @Test void createsDeterministicSha256WithoutReturningRawData() {
        ImportRow row = new ImportRow("JAVA-A", "REGULAR", LocalDate.of(2026, 5, 11), "3회차",
                "샘플학생", "가상중학교", "ACTIVE", "출석", "샘플보호자",
                "parent@example.invalid", "A", "B", "13/39");
        String first = ImportHashUtil.rowHash(row);
        assertEquals(64, first.length());
        assertEquals(first, ImportHashUtil.rowHash(row));
        assertFalse(first.contains("샘플학생"));
    }
}
