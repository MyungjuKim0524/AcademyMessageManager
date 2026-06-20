package com.academy.message.view;

import com.academy.message.dao.AcademyImportDAO;
import com.academy.message.dao.EnrollmentDAO;
import com.academy.message.dao.MakeupDAO;
import com.academy.message.dao.SendLogDAO;
import com.academy.message.dao.TemplateDAO;
import com.academy.message.model.AbsentStudentRow;
import com.academy.message.model.EmailSendResult;
import com.academy.message.model.EnrollmentStatusRow;
import com.academy.message.model.ImportRow;
import com.academy.message.model.ImportSummary;
import com.academy.message.model.MakeupRequestRow;
import com.academy.message.model.MailCredentials;
import com.academy.message.model.MessagePreview;
import com.academy.message.model.SendLogRow;
import com.academy.message.model.SessionOptionRow;
import com.academy.message.service.DataValidationService;
import com.academy.message.service.EmailSendService;
import com.academy.message.service.MailCredentialStore;
import com.academy.message.service.MessageGenerationService;
import com.academy.message.service.SpreadsheetImportService;
import com.academy.message.util.CsvExportUtil;
import com.academy.message.util.ClassTypeUtil;
import com.academy.message.util.EmailValidator;
import com.academy.message.util.EnrollmentStatusUtil;
import com.academy.message.util.SendStatusUtil;

import javax.swing.BorderFactory;
import javax.swing.JButton;
import javax.swing.JComboBox;
import javax.swing.JFileChooser;
import javax.swing.JFrame;
import javax.swing.JLabel;
import javax.swing.JList;
import javax.swing.JOptionPane;
import javax.swing.JPanel;
import javax.swing.JPasswordField;
import javax.swing.JScrollPane;
import javax.swing.JSplitPane;
import javax.swing.JTabbedPane;
import javax.swing.JTable;
import javax.swing.JTextArea;
import javax.swing.JTextField;
import javax.swing.ListSelectionModel;
import javax.swing.event.ListSelectionEvent;
import javax.swing.table.DefaultTableModel;
import java.awt.BorderLayout;
import java.awt.FlowLayout;
import java.awt.Font;
import java.awt.GridLayout;
import java.io.File;
import java.time.format.DateTimeFormatter;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

public class MainFrame extends JFrame {
    private final SpreadsheetImportService importService = new SpreadsheetImportService();
    private final DataValidationService validationService = new DataValidationService();
    private final MessageGenerationService messageGenerationService = new MessageGenerationService();
    private final AcademyImportDAO academyImportDAO = new AcademyImportDAO();
    private final SendLogDAO sendLogDAO = new SendLogDAO();
    private final TemplateDAO templateDAO = new TemplateDAO();
    private final MakeupDAO makeupDAO = new MakeupDAO();
    private final EnrollmentDAO enrollmentDAO = new EnrollmentDAO();
    private final EmailSendService emailSendService = new EmailSendService();
    private final MailCredentialStore mailCredentialStore = new MailCredentialStore();
    private final DateTimeFormatter dateFormatter = DateTimeFormatter.ofPattern("yyyy-MM-dd");
    private final DateTimeFormatter dateTimeFormatter = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");

    private final DefaultTableModel previewTableModel = new DefaultTableModel();
    private final DefaultTableModel sendTableModel = new DefaultTableModel();
    private final DefaultTableModel logTableModel = new DefaultTableModel();
    private final DefaultTableModel absentTableModel = new DefaultTableModel();
    private final DefaultTableModel sessionOptionTableModel = new DefaultTableModel();
    private final DefaultTableModel makeupRequestTableModel = new DefaultTableModel();
    private final DefaultTableModel enrollmentTableModel = new DefaultTableModel();
    private final JList<String> messageList = new JList<>();
    private final JTextArea messageArea = new JTextArea();
    private final JComboBox<String> templateTypeCombo = new JComboBox<>(new String[] { "정규", "내신 대비" });
    private final JTextArea templateArea = new JTextArea();
    private final JComboBox<String> logStatusCombo = new JComboBox<>(
            new String[] { "전체", "발송 성공", "발송 실패", "발송 제외" });
    private final JTextField logClassField = new JTextField(10);
    private final JTextField logDateField = new JTextField(10);
    private final JTextField makeupFromField = new JTextField(10);
    private final JTextField makeupToField = new JTextField(10);
    private final JComboBox<String> enrollmentStatusCombo = new JComboBox<>(new String[] { "전체", "재원", "휴원", "퇴원" });
    private final JComboBox<String> enrollmentClassCombo = new JComboBox<>();
    private final JTextField enrollmentEmailField = new JTextField(18);
    private final JComboBox<String> enrollmentEditStatusCombo = new JComboBox<>(new String[] { "재원", "휴원", "퇴원" });
    private final JTextField mailUsernameField = new JTextField(24);
    private final JPasswordField mailAppPasswordField = new JPasswordField(24);
    private final JPasswordField mailMasterPasswordField = new JPasswordField(24);
    private final JPasswordField mailMasterConfirmField = new JPasswordField(24);
    private final JLabel statusLabel = new JLabel("CSV 파일을 불러와 주세요.");

    private List<ImportRow> importedRows = new ArrayList<>();
    private List<MessagePreview> messagePreviews = new ArrayList<>();
    private List<SendLogRow> displayedLogRows = new ArrayList<>();
    private List<AbsentStudentRow> absentRows = new ArrayList<>();
    private List<SessionOptionRow> sessionOptionRows = new ArrayList<>();
    private List<MakeupRequestRow> makeupRequestRows = new ArrayList<>();
    private List<EnrollmentStatusRow> enrollmentRows = new ArrayList<>();

    public MainFrame() {
        setTitle("Academy Message Manager");
        setSize(1080, 720);
        setLocationRelativeTo(null);
        setDefaultCloseOperation(JFrame.EXIT_ON_CLOSE);

        JTabbedPane tabs = new JTabbedPane();
        tabs.addTab("데이터 불러오기", createImportPanel());
        tabs.addTab("메시지 생성", createMessagePanel());
        tabs.addTab("이메일 발송", createSendPanel());
        tabs.addTab("발송 내역", createLogPanel());
        tabs.addTab("템플릿 설정", createTemplatePanel());
        tabs.addTab("보강 관리", createMakeupPanel());
        tabs.addTab("학생 관리", createEnrollmentPanel());
        tabs.addTab("메일 설정", createMailSettingsPanel());

        add(tabs, BorderLayout.CENTER);
        add(statusLabel, BorderLayout.SOUTH);
    }

    private JPanel createImportPanel() {
        previewTableModel.setColumnIdentifiers(new String[] {
                "분반명", "수업유형", "수업일자", "시험회차", "이름", "학교명", "출석", "보호자 이메일", "예습과제", "주간과제", "test"
        });

        JButton loadButton = new JButton("Excel/CSV 파일 선택");
        loadButton.addActionListener(event -> loadCsvFile());

        JButton dbUpdateButton = new JButton("불러온 데이터 DB 반영");
        dbUpdateButton.addActionListener(event -> updateDatabase());

        JPanel top = new JPanel(new FlowLayout(FlowLayout.LEFT));
        top.add(loadButton);
        top.add(dbUpdateButton);

        JPanel panel = new JPanel(new BorderLayout());
        panel.add(top, BorderLayout.NORTH);
        panel.add(new JScrollPane(new JTable(previewTableModel)), BorderLayout.CENTER);
        panel.setBorder(BorderFactory.createEmptyBorder(8, 8, 8, 8));
        return panel;
    }

    private JPanel createMessagePanel() {
        messageArea.setLineWrap(true);
        messageArea.setWrapStyleWord(true);
        messageArea.setFont(new Font(Font.SANS_SERIF, Font.PLAIN, 14));
        messageList.setSelectionMode(ListSelectionModel.SINGLE_SELECTION);
        messageList.addListSelectionListener(event -> showSelectedMessage());

        JButton saveButton = new JButton("선택 학생 메시지 저장");
        saveButton.addActionListener(event -> saveCurrentMessage());

        JButton generateButton = new JButton("전체 메시지 생성");
        generateButton.addActionListener(event -> generateMessages());

        JPanel buttons = new JPanel(new FlowLayout(FlowLayout.RIGHT));
        buttons.add(generateButton);
        buttons.add(saveButton);

        JPanel right = new JPanel(new BorderLayout());
        right.add(new JScrollPane(messageArea), BorderLayout.CENTER);
        right.add(buttons, BorderLayout.SOUTH);

        JSplitPane splitPane = new JSplitPane(JSplitPane.HORIZONTAL_SPLIT, new JScrollPane(messageList), right);
        splitPane.setDividerLocation(240);

        JPanel panel = new JPanel(new BorderLayout());
        panel.add(splitPane, BorderLayout.CENTER);
        panel.setBorder(BorderFactory.createEmptyBorder(8, 8, 8, 8));
        return panel;
    }

    private JPanel createSendPanel() {
        sendTableModel.setColumnIdentifiers(new String[] { "선택", "학생명", "보호자 이메일", "수강 상태", "발송 상태" });
        JTable sendTable = new JTable(sendTableModel) {
            @Override
            public Class<?> getColumnClass(int column) {
                return column == 0 ? Boolean.class : String.class;
            }

            @Override
            public boolean isCellEditable(int row, int column) {
                if (column != 0) {
                    return false;
                }
                String status = String.valueOf(getValueAt(row, 4));
                return !"퇴원 제외".equals(status) && !"이메일 오류".equals(status);
            }
        };

        JButton refreshButton = new JButton("발송 대상 새로고침");
        refreshButton.addActionListener(event -> refreshSendTable());

        JButton selectAllButton = new JButton("전체 선택");
        selectAllButton.addActionListener(event -> selectAllSendRows());

        JButton clearAllButton = new JButton("전체 해제");
        clearAllButton.addActionListener(event -> clearAllSendRows());

        JButton sendButton = new JButton("선택 대상 이메일 발송");
        sendButton.addActionListener(event -> sendSelectedEmails(sendTable));

        JPanel top = new JPanel(new FlowLayout(FlowLayout.LEFT));
        top.add(refreshButton);
        top.add(selectAllButton);
        top.add(clearAllButton);
        top.add(sendButton);

        JPanel panel = new JPanel(new BorderLayout());
        panel.add(top, BorderLayout.NORTH);
        panel.add(new JScrollPane(sendTable), BorderLayout.CENTER);
        panel.setBorder(BorderFactory.createEmptyBorder(8, 8, 8, 8));
        return panel;
    }

    private JPanel createLogPanel() {
        logTableModel.setColumnIdentifiers(new String[] { "학생명", "학교", "이메일", "상태", "발송 시간", "실패 사유" });
        JTable logTable = new JTable(logTableModel);
        JButton refreshButton = new JButton("DB 로그 새로고침");
        refreshButton.addActionListener(event -> refreshLogTableFromDatabase());

        JButton searchButton = new JButton("발송 로그 검색");
        searchButton.addActionListener(event -> searchLogTable());

        JButton retryButton = new JButton("선택 실패 건 재시도");
        retryButton.addActionListener(event -> retrySelectedFailedLog(logTable));

        JButton exportButton = new JButton("전체 로그 CSV 저장");
        exportButton.addActionListener(event -> exportLogCsv());

        JPanel top = new JPanel(new FlowLayout(FlowLayout.LEFT));
        top.add(new JLabel("상태"));
        top.add(logStatusCombo);
        top.add(new JLabel("분반"));
        top.add(logClassField);
        top.add(new JLabel("날짜"));
        top.add(logDateField);
        top.add(searchButton);
        top.add(refreshButton);
        top.add(retryButton);
        top.add(exportButton);

        JPanel panel = new JPanel(new BorderLayout());
        panel.add(top, BorderLayout.NORTH);
        panel.add(new JScrollPane(logTable), BorderLayout.CENTER);
        panel.setBorder(BorderFactory.createEmptyBorder(8, 8, 8, 8));
        return panel;
    }

    private JPanel createTemplatePanel() {
        templateArea.setLineWrap(true);
        templateArea.setWrapStyleWord(true);
        templateArea.setFont(new Font(Font.SANS_SERIF, Font.PLAIN, 14));
        templateTypeCombo.addActionListener(event -> loadTemplate());

        JButton saveButton = new JButton("선택 템플릿 저장");
        saveButton.addActionListener(event -> saveTemplate());

        JPanel top = new JPanel(new FlowLayout(FlowLayout.LEFT));
        top.add(templateTypeCombo);
        top.add(saveButton);

        JPanel panel = new JPanel(new BorderLayout());
        panel.add(top, BorderLayout.NORTH);
        panel.add(new JScrollPane(templateArea), BorderLayout.CENTER);
        panel.setBorder(BorderFactory.createEmptyBorder(8, 8, 8, 8));

        loadTemplate();
        return panel;
    }

    private JPanel createMakeupPanel() {
        absentTableModel.setColumnIdentifiers(new String[] { "학생명", "학교", "원 수업", "날짜", "회차", "보강 상태" });
        sessionOptionTableModel.setColumnIdentifiers(new String[] { "보강 수업", "유형", "날짜", "회차" });
        makeupRequestTableModel.setColumnIdentifiers(new String[] { "ID", "학생명", "학교", "원 수업", "원 날짜", "보강 수업", "보강 날짜", "상태" });

        JTable absentTable = new JTable(absentTableModel);
        JTable sessionTable = new JTable(sessionOptionTableModel);
        JTable requestTable = new JTable(makeupRequestTableModel);
        absentTable.setSelectionMode(ListSelectionModel.SINGLE_SELECTION);
        sessionTable.setSelectionMode(ListSelectionModel.SINGLE_SELECTION);
        requestTable.setSelectionMode(ListSelectionModel.SINGLE_SELECTION);
        absentTable.getSelectionModel().addListSelectionListener(event -> loadSessionOptionsForSelectedAbsent(event, absentTable));

        JButton refreshButton = new JButton("보강 목록 새로고침");
        refreshButton.addActionListener(event -> refreshMakeupTables());

        JButton requestButton = new JButton("보강 신청");
        requestButton.addActionListener(event -> requestSelectedMakeup(absentTable, sessionTable));

        JButton completeButton = new JButton("보강 완료");
        completeButton.addActionListener(event -> updateSelectedMakeupStatus(requestTable, "COMPLETED"));

        JButton cancelButton = new JButton("보강 취소");
        cancelButton.addActionListener(event -> updateSelectedMakeupStatus(requestTable, "CANCELED"));

        JPanel top = new JPanel(new FlowLayout(FlowLayout.LEFT));
        top.add(new JLabel("보강 시작일"));
        top.add(makeupFromField);
        top.add(new JLabel("보강 종료일"));
        top.add(makeupToField);
        top.add(refreshButton);
        top.add(requestButton);
        top.add(completeButton);
        top.add(cancelButton);

        JSplitPane leftSplit = new JSplitPane(JSplitPane.VERTICAL_SPLIT,
                new JScrollPane(absentTable), new JScrollPane(sessionTable));
        leftSplit.setDividerLocation(220);

        JSplitPane mainSplit = new JSplitPane(JSplitPane.HORIZONTAL_SPLIT,
                leftSplit, new JScrollPane(requestTable));
        mainSplit.setDividerLocation(560);

        JPanel panel = new JPanel(new BorderLayout());
        panel.add(top, BorderLayout.NORTH);
        panel.add(mainSplit, BorderLayout.CENTER);
        panel.setBorder(BorderFactory.createEmptyBorder(8, 8, 8, 8));
        refreshMakeupTables();
        return panel;
    }

    private JPanel createEnrollmentPanel() {
        enrollmentTableModel.setColumnIdentifiers(new String[] { "분반", "유형", "학생명", "학교", "이메일", "상태", "시작일", "종료일" });
        JTable table = new JTable(enrollmentTableModel);
        table.setSelectionMode(ListSelectionModel.SINGLE_SELECTION);
        table.getSelectionModel().addListSelectionListener(event -> loadSelectedEnrollmentToEditor(event, table));

        JButton searchButton = new JButton("학생 목록 조회");
        searchButton.addActionListener(event -> refreshEnrollmentTable());

        JButton saveButton = new JButton("수정 사항 DB 반영");
        saveButton.addActionListener(event -> saveSelectedEnrollment(table));

        refreshEnrollmentClassCombo();

        JPanel top = new JPanel(new FlowLayout(FlowLayout.LEFT));
        top.add(new JLabel("분반"));
        top.add(enrollmentClassCombo);
        top.add(new JLabel("상태"));
        top.add(enrollmentStatusCombo);
        top.add(searchButton);
        top.add(new JLabel("이메일"));
        top.add(enrollmentEmailField);
        top.add(new JLabel("변경 상태"));
        top.add(enrollmentEditStatusCombo);
        top.add(saveButton);

        JPanel panel = new JPanel(new BorderLayout());
        panel.add(top, BorderLayout.NORTH);
        panel.add(new JScrollPane(table), BorderLayout.CENTER);
        panel.setBorder(BorderFactory.createEmptyBorder(8, 8, 8, 8));
        refreshEnrollmentTable();
        return panel;
    }

    private JPanel createMailSettingsPanel() {
        JPanel form = new JPanel(new GridLayout(0, 2, 8, 8));
        form.add(new JLabel("Gmail 주소"));
        form.add(mailUsernameField);
        form.add(new JLabel("Gmail 앱 비밀번호"));
        form.add(mailAppPasswordField);
        form.add(new JLabel("마스터 암호 (8자 이상)"));
        form.add(mailMasterPasswordField);
        form.add(new JLabel("마스터 암호 확인"));
        form.add(mailMasterConfirmField);
        form.add(new JLabel("암호화 파일"));
        form.add(new JLabel(mailCredentialStore.getCredentialPath().toString()));

        JButton saveButton = new JButton("메일 계정 암호화 저장");
        saveButton.addActionListener(event -> saveEncryptedMailSettings());

        JPanel buttons = new JPanel(new FlowLayout(FlowLayout.RIGHT));
        buttons.add(saveButton);

        JPanel panel = new JPanel(new BorderLayout(8, 8));
        panel.add(form, BorderLayout.NORTH);
        panel.add(buttons, BorderLayout.SOUTH);
        panel.setBorder(BorderFactory.createEmptyBorder(16, 16, 16, 16));
        return panel;
    }

    private void loadCsvFile() {
        JFileChooser chooser = new JFileChooser();
        chooser.setCurrentDirectory(new File("data"));
        int result = chooser.showOpenDialog(this);
        if (result != JFileChooser.APPROVE_OPTION) {
            return;
        }

        try {
            importedRows = importService.importFile(chooser.getSelectedFile());
            List<String> errors = validationService.validate(importedRows);
            fillPreviewTable();
            if (errors.isEmpty()) {
                statusLabel.setText(importedRows.size() + "건을 불러왔습니다. 검증 오류 없음.");
            } else {
                JOptionPane.showMessageDialog(this, String.join("\n", errors), "검증 오류", JOptionPane.WARNING_MESSAGE);
                statusLabel.setText(importedRows.size() + "건을 불러왔고, 검증 오류 " + errors.size() + "건이 있습니다.");
            }
        } catch (Exception ex) {
            JOptionPane.showMessageDialog(this, ex.getMessage(), "파일 읽기 실패", JOptionPane.ERROR_MESSAGE);
        }
    }

    private void fillPreviewTable() {
        previewTableModel.setRowCount(0);
        for (ImportRow row : importedRows) {
            previewTableModel.addRow(new Object[] {
                    row.getClassName(), ClassTypeUtil.toDisplayName(row.getClassType()),
                    dateFormatter.format(row.getSessionDate()), row.getTestRound(),
                    row.getStudentName(), row.getSchoolName(), row.getAttendance(), row.getParentEmail(),
                    row.getPreGrade(), row.getWeeklyGrade(), row.getTestResult()
            });
        }
    }

    private void generateMessages() {
        if (importedRows.isEmpty()) {
            JOptionPane.showMessageDialog(this, "먼저 CSV 파일을 불러와 주세요.");
            return;
        }
        boolean includePreGrade = messageGenerationService.hasAnyPreGrade(importedRows);
        boolean includeWeeklyGrade = messageGenerationService.hasAnyWeeklyGrade(importedRows);
        boolean includeTestResult = messageGenerationService.hasAnyTestResult(importedRows);

        messagePreviews = importedRows.stream()
                .map(row -> new MessagePreview(row, messageGenerationService.generateMessage(row, includePreGrade, includeWeeklyGrade, includeTestResult)))
                .collect(Collectors.toList());
        messageList.setListData(messagePreviews.stream()
                .map(preview -> preview.getRow().getStudentName() + " / " + preview.getRow().getClassName())
                .toArray(String[]::new));
        if (!messagePreviews.isEmpty()) {
            messageList.setSelectedIndex(0);
        }
        refreshSendTable();
        statusLabel.setText(messagePreviews.size() + "건의 메시지를 생성했습니다.");
    }

    private void updateDatabase() {
        if (importedRows.isEmpty()) {
            JOptionPane.showMessageDialog(this, "먼저 Excel 또는 CSV 파일을 불러와 주세요.");
            return;
        }
        List<String> errors = validationService.validate(importedRows);
        if (!errors.isEmpty()) {
            JOptionPane.showMessageDialog(this, String.join("\n", errors), "검증 오류", JOptionPane.WARNING_MESSAGE);
            return;
        }

        int confirm = JOptionPane.showConfirmDialog(this,
                importedRows.size() + "건을 DB에 반영할까요?",
                "DB 업데이트 확인",
                JOptionPane.YES_NO_OPTION);
        if (confirm != JOptionPane.YES_OPTION) {
            return;
        }

        try {
            ImportSummary summary = academyImportDAO.importRows(importedRows);
            JOptionPane.showMessageDialog(this, summary.toDisplayText(), "DB 업데이트 완료", JOptionPane.INFORMATION_MESSAGE);
            statusLabel.setText("DB 업데이트를 완료했습니다.");
        } catch (Exception ex) {
            JOptionPane.showMessageDialog(this, ex.getMessage(), "DB 업데이트 실패", JOptionPane.ERROR_MESSAGE);
            statusLabel.setText("DB 업데이트 실패: " + ex.getMessage());
        }
    }

    private void showSelectedMessage() {
        int index = messageList.getSelectedIndex();
        if (index >= 0 && index < messagePreviews.size()) {
            messageArea.setText(messagePreviews.get(index).getContent());
            messageArea.setCaretPosition(0);
        }
    }

    private void saveCurrentMessage() {
        int index = messageList.getSelectedIndex();
        if (index >= 0 && index < messagePreviews.size()) {
            messagePreviews.get(index).setContent(messageArea.getText());
            statusLabel.setText("메시지 수정 내용을 저장했습니다.");
        }
    }

    private void selectAllSendRows() {
        int selectedCount = 0;
        for (int i = 0; i < sendTableModel.getRowCount(); i++) {
            String sendStatus = String.valueOf(sendTableModel.getValueAt(i, 4));
            boolean eligible = !"퇴원 제외".equals(sendStatus) && !"이메일 오류".equals(sendStatus);
            sendTableModel.setValueAt(eligible, i, 0);
            if (eligible) {
                selectedCount++;
            }
        }
        statusLabel.setText("발송 가능한 학생 " + selectedCount + "명을 선택했습니다.");
    }

    private void clearAllSendRows() {
        for (int i = 0; i < sendTableModel.getRowCount(); i++) {
            sendTableModel.setValueAt(false, i, 0);
        }
        statusLabel.setText("이메일 발송 대상을 모두 해제했습니다.");
    }

    private void refreshSendTable() {
        sendTableModel.setRowCount(0);
        for (MessagePreview preview : messagePreviews) {
            String enrollmentStatus = findEnrollmentStatusForPreview(preview);
            String currentEmail = findCurrentEmailForPreview(preview);
            boolean excluded = isWithdrawn(enrollmentStatus) || isBlank(currentEmail)
                    || !EmailValidator.isValid(currentEmail);
            if (excluded) {
                preview.setSelectedToSend(false);
            }
            sendTableModel.addRow(new Object[] {
                    preview.isSelectedToSend() && !excluded,
                    preview.getRow().getStudentName(),
                    currentEmail,
                    displayStatus(enrollmentStatus),
                    excluded ? excludedReason(currentEmail, enrollmentStatus)
                            : SendStatusUtil.toDisplayName(preview.getStatus())
            });
        }
    }

    private void sendSelectedEmails(JTable sendTable) {
        int selectedCount = 0;
        for (int i = 0; i < sendTableModel.getRowCount(); i++) {
            if (Boolean.TRUE.equals(sendTableModel.getValueAt(i, 0))) {
                selectedCount++;
            }
        }
        if (selectedCount == 0) {
            JOptionPane.showMessageDialog(this, "이메일을 발송할 학생을 선택해 주세요.");
            return;
        }
        int confirmation = JOptionPane.showConfirmDialog(
                this,
                "선택한 " + selectedCount + "명에게 이메일을 발송하시겠습니까?",
                "이메일 발송 확인",
                JOptionPane.YES_NO_OPTION);
        if (confirmation != JOptionPane.YES_OPTION) {
            return;
        }
        char[] masterPassword = requestMailMasterPassword();
        if (masterPassword == null) {
            return;
        }
        for (int i = 0; i < sendTableModel.getRowCount(); i++) {
            boolean selected = Boolean.TRUE.equals(sendTableModel.getValueAt(i, 0));
            if (!selected) {
                continue;
            }
            MessagePreview preview = messagePreviews.get(i);
            String enrollmentStatus = findEnrollmentStatusForPreview(preview);
            String currentEmail = findCurrentEmailForPreview(preview);
            if (isWithdrawn(enrollmentStatus)) {
                preview.setStatus("SKIPPED");
                saveAndAppendLog(preview, currentEmail, "SKIPPED", "퇴원 상태 학생");
            } else if (!EmailValidator.isValid(currentEmail)) {
                preview.setStatus("SKIPPED");
                saveAndAppendLog(preview, currentEmail, "SKIPPED", "이메일 없음 또는 형식 오류");
            } else {
                preview.setSelectedToSend(true);
                EmailSendResult result = emailSendService.sendEmail(
                        currentEmail,
                        "[JAVA 학원] " + preview.getRow().getStudentName() + " 학생 학습 현황 안내",
                        preview.getContent(),
                        masterPassword);
                if (result.isSuccess()) {
                    preview.setStatus("SENT");
                    saveAndAppendLog(preview, currentEmail, "SENT", "");
                } else {
                    preview.setStatus("FAILED");
                    saveAndAppendLog(preview, currentEmail, "FAILED", result.getErrorMessage());
                }
            }
        }
        Arrays.fill(masterPassword, '\0');
        refreshSendTable();
        statusLabel.setText("선택 대상 이메일 발송 시도를 완료했습니다.");
    }

    private String findEnrollmentStatusForPreview(MessagePreview preview) {
        try {
            String status = enrollmentDAO.findEnrollmentStatus(
                    preview.getRow().getStudentName(),
                    preview.getRow().getSchoolName(),
                    preview.getRow().getClassName());
            if (status != null && !status.isBlank()) {
                return status.trim();
            }
        } catch (Exception ex) {
            // Use the imported value when the student has not been saved to DB yet.
        }
        return preview.getRow().getEnrollmentStatus() == null
                ? ""
                : preview.getRow().getEnrollmentStatus().trim();
    }

    private String findCurrentEmailForPreview(MessagePreview preview) {
        try {
            String email = enrollmentDAO.findParentEmail(
                    preview.getRow().getStudentName(),
                    preview.getRow().getSchoolName());
            if (email != null && !email.isBlank()) {
                return email.trim();
            }
        } catch (Exception ex) {
            // Use the imported value when the student has not been saved to DB yet.
        }
        return preview.getRow().getParentEmail() == null
                ? ""
                : preview.getRow().getParentEmail().trim();
    }

    private boolean isWithdrawn(String status) {
        return "WITHDRAWN".equalsIgnoreCase(status == null ? "" : status.trim());
    }

    private boolean isBlank(String value) {
        return value == null || value.isBlank();
    }

    private String displayStatus(String status) {
        return isBlank(status) ? "미확인" : EnrollmentStatusUtil.toDisplayName(status.trim());
    }

    private String excludedReason(String email, String enrollmentStatus) {
        if (isWithdrawn(enrollmentStatus)) {
            return "퇴원 제외";
        }
        if (!EmailValidator.isValid(email)) {
            return "이메일 오류";
        }
        return "READY";
    }

    private void saveAndAppendLog(MessagePreview preview, String status, String error) {
        saveAndAppendLog(preview, preview.getRow().getParentEmail(), status, error);
    }

    private void saveAndAppendLog(MessagePreview preview, String parentEmail, String status, String error) {
        try {
            sendLogDAO.insertSendLog(preview, parentEmail, status, error);
            appendLog(preview, parentEmail, error);
        } catch (Exception ex) {
            preview.setStatus("FAILED");
            appendLog(preview, ex.getMessage());
            JOptionPane.showMessageDialog(this, ex.getMessage(), "발송 로그 저장 실패", JOptionPane.ERROR_MESSAGE);
        }
    }

    private void appendLog(MessagePreview preview, String error) {
        appendLog(preview, preview.getRow().getParentEmail(), error);
    }

    private void appendLog(MessagePreview preview, String parentEmail, String error) {
        logTableModel.addRow(new Object[] {
                preview.getRow().getStudentName(),
                preview.getRow().getSchoolName(),
                parentEmail,
                SendStatusUtil.toDisplayName(preview.getStatus()),
                dateTimeFormatter.format(java.time.LocalDateTime.now()),
                error
        });
    }

    private void refreshLogTableFromDatabase() {
        try {
            displayedLogRows = sendLogDAO.findAll();
            fillLogTable(displayedLogRows);
            statusLabel.setText("DB 발송 로그를 불러왔습니다.");
        } catch (Exception ex) {
            JOptionPane.showMessageDialog(this, ex.getMessage(), "발송 로그 조회 실패", JOptionPane.ERROR_MESSAGE);
        }
    }

    private void searchLogTable() {
        try {
            LocalDate sentDate = parseOptionalDate(logDateField.getText());
            displayedLogRows = sendLogDAO.searchLogs(
                    SendStatusUtil.toCode(String.valueOf(logStatusCombo.getSelectedItem())),
                    logClassField.getText(),
                    sentDate);
            fillLogTable(displayedLogRows);
            statusLabel.setText("발송 로그 검색 결과 " + displayedLogRows.size() + "건을 불러왔습니다.");
        } catch (Exception ex) {
            JOptionPane.showMessageDialog(this, ex.getMessage(), "발송 로그 검색 실패", JOptionPane.ERROR_MESSAGE);
        }
    }

    private LocalDate parseOptionalDate(String text) {
        if (text == null || text.isBlank()) {
            return null;
        }
        return LocalDate.parse(text.trim());
    }

    private void fillLogTable(List<SendLogRow> logs) {
        logTableModel.setRowCount(0);
        for (SendLogRow log : logs) {
            logTableModel.addRow(new Object[] {
                    log.getStudentName(),
                    log.getSchoolName(),
                    log.getParentEmail(),
                    SendStatusUtil.toDisplayName(log.getStatus()),
                    log.getSentAt() == null ? "" : dateTimeFormatter.format(log.getSentAt()),
                    log.getErrorMessage() == null ? "" : log.getErrorMessage()
            });
        }
    }

    private void retrySelectedFailedLog(JTable logTable) {
        int selected = logTable.getSelectedRow();
        if (selected < 0 || selected >= displayedLogRows.size()) {
            JOptionPane.showMessageDialog(this, "재시도할 실패 로그를 선택해 주세요.");
            return;
        }
        SendLogRow log = displayedLogRows.get(selected);
        if (!"FAILED".equals(log.getStatus())) {
            JOptionPane.showMessageDialog(this, "FAILED 상태인 로그만 재시도할 수 있습니다.");
            return;
        }
        try {
            if (!EmailValidator.isValid(log.getParentEmail())) {
                JOptionPane.showMessageDialog(this, "이메일 주소가 없거나 형식이 올바르지 않습니다.");
                return;
            }
            char[] masterPassword = requestMailMasterPassword();
            if (masterPassword == null) {
                return;
            }
            EmailSendResult result = emailSendService.sendEmail(
                    log.getParentEmail(),
                    "[JAVA 학원] 학습 현황 안내 재발송",
                    log.getMessageContent(),
                    masterPassword);
            Arrays.fill(masterPassword, '\0');
            if (result.isSuccess()) {
                sendLogDAO.markRetriedAsSent(log.getLogId());
            } else {
                sendLogDAO.markFailed(log.getLogId(), result.getErrorMessage());
                JOptionPane.showMessageDialog(this, result.getErrorMessage(), "재발송 실패", JOptionPane.ERROR_MESSAGE);
            }
            refreshLogTableFromDatabase();
            statusLabel.setText("선택한 실패 건을 재시도 처리했습니다.");
        } catch (Exception ex) {
            JOptionPane.showMessageDialog(this, ex.getMessage(), "재시도 실패", JOptionPane.ERROR_MESSAGE);
        }
    }

    private void exportLogCsv() {
        try {
            List<SendLogRow> logs = sendLogDAO.findAll();
            if (logs.isEmpty()) {
                JOptionPane.showMessageDialog(this, "저장할 발송 로그가 없습니다.");
                return;
            }

            JFileChooser chooser = new JFileChooser();
            chooser.setSelectedFile(new File("send_logs.csv"));
            int result = chooser.showSaveDialog(this);
            if (result != JFileChooser.APPROVE_OPTION) {
                return;
            }

            File file = chooser.getSelectedFile();
            if (!file.getName().toLowerCase().endsWith(".csv")) {
                file = new File(file.getParentFile(), file.getName() + ".csv");
            }
            CsvExportUtil.exportSendLogs(file, logs);
            JOptionPane.showMessageDialog(this, "CSV 저장 완료:\n" + file.getAbsolutePath());
            statusLabel.setText("발송 로그 CSV를 저장했습니다.");
        } catch (Exception ex) {
            JOptionPane.showMessageDialog(this, ex.getMessage(), "CSV 저장 실패", JOptionPane.ERROR_MESSAGE);
        }
    }

    private void loadTemplate() {
        try {
            templateArea.setText(templateDAO.findOrCreateActiveTemplate(selectedTemplateType()));
            templateArea.setCaretPosition(0);
            statusLabel.setText(selectedTemplateDisplayName() + " 템플릿을 불러왔습니다.");
        } catch (Exception ex) {
            templateArea.setText(templateDAO.defaultTemplate(selectedTemplateType()));
            JOptionPane.showMessageDialog(this, ex.getMessage(), "템플릿 불러오기 실패", JOptionPane.WARNING_MESSAGE);
        }
    }

    private void saveTemplate() {
        try {
            templateDAO.saveTemplate(selectedTemplateType(), templateArea.getText());
            statusLabel.setText(selectedTemplateDisplayName() + " 템플릿을 저장했습니다.");
            JOptionPane.showMessageDialog(this, "템플릿을 저장했습니다.");
        } catch (Exception ex) {
            JOptionPane.showMessageDialog(this, ex.getMessage(), "템플릿 저장 실패", JOptionPane.ERROR_MESSAGE);
        }
    }

    private String selectedTemplateType() {
        return ClassTypeUtil.toCode(String.valueOf(templateTypeCombo.getSelectedItem()));
    }

    private String selectedTemplateDisplayName() {
        return String.valueOf(templateTypeCombo.getSelectedItem());
    }

    private void refreshMakeupTables() {
        try {
            absentRows = makeupDAO.findAbsentStudents();
            makeupRequestRows = makeupDAO.findRequests();
            fillAbsentTable();
            fillMakeupRequestTable();
            sessionOptionRows = new ArrayList<>();
            fillSessionOptionTable();
            statusLabel.setText("보강 관리 데이터를 불러왔습니다.");
        } catch (Exception ex) {
            JOptionPane.showMessageDialog(this, ex.getMessage(), "보강 데이터 조회 실패", JOptionPane.ERROR_MESSAGE);
        }
    }

    private void fillAbsentTable() {
        absentTableModel.setRowCount(0);
        for (AbsentStudentRow row : absentRows) {
            absentTableModel.addRow(new Object[] {
                    row.getStudentName(),
                    row.getSchoolName(),
                    row.getClassName(),
                    dateFormatter.format(row.getSessionDate()),
                    row.getTestRound(),
                    row.getMakeupStatus() == null ? "미신청" : row.getMakeupStatus()
            });
        }
    }

    private void fillSessionOptionTable() {
        sessionOptionTableModel.setRowCount(0);
        for (SessionOptionRow row : sessionOptionRows) {
            sessionOptionTableModel.addRow(new Object[] {
                    row.getClassName(),
                    ClassTypeUtil.toDisplayName(row.getClassType()),
                    dateFormatter.format(row.getSessionDate()),
                    row.getTestRound()
            });
        }
    }

    private void fillMakeupRequestTable() {
        makeupRequestTableModel.setRowCount(0);
        for (MakeupRequestRow row : makeupRequestRows) {
            makeupRequestTableModel.addRow(new Object[] {
                    row.getMakeupId(),
                    row.getStudentName(),
                    row.getSchoolName(),
                    row.getOriginalClassName(),
                    dateFormatter.format(row.getOriginalDate()),
                    row.getTargetClassName() == null ? "" : row.getTargetClassName(),
                    row.getTargetDate() == null ? "" : dateFormatter.format(row.getTargetDate()),
                    row.getStatus()
            });
        }
    }

    private void loadSessionOptionsForSelectedAbsent(ListSelectionEvent event, JTable absentTable) {
        if (event.getValueIsAdjusting()) {
            return;
        }
        int selected = absentTable.getSelectedRow();
        if (selected < 0 || selected >= absentRows.size()) {
            return;
        }
        try {
            sessionOptionRows = makeupDAO.findAvailableSessions(
                    absentRows.get(selected).getSessionId(),
                    parseOptionalDate(makeupFromField.getText()),
                    parseOptionalDate(makeupToField.getText()));
            fillSessionOptionTable();
        } catch (Exception ex) {
            JOptionPane.showMessageDialog(this, ex.getMessage(), "보강 가능 수업 조회 실패", JOptionPane.ERROR_MESSAGE);
        }
    }

    private void requestSelectedMakeup(JTable absentTable, JTable sessionTable) {
        int absentIndex = absentTable.getSelectedRow();
        int sessionIndex = sessionTable.getSelectedRow();
        if (absentIndex < 0 || sessionIndex < 0) {
            JOptionPane.showMessageDialog(this, "결석 학생과 보강 수업을 각각 선택해 주세요.");
            return;
        }
        try {
            AbsentStudentRow absent = absentRows.get(absentIndex);
            SessionOptionRow target = sessionOptionRows.get(sessionIndex);
            makeupDAO.requestMakeup(absent.getStudentId(), absent.getSessionId(), target.getSessionId());
            refreshMakeupTables();
            statusLabel.setText("보강 신청을 등록했습니다.");
        } catch (Exception ex) {
            JOptionPane.showMessageDialog(this, ex.getMessage(), "보강 신청 실패", JOptionPane.ERROR_MESSAGE);
        }
    }

    private void updateSelectedMakeupStatus(JTable requestTable, String status) {
        int selected = requestTable.getSelectedRow();
        if (selected < 0 || selected >= makeupRequestRows.size()) {
            JOptionPane.showMessageDialog(this, "보강 신청 내역을 선택해 주세요.");
            return;
        }
        try {
            makeupDAO.updateStatus(makeupRequestRows.get(selected).getMakeupId(), status);
            refreshMakeupTables();
            statusLabel.setText("보강 상태를 " + status + "(으)로 변경했습니다.");
        } catch (Exception ex) {
            JOptionPane.showMessageDialog(this, ex.getMessage(), "보강 상태 변경 실패", JOptionPane.ERROR_MESSAGE);
        }
    }

    private void refreshEnrollmentTable() {
        try {
            String selectedClass = String.valueOf(enrollmentClassCombo.getSelectedItem());
            if ("ALL".equals(selectedClass)) {
                selectedClass = "";
            }
            String selectedStatus = String.valueOf(enrollmentStatusCombo.getSelectedItem());
            selectedStatus = "전체".equals(selectedStatus) ? "ALL" : EnrollmentStatusUtil.toCode(selectedStatus);
            enrollmentRows = enrollmentDAO.search(
                    selectedStatus,
                    selectedClass);
            enrollmentTableModel.setRowCount(0);
            for (EnrollmentStatusRow row : enrollmentRows) {
                enrollmentTableModel.addRow(new Object[] {
                        row.getClassName(),
                        ClassTypeUtil.toDisplayName(row.getClassType()),
                        row.getStudentName(),
                        row.getSchoolName(),
                        row.getParentEmail(),
                        EnrollmentStatusUtil.toDisplayName(row.getStatus()),
                        row.getStartDate() == null ? "" : dateFormatter.format(row.getStartDate()),
                        row.getEndDate() == null ? "" : dateFormatter.format(row.getEndDate())
                });
            }
            statusLabel.setText("학생 관리 목록 " + enrollmentRows.size() + "건을 조회했습니다.");
        } catch (Exception ex) {
            JOptionPane.showMessageDialog(this, ex.getMessage(), "학생 관리 조회 실패", JOptionPane.ERROR_MESSAGE);
        }
    }

    private void refreshEnrollmentClassCombo() {
        try {
            enrollmentClassCombo.removeAllItems();
            enrollmentClassCombo.addItem("ALL");
            for (String className : enrollmentDAO.findClassNames()) {
                enrollmentClassCombo.addItem(className);
            }
        } catch (Exception ex) {
            enrollmentClassCombo.removeAllItems();
            enrollmentClassCombo.addItem("ALL");
        }
    }

    private void loadSelectedEnrollmentToEditor(ListSelectionEvent event, JTable table) {
        if (event.getValueIsAdjusting()) {
            return;
        }
        int selected = table.getSelectedRow();
        if (selected < 0 || selected >= enrollmentRows.size()) {
            return;
        }
        EnrollmentStatusRow row = enrollmentRows.get(selected);
        enrollmentEmailField.setText(row.getParentEmail() == null ? "" : row.getParentEmail());
        enrollmentEditStatusCombo.setSelectedItem(EnrollmentStatusUtil.toDisplayName(row.getStatus()));
    }

    private void saveSelectedEnrollment(JTable table) {
        int selected = table.getSelectedRow();
        if (selected < 0 || selected >= enrollmentRows.size()) {
            JOptionPane.showMessageDialog(this, "수정할 학생을 선택해 주세요.");
            return;
        }
        EnrollmentStatusRow row = enrollmentRows.get(selected);
        String newStatus = EnrollmentStatusUtil.toCode(String.valueOf(enrollmentEditStatusCombo.getSelectedItem()));
        String message = row.getStudentName() + " 학생의 수정 사항을 DB에 반영하시겠습니까?";
        if ("WITHDRAWN".equals(newStatus)) {
            message += "\n퇴원 처리 시 미완료 보강 신청은 자동으로 CANCELED 처리됩니다.";
        }
        int confirm = JOptionPane.showConfirmDialog(this, message, "DB 반영 확인", JOptionPane.YES_NO_OPTION);
        if (confirm != JOptionPane.YES_OPTION) {
            return;
        }
        try {
            enrollmentDAO.updateStudentManagement(
                    row.getEnrollmentId(),
                    row.getStudentId(),
                    enrollmentEmailField.getText(),
                    newStatus);
            refreshEnrollmentTable();
            refreshMakeupTables();
            statusLabel.setText("학생 관리 수정 사항을 DB에 반영했습니다.");
        } catch (Exception ex) {
            JOptionPane.showMessageDialog(this, ex.getMessage(), "학생 관리 저장 실패", JOptionPane.ERROR_MESSAGE);
        }
    }

    private void saveEncryptedMailSettings() {
        char[] masterPassword = mailMasterPasswordField.getPassword();
        char[] masterConfirm = mailMasterConfirmField.getPassword();
        char[] appPassword = mailAppPasswordField.getPassword();
        try {
            if (!Arrays.equals(masterPassword, masterConfirm)) {
                JOptionPane.showMessageDialog(this, "마스터 암호 확인값이 일치하지 않습니다.");
                return;
            }
            String username = mailUsernameField.getText().trim();
            if (!EmailValidator.isValid(username)) {
                JOptionPane.showMessageDialog(this, "Gmail 주소 형식이 올바르지 않습니다.");
                return;
            }
            if (appPassword.length == 0) {
                JOptionPane.showMessageDialog(this, "Gmail 앱 비밀번호를 입력해 주세요.");
                return;
            }

            mailCredentialStore.save(
                    new MailCredentials(username, new String(appPassword)),
                    masterPassword);
            mailAppPasswordField.setText("");
            mailMasterPasswordField.setText("");
            mailMasterConfirmField.setText("");
            JOptionPane.showMessageDialog(this,
                    "메일 계정을 암호화해 저장했습니다.\n마스터 암호를 잊으면 복구할 수 없습니다.");
            statusLabel.setText("암호화된 메일 계정 설정을 저장했습니다.");
        } catch (Exception ex) {
            JOptionPane.showMessageDialog(this, ex.getMessage(), "메일 설정 저장 실패", JOptionPane.ERROR_MESSAGE);
        } finally {
            Arrays.fill(masterPassword, '\0');
            Arrays.fill(masterConfirm, '\0');
            Arrays.fill(appPassword, '\0');
        }
    }

    private char[] requestMailMasterPassword() {
        if (!mailCredentialStore.exists()) {
            JOptionPane.showMessageDialog(this, "먼저 메일 설정 탭에서 계정을 암호화해 저장해 주세요.");
            return null;
        }
        JPasswordField passwordField = new JPasswordField(20);
        int result = JOptionPane.showConfirmDialog(
                this,
                passwordField,
                "메일 계정 마스터 암호",
                JOptionPane.OK_CANCEL_OPTION,
                JOptionPane.PLAIN_MESSAGE);
        if (result != JOptionPane.OK_OPTION) {
            return null;
        }
        return passwordField.getPassword();
    }
}
