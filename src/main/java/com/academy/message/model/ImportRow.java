package com.academy.message.model;

import java.time.LocalDate;

public class ImportRow {
    private final String className;
    private final String classType;
    private final LocalDate sessionDate;
    private final String testRound;
    private final String studentName;
    private final String schoolName;
    private final String enrollmentStatus;
    private final String attendance;
    private final String parentName;
    private final String parentEmail;
    private final String preGrade;
    private final String weeklyGrade;
    private final String testResult;

    public ImportRow(String className, String classType, LocalDate sessionDate, String testRound,
            String studentName, String schoolName, String enrollmentStatus, String attendance,
            String parentName, String parentEmail, String preGrade, String weeklyGrade, String testResult) {
        this.className = className;
        this.classType = classType;
        this.sessionDate = sessionDate;
        this.testRound = testRound;
        this.studentName = studentName;
        this.schoolName = schoolName;
        this.enrollmentStatus = enrollmentStatus;
        this.attendance = attendance;
        this.parentName = parentName;
        this.parentEmail = parentEmail;
        this.preGrade = preGrade;
        this.weeklyGrade = weeklyGrade;
        this.testResult = testResult;
    }

    public String getClassName() {
        return className;
    }

    public String getClassType() {
        return classType;
    }

    public LocalDate getSessionDate() {
        return sessionDate;
    }

    public String getTestRound() {
        return testRound;
    }

    public String getStudentName() {
        return studentName;
    }

    public String getSchoolName() {
        return schoolName;
    }

    public String getEnrollmentStatus() {
        return enrollmentStatus;
    }

    public String getAttendance() {
        return attendance;
    }

    public String getParentName() {
        return parentName;
    }

    public String getParentEmail() {
        return parentEmail;
    }

    public String getPreGrade() {
        return preGrade;
    }

    public String getWeeklyGrade() {
        return weeklyGrade;
    }

    public String getTestResult() {
        return testResult;
    }
}
