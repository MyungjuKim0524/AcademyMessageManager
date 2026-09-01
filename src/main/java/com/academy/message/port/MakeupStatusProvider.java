package com.academy.message.port;

import java.sql.SQLException;
import java.time.LocalDate;

public interface MakeupStatusProvider {
    String findLatestStatus(String studentName, String schoolName, String className,
            LocalDate sessionDate, String testRound) throws SQLException;
}
