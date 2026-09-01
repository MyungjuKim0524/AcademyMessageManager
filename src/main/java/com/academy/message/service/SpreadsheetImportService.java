package com.academy.message.service;

import com.academy.message.model.ImportRow;

import java.io.File;
import java.io.IOException;
import java.util.List;

public class SpreadsheetImportService {
    private final CsvImportService csvImportService = new CsvImportService();
    private final XlsxImportService xlsxImportService = new XlsxImportService();

    public List<ImportRow> importFile(File file) throws IOException {
        String fileName = file.getName().toLowerCase();
        if (fileName.endsWith(".csv")) {
            return csvImportService.importCsv(file);
        }
        if (fileName.endsWith(".xlsx")) {
            return xlsxImportService.importXlsx(file);
        }
        throw new IOException("지원하지 않는 파일 형식입니다. .csv 또는 .xlsx 파일을 선택해 주세요.");
    }
}
