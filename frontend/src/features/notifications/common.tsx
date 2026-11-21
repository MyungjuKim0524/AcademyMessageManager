import { CheckCircleOutlined, CloseCircleOutlined, EditOutlined, ExperimentOutlined, EyeOutlined, StopOutlined } from '@ant-design/icons'
import { Tag } from 'antd'
import type { ReactNode } from 'react'
import type { NotificationStatus } from './api'

// Status is always shown with an icon and words, never by colour alone.
export const STATUS: Record<NotificationStatus, { label: string; color: string; icon: ReactNode }> = {
  DRAFT: { label: '초안', color: 'default', icon: <EditOutlined /> },
  READY_FOR_REVIEW: { label: '검토 대기', color: 'blue', icon: <EyeOutlined /> },
  APPROVED: { label: '확정됨 (발송 대기)', color: 'green', icon: <CheckCircleOutlined /> },
  MOCK_SENT: { label: '모의 발송 성공 (실제 미전송)', color: 'cyan', icon: <ExperimentOutlined /> },
  MOCK_FAILED: { label: '모의 발송 실패', color: 'red', icon: <CloseCircleOutlined /> },
  CANCELLED: { label: '취소', color: 'default', icon: <StopOutlined /> },
}

export function StatusTag({ status }: { status: NotificationStatus }) {
  const meta = STATUS[status]
  return <Tag color={meta.color} icon={meta.icon}>{meta.label}</Tag>
}

export const EVENT_LABEL: Record<string, string> = {
  NOTIFICATION_CREATED: '초안 생성',
  NOTIFICATION_EDITED: '본문 수정',
  NOTIFICATION_SUBMITTED: '검토 요청',
  NOTIFICATION_APPROVED: '내용 확정',
  NOTIFICATION_APPROVAL_REVOKED: '확정 취소',
  NOTIFICATION_CANCELLED: '메시지 취소',
  NOTIFICATION_MOCK_SEND: '모의 발송',
}

// Academy policy: assistants confirm and send; teachers and admins may too (server enforces).
export const canApprove = (role?: string) => role === 'ADMIN' || role === 'TEACHER' || role === 'ASSISTANT'

/** Idempotency key for one mock-send action; kept until the server answers. */
export function newRequestKey(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  const bytes = new Uint8Array(16)
  crypto.getRandomValues(bytes)
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}
