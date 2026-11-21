import { apiClient } from '../../shared/api/client'

/** Rates / averages are null when they cannot be computed (no target) — never shown as 0. */
export interface AttendanceCounts {
  target: number; recorded: number; unrecorded: number
  present: number; late: number; absent: number; excused: number; outside_records: number
  record_rate: number | null; attendance_rate: number | null
}
export interface StudentAttendance extends AttendanceCounts {
  enrollment_id: number; student_id: number; student_name: string; enrollment_status: string
}
export interface LessonAttendance { lesson_id: number; lesson_date: string; session_no: number; topic: string | null; target: number; recorded: number; unrecorded: number }
export interface AttendanceAnalytics {
  classroom_id: number; date_from: string; date_to: string; counted_until: string
  policy: { held_lesson: string; attendance_rate: string }
  summary: AttendanceCounts; held_lessons: number; not_held_lessons: number
  students: StudentAttendance[]; lessons: LessonAttendance[]
}
export type AttendanceStatus = 'PRESENT' | 'LATE' | 'ABSENT' | 'EXCUSED'
export interface AttendanceHistoryRow {
  lesson_id: number; lesson_date: string; session_no: number; topic: string | null; eligible: boolean; status: AttendanceStatus | null
  /** Homework grades of that lesson (A/B/C); null = not entered. */
  prework?: string | null; weekly?: string | null
}
export interface StudentAttendanceHistory {
  classroom_id: number; student_id: number; student_name: string; enrollment_id: number
  date_from: string; date_to: string; counted_until: string; summary: AttendanceCounts; rows: AttendanceHistoryRow[]
}

export interface AssessmentStats {
  assessment_id: number; title: string; assessment_date: string; max_score: number; lesson_id: number | null; upcoming: boolean
  target: number; scored: number; not_taken: number; missing: number; outside_records: number
  entry_rate: number | null; average: number | null; average_count: number; average_percent: number | null
}
export interface GradeAnalytics { classroom_id: number; date_from: string; date_to: string; assessments: AssessmentStats[] }
export type GradeStatus = 'SCORED' | 'NOT_TAKEN' | 'MISSING' | 'UPCOMING'
export interface AssessmentStudentRow { enrollment_id: number; student_id: number; student_name: string; eligible: boolean; status: GradeStatus; score: number | null; percent: number | null }
export interface AssessmentDetail { classroom_id: number; stats: AssessmentStats; rows: AssessmentStudentRow[] }
export interface GradeTrendRow {
  assessment_id: number; title: string; assessment_date: string; max_score: number; lesson_id: number | null
  eligible: boolean; status: GradeStatus; score: number | null; percent: number | null
}
export interface StudentGradeTrend { classroom_id: number; student_id: number; student_name: string; enrollment_id: number; date_from: string; date_to: string; rows: GradeTrendRow[] }

/** 관심 필요 학생 (2026-11-20): rule-based, every reason says which rule and how often. */
export interface WatchReason { code: 'LOW_SCORE' | 'DECLINING' | 'HOMEWORK_C' | 'ABSENCE'; title: string | null; count: number; text: string }
export interface WatchStudent { enrollment_id: number; student_id: number; student_name: string; reasons: WatchReason[] }
export interface Watchlist { classroom_id: number; window_from: string; window_to: string; rules: string[]; students: WatchStudent[] }
/** A session of one 평가 항목: the student's % next to the class average % of the same session. */
export interface ReportPoint extends GradeTrendRow { class_average_percent: number | null; diff: number | null }
export interface ReportCategory { title: string; points: ReportPoint[]; scored_count: number; average_diff: number | null }
export interface StudentReport {
  classroom_id: number; student_id: number; student_name: string; enrollment_id: number; date_from: string; date_to: string
  categories: ReportCategory[]; attendance: AttendanceCounts; lessons: AttendanceHistoryRow[]; watch_reasons: WatchReason[]
}

type Period = { classroomId: number; dateFrom: string; dateTo: string }
const params = ({ classroomId, dateFrom, dateTo }: Period) => ({ classroom_id: classroomId, date_from: dateFrom, date_to: dateTo })

export const getAttendance = async (period: Period) =>
  (await apiClient.get<AttendanceAnalytics>('/api/analytics/attendance', { params: params(period) })).data
export const getStudentAttendance = async (studentId: number, period: Period) =>
  (await apiClient.get<StudentAttendanceHistory>(`/api/analytics/attendance/students/${studentId}`, { params: params(period) })).data
export const getGrades = async (period: Period) =>
  (await apiClient.get<GradeAnalytics>('/api/analytics/grades', { params: params(period) })).data
export const getAssessment = async (assessmentId: number) =>
  (await apiClient.get<AssessmentDetail>(`/api/analytics/grades/assessments/${assessmentId}`)).data
export const getStudentGrades = async (studentId: number, period: Period) =>
  (await apiClient.get<StudentGradeTrend>(`/api/analytics/grades/students/${studentId}`, { params: params(period) })).data
export const getWatchlist = async (classroomId: number) =>
  (await apiClient.get<Watchlist>('/api/analytics/watchlist', { params: { classroom_id: classroomId } })).data
export const getStudentReport = async (studentId: number, period: Period) =>
  (await apiClient.get<StudentReport>(`/api/analytics/students/${studentId}/report`, { params: params(period) })).data
