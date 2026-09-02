package com.academy.message.domain;

import com.academy.message.model.ImportRow;
import org.junit.jupiter.api.Test;
import java.time.LocalDate;
import static org.junit.jupiter.api.Assertions.*;

class LearningMessageComposerTest {
    @Test void composesOnlySelectedNonBlankSections() {
        ImportRow row = new ImportRow("A반", "REGULAR", LocalDate.of(2026, 8, 8), "1회",
                "김학생", "코덱스중", "ACTIVE", "결석", "김보호", "parent@example.invalid",
                "A", "", "90/100");
        String template = "{학생명}\n{예습메시지}\n{주간메시지}\n{테스트메시지}\n{보강메시지}";

        String result = new LearningMessageComposer().compose(template, row,
                new MessageSections(true, true, true), MakeupStatus.REQUESTED);

        assertTrue(result.contains("김학생"));
        assertTrue(result.contains("예습 과제를 성실하게"));
        assertTrue(result.contains("테스트 결과는 90/100"));
        assertTrue(result.contains("보강 수업에서 보완할 예정"));
        assertFalse(result.contains("{주간메시지}"));
    }
}
