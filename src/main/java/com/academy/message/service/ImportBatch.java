package com.academy.message.service;

import com.academy.message.model.ImportRow;
import java.util.List;

public record ImportBatch(List<ImportRow> rows, List<String> validationErrors) {
    public ImportBatch {
        rows = List.copyOf(rows);
        validationErrors = List.copyOf(validationErrors);
    }

    public boolean isValid() { return validationErrors.isEmpty(); }
}
