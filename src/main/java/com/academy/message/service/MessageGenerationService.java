package com.academy.message.service;

import com.academy.message.dao.MakeupDAO;
import com.academy.message.dao.TemplateDAO;
import com.academy.message.model.ImportRow;
import com.academy.message.domain.LearningMessageComposer;
import com.academy.message.domain.MakeupStatus;
import com.academy.message.domain.MessageSections;
import com.academy.message.port.MakeupStatusProvider;
import com.academy.message.port.TemplateProvider;

import java.util.List;

public class MessageGenerationService {
    private final TemplateProvider templateProvider;
    private final MakeupStatusProvider makeupStatusProvider;
    private final LearningMessageComposer composer;

    public MessageGenerationService() {
        this(new TemplateDAO(), new MakeupDAO(), new LearningMessageComposer());
    }

    public MessageGenerationService(TemplateProvider templateProvider, MakeupStatusProvider makeupStatusProvider,
            LearningMessageComposer composer) {
        this.templateProvider = templateProvider;
        this.makeupStatusProvider = makeupStatusProvider;
        this.composer = composer;
    }

    public String generateMessage(ImportRow row, boolean includePreGrade, boolean includeWeeklyGrade, boolean includeTestResult) {
        String template = loadTemplate(row.getClassType());
        return composer.compose(template, row,
                new MessageSections(includePreGrade, includeWeeklyGrade, includeTestResult), findMakeupStatus(row));
    }

    private String loadTemplate(String classType) {
        try {
            return templateProvider.findOrCreateActiveTemplate(classType);
        } catch (Exception ex) {
            return templateProvider.defaultTemplate(classType);
        }
    }

    private MakeupStatus findMakeupStatus(ImportRow row) {
        if (!"결석".equals(row.getAttendance())) return null;
        try {
            String status = makeupStatusProvider.findLatestStatus(
                    row.getStudentName(),
                    row.getSchoolName(),
                    row.getClassName(),
                    row.getSessionDate(),
                    row.getTestRound());
            return MakeupStatus.fromNullable(status);
        } catch (Exception ignored) {
            return null;
        }
    }

    public boolean hasAnyPreGrade(List<ImportRow> rows) {
        return rows.stream().anyMatch(row -> !row.getPreGrade().isBlank());
    }

    public boolean hasAnyWeeklyGrade(List<ImportRow> rows) {
        return rows.stream().anyMatch(row -> !row.getWeeklyGrade().isBlank());
    }

    public boolean hasAnyTestResult(List<ImportRow> rows) {
        return rows.stream().anyMatch(row -> !row.getTestResult().isBlank());
    }

}
