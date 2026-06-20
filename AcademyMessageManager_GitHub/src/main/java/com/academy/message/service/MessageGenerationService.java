package com.academy.message.service;

import com.academy.message.dao.MakeupDAO;
import com.academy.message.dao.TemplateDAO;
import com.academy.message.model.ImportRow;

import java.util.List;

public class MessageGenerationService {
    private final TemplateDAO templateDAO = new TemplateDAO();
    private final MakeupDAO makeupDAO = new MakeupDAO();

    public String generateMessage(ImportRow row, boolean includePreGrade, boolean includeWeeklyGrade, boolean includeTestResult) {
        String template = loadTemplate(row.getClassType());
        String preMessage = includePreGrade && !row.getPreGrade().isBlank() ? convertPreGradeMessage(row.getPreGrade()) : "";
        String weeklyMessage = includeWeeklyGrade && !row.getWeeklyGrade().isBlank() ? convertWeeklyGradeMessage(row.getWeeklyGrade()) : "";
        String testMessage = includeTestResult && !row.getTestResult().isBlank()
                ? "테스트 결과는 " + row.getTestResult() + "입니다."
                : "";
        String makeupMessage = generateMakeupMessage(row);

        return cleanupBlankLines(template
                .replace("{학생명}", row.getStudentName())
                .replace("{분반명}", row.getClassName())
                .replace("{수업일자}", row.getSessionDate().toString())
                .replace("{시험회차}", row.getTestRound())
                .replace("{예습메시지}", preMessage)
                .replace("{주간메시지}", weeklyMessage)
                .replace("{테스트메시지}", testMessage)
                .replace("{보강메시지}", makeupMessage));
    }

    private String loadTemplate(String classType) {
        try {
            return templateDAO.findOrCreateActiveTemplate(classType);
        } catch (Exception ex) {
            return templateDAO.defaultTemplate(classType);
        }
    }

    private String generateMakeupMessage(ImportRow row) {
        if (!"결석".equals(row.getAttendance())) {
            return "";
        }
        try {
            String status = makeupDAO.findLatestStatus(
                    row.getStudentName(),
                    row.getSchoolName(),
                    row.getClassName(),
                    row.getSessionDate(),
                    row.getTestRound());
            if ("COMPLETED".equals(status)) {
                return "결석한 수업 내용은 보강 수업을 통해 보완하였습니다.";
            }
            if ("REQUESTED".equals(status) || "APPROVED".equals(status)) {
                return "결석한 수업 내용은 신청한 보강 수업에서 보완할 예정입니다.";
            }
        } catch (Exception ignored) {
            // If DB lookup fails, keep the message generation available with the default absence text.
        }
        return "이번 수업은 결석으로 인해 학습 내용 확인이 필요합니다.";
    }

    public boolean hasAnyPreGrade(List<ImportRow> rows) {
        return rows.stream().anyMatch(row -> !row.getPreGrade().isBlank());
    }

    public boolean hasAnyWeeklyGrade(List<ImportRow> rows) {
        return rows.stream().anyMatch(row -> !row.getWeeklyGrade().isBlank());
    }

    public boolean hasAnyTestResult(List<ImportRow> rows) {
        return rows.stream().anyMatch(row -> !row.getTestResult().isBlank());
    }

    private String convertPreGradeMessage(String grade) {
        switch (grade) {
            case "A":
                return "예습 과제를 성실하게 수행하였습니다.";
            case "B":
                return "예습 과제를 대체로 수행하였으나 일부 보완이 필요합니다.";
            case "C":
                return "예습 과제 수행이 부족하여 추가적인 확인이 필요합니다.";
            default:
                return "";
        }
    }

    private String convertWeeklyGradeMessage(String grade) {
        switch (grade) {
            case "A":
                return "주간 과제를 안정적으로 완료하였습니다.";
            case "B":
                return "주간 과제 수행은 양호하나 일부 문항에서 보완이 필요합니다.";
            case "C":
                return "주간 과제 수행이 부족하여 가정에서도 추가 학습이 필요합니다.";
            default:
                return "";
        }
    }

    private String cleanupBlankLines(String text) {
        String normalized = text.replace("\r\n", "\n").replace('\r', '\n');
        while (normalized.contains("\n\n\n")) {
            normalized = normalized.replace("\n\n\n", "\n\n");
        }
        return normalized.trim();
    }
}
