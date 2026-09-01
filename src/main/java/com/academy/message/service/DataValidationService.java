package com.academy.message.service;

import com.academy.message.model.ImportRow;
import com.academy.message.util.EmailValidator;
import com.academy.message.domain.AchievementGrade;
import com.academy.message.domain.AttendanceStatus;
import com.academy.message.domain.ClassType;
import com.academy.message.domain.EnrollmentStatus;

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

            validateDomainValue(errors, line, () -> ClassType.from(row.getClassType()));
            validateDomainValue(errors, line, () -> EnrollmentStatus.from(row.getEnrollmentStatus()));
            validateDomainValue(errors, line, () -> AttendanceStatus.from(row.getAttendance()));
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
        try { AchievementGrade.from(grade); }
        catch (IllegalArgumentException ex) { errors.add(line + "행: " + label + "은 A, B, C 또는 공백이어야 합니다."); }
    }

    private void validateDomainValue(List<String> errors, int line, Runnable validation) {
        try { validation.run(); }
        catch (IllegalArgumentException ex) { errors.add(line + "행: " + ex.getMessage()); }
    }
}
