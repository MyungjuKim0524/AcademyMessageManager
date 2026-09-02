package com.academy.message.domain;

import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class MakeupGuidancePolicyTest {
    private final MakeupGuidancePolicy policy = new MakeupGuidancePolicy();

    @Test void presentStudentDoesNotReceiveMakeupGuidance() {
        assertEquals("", policy.guidanceFor(AttendanceStatus.PRESENT, MakeupStatus.REQUESTED));
    }

    @Test void completedMakeupIsReportedAsCompleted() {
        assertTrue(policy.guidanceFor(AttendanceStatus.ABSENT, MakeupStatus.COMPLETED).contains("보완하였습니다"));
    }

    @Test void absenceWithoutRequestRequiresFollowUp() {
        assertTrue(policy.guidanceFor(AttendanceStatus.ABSENT, null).contains("확인이 필요"));
    }

    @Test void completedAndCanceledRequestsAreTerminal() {
        assertFalse(MakeupStatus.COMPLETED.canTransitionTo(MakeupStatus.CANCELLED));
        assertFalse(MakeupStatus.CANCELLED.canTransitionTo(MakeupStatus.REQUESTED));
        assertTrue(MakeupStatus.REQUESTED.canTransitionTo(MakeupStatus.COMPLETED));
    }
}
