import { apiClient } from '../../shared/api/client'

export type LessonStatus = 'SCHEDULED' | 'COMPLETED' | 'CANCELLED'
export type AttendanceStatus = 'PRESENT' | 'ABSENT' | 'LATE' | 'EXCUSED'
export type ResultStatus = 'SCORED' | 'NOT_TAKEN'

export interface Classroom { id: number; name: string; class_type: string; is_active: boolean }
export interface Lesson {
  id: number; classroom_id: number; lesson_date: string; session_no: number; exam_round: string | null; topic: string | null
  memo: string | null; status: LessonStatus; version: number; created_at: string; updated_at: string
}
export interface LessonListItem extends Lesson { attendance_recorded: number }
export interface AttendanceSummary { eligible: number; recorded: number; unrecorded: number; present: number; absent: number; late: number; excused: number }
export interface AttendanceRecord { status: AttendanceStatus; memo: string | null; version: number; updated_at: string }
export interface AttendanceRow { enrollment_id: number; student_id: number; student_name: string; school_name: string | null; eligible: boolean; record: AttendanceRecord | null }
export interface AttendanceRoster { lesson: Lesson; summary: AttendanceSummary; items: AttendanceRow[]; changed: number | null }
export interface AttendanceInput { enrollment_id: number; status: AttendanceStatus; memo: string | null; version: number | null }

export interface Assessment {
  id: number; classroom_id: number; lesson_id: number | null; title: string; assessment_date: string
  max_score: number; version: number; created_at: string; updated_at: string
}
export interface AssessmentListItem extends Assessment { scored: number; not_taken: number }
export interface GradeSummary { eligible: number; scored: number; not_taken: number; unrecorded: number }
export interface GradeRecord { result_status: ResultStatus; score: number | null; memo: string | null; version: number; updated_at: string }
export interface GradeRow { enrollment_id: number; student_id: number; student_name: string; school_name: string | null; eligible: boolean; record: GradeRecord | null }
export interface GradeRoster { assessment: Assessment; summary: GradeSummary; items: GradeRow[]; changed: number | null }
export interface GradeInput { enrollment_id: number; result_status: ResultStatus; score: number | null; memo: string | null; version: number | null }

export interface StudentRecords {
  student_id: number; student_name: string; enrollment_status: string; enrolled_at: string; ended_at: string | null
  lessons: { lesson_id: number; lesson_date: string; session_no: number; exam_round: string | null; topic: string | null; lesson_status: LessonStatus; attendance_status: AttendanceStatus | null; prework_grade?: AssignmentGrade | null; weekly_grade?: AssignmentGrade | null; memo: string | null }[]
  assessments: { assessment_id: number; title: string; assessment_date: string; max_score: number; result_status: ResultStatus | null; score: number | null; memo: string | null }[]
}

// ---- 학습 현황: student × lesson grid and one-cell correction ----
export type AssignmentGrade = 'A' | 'B' | 'C'
export interface ProgressAssessment { id: number; title: string; max_score: number; version: number }
export interface ProgressColumn {
  key: string; kind: 'LESSON' | 'ASSESSMENT'; lesson_id: number | null; day: string; session_no: number | null
  exam_round: string | null; topic: string | null; lesson_status: LessonStatus | null; assessments: ProgressAssessment[]
}
export interface ProgressScore { assessment_id: number; result_status: ResultStatus; score: number | null; memo: string | null; version: number }
export interface ProgressCell {
  key: string; eligible: boolean; attendance_status: AttendanceStatus | null; prework_grade: AssignmentGrade | null
  weekly_grade: AssignmentGrade | null; result_version: number | null; scores: ProgressScore[]
}
export interface ProgressStudent { enrollment_id: number; student_id: number; student_name: string; enrollment_status: string; cells: ProgressCell[] }
export interface ClassProgress { classroom_id: number; date_from: string; date_to: string; columns: ProgressColumn[]; students: ProgressStudent[] }
export interface RecordUpdate {
  result_version?: number | null; attendance_status?: AttendanceStatus; prework_grade?: AssignmentGrade | null; weekly_grade?: AssignmentGrade | null
  scores?: { assessment_id: number; result_status: ResultStatus; score: number | null; version: number | null }[]
}

export const getProgress = async (classroomId: number, dateFrom: string, dateTo: string) =>
  (await apiClient.get<ClassProgress>(`/api/classrooms/${classroomId}/progress`, { params: { date_from: dateFrom, date_to: dateTo } })).data
export const updateRecord = async (lessonId: number, enrollmentId: number, body: RecordUpdate) =>
  (await apiClient.put<{ changed: number }>(`/api/lessons/${lessonId}/records/${enrollmentId}`, body)).data

export const listClassrooms = async () => (await apiClient.get<{ items: Classroom[] }>('/api/classrooms', { params: { limit: 100 } })).data.items
export const listLessons = async (classroomId: number) => (await apiClient.get<{ items: LessonListItem[] }>(`/api/classrooms/${classroomId}/lessons`, { params: { limit: 100 } })).data.items
export const createLesson = async (classroomId: number, body: Partial<Lesson>) => (await apiClient.post<Lesson>(`/api/classrooms/${classroomId}/lessons`, body)).data
/** "오늘 수업 시작": find or create today's 1st-session lesson (attendance writers, incl. assistants). */
export const startTodayLesson = async (classroomId: number) =>
  (await apiClient.post<{ lesson: Lesson; created: boolean }>(`/api/classrooms/${classroomId}/lessons/today`)).data
export const updateLesson = async (lessonId: number, body: Partial<Lesson> & { version: number }) => (await apiClient.patch<Lesson>(`/api/lessons/${lessonId}`, body)).data
export const getAttendance = async (lessonId: number) => (await apiClient.get<AttendanceRoster>(`/api/lessons/${lessonId}/attendance`)).data
export const saveAttendance = async (lessonId: number, items: AttendanceInput[]) => (await apiClient.put<AttendanceRoster>(`/api/lessons/${lessonId}/attendance`, { items })).data
export const listAssessments = async (classroomId: number) => (await apiClient.get<{ items: AssessmentListItem[] }>(`/api/classrooms/${classroomId}/assessments`, { params: { limit: 100 } })).data.items
export const createAssessment = async (classroomId: number, body: { title: string; assessment_date: string; max_score: number; lesson_id: number | null }) => (await apiClient.post<Assessment>(`/api/classrooms/${classroomId}/assessments`, body)).data
export const updateAssessment = async (assessmentId: number, body: { version: number; title?: string; max_score?: number }) => (await apiClient.patch<Assessment>(`/api/assessments/${assessmentId}`, body)).data
export const getGrades = async (assessmentId: number) => (await apiClient.get<GradeRoster>(`/api/assessments/${assessmentId}/grades`)).data
export const saveGrades = async (assessmentId: number, items: GradeInput[]) => (await apiClient.put<GradeRoster>(`/api/assessments/${assessmentId}/grades`, { items })).data
export const getStudentRecords = async (classroomId: number, studentId: number) => (await apiClient.get<StudentRecords>(`/api/classrooms/${classroomId}/students/${studentId}/records`)).data
