import { CheckCircleOutlined, ClockCircleOutlined, CloseCircleOutlined, FileDoneOutlined, MinusCircleOutlined, StopOutlined } from '@ant-design/icons'
import { Tag } from 'antd'
import type { ReactNode } from 'react'
import type { FieldErrorResponse } from '../../shared/api/types'
import type { AttendanceStatus, LessonStatus, ResultStatus } from './api'

export type Notice = { type: 'success' | 'error' | 'warning'; text: string } | null

export { shiftDay, todayLocal } from '../../shared/date'

export const LESSON_STATUS: Record<LessonStatus, { label: string; color: string }> = {
  SCHEDULED: { label: '예정', color: 'blue' },
  COMPLETED: { label: '완료', color: 'green' },
  CANCELLED: { label: '취소', color: 'default' },
}

/** e.g. `2026-11-03 2교시 (3회차)` — the session number is shown only when it is not the first. */
export const lessonTitle = (lesson: { lesson_date: string; session_no: number; exam_round: string | null }) =>
  `${lesson.lesson_date}${lesson.session_no > 1 ? ` ${lesson.session_no}교시` : ''}${lesson.exam_round ? ` (${lesson.exam_round})` : ''}`

export function LessonStatusTag({ status }: { status: LessonStatus }) {
  return <Tag color={LESSON_STATUS[status].color}>{LESSON_STATUS[status].label}</Tag>
}

// Status is always shown as icon + text, never by colour alone.
export const ATTENDANCE: Record<AttendanceStatus, { label: string; color: string; icon: ReactNode }> = {
  PRESENT: { label: '출석', color: 'green', icon: <CheckCircleOutlined /> },
  LATE: { label: '지각', color: 'orange', icon: <ClockCircleOutlined /> },
  ABSENT: { label: '결석', color: 'red', icon: <CloseCircleOutlined /> },
  EXCUSED: { label: '인정결석', color: 'purple', icon: <FileDoneOutlined /> },
}

export function AttendanceTag({ status }: { status: AttendanceStatus | null }) {
  if (status === null) return <Tag icon={<MinusCircleOutlined />}>미입력</Tag>
  const meta = ATTENDANCE[status]
  return <Tag color={meta.color} icon={meta.icon}>{meta.label}</Tag>
}

export function GradeTag({ status, score, max }: { status: ResultStatus | null; score: number | null; max?: number }) {
  if (status === null) return <Tag icon={<MinusCircleOutlined />}>미입력</Tag>
  if (status === 'NOT_TAKEN') return <Tag icon={<StopOutlined />}>미응시</Tag>
  return <Tag color="blue">{score}{max !== undefined ? ` / ${max}` : ''}점</Tag>
}

/** Map server field errors like `items.2.score` back to the row (enrollment) that was sent. */
export function rowErrors(fields: FieldErrorResponse[], sent: { enrollment_id: number }[]) {
  const result: Record<number, string[]> = {}
  for (const field of fields) {
    const match = /^items\.(\d+)\./.exec(field.field)
    const item = match ? sent[Number(match[1])] : undefined
    if (item) (result[item.enrollment_id] ??= []).push(field.message)
  }
  return result
}

export const canWriteLessons = (role?: string) => role === 'ADMIN' || role === 'TEACHER'
export const canWriteAttendance = (role?: string) => role === 'ADMIN' || role === 'TEACHER' || role === 'ASSISTANT'
/** Creating / editing assessments (평가 관리) — assistants too (2026-11-19 decision). */
export const canWriteGrades = canWriteAttendance
/** Recording and correcting scores and assignment grades — assistants too (2026-11-19 decision). */
export const canWriteScores = canWriteAttendance
