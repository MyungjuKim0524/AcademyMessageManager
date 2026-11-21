import { apiClient } from '../../shared/api/client'

export type ObligationStatus = 'MISSING' | 'IN_REVIEW' | 'READY_TO_SEND' | 'FAILED' | 'DONE' | 'EXEMPT'
export type NextAction = 'CREATE_DRAFT' | 'REVIEW' | 'MOCK_SEND' | 'RETRY' | 'VIEW_HISTORY' | 'NONE'

export interface Counts {
  total: number; missing: number; in_review: number; ready_to_send: number; failed: number; done: number
  pending: number; exempt: number; overdue: number | null; completion_rate: number | null
}
export interface ClassroomCounts extends Counts { classroom_id: number; classroom_name: string; class_type: string }
export interface Summary { date_from: string; date_to: string; deadline_policy: 'NOT_CONFIGURED'; totals: Counts; classrooms: ClassroomCounts[] }
export interface Failure { code: string | null; category: 'RECIPIENT' | 'VALIDATION' | 'SENDER' | 'UNKNOWN'; category_label: string; message: string | null; attempted_at: string }
export interface Obligation {
  lesson_id: number; enrollment_id: number; classroom_id: number; classroom_name: string; student_id: number; student_name: string
  lesson_date: string; session_no: number; exam_round: string | null; topic: string | null; lesson_status: string
  obligated: boolean; exempt_reason: string | null; exempt_reason_label: string | null; status: ObligationStatus
  notification_id: number | null; notification_status: string | null; template_name: string | null; active_messages: number
  processed_at: string | null; attempt_count: number; failure: Failure | null; hints: string[]; next_action: NextAction; overdue: boolean | null
}
export interface ObligationPage { items: Obligation[]; total: number; limit: number; offset: number }

/** Dashboard '성적 안내 할 일': one class lesson with unfinished notices, most urgent first. */
export interface TodoItem {
  classroom_id: number; classroom_name: string; lesson_id: number; lesson_date: string; session_no: number
  failed: number; ready_to_send: number; in_review: number; missing: number; missing_no_email: number; missing_no_attendance: number
  next_action: 'RETRY' | 'SEND' | 'REVIEW' | 'COMPOSE'
}
export const getTodo = async () =>
  (await apiClient.get<{ date_from: string; date_to: string; items: TodoItem[] }>('/api/message-operations/todo')).data

export const getSummary = async (dateFrom: string, dateTo: string) =>
  (await apiClient.get<Summary>('/api/message-operations/summary', { params: { date_from: dateFrom, date_to: dateTo } })).data
export const listObligations = async (classroomId: number, dateFrom: string, dateTo: string, status: ObligationStatus | undefined, limit: number, offset: number) =>
  (await apiClient.get<ObligationPage>('/api/message-operations/obligations', {
    params: { classroom_id: classroomId, date_from: dateFrom, date_to: dateTo, status, limit, offset },
  })).data
