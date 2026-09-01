package com.academy.message.domain;

public final class MakeupGuidancePolicy {
    public String guidanceFor(AttendanceStatus attendance, MakeupStatus makeupStatus) {
        if (!attendance.requiresMakeupGuidance()) return "";
        if (makeupStatus == MakeupStatus.COMPLETED) {
            return "결석한 수업 내용은 보강 수업을 통해 보완하였습니다.";
        }
        if (makeupStatus == MakeupStatus.REQUESTED || makeupStatus == MakeupStatus.APPROVED) {
            return "결석한 수업 내용은 신청한 보강 수업에서 보완할 예정입니다.";
        }
        return "이번 수업은 결석으로 인해 학습 내용 확인이 필요합니다.";
    }
}
