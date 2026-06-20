package com.academy.message.model;

import java.time.LocalDate;

public class MakeupRequestRow {
    private final int makeupId;
    private final String studentName;
    private final String schoolName;
    private final String originalClassName;
    private final LocalDate originalDate;
    private final String targetClassName;
    private final LocalDate targetDate;
    private final String status;

    public MakeupRequestRow(int makeupId, String studentName, String schoolName, String originalClassName,
            LocalDate originalDate, String targetClassName, LocalDate targetDate, String status) {
        this.makeupId = makeupId;
        this.studentName = studentName;
        this.schoolName = schoolName;
        this.originalClassName = originalClassName;
        this.originalDate = originalDate;
        this.targetClassName = targetClassName;
        this.targetDate = targetDate;
        this.status = status;
    }

    public int getMakeupId() {
        return makeupId;
    }

    public String getStudentName() {
        return studentName;
    }

    public String getSchoolName() {
        return schoolName;
    }

    public String getOriginalClassName() {
        return originalClassName;
    }

    public LocalDate getOriginalDate() {
        return originalDate;
    }

    public String getTargetClassName() {
        return targetClassName;
    }

    public LocalDate getTargetDate() {
        return targetDate;
    }

    public String getStatus() {
        return status;
    }
}
