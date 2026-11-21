import { apiClient } from '../../shared/api/client'

export type RowStatus = 'MATCHED' | 'UNREGISTERED' | 'INVALID' | 'SKIPPED'
export type Decision = 'NEW' | 'RETURNING' | 'EXCLUDE'

/** A value already in the app that confirming will replace (scores and homework grades follow the workbook). */
export interface AppChange { field: 'score' | 'prework' | 'weekly'; label: string; app: string; upload: string }
export interface UploadRow {
  key: string; row: number; name: string; status: RowStatus
  attendance: string | null; prework: string | null; weekly: string | null; scores: Record<string, number | null>
  issues: string[]; warnings: string[]; app_attendance: string | null; attendance_mismatch: boolean; returning_available: boolean
  app_changes?: AppChange[]
  /** Already equal to the app: confirming writes nothing for this row and leaves no audit record. */
  unchanged?: boolean
  /** Same name (+ school) already registered outside this class: the upload cannot register it as new (SEC-01). */
  existing_student_conflict?: boolean
}
/** A sheet (time slot) of the workbook with class blocks; student_rows 0 = nothing entered yet. */
export interface SheetSummary { name: string; class_names: string[]; student_rows: number }
export interface UploadBlock {
  sheet: string; row: number; class_name: string; class_type: 'REGULAR' | 'EXAM_PREP' | null; classroom_id: number | null
  tests: { title: string; total: number }[]; issues: string[]; rows: UploadRow[]
  max_score_changes?: { title: string; app: string; upload: string }[]
}
export interface UploadPreview {
  lesson_date: string; blocks: UploadBlock[]; can_confirm: boolean; blocking: string[]
  sheets?: SheetSummary[]; selected_sheets?: string[]
}
export interface UploadResult {
  /** saved_rows = rows that wrote something; unchanged_rows = rows already equal to the app (skipped, not audited). */
  lesson_date: string; saved_rows: number; unchanged_rows?: number; new_students: number; returned_students: number; excluded_rows: number
  attendance_mismatches: string[]; drafts: { class_name: string; created: number; skipped: string[] }[]
}

const form = (file: File, lessonDate?: string, decisions?: Record<string, Decision>, sheets?: string[]) => {
  const data = new FormData()
  data.append('file', file)
  if (lessonDate) data.append('lesson_date', lessonDate)
  if (decisions) data.append('decisions', JSON.stringify(decisions))
  for (const sheet of sheets ?? []) data.append('sheets', sheet)
  return data
}

// Uploads can take longer than ordinary requests.
/** The workbook's time-slot sheets (reads the file only, no lesson data). */
export const listSheets = async (file: File) =>
  (await apiClient.post<{ sheets: SheetSummary[] }>('/api/lesson-uploads/sheets', form(file), { timeout: 60_000 })).data.sheets
export const previewUpload = async (file: File, lessonDate: string, sheets: string[]) =>
  (await apiClient.post<UploadPreview>('/api/lesson-uploads/preview', form(file, lessonDate, undefined, sheets), { timeout: 60_000 })).data
export const confirmUpload = async (file: File, lessonDate: string, decisions: Record<string, Decision>, sheets: string[]) =>
  (await apiClient.post<UploadResult>('/api/lesson-uploads/confirm', form(file, lessonDate, decisions, sheets), { timeout: 120_000 })).data
