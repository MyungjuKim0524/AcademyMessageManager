package com.academy.message.dao;

import com.academy.message.model.ImportRow;
import com.academy.message.model.MessagePreview;
import com.academy.message.model.SendLogRow;
import com.academy.message.port.ConnectionProvider;
import java.sql.*;
import java.time.*;
import java.util.ArrayList;
import java.util.List;

/** Maps the legacy send-log UI onto message_draft, delivery_job and delivery_attempt. */
public class SendLogDAO {
    private final ConnectionProvider connectionProvider;
    public SendLogDAO() { this(new DBConnection()); }
    public SendLogDAO(ConnectionProvider provider) { this.connectionProvider = provider; }

    public void insertSendLog(MessagePreview preview,String status,String error)throws SQLException{
        insertSendLog(preview,preview.getRow().getParentEmail(),status,error);
    }

    public void insertSendLog(MessagePreview preview,String email,String status,String error)throws SQLException{
        try(Connection c=connectionProvider.getConnection()){
            c.setAutoCommit(false);
            try{
                ImportRow row=preview.getRow(); long resultId=requireResult(c,row); long templateId=requireTemplate(c,row.getClassType());
                long draftId=returning(c,"INSERT INTO message_draft(lesson_result_id,template_id,subject,body,draft_status) VALUES(?,?,?,?,?) RETURNING id",
                        resultId,templateId,"학습 안내",preview.getContent(),"READY");
                String dbStatus=toDbStatus(status);
                long jobId=returning(c,"INSERT INTO delivery_job(message_draft_id,recipient_email,status,processed_at) VALUES(?,?,?,?) RETURNING id",
                        draftId,email,dbStatus,"PENDING".equals(dbStatus)?null:Timestamp.valueOf(LocalDateTime.now()));
                if("SUCCESS".equals(dbStatus)||"FAILED".equals(dbStatus)) insertAttempt(c,jobId,dbStatus,error);
                c.commit();
            }catch(SQLException ex){c.rollback();throw ex;}
        }
    }

    public List<SendLogRow> findAll()throws SQLException{return query(null,null,null);}
    public List<SendLogRow> findFailedLogs()throws SQLException{return query("FAILED",null,null);}
    public List<SendLogRow> searchLogs(String status,String className,LocalDate date)throws SQLException{return query(status,className,date);}

    public void markRetriedAsSent(int id)throws SQLException{
        try(Connection c=connectionProvider.getConnection()){c.setAutoCommit(false);try{
            try(PreparedStatement s=c.prepareStatement("UPDATE delivery_job SET status='SUCCESS',processed_at=CURRENT_TIMESTAMP WHERE id=?")){s.setInt(1,id);s.executeUpdate();}
            insertAttempt(c,id,"SUCCESS",null);c.commit();
        }catch(SQLException ex){c.rollback();throw ex;}}
    }

    public void markFailed(int id,String error)throws SQLException{
        try(Connection c=connectionProvider.getConnection()){c.setAutoCommit(false);try{
            try(PreparedStatement s=c.prepareStatement("UPDATE delivery_job SET status='FAILED',processed_at=CURRENT_TIMESTAMP WHERE id=?")){s.setInt(1,id);s.executeUpdate();}
            insertAttempt(c,id,"FAILED",error);c.commit();
        }catch(SQLException ex){c.rollback();throw ex;}}
    }

    private List<SendLogRow> query(String status,String className,LocalDate date)throws SQLException{
        List<SendLogRow> out=new ArrayList<>();
        StringBuilder sql=new StringBuilder("SELECT dj.id AS log_id,s.name AS student_name,s.school_name,dj.recipient_email AS parent_email,md.body AS message_content,dj.status,dj.processed_at AS sent_at,a.error_message FROM delivery_job dj JOIN message_draft md ON md.id=dj.message_draft_id JOIN lesson_result lr ON lr.id=md.lesson_result_id JOIN enrollment e ON e.id=lr.enrollment_id JOIN student s ON s.id=e.student_id JOIN lesson l ON l.id=lr.lesson_id JOIN classroom c ON c.id=l.classroom_id LEFT JOIN LATERAL (SELECT error_message FROM delivery_attempt WHERE delivery_job_id=dj.id ORDER BY attempt_no DESC LIMIT 1) a ON TRUE WHERE 1=1 ");
        if(status!=null&&!status.isBlank()&&!"ALL".equals(status))sql.append("AND dj.status=? ");
        if(className!=null&&!className.isBlank())sql.append("AND c.name LIKE ? ");
        if(date!=null)sql.append("AND dj.processed_at::date=? ");
        sql.append("ORDER BY dj.id DESC");
        try(Connection c=connectionProvider.getConnection();PreparedStatement s=c.prepareStatement(sql.toString())){
            int i=1;if(status!=null&&!status.isBlank()&&!"ALL".equals(status))s.setString(i++,toDbStatus(status));
            if(className!=null&&!className.isBlank())s.setString(i++,"%"+className.trim()+"%");if(date!=null)s.setDate(i,Date.valueOf(date));
            try(ResultSet rs=s.executeQuery()){while(rs.next()){Timestamp at=rs.getTimestamp("sent_at");out.add(new SendLogRow(rs.getInt("log_id"),rs.getString("student_name"),rs.getString("school_name"),rs.getString("parent_email"),rs.getString("message_content"),toUiStatus(rs.getString("status")),at==null?null:at.toLocalDateTime(),rs.getString("error_message")));}}
        }return out;
    }

    private long requireResult(Connection c,ImportRow r)throws SQLException{
        try(PreparedStatement s=c.prepareStatement("SELECT lr.id FROM lesson_result lr JOIN enrollment e ON e.id=lr.enrollment_id JOIN student st ON st.id=e.student_id JOIN lesson l ON l.id=lr.lesson_id JOIN classroom cl ON cl.id=l.classroom_id WHERE st.name=? AND st.school_name=? AND cl.name=? AND l.lesson_date=? AND l.exam_round IS NOT DISTINCT FROM ? ORDER BY lr.id DESC LIMIT 1")){
            s.setString(1,r.getStudentName());s.setString(2,r.getSchoolName());s.setString(3,r.getClassName());s.setDate(4,Date.valueOf(r.getSessionDate()));s.setString(5,blank(r.getTestRound()));try(ResultSet rs=s.executeQuery()){if(!rs.next())throw new SQLException("메시지와 연결할 수업 결과가 없습니다.");return rs.getLong(1);}}
    }
    private long requireTemplate(Connection c,String type)throws SQLException{try(PreparedStatement s=c.prepareStatement("SELECT id FROM message_template WHERE class_type=? AND is_active=TRUE")){s.setString(1,type);try(ResultSet rs=s.executeQuery()){if(!rs.next())throw new SQLException("활성 메시지 템플릿이 없습니다.");return rs.getLong(1);}}}
    private void insertAttempt(Connection c,long job,String status,String error)throws SQLException{try(PreparedStatement s=c.prepareStatement("INSERT INTO delivery_attempt(delivery_job_id,attempt_no,attempt_status,error_message) SELECT ?,COALESCE(MAX(attempt_no),0)+1,?,? FROM delivery_attempt WHERE delivery_job_id=?")){s.setLong(1,job);s.setString(2,status);s.setString(3,blank(error));s.setLong(4,job);s.executeUpdate();}}
    private long returning(Connection c,String sql,Object...v)throws SQLException{try(PreparedStatement s=c.prepareStatement(sql)){for(int i=0;i<v.length;i++)s.setObject(i+1,v[i]);try(ResultSet rs=s.executeQuery()){rs.next();return rs.getLong(1);}}}
    private String toDbStatus(String s){return switch(s){case "READY"->"PENDING";case "SENT"->"SUCCESS";default->s;};}
    private String toUiStatus(String s){return switch(s){case "PENDING","PROCESSING"->"READY";case "SUCCESS"->"SENT";default->s;};}
    private String blank(String v){return v==null||v.isBlank()?null:v.trim();}
}
