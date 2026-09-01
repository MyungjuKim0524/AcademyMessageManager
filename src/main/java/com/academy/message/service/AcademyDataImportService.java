package com.academy.message.service;

import java.io.File;
import java.io.IOException;
import java.util.Objects;

/** 파일 해석과 비즈니스 검증을 하나의 유스케이스로 제공한다. DB 반영은 사용자 승인 후 별도로 수행한다. */
public final class AcademyDataImportService {
    private final SpreadsheetImportService spreadsheetImportService;
    private final DataValidationService validationService;

    public AcademyDataImportService() {
        this(new SpreadsheetImportService(), new DataValidationService());
    }

    public AcademyDataImportService(SpreadsheetImportService spreadsheetImportService,
            DataValidationService validationService) {
        this.spreadsheetImportService = Objects.requireNonNull(spreadsheetImportService);
        this.validationService = Objects.requireNonNull(validationService);
    }

    public ImportBatch loadAndValidate(File file) throws IOException {
        if (file == null || !file.isFile()) throw new IOException("불러올 파일을 찾을 수 없습니다.");
        var rows = spreadsheetImportService.importFile(file);
        return new ImportBatch(rows, validationService.validate(rows));
    }
}
