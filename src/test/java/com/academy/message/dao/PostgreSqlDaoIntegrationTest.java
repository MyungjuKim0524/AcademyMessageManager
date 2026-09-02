package com.academy.message.dao;

import static org.junit.jupiter.api.Assertions.*;

import com.academy.message.domain.LearningMessageComposer;
import com.academy.message.model.AbsentStudentRow;
import com.academy.message.model.ImportRow;
import com.academy.message.model.MakeupRequestRow;
import com.academy.message.model.MessagePreview;
import com.academy.message.port.ConnectionProvider;
import com.academy.message.service.AcademyDataImportService;
import com.academy.message.service.ImportBatch;
import com.academy.message.service.MessageGenerationService;
import java.io.File;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.List;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInstance;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;

@TestInstance(TestInstance.Lifecycle.PER_CLASS)
@EnabledIfEnvironmentVariable(named = "RUN_POSTGRES_INTEGRATION", matches = "true")
class PostgreSqlDaoIntegrationTest {
    private final ConnectionProvider connections = new DBConnection();

    @BeforeAll
    void resetDatabase() throws SQLException {
        try (Connection connection = connections.getConnection(); Statement statement = connection.createStatement()) {
            statement.execute("TRUNCATE TABLE delivery_attempt, delivery_job, message_draft, message_template, "
                    + "makeup_request, import_row, import_job, lesson_result, lesson, enrollment, student, classroom "
                    + "RESTART IDENTITY CASCADE");
        }
    }

    @Test
    void actualPostgreSqlSupportsImportMessageMakeupAndDeliveryHistory() throws Exception {
        AcademyDataImportService importService = new AcademyDataImportService();
        AcademyImportDAO importDao = new AcademyImportDAO(connections);

        File csv = new File("data/sample_students.csv");
        File xlsx = new File("data/sample_students.xlsx");
        ImportBatch csvBatch = importService.loadAndValidate(csv);
        ImportBatch xlsxBatch = importService.loadAndValidate(xlsx);

        assertTrue(csvBatch.isValid(), csvBatch.validationErrors().toString());
        assertTrue(xlsxBatch.isValid(), xlsxBatch.validationErrors().toString());
        assertEquals(3, csvBatch.rows().size());
        assertEquals(3, xlsxBatch.rows().size());
        importDao.importRows(csvBatch.rows(), csv);
        importDao.importRows(xlsxBatch.rows(), xlsx);

        assertEquals(3, count("student"));
        assertEquals(2, count("classroom"));
        assertEquals(3, count("enrollment"));
        assertEquals(2, count("lesson"));
        assertEquals(3, count("lesson_result"));
        assertEquals(2, count("import_job"));
        assertEquals(6, count("import_row"));

        ImportRow present = csvBatch.rows().get(0);
        MessageGenerationService messageService = new MessageGenerationService(
                new TemplateDAO(connections), new MakeupDAO(connections), new LearningMessageComposer());
        String message = messageService.generateMessage(present, true, true, true);
        assertTrue(message.contains("13/39"));
        assertFalse(message.isBlank());

        MakeupDAO makeupDao = new MakeupDAO(connections);
        List<AbsentStudentRow> absentStudents = makeupDao.findAbsentStudents();
        assertEquals(1, absentStudents.size());
        AbsentStudentRow absent = absentStudents.get(0);
        int targetLessonId = makeupDao.findAvailableSessions(absent.getSessionId()).get(0).getSessionId();
        makeupDao.requestMakeup(absent.getStudentId(), absent.getSessionId(), targetLessonId);
        List<MakeupRequestRow> requests = makeupDao.findRequests();
        assertEquals(1, requests.size());
        assertNotNull(requests.get(0).getTargetDate());
        assertEquals("REQUESTED", requests.get(0).getStatus());
        makeupDao.updateStatus(requests.get(0).getMakeupId(), "COMPLETED");
        assertEquals("COMPLETED", makeupDao.findRequests().get(0).getStatus());

        SendLogDAO sendLogDao = new SendLogDAO(connections);
        sendLogDao.insertSendLog(new MessagePreview(present, message), "parent1@example.invalid", "SENT", null);
        assertEquals(1, sendLogDao.findAll().size());
        assertEquals("SENT", sendLogDao.findAll().get(0).getStatus());
        assertEquals(1, count("delivery_attempt"));
    }

    @Test
    void actualPostgreSqlEnforcesForeignKeysAndRollsBackTransactions() throws Exception {
        long before = count("student");
        try (Connection connection = connections.getConnection()) {
            connection.setAutoCommit(false);
            try (PreparedStatement statement = connection.prepareStatement(
                    "INSERT INTO student(name, school_name) VALUES (?, ?)")) {
                statement.setString(1, "롤백학생");
                statement.setString(2, "가상학교");
                statement.executeUpdate();
            }
            connection.rollback();
        }
        assertEquals(before, count("student"));

        try (Connection connection = connections.getConnection(); PreparedStatement statement = connection.prepareStatement(
                "INSERT INTO delivery_attempt(delivery_job_id, attempt_no, attempt_status) VALUES (999999, 1, 'FAILED')")) {
            assertThrows(SQLException.class, statement::executeUpdate);
        }
    }

    private long count(String table) throws SQLException {
        try (Connection connection = connections.getConnection();
                Statement statement = connection.createStatement();
                ResultSet resultSet = statement.executeQuery("SELECT COUNT(*) FROM " + table)) {
            resultSet.next();
            return resultSet.getLong(1);
        }
    }
}
