package com.academy.message.model;

import java.time.LocalDate;

public class AbsentStudentRow {
    private final int studentId;
    private final int sessionId;
    private final String studentName;
    private final String schoolName;
    private final String className;
    private final LocalDate sessionDate;
    private final String testRound;
    private final String makeupStatus;

    public AbsentStudentRow(int studentId, int sessionId, String studentName, String schoolName,
            String className, LocalDate sessionDate, String testRound, String makeupStatus) {
        this.studentId = studentId;
        this.sessionId = sessionId;
        this.studentName = studentName;
        this.schoolName = schoolName;
        this.className = className;
        this.sessionDate = sessionDate;
        this.testRound = testRound;
        this.makeupStatus = makeupStatus;
    }

    public int getStudentId() {
        return studentId;
    }

    public int getSessionId() {
        return sessionId;
    }

    public String getStudentName() {
        return studentName;
    }

    public String getSchoolName() {
        return schoolName;
    }

    public String getClassName() {
        return className;
    }

    public LocalDate getSessionDate() {
        return sessionDate;
    }

    public String getTestRound() {
        return testRound;
    }

    public String getMakeupStatus() {
        return makeupStatus;
    }
}
