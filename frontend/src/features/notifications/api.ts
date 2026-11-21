import { apiClient } from '../../shared/api/client'

export type NotificationStatus = 'DRAFT' | 'READY_FOR_REVIEW' | 'APPROVED' | 'MOCK_SENT' | 'MOCK_FAILED' | 'CANCELLED'

export type ClassType = 'REGULAR' | 'EXAM_PREP'
export interface Template { id: number; name: string; body: string; is_active: boolean; version: number; default_for_class_type: ClassType | null; created_at: string; updated_at: string }
export interface TemplateVariable { name: string; description: string }
export interface TemplateValidation { ok: boolean; errors: string[]; variables: string[]; sample_body: string | null; sample_issues: string[] }
export interface PreviewItem {
  enrollment_id: number; student_id: number | null; student_name: string | null; ok: boolean; body: string | null
  issues: string[]; warnings: string[]; existing_notification_id: number | null
}
export interface PreviewResponse { lesson_id: number; template_id: number; template_version: number; items: PreviewItem[] }
export interface GenerateResponse { created: number[]; skipped: { enrollment_id: number; student_name: string | null; reasons: string[]; existing_notification_id: number | null }[] }
export interface NotificationItem {
  id: number; classroom_id: number; lesson_id: number; lesson_date: string; session_no: number; enrollment_id: number
  student_name: string; template_id: number; template_name: string; status: NotificationStatus; recipient: string; version: number; updated_at: string
}
export interface Attempt { id: number; channel: string; result: 'MOCK_SUCCESS' | 'MOCK_FAILURE'; error_code: string | null; error_message: string | null; requested_by: string | null; attempted_at: string }
export interface HistoryEvent { event_type: string; actor: string | null; created_at: string; details: Record<string, unknown> }
export interface NotificationDetail extends NotificationItem {
  recipient_email: string; body: string; template_version: number; created_by: string | null; approved_by: string | null; approved_at: string | null
  source_changed: boolean; attempts: Attempt[]; history: HistoryEvent[]
}
export interface MockSendResponse { notification: NotificationDetail; attempt: Attempt; replayed: boolean }
export type Transition = 'submit' | 'approve' | 'revoke' | 'cancel'
/** Class batch (one lesson on one screen): body to read, whether the source changed, facts worth a second look. */
export interface BatchMessage extends NotificationItem { body: string; source_changed: boolean; attention: string[] }
export interface BatchView { lesson_id: number; classroom_id: number; items: BatchMessage[] }
/** Per message: confirmed / sent / failed / skipped with the reason (each message is processed on its own). */
export interface BatchResult {
  id: number; student_name: string | null; outcome: 'APPROVED' | 'MOCK_SENT' | 'MOCK_FAILED' | 'SKIPPED'
  code: string | null; message: string | null; replayed: boolean
}

export const listTemplates = async () => (await apiClient.get<Template[]>('/api/notification-templates')).data
export const listVariables = async () => (await apiClient.get<TemplateVariable[]>('/api/notification-templates/variables')).data
export const validateTemplate = async (body: string) => (await apiClient.post<TemplateValidation>('/api/notification-templates/validate', { body })).data
export const createTemplate = async (name: string, body: string) => (await apiClient.post<Template>('/api/notification-templates', { name, body })).data
export const updateTemplate = async (id: number, change: { version: number; name?: string; body?: string; is_active?: boolean; default_for_class_type?: ClassType | 'NONE' }) =>
  (await apiClient.patch<Template>(`/api/notification-templates/${id}`, change)).data

export const preview = async (lessonId: number, templateId: number) =>
  (await apiClient.post<PreviewResponse>(`/api/lessons/${lessonId}/notifications/preview`, { template_id: templateId })).data
export const createDrafts = async (lessonId: number, templateId: number, enrollmentIds: number[]) =>
  (await apiClient.post<GenerateResponse>(`/api/lessons/${lessonId}/notifications`, { template_id: templateId, enrollment_ids: enrollmentIds })).data

export const listNotifications = async (classroomId: number, filter: { lessonId?: number; status?: NotificationStatus }) =>
  (await apiClient.get<{ items: NotificationItem[] }>('/api/notifications', {
    params: { classroom_id: classroomId, lesson_id: filter.lessonId, status: filter.status },
  })).data.items
export const getNotification = async (id: number) => (await apiClient.get<NotificationDetail>(`/api/notifications/${id}`)).data
export const editNotification = async (id: number, version: number, body: string) =>
  (await apiClient.patch<NotificationDetail>(`/api/notifications/${id}`, { version, body })).data
export const transition = async (id: number, action: Transition, version: number) =>
  (await apiClient.post<NotificationDetail>(`/api/notifications/${id}/${action}`, { version })).data
export const mockSend = async (id: number, idempotencyKey: string) =>
  (await apiClient.post<MockSendResponse>(`/api/notifications/${id}/mock-send`, null, { headers: { 'Idempotency-Key': idempotencyKey } })).data
/** Phase 9: manual retry of a failed mock send (same confirmed body; earlier attempts are kept). */
export const retryMockSend = async (id: number, idempotencyKey: string) =>
  (await apiClient.post<MockSendResponse>(`/api/notifications/${id}/retry-mock-send`, null, { headers: { 'Idempotency-Key': idempotencyKey } })).data

export const batchView = async (lessonId: number) =>
  (await apiClient.get<BatchView>(`/api/lessons/${lessonId}/notifications/batch`)).data
export const batchApprove = async (lessonId: number, items: { id: number; version: number }[]) =>
  (await apiClient.post<{ results: BatchResult[] }>(`/api/lessons/${lessonId}/notifications/batch-approve`, { items })).data.results
/** Confirmed messages are sent and failed ones retried, each with its own idempotency key. */
export const batchMockSend = async (lessonId: number, items: { id: number; idempotency_key: string }[]) =>
  (await apiClient.post<{ results: BatchResult[] }>(`/api/lessons/${lessonId}/notifications/batch-mock-send`, { items }, { timeout: 120_000 })).data.results
