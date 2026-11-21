export type ClassType = 'REGULAR' | 'EXAM_PREP'
export type AttendanceStatus = 'PRESENT' | 'ABSENT' | 'LATE'
export type AchievementGrade = 'A' | 'B' | 'C'

export interface MessagePreviewRequest {
  studentName: string
  className: string
  classType: ClassType
  lessonDate: string
  testRound?: string
  attendance: AttendanceStatus
  preGrade?: AchievementGrade
  weeklyGrade?: AchievementGrade
  correctCount?: number
  totalCount?: number
  includePreGrade: boolean
  includeWeeklyGrade: boolean
  includeTestResult: boolean
}

export interface MessagePreviewResponse {
  message: string
}

export interface HealthResponse {
  status: string
}
