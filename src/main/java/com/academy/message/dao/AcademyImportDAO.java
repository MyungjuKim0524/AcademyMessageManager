package com.academy.message.dao;

import com.academy.message.domain.AttendanceStatus;
import com.academy.message.model.ImportRow;
import com.academy.message.model.ImportSummary;
import com.academy.message.port.ConnectionProvider;
import com.academy.message.util.ImportHashUtil;
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.security.MessageDigest;
import java.sql.*;
import java.util.*;

public class AcademyImportDAO {
    private final ConnectionProvider connectionProvider;
    public AcademyImportDAO() { this(new DBConnection()); }
    public AcademyImportDAO(ConnectionProvider provider) { this.connectionProvider = provider; }

    public ImportSummary importRows(Iterable<ImportRow> rows, File sourceFile) throws SQLException {
        List<ImportRow> list = new ArrayList<>(); rows.forEach(list::add);
        try (Connection c = connectionProvider.getConnection()) {
            c.setAutoCommit(false);
            try {
                long jobId = createImportJob(c, sourceFile, list.size());
                ImportSummary summary = new ImportSummary(); int rowNumber = 2;
                for (ImportRow row : list) {
                    long classroomId = classroom(c, row, summary);
                    long studentId = student(c, row, summary);
                    long enrollmentId = enrollment(c, classroomId, studentId, row, summary);
                    long lessonId = lesson(c, classroomId, row, summary);
                    Result result = lessonResult(c, lessonId, enrollmentId, row, summary);
                    auditRow(c, jobId, result.id(), rowNumber++, row, result.action());
                }
                try (PreparedStatement s = c.prepareStatement("UPDATE import_job SET success_rows=?, status='COMPLETED', finished_at=CURRENT_TIMESTAMP WHERE id=?")) {
                    s.setInt(1, list.size()); s.setLong(2, jobId); s.executeUpdate();
                }
                c.commit(); return summary;
            } catch (Exception ex) {
                c.rollback();
                if (ex instanceof SQLException sql) throw sql;
                throw new SQLException("가져오기 처리 중 오류가 발생했습니다.", ex);
            }
        }
    }

    private long classroom(Connection c, ImportRow r, ImportSummary sum) throws SQLException {
        Long id = id(c, "SELECT id FROM classroom WHERE name=? AND class_type=?", r.getClassName(), r.getClassType());
        if (id != null) return id;
        sum.incrementInsertedClasses();
        return returning(c, "INSERT INTO classroom(name,class_type) VALUES(?,?) RETURNING id", r.getClassName(), r.getClassType());
    }

    private long student(Connection c, ImportRow r, ImportSummary sum) throws SQLException {
        Long id = id(c, "SELECT id FROM student WHERE name=? AND school_name=? ORDER BY id LIMIT 1", r.getStudentName(), r.getSchoolName());
        if (id == null) {
            sum.incrementInsertedStudents();
            return returning(c, "INSERT INTO student(name,school_name,parent_name,parent_email) VALUES(?,?,?,?) RETURNING id",
                    r.getStudentName(), r.getSchoolName(), blank(r.getParentName()), blank(r.getParentEmail()));
        }
        try (PreparedStatement s = c.prepareStatement("UPDATE student SET parent_name=?,parent_email=? WHERE id=?")) {
            s.setString(1, blank(r.getParentName())); s.setString(2, blank(r.getParentEmail())); s.setLong(3, id);
            if (s.executeUpdate() > 0) sum.incrementUpdatedStudents();
        }
        return id;
    }

    private long enrollment(Connection c, long classroomId, long studentId, ImportRow r, ImportSummary sum) throws SQLException {
        Long id = id(c, "SELECT id FROM enrollment WHERE classroom_id=? AND student_id=? ORDER BY enrolled_at DESC LIMIT 1", classroomId, studentId);
        if (id != null) return id;
        sum.incrementInsertedEnrollments();
        return returning(c, "INSERT INTO enrollment(classroom_id,student_id,status,enrolled_at) VALUES(?,?,?,?) RETURNING id",
                classroomId, studentId, defaultValue(r.getEnrollmentStatus(), "ACTIVE"), java.sql.Date.valueOf(r.getSessionDate()));
    }

    private long lesson(Connection c, long classroomId, ImportRow r, ImportSummary sum) throws SQLException {
        Long id = id(c, "SELECT id FROM lesson WHERE classroom_id=? AND lesson_date=? AND exam_round IS NOT DISTINCT FROM ?",
                classroomId, java.sql.Date.valueOf(r.getSessionDate()), blank(r.getTestRound()));
        if (id != null) return id;
        sum.incrementInsertedSessions();
        return returning(c, "INSERT INTO lesson(classroom_id,lesson_date,exam_round) VALUES(?,?,?) RETURNING id",
                classroomId, java.sql.Date.valueOf(r.getSessionDate()), blank(r.getTestRound()));
    }

    private Result lessonResult(Connection c, long lessonId, long enrollmentId, ImportRow r, ImportSummary sum) throws SQLException {
        try (PreparedStatement s = c.prepareStatement("SELECT id,attendance_status,prework_grade,weekly_assignment_grade,correct_count,total_count FROM lesson_result WHERE lesson_id=? AND enrollment_id=?")) {
            s.setLong(1, lessonId); s.setLong(2, enrollmentId);
            try (ResultSet rs = s.executeQuery()) {
                if (!rs.next()) {
                    long id = insertResult(c, lessonId, enrollmentId, r); sum.incrementInsertedGrades(); return new Result(id,"INSERT");
                }
                long id = rs.getLong("id");
                boolean changed = !Objects.equals(rs.getString("attendance_status"), attendance(r))
                        || !Objects.equals(rs.getString("prework_grade"), blank(r.getPreGrade()))
                        || !Objects.equals(rs.getString("weekly_assignment_grade"), blank(r.getWeeklyGrade()))
                        || !Objects.equals(nullableInt(rs,"correct_count"), r.getCorrectCount())
                        || !Objects.equals(nullableInt(rs,"total_count"), r.getTotalCount());
                if (!changed) { sum.incrementSkippedGrades(); return new Result(id,"SKIP"); }
                try (PreparedStatement u = c.prepareStatement("UPDATE lesson_result SET attendance_status=?,prework_grade=?,weekly_assignment_grade=?,correct_count=?,total_count=? WHERE id=?")) {
                    setResultValues(u, r, 1); u.setLong(6,id); u.executeUpdate();
                }
                sum.incrementUpdatedGrades(); return new Result(id,"UPDATE");
            }
        }
    }

    private long insertResult(Connection c, long lessonId, long enrollmentId, ImportRow r) throws SQLException {
        try (PreparedStatement s = c.prepareStatement("INSERT INTO lesson_result(lesson_id,enrollment_id,attendance_status,prework_grade,weekly_assignment_grade,correct_count,total_count) VALUES(?,?,?,?,?,?,?) RETURNING id")) {
            s.setLong(1,lessonId); s.setLong(2,enrollmentId); setResultValues(s,r,3);
            try(ResultSet rs=s.executeQuery()){rs.next();return rs.getLong(1);}
        }
    }

    private void setResultValues(PreparedStatement s, ImportRow r, int i) throws SQLException {
        s.setString(i,attendance(r)); s.setString(i+1,blank(r.getPreGrade())); s.setString(i+2,blank(r.getWeeklyGrade()));
        nullable(s,i+3,r.getCorrectCount()); nullable(s,i+4,r.getTotalCount());
    }

    private long createImportJob(Connection c, File file, int count) throws Exception {
        String name=file==null?"unknown.csv":file.getName(); String type=name.toLowerCase().endsWith(".xlsx")?"XLSX":"CSV";
        String hash=file==null?null:ImportHashUtil.fileHash(file);
        return returning(c,"INSERT INTO import_job(source_type,source_file_name,file_hash,total_rows,status) VALUES(?,?,?,?,'PROCESSING') RETURNING id",type,name,hash,count);
    }

    private void auditRow(Connection c,long job,long result,int number,ImportRow r,String action)throws Exception{
        String hash=ImportHashUtil.rowHash(r);
        try(PreparedStatement s=c.prepareStatement("INSERT INTO import_row(import_job_id,lesson_result_id,row_number,row_hash,processing_result,enrollment_action) VALUES(?,?,?,?,?,'SKIP')")){
            s.setLong(1,job);s.setLong(2,result);s.setInt(3,number);s.setString(4,hash);s.setString(5,action);s.executeUpdate();
        }
    }

    private Long id(Connection c,String sql,Object...v)throws SQLException{try(PreparedStatement s=c.prepareStatement(sql)){params(s,v);try(ResultSet rs=s.executeQuery()){return rs.next()?rs.getLong(1):null;}}}
    private long returning(Connection c,String sql,Object...v)throws SQLException{try(PreparedStatement s=c.prepareStatement(sql)){params(s,v);try(ResultSet rs=s.executeQuery()){if(!rs.next())throw new SQLException("ID 반환 실패");return rs.getLong(1);}}}
    private void params(PreparedStatement s,Object...v)throws SQLException{for(int i=0;i<v.length;i++)s.setObject(i+1,v[i]);}
    private void nullable(PreparedStatement s,int i,Integer v)throws SQLException{if(v==null)s.setNull(i,Types.SMALLINT);else s.setInt(i,v);}
    private Integer nullableInt(ResultSet rs,String n)throws SQLException{int v=rs.getInt(n);return rs.wasNull()?null:v;}
    private String attendance(ImportRow r){return AttendanceStatus.from(r.getAttendance()).name();}
    private String blank(String v){return v==null||v.isBlank()?null:v.trim();}
    private String defaultValue(String v,String d){return v==null||v.isBlank()?d:v.trim();}
    private record Result(long id,String action){}
}
