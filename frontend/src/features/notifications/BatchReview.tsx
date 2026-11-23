import { useCallback, useEffect, useMemo, useRef, useState, type Key } from 'react'
import { Alert, Button, Card, Empty, Popconfirm, Select, Space, Table, Tag, Typography } from 'antd'
import { toApiClientError } from '../../shared/api/ApiClientError'
import { lessonTitle, todayLocal } from '../classwork/common'
import * as api from './api'
import { StatusTag, canApprove, newRequestKey } from './common'
import type { NotificationContext } from './NotificationsPage'

const EDITABLE: api.NotificationStatus[] = ['DRAFT', 'READY_FOR_REVIEW']
const SENDABLE: api.NotificationStatus[] = ['APPROVED', 'MOCK_FAILED']
const OUTCOME: Record<api.BatchResult['outcome'], string> = {
  APPROVED: '확정', MOCK_SENT: '모의 발송 성공', MOCK_FAILED: '모의 발송 실패', SKIPPED: '제외',
}
/** Absence notes the server puts on a message (notifications/service.py `_attention`). */
const ABSENCE_NOTES: readonly string[] = ['결석', '인정결석']
const absenceOf = (m: api.BatchMessage) => m.attention.find((note) => ABSENCE_NOTES.includes(note))

type Props = Pick<NotificationContext, 'role' | 'lessons' | 'notify' | 'fail'> & {
  /** Opens one message in the one-by-one view (to edit, revoke or cancel it). */
  onOpen: (notificationId: number) => void
  /** Lesson to open with (e.g. from the dashboard to-do list); otherwise the latest lesson. */
  initialLessonId?: number
}

/** The most recent lesson that can have messages (not cancelled, not in the future). */
function latestLesson(lessons: NotificationContext['lessons']): number | undefined {
  const today = todayLocal()
  return [...lessons]
    .filter((row) => row.status !== 'CANCELLED' && row.lesson_date <= today)
    .sort((a, b) => b.lesson_date.localeCompare(a.lesson_date) || b.session_no - a.session_no)[0]?.id
}

/**
 * 2026-11-20: one class lesson on one screen — read every body, confirm the chosen ones, then
 * mock-send the confirmed ones. Nothing is pre-selected: confirming is a choice made after
 * reading. The server processes each message on its own (version, source check, idempotency key,
 * audit), so a skipped or failed message never stops or undoes the others.
 */
export function BatchReview({ role, lessons, notify, fail, onOpen, initialLessonId }: Props) {
  const [lessonId, setLessonId] = useState<number | undefined>(() => initialLessonId ?? latestLesson(lessons))
  const [view, setView] = useState<api.BatchView | null>(null)
  const [loading, setLoading] = useState(false)
  const [selected, setSelected] = useState<number[]>([])
  const [busy, setBusy] = useState(false)
  const [results, setResults] = useState<{ kind: 'approve' | 'send'; items: api.BatchResult[] } | null>(null)
  // One idempotency key per message, kept until the server answers (a repeated click replays).
  const sendKeys = useRef(new Map<number, string>())

  useEffect(() => { if (lessonId === undefined) setLessonId(latestLesson(lessons)) }, [lessons, lessonId])

  const load = useCallback(async () => {
    if (lessonId === undefined) { setView(null); return }
    setLoading(true)
    try { setView(await api.batchView(lessonId)); setSelected([]) } catch (error) { fail(error) } finally { setLoading(false) }
  }, [lessonId, fail])

  useEffect(() => { setResults(null); void load() }, [load])

  const items = useMemo(() => view?.items ?? [], [view])
  const confirmable = items.filter((m) => EDITABLE.includes(m.status) && !m.source_changed)
  const sendable = items.filter((m) => SENDABLE.includes(m.status) && !m.source_changed)
  const counts = {
    review: items.filter((m) => EDITABLE.includes(m.status)).length,
    approved: items.filter((m) => m.status === 'APPROVED').length,
    failed: items.filter((m) => m.status === 'MOCK_FAILED').length,
    sent: items.filter((m) => m.status === 'MOCK_SENT').length,
    changed: items.filter((m) => m.source_changed).length,
  }
  const lesson = lessons.find((row) => row.id === lessonId)
  const title = lesson ? lessonTitle(lesson) : ''
  const approver = canApprove(role)
  // 2026-11-23: absent students' guardians are often phoned by the front desk, so a message to
  // them is a one-by-one choice: "select all" leaves them out (a box ticked by hand is kept) and
  // the confirm dialog counts them. Clicking "select all" again clears the selection.
  const absentIds = new Set(items.filter((m) => absenceOf(m)).map((m) => m.id))
  const absentConfirmable = confirmable.filter((m) => absentIds.has(m.id)).length
  const chosen = items.filter((m) => selected.includes(m.id))
  const chosenAbsent = chosen.filter((m) => absenceOf(m) === '결석').length
  const chosenExcused = chosen.filter((m) => absenceOf(m) === '인정결석').length
  const absenceWarning = chosenAbsent + chosenExcused > 0
    ? ` 이 중 ${[chosenAbsent && `결석 ${chosenAbsent}건`, chosenExcused && `인정결석 ${chosenExcused}건`].filter(Boolean).join(' · ')}이 포함되어 있습니다. 보호자에게 이미 연락했는지 확인하세요.`
    : ''
  const onSelect = (keys: Key[], _rows: api.BatchMessage[], info: { type: string }) => {
    const next = keys as number[]
    if (info.type !== 'all') { setSelected(next); return }
    const picked = next.filter((id) => !absentIds.has(id) || selected.includes(id))
    const unchanged = picked.length === selected.length && picked.every((id) => selected.includes(id))
    setSelected(unchanged ? [] : picked)
  }

  const report = (kind: 'approve' | 'send', outcome: api.BatchResult[]) => {
    setResults({ kind, items: outcome })
    const done = outcome.filter((r) => r.outcome === (kind === 'approve' ? 'APPROVED' : 'MOCK_SENT')).length
    const failed = outcome.filter((r) => r.outcome === 'MOCK_FAILED').length
    const skipped = outcome.filter((r) => r.outcome === 'SKIPPED').length
    const text = kind === 'approve'
      ? `확정 ${done}건${skipped ? ` · 제외 ${skipped}건` : ''}`
      : `모의 발송 성공 ${done}건${failed ? ` · 실패 ${failed}건` : ''}${skipped ? ` · 제외 ${skipped}건` : ''} (실제 문자·이메일은 전송되지 않음)`
    notify({ type: failed || skipped ? 'warning' : 'success', text })
  }

  const approve = async () => {
    if (lessonId === undefined) return
    const chosen = items.filter((m) => selected.includes(m.id)).map((m) => ({ id: m.id, version: m.version }))
    setBusy(true)
    try { report('approve', await api.batchApprove(lessonId, chosen)); await load() } catch (error) { fail(error) } finally { setBusy(false) }
  }

  const send = async () => {
    if (lessonId === undefined) return
    const chosen = sendable.map((m) => {
      if (!sendKeys.current.has(m.id)) sendKeys.current.set(m.id, newRequestKey())
      return { id: m.id, idempotency_key: sendKeys.current.get(m.id)! }
    })
    setBusy(true)
    try {
      const outcome = await api.batchMockSend(lessonId, chosen)
      for (const r of outcome) sendKeys.current.delete(r.id) // answered: a later send is a new request
      report('send', outcome)
      await load()
    } catch (error) {
      // No answer: keep the keys, so sending again replays instead of sending twice.
      const code = toApiClientError(error).code
      if (code !== 'CLIENT_ERROR' && code !== 'NETWORK_ERROR') sendKeys.current.clear()
      fail(error)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card size="small" title="반 일괄 처리 — 수업 하나의 메시지를 한 화면에서 검토·확정·모의 발송">
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        <Space wrap>
          <Select aria-label="일괄 처리 수업" placeholder="수업 선택" style={{ width: 200 }} value={lessonId}
            onChange={(value) => setLessonId(value)}
            options={lessons.filter((row) => row.status !== 'CANCELLED').map((row) => ({ value: row.id, label: lessonTitle(row) }))} />
          <Button onClick={() => void load()} disabled={lessonId === undefined || busy}>새로고침</Button>
        </Space>
        {view && (
          <Typography.Text type="secondary">
            {`검토 대기 ${counts.review} · 확정(발송 대기) ${counts.approved} · 모의 발송 실패 ${counts.failed} · 모의 발송 완료 ${counts.sent} · 원본 변경 ${counts.changed}`}
          </Typography.Text>
        )}
        {counts.changed > 0 && (
          <Alert type="warning" showIcon message={`생성 후 출결·성적·연락처가 바뀐 메시지 ${counts.changed}건은 확정·발송할 수 없습니다. 학생 이름을 눌러 한 건씩 보기에서 취소한 뒤 다시 생성하세요.`} />
        )}
        <Table
          rowKey="id"
          size="small"
          loading={loading}
          dataSource={items}
          pagination={false}
          scroll={{ x: 'max-content' }}
          locale={{ emptyText: <Empty description={lessonId === undefined ? '수업을 선택하세요.' : '이 수업의 메시지가 없습니다.'} /> }}
          rowSelection={approver ? {
            selectedRowKeys: selected,
            onChange: onSelect,
            getCheckboxProps: (m) => ({ disabled: !confirmable.includes(m), 'aria-label': `${m.student_name} 확정 선택` }),
          } : undefined}
          columns={[
            {
              title: '학생', className: 'cell-nowrap',
              render: (_, m) => <Button type="link" size="small" style={{ padding: 0 }} onClick={() => onOpen(m.id)}>{m.student_name}</Button>,
            },
            { title: '상태', className: 'cell-nowrap', render: (_, m) => <StatusTag status={m.status} /> },
            {
              title: '확인', className: 'cell-nowrap',
              render: (_, m) => (
                <Space size={2} wrap>
                  {m.source_changed && <Tag color="red">원본 변경</Tag>}
                  {m.attention.map((note) => <Tag key={note} color="gold">{note}</Tag>)}
                </Space>
              ),
            },
            {
              title: '본문', onCell: () => ({ style: { minWidth: 320 } }),
              render: (_, m) => <Typography.Paragraph style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{m.body}</Typography.Paragraph>,
            },
            { title: '수신', dataIndex: 'recipient', className: 'cell-nowrap' },
          ]}
        />
        {approver && view && (
          <Space wrap>
            <Popconfirm
              title={`선택한 ${selected.length}건을 확정할까요?`}
              description={`${title} 메시지 ${selected.length}건을 확정합니다.${absenceWarning} 목록의 본문을 확인했는지 다시 봐 주세요. 그사이 원본이 바뀐 메시지는 확정하지 않고 결과에 따로 표시합니다.`}
              okText="확정" cancelText="닫기" onConfirm={() => void approve()} disabled={selected.length === 0}
            >
              <Button type="primary" disabled={selected.length === 0 || busy}>{`선택한 ${selected.length}건 확정`}</Button>
            </Popconfirm>
            <Popconfirm
              title={`${sendable.length}건을 모의 발송할까요?`}
              description={`${title} 확정 ${counts.approved}건${counts.failed ? ` · 실패 재시도 ${sendable.length - counts.approved}건` : ''}. 메시지마다 따로 처리하며 한 건이 실패해도 나머지는 계속됩니다. 실제 문자·이메일은 전송되지 않습니다.`}
              okText="모의 발송" cancelText="닫기" onConfirm={() => void send()} disabled={sendable.length === 0}
            >
              <Button disabled={sendable.length === 0 || busy}>{`확정된 ${sendable.length}건 모의 발송`}</Button>
            </Popconfirm>
            <Typography.Text type="secondary">고칠 메시지는 선택하지 말고 학생 이름을 눌러 한 건씩 수정하세요.</Typography.Text>
            {absentConfirmable > 0 && (
              <Typography.Text type="secondary">{`전체 선택은 결석·인정결석 ${absentConfirmable}명을 빼고 선택합니다. 그 학생에게도 보내려면 직접 체크하세요.`}</Typography.Text>
            )}
          </Space>
        )}
        {results && (
          <Alert
            type={results.items.some((r) => r.outcome === 'SKIPPED' || r.outcome === 'MOCK_FAILED') ? 'warning' : 'success'}
            showIcon
            message={results.kind === 'approve' ? '일괄 확정 결과' : '일괄 모의 발송 결과'}
            description={(
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {results.items.map((r) => (
                  <li key={r.id}>{`${r.student_name ?? `메시지 ${r.id}`}: ${OUTCOME[r.outcome]}${r.message ? ` — ${r.message}` : ''}${r.replayed ? ' (이전 요청 결과)' : ''}`}</li>
                ))}
              </ul>
            )}
          />
        )}
      </Space>
    </Card>
  )
}
