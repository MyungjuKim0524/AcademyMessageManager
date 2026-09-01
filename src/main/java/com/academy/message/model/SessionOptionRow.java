package com.academy.message.model;

import java.time.LocalDate;

public class SessionOptionRow {
    private final int sessionId;
    private final String className;
    private final String classType;
    private final LocalDate sessionDate;
    private final String testRound;

    public SessionOptionRow(int sessionId, String className, String classType, LocalDate sessionDate, String testRound) {
        this.sessionId = sessionId;
        this.className = className;
        this.classType = classType;
        this.sessionDate = sessionDate;
        this.testRound = testRound;
    }

    public int getSessionId() {
        return sessionId;
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
}
