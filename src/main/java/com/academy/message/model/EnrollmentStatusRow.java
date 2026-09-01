package com.academy.message.model;

import java.time.LocalDate;

public class EnrollmentStatusRow {
    private final int enrollmentId;
    private final int studentId;
    private final String className;
    private final String classType;
    private final String studentName;
    private final String schoolName;
    private final String parentEmail;
    private final String status;
    private final LocalDate startDate;
    private final LocalDate endDate;

    public EnrollmentStatusRow(int enrollmentId, int studentId, String className, String classType, String studentName, String schoolName,
            String parentEmail, String status, LocalDate startDate, LocalDate endDate) {
        this.enrollmentId = enrollmentId;
        this.studentId = studentId;
        this.className = className;
        this.classType = classType;
        this.studentName = studentName;
        this.schoolName = schoolName;
        this.parentEmail = parentEmail;
        this.status = status;
        this.startDate = startDate;
        this.endDate = endDate;
    }

    public int getEnrollmentId() {
        return enrollmentId;
    }

    public int getStudentId() {
        return studentId;
    }

    public String getClassName() {
        return className;
    }

    public String getClassType() {
        return classType;
    }

    public String getStudentName() {
        return studentName;
    }

    public String getSchoolName() {
        return schoolName;
    }

    public String getParentEmail() {
        return parentEmail;
    }

    public String getStatus() {
        return status;
    }

    public LocalDate getStartDate() {
        return startDate;
    }

    public LocalDate getEndDate() {
        return endDate;
    }
}
