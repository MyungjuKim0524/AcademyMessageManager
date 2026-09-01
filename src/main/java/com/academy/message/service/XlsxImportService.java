package com.academy.message.service;

import com.academy.message.model.ImportRow;
import com.academy.message.util.ClassTypeUtil;
import com.academy.message.util.EnrollmentStatusUtil;

import org.apache.poi.ss.usermodel.Cell;
import org.apache.poi.ss.usermodel.CellType;
import org.apache.poi.ss.usermodel.DataFormatter;
import org.apache.poi.ss.usermodel.DateUtil;
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.ss.usermodel.Sheet;
import org.apache.poi.ss.usermodel.Workbook;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;

import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class XlsxImportService {
    private static final String[] REQUIRED_HEADERS = {
            "분반명", "수업유형", "수업일자", "시험회차", "이름", "학교명", "수강상태", "출석 여부",
            "보호자명", "보호자 이메일", "예습 과제 등급", "주간 과제 등급", "test 결과"
    };

    private final DataFormatter formatter = new DataFormatter();

    public List<ImportRow> importXlsx(File file) throws IOException {
        try (FileInputStream input = new FileInputStream(file);
                Workbook workbook = new XSSFWorkbook(input)) {
            Sheet sheet = workbook.getSheetAt(0);
            Row headerRow = sheet.getRow(sheet.getFirstRowNum());
            if (headerRow == null) {
                throw new IOException("엑셀 첫 번째 시트가 비어 있습니다.");
            }

            Map<String, Integer> index = buildHeaderIndex(headerRow);
            List<ImportRow> rows = new ArrayList<>();
            for (int rowIndex = sheet.getFirstRowNum() + 1; rowIndex <= sheet.getLastRowNum(); rowIndex++) {
                Row row = sheet.getRow(rowIndex);
                if (row == null || isBlankRow(row)) {
                    continue;
                }
                rows.add(new ImportRow(
                        text(row, index, "분반명"),
                        ClassTypeUtil.toCode(text(row, index, "수업유형")),
                        date(row, index, "수업일자"),
                        text(row, index, "시험회차"),
                        text(row, index, "이름"),
                        text(row, index, "학교명"),
                        EnrollmentStatusUtil.toCode(text(row, index, "수강상태")),
                        text(row, index, "출석 여부"),
                        text(row, index, "보호자명"),
                        text(row, index, "보호자 이메일"),
                        text(row, index, "예습 과제 등급"),
                        text(row, index, "주간 과제 등급"),
                        text(row, index, "test 결과")));
            }
            return rows;
        }
    }

    private Map<String, Integer> buildHeaderIndex(Row headerRow) throws IOException {
        Map<String, Integer> index = new HashMap<>();
        for (Cell cell : headerRow) {
            String header = formatter.formatCellValue(cell).trim();
            if (!header.isBlank()) {
                index.put(header, cell.getColumnIndex());
            }
        }
        for (String required : REQUIRED_HEADERS) {
            if (!index.containsKey(required)) {
                throw new IOException("필수 컬럼 누락: " + required);
            }
        }
        return index;
    }

    private boolean isBlankRow(Row row) {
        for (Cell cell : row) {
            if (!formatter.formatCellValue(cell).trim().isBlank()) {
                return false;
            }
        }
        return true;
    }

    private String text(Row row, Map<String, Integer> index, String key) {
        Cell cell = row.getCell(index.get(key));
        if (cell == null) {
            return "";
        }
        return formatter.formatCellValue(cell).trim();
    }

    private LocalDate date(Row row, Map<String, Integer> index, String key) throws IOException {
        Cell cell = row.getCell(index.get(key));
        if (cell == null) {
            throw new IOException("수업일자 값이 비어 있습니다. 행: " + (row.getRowNum() + 1));
        }
        if (cell.getCellType() == CellType.NUMERIC && DateUtil.isCellDateFormatted(cell)) {
            return cell.getDateCellValue().toInstant().atZone(ZoneId.systemDefault()).toLocalDate();
        }
        String text = formatter.formatCellValue(cell).trim().replace('.', '-').replace('/', '-');
        try {
            return LocalDate.parse(text);
        } catch (Exception ex) {
            throw new IOException("수업일자 형식이 올바르지 않습니다. 행: " + (row.getRowNum() + 1) + ", 값: " + text);
        }
    }
}
