package com.academy.message.domain;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class TestScoreTest {
    @Test void parsesAndFormatsScore() {
        TestScore score = TestScore.parse("13/39");
        assertEquals(13, score.correctCount());
        assertEquals(39, score.totalCount());
        assertEquals("13/39", score.format());
    }

    @Test void acceptsEmptyAndPerfectScore() {
        assertTrue(TestScore.parse("").isEmpty());
        assertEquals("39/39", new TestScore(39, 39).format());
    }

    @Test void rejectsInvalidScores() {
        assertThrows(IllegalArgumentException.class, () -> TestScore.parse("31/30"));
        assertThrows(IllegalArgumentException.class, () -> TestScore.parse("0/0"));
        assertThrows(IllegalArgumentException.class, () -> TestScore.parse("13점"));
        assertThrows(IllegalArgumentException.class, () -> new TestScore(1, null));
    }
}
