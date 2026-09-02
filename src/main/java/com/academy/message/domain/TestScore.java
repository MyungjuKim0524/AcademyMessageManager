package com.academy.message.domain;

/** Nullable score pair used by PostgreSQL lesson_result. */
public record TestScore(Integer correctCount, Integer totalCount) {
    public TestScore {
        if ((correctCount == null) != (totalCount == null)) {
            throw new IllegalArgumentException("정답 수와 전체 문항 수는 함께 입력해야 합니다.");
        }
        if (correctCount != null && (correctCount < 0 || totalCount <= 0 || correctCount > totalCount)) {
            throw new IllegalArgumentException("테스트 결과는 0 <= 정답 수 <= 전체 문항 수이고 전체 문항 수는 0보다 커야 합니다.");
        }
    }

    public static TestScore parse(String value) {
        if (value == null || value.isBlank()) return new TestScore(null, null);
        String[] parts = value.trim().split("/", -1);
        if (parts.length != 2) throw new IllegalArgumentException("테스트 결과는 정답수/전체문항수 형식이어야 합니다.");
        try {
            return new TestScore(Integer.valueOf(parts[0].trim()), Integer.valueOf(parts[1].trim()));
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException("테스트 결과는 숫자/숫자 형식이어야 합니다.", ex);
        }
    }

    public boolean isEmpty() { return correctCount == null; }
    public String format() { return isEmpty() ? "" : correctCount + "/" + totalCount; }
}
