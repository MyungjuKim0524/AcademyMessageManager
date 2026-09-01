package com.academy.message.model;

public class ImportSummary {
    private int insertedClasses;
    private int insertedStudents;
    private int insertedEnrollments;
    private int insertedSessions;
    private int insertedGrades;
    private int updatedStudents;
    private int updatedGrades;
    private int skippedGrades;

    public void incrementInsertedClasses() {
        insertedClasses++;
    }

    public void incrementInsertedStudents() {
        insertedStudents++;
    }

    public void incrementInsertedEnrollments() {
        insertedEnrollments++;
    }

    public void incrementInsertedSessions() {
        insertedSessions++;
    }

    public void incrementInsertedGrades() {
        insertedGrades++;
    }

    public void incrementUpdatedStudents() {
        updatedStudents++;
    }

    public void incrementUpdatedGrades() {
        updatedGrades++;
    }

    public void incrementSkippedGrades() {
        skippedGrades++;
    }

    public String toDisplayText() {
        return "DB 업데이트 결과\n"
                + "- 신규 분반: " + insertedClasses + "건\n"
                + "- 신규 학생: " + insertedStudents + "건\n"
                + "- 학생 정보 수정: " + updatedStudents + "건\n"
                + "- 신규 수강 등록: " + insertedEnrollments + "건\n"
                + "- 신규 수업 회차: " + insertedSessions + "건\n"
                + "- 신규 성적: " + insertedGrades + "건\n"
                + "- 성적 수정: " + updatedGrades + "건\n"
                + "- 변경 없음: " + skippedGrades + "건";
    }
}
