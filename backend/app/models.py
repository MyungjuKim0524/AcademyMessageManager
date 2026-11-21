from pydantic import BaseModel, ConfigDict, StrictBool, StrictInt, StrictStr


class HealthResponse(BaseModel):
    status: str


class MessagePreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    studentName: StrictStr | None = None
    className: StrictStr | None = None
    classType: StrictStr | None = None
    lessonDate: StrictStr | None = None
    testRound: StrictStr | None = None
    attendance: StrictStr | None = None
    preGrade: StrictStr | None = None
    weeklyGrade: StrictStr | None = None
    correctCount: StrictInt | None = None
    totalCount: StrictInt | None = None
    includePreGrade: StrictBool | None = None
    includeWeeklyGrade: StrictBool | None = None
    includeTestResult: StrictBool | None = None


class MessagePreviewResponse(BaseModel):
    message: str
