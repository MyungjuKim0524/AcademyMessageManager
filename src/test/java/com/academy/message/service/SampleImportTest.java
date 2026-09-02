package com.academy.message.service;

import org.junit.jupiter.api.Test;
import java.io.File;
import static org.junit.jupiter.api.Assertions.*;

class SampleImportTest {
    @Test void importsCsvAndXlsxWithEquivalentScores() throws Exception {
        AcademyDataImportService service = new AcademyDataImportService();
        ImportBatch csv = service.loadAndValidate(new File("data/sample_students.csv"));
        ImportBatch xlsx = service.loadAndValidate(new File("data/sample_students.xlsx"));
        assertTrue(csv.isValid(), csv.validationErrors().toString());
        assertTrue(xlsx.isValid(), xlsx.validationErrors().toString());
        assertEquals(3, csv.rows().size());
        assertEquals(csv.rows().size(), xlsx.rows().size());
        for (int i = 0; i < csv.rows().size(); i++) {
            assertEquals(csv.rows().get(i).getCorrectCount(), xlsx.rows().get(i).getCorrectCount());
            assertEquals(csv.rows().get(i).getTotalCount(), xlsx.rows().get(i).getTotalCount());
        }
    }
}
