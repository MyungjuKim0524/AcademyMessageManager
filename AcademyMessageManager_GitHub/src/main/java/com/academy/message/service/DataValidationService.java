package com.academy.message.service;

import com.academy.message.model.ImportRow;
import com.academy.message.util.EmailValidator;

import java.util.ArrayList;
import java.util.List;

public class DataValidationService {
    public List<String> validate(List<ImportRow> rows) {
        List<String> errors = new ArrayList<>();
        for (int i = 0; i < rows.size(); i++) {
            ImportRow row = rows.get(i);
            int line = i + 2;
            require(errors, line, "분반명", row.getClassName());
            require(errors, line, "이름", row.getStudentName());
            require(errors, line, "보호자 이메일", row.getParentEmail());

            if (!"REGULAR".equals(row.getClassType()) && !"EXAM_PREP".equals(row.getClassType())) {
                errors.add(line + "행: 수업유형은 REGULAR 또는 EXAM_PREP 이어야 합니다.");
            }
            if (!"출석".equals(row.getAttendance()) && !"결석".equals(row.getAttendance())) {
                errors.add(line + "행: 출석 여부는 출석 또는 결석이어야 합니다.");
            }
            validateGrade(errors, line, "예습 과제 등급", row.getPreGrade());
            validateGrade(errors, line, "주간 과제 등급", row.getWeeklyGrade());
            if (!EmailValidator.isValid(row.getParentEmail())) {
                errors.add(line + "행: 이메일 형식이 올바르지 않습니다.");
            }
        }
        return errors;
    }

    private void require(List<String> errors, int line, String label, String value) {
        if (value == null || value.isBlank()) {
            errors.add(line + "행: " + label + " 값이 비어 있습니다.");
        }
    }

    private void validateGrade(List<String> errors, int line, String label, String grade) {
        if (grade == null || grade.isBlank()) {
            return;
        }
        if (!"A".equals(grade) && !"B".equals(grade) && !"C".equals(grade)) {
            errors.add(line + "행: " + label + "은 A, B, C 또는 공백이어야 합니다.");
        }
    }
}
