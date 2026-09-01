package com.academy.message.domain;

import com.academy.message.model.ImportRow;

public final class LearningMessageComposer {
    private final MakeupGuidancePolicy makeupGuidancePolicy;

    public LearningMessageComposer() {
        this(new MakeupGuidancePolicy());
    }

    public LearningMessageComposer(MakeupGuidancePolicy makeupGuidancePolicy) {
        this.makeupGuidancePolicy = makeupGuidancePolicy;
    }

    public String compose(String template, ImportRow row, MessageSections sections, MakeupStatus makeupStatus) {
        AttendanceStatus attendance = AttendanceStatus.from(row.getAttendance());
        String preMessage = sections.includePreGrade() ? preGradeMessage(row.getPreGrade()) : "";
        String weeklyMessage = sections.includeWeeklyGrade() ? weeklyGradeMessage(row.getWeeklyGrade()) : "";
        String testMessage = sections.includeTestResult() && hasText(row.getTestResult())
                ? "테스트 결과는 " + row.getTestResult() + "입니다." : "";

        return cleanupBlankLines(template
                .replace("{학생명}", safe(row.getStudentName()))
                .replace("{분반명}", safe(row.getClassName()))
                .replace("{수업일자}", row.getSessionDate() == null ? "" : row.getSessionDate().toString())
                .replace("{시험회차}", safe(row.getTestRound()))
                .replace("{예습메시지}", preMessage)
                .replace("{주간메시지}", weeklyMessage)
                .replace("{테스트메시지}", testMessage)
                .replace("{보강메시지}", makeupGuidancePolicy.guidanceFor(attendance, makeupStatus)));
    }

    private String preGradeMessage(String value) {
        AchievementGrade grade = AchievementGrade.from(value);
        if (grade == null) return "";
        return switch (grade) {
            case A -> "예습 과제를 성실하게 수행하였습니다.";
            case B -> "예습 과제를 대체로 수행하였으나 일부 보완이 필요합니다.";
            case C -> "예습 과제 수행이 부족하여 추가적인 확인이 필요합니다.";
        };
    }

    private String weeklyGradeMessage(String value) {
        AchievementGrade grade = AchievementGrade.from(value);
        if (grade == null) return "";
        return switch (grade) {
            case A -> "주간 과제를 안정적으로 완료하였습니다.";
            case B -> "주간 과제 수행은 양호하나 일부 문항에서 보완이 필요합니다.";
            case C -> "주간 과제 수행이 부족하여 가정에서도 추가 학습이 필요합니다.";
        };
    }

    private boolean hasText(String value) { return value != null && !value.isBlank(); }
    private String safe(String value) { return value == null ? "" : value; }

    private String cleanupBlankLines(String text) {
        String normalized = text.replace("\r\n", "\n").replace('\r', '\n');
        while (normalized.contains("\n\n\n")) normalized = normalized.replace("\n\n\n", "\n\n");
        return normalized.trim();
    }
}
