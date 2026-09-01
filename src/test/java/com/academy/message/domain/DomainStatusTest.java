package com.academy.message.domain;

import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class DomainStatusTest {
    @Test void acceptsKoreanAndCodeClassTypes() {
        assertEquals(ClassType.REGULAR, ClassType.from("정규"));
        assertEquals(ClassType.EXAM_PREP, ClassType.from("exam_prep"));
    }

    @Test void onlyActiveStudentsCanRequestMakeup() {
        assertTrue(EnrollmentStatus.ACTIVE.canRequestMakeup());
        assertFalse(EnrollmentStatus.PAUSED.canRequestMakeup());
        assertFalse(EnrollmentStatus.WITHDRAWN.canRequestMakeup());
    }

    @Test void rejectsUnknownAchievementGrade() {
        assertThrows(IllegalArgumentException.class, () -> AchievementGrade.from("D"));
    }
}
