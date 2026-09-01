package com.academy.message.util;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class CsvExportUtilTest {
    @Test
    void prefixesFormulaCharactersBeforeExport() {
        assertEquals("'=SUM(A1:A2)", CsvExportUtil.csv("=SUM(A1:A2)"));
        assertEquals("'+가상중학교", CsvExportUtil.csv("+가상중학교"));
        assertEquals("'-parent@example.invalid", CsvExportUtil.csv("-parent@example.invalid"));
        assertEquals("'@FAILED", CsvExportUtil.csv("@FAILED"));
        assertEquals("\"'=CMD(),test\"", CsvExportUtil.csv("=CMD(),test"));
        assertEquals("일반값", CsvExportUtil.csv("일반값"));
    }
}
