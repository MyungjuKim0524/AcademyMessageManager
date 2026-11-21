import { useCallback, useEffect, useRef, useState } from 'react'
import { Alert, Button, Card, Col, Empty, Input, Popconfirm, Progress, Radio, Row, Space, Spin, Statistic, Table, Tag, Typography } from 'antd'
import {
  CheckCircleOutlined, ClockCircleOutlined, CloseCircleOutlined, EditOutlined, ExperimentOutlined, MinusCircleOutlined, SendOutlined,
} from '@ant-design/icons'
import type { ReactNode } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router'
import { toApiClientError } from '../../shared/api/ApiClientError'
import { rememberClassroom, rememberedClassroom, withReturn } from '../../shared/workingContext'
import { useAuth } from '../auth/AuthProvider'
import { lessonTitle } from '../classwork/common'
import { shiftDay, todayLocal } from '../../shared/date'
import { newRequestKey } from '../notifications/common'
import * as notifications from '../notifications/api'
import * as api from './api'
import { PageHeader } from '../../shared/ui/PageHeader'

const PAGE_SIZE = 50

// Status is always shown with an icon and words, never by colour alone.
export const OPS_STATUS: Record<api.ObligationStatus, { label: string; color: string; icon: ReactNode }> = {
  MISSING: { label: '초안 미생성', color: 'orange', icon: <MinusCircleOutlined /> },
  IN_REVIEW: { label: '검토·확정 대기', color: 'blue', icon: <EditOutlined /> },
  READY_TO_SEND: { label: '모의 발송 대기', color: 'geekblue', icon: <SendOutlined /> },
  FAILED: { label: '모의 발송 실패', color: 'red', icon: <CloseCircleOutlined /> },
  DONE: { label: '모의 발송 완료', color: 'green', icon: <CheckCircleOutlined /> },
  EXEMPT: { label: '안내 대상 아님', color: 'default', icon: <ClockCircleOutlined /> },
}

export function OpsStatusTag({ status }: { status: api.ObligationStatus }) {
  const meta = OPS_STATUS[status]
  return <Tag color={meta.color} icon={meta.icon}>{meta.label}</Tag>
}

const rate = (value: number | null) => (value === null ? '대상 없음' : `${value}%`)

/** Per-status count in the summary (same numbers the server returns per class). */
const COUNT_OF: Record<api.ObligationStatus, keyof api.Counts> = {
  MISSING: 'missing', IN_REVIEW: 'in_review', READY_TO_SEND: 'ready_to_send', FAILED: 'failed', DONE: 'done', EXEMPT: 'exempt',
}
/** Work still to do, shown first; completion is the supporting figure. */
const ATTENTION: api.ObligationStatus[] = ['MISSING', 'IN_REVIEW', 'READY_TO_SEND', 'FAILED']

type Props = {
  /** Shown as the '메시지 처리 현황' tab of 성적 안내: no own page header / mock notice (the page has them). */
  embedded?: boolean
  /** The class chosen on the surrounding page; a row click here changes it there too. */
  classroomId?: number | null
  onSelectClassroom?: (id: number) => void
}

export function MessageOperationsPage({ embedded = false, classroomId: pageClassroom, onSelectClassroom }: Props = {}) {
  const navigate = useNavigate()
  const location = useLocation()
  const [params] = useSearchParams()
  const { user } = useAuth()
  const admin = user?.role === 'ADMIN'
  const [dateTo, setDateTo] = useState(todayLocal())
  const [dateFrom, setDateFrom] = useState(shiftDay(todayLocal(), -13))
  const [summary, setSummary] = useState<api.Summary | null>(null)
  const [loading, setLoading] = useState(false)
  const [classroomId, setClassroomId] = useState<number | null>(null)
  // `?status=FAILED` (dashboard "발송 실패 확인") preselects the filter.
  const [status, setStatus] = useState<api.ObligationStatus | undefined>(() => {
    const wanted = params.get('status')
    return wanted && wanted in OPS_STATUS ? (wanted as api.ObligationStatus) : undefined
  })
  const [page, setPage] = useState(1)
  const [items, setItems] = useState<api.ObligationPage | null>(null)
  const [itemsLoading, setItemsLoading] = useState(false)
  const [notice, setNotice] = useState<{ type: 'success' | 'error' | 'warning'; text: string } | null>(null)
  const [retrying, setRetrying] = useState<number | null>(null)
  const retryKeys = useRef(new Map<number, string>()) // one idempotency key per message until answered

  const fail = useCallback((error: unknown) => setNotice({ type: 'error', text: toApiClientError(error).message }), [])

  const loadSummary = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.getSummary(dateFrom, dateTo)
      setSummary(data)
      // The class being worked on (this screen, or another screen in this browser tab) stays selected.
      setClassroomId((current) => {
        const kept = [current, rememberedClassroom()].find((id) => id && data.classrooms.some((c) => c.classroom_id === id))
        const picked = kept ?? (data.classrooms.find((c) => c.total > 0) ?? data.classrooms[0])?.classroom_id ?? null
        rememberClassroom(picked)
        return picked
      })
    } catch (error) { setSummary(null); fail(error) } finally { setLoading(false) }
  }, [dateFrom, dateTo, fail])

  const loadItems = useCallback(async () => {
    if (classroomId === null) { setItems(null); return }
    setItemsLoading(true)
    try { setItems(await api.listObligations(classroomId, dateFrom, dateTo, status, PAGE_SIZE, (page - 1) * PAGE_SIZE)) } catch (error) { setItems(null); fail(error) } finally { setItemsLoading(false) }
  }, [classroomId, dateFrom, dateTo, status, page, fail])

  // Follow the class picked on the surrounding 성적 안내 page.
  useEffect(() => { if (pageClassroom) { setClassroomId(pageClassroom); setPage(1) } }, [pageClassroom])
  useEffect(() => { void loadSummary() }, [loadSummary])
  useEffect(() => { void loadItems() }, [loadItems])

  const refresh = async () => { await loadSummary(); await loadItems() }

  const openNotifications = (row: api.Obligation, tab: 'compose' | 'review') => {
    const params = new URLSearchParams({ classroom: String(row.classroom_id), tab })
    if (tab === 'compose') params.set('lesson', String(row.lesson_id))
    else if (row.notification_id) params.set('notification', String(row.notification_id))
    navigate(`/notifications?${params}`)
  }

  const retry = async (row: api.Obligation) => {
    const id = row.notification_id
    if (id === null || retrying !== null) return
    const key = retryKeys.current.get(id) ?? newRequestKey()
    retryKeys.current.set(id, key) // reused if this click is repeated before the server answers
    setRetrying(id)
    try {
      const result = await notifications.retryMockSend(id, key)
      retryKeys.current.delete(id)
      setNotice(result.attempt.result === 'MOCK_SUCCESS'
        ? { type: 'success', text: `${row.student_name} 메시지를 다시 모의 발송했습니다(성공). 실제 문자·이메일은 전송되지 않았습니다.` }
        : { type: 'error', text: `${row.student_name} 재시도도 실패했습니다: ${result.attempt.error_message ?? result.attempt.error_code}` })
      await refresh()
    } catch (error) {
      const apiError = toApiClientError(error)
      if (apiError.code !== 'CLIENT_ERROR') retryKeys.current.delete(id)
      setNotice({ type: apiError.code === 'SOURCE_CHANGED' ? 'warning' : 'error', text: apiError.message })
      await refresh()
    } finally {
      setRetrying(null)
    }
  }

  const action = (row: api.Obligation) => {
    switch (row.next_action) {
      case 'CREATE_DRAFT': return <Button size="small" onClick={() => openNotifications(row, 'compose')}>초안 생성</Button>
      case 'REVIEW': return <Button size="small" onClick={() => openNotifications(row, 'review')}>검토·확정</Button>
      case 'MOCK_SEND': return <Button size="small" onClick={() => openNotifications(row, 'review')}>모의 발송</Button>
      case 'VIEW_HISTORY': return <Button size="small" type="link" onClick={() => openNotifications(row, 'review')}>이력 보기</Button>
      case 'RETRY': return (
        <Space size={4} wrap>
          <Popconfirm title="모의 발송을 재시도할까요?" description="확정된 본문 그대로 다시 모의 발송합니다. 이전 실패 기록은 남고, 실제 문자·이메일은 전송되지 않습니다."
            okText="재시도" cancelText="닫기" onConfirm={() => void retry(row)}>
            <Button size="small" type="primary" danger loading={retrying === row.notification_id} disabled={retrying !== null && retrying !== row.notification_id}>재시도</Button>
          </Popconfirm>
          <Button size="small" type="link" onClick={() => openNotifications(row, 'review')}>상세</Button>
        </Space>
      )
      default: return <Typography.Text type="secondary">-</Typography.Text>
    }
  }

  const reason = (row: api.Obligation) => {
    if (!row.obligated) return <Typography.Text type="secondary">{row.exempt_reason_label}</Typography.Text>
    if (row.failure) return <Typography.Text type="danger">{`${row.failure.category_label}: ${row.failure.message ?? row.failure.code}`}</Typography.Text>
    if (row.hints.length) {
      // Guardian e-mail is edited by administrators only (server rule), so only they get the link.
      const contact = admin && row.hints.includes('보호자 이메일 없음')
      return (
        <Space size={4} wrap>
          <Typography.Text type="warning">{row.hints.join(' · ')}</Typography.Text>
          {contact && (
            <Button size="small" type="link" onClick={() => navigate(withReturn(`/students?contact=${row.student_id}`, `${location.pathname}${location.search}`))}>메일 주소 변경</Button>
          )}
        </Space>
      )
    }
    if (row.active_messages > 1) return <Typography.Text type="secondary">{`활성 메시지 ${row.active_messages}건 (가장 진행된 건 기준)`}</Typography.Text>
    return null
  }

  const totals = summary?.totals
  const selected = summary?.classrooms.find((c) => c.classroom_id === classroomId)
  const selectClassroom = (id: number) => { setClassroomId(id); rememberClassroom(id); setPage(1); onSelectClassroom?.(id) }

  return (
    <Space direction="vertical" size={embedded ? 'middle' : 'large'} style={{ width: '100%' }}>
      {!embedded && <PageHeader title="메시지 처리 현황" description="안내 대상별 처리 상태를 확인하고 미처리·실패 건을 해당 작업 화면에서 조치합니다." />}
      <Alert type="info" showIcon message="모의 발송 기준 현황입니다. 실제 문자·이메일은 전송되지 않으며, '완료'는 실제 학부모 수신을 뜻하지 않습니다." />
      {notice && <Alert type={notice.type} showIcon closable message={notice.text} onClose={() => setNotice(null)} />}
      <Space wrap>
        <Input aria-label="시작일" type="date" value={dateFrom} max={dateTo} onChange={(e) => { if (e.target.value) { setDateFrom(e.target.value); setPage(1) } }} style={{ width: 160 }} />
        <span>~</span>
        <Input aria-label="종료일" type="date" value={dateTo} min={dateFrom} onChange={(e) => { if (e.target.value) { setDateTo(e.target.value); setPage(1) } }} style={{ width: 160 }} />
        <Button loading={loading} onClick={() => void refresh()}>새로고침</Button>
        <Typography.Text type="secondary">처리 기한 정책: 미설정 (기한 초과 판정 안 함) · 최대 3개월</Typography.Text>
      </Space>

      {loading && !summary ? <Spin /> : !summary || !totals ? null : (
        <>
          {/* Phase 9.6: one summary instead of seven separate cards — work still to do first,
              completion as the supporting figure. */}
          <Card size="small" title={`전체 반 요약 (${summary.date_from} ~ ${summary.date_to})`}>
            <Row gutter={[24, 16]} align="middle">
              <Col xs={24} md={9}>
                <Space direction="vertical" size={4} style={{ width: '100%' }}>
                  <Space size="large" wrap>
                    <Statistic title="안내 대상" value={totals.total} suffix="건" />
                    <Statistic title={<Space size={4}>{OPS_STATUS.DONE.icon}모의 발송 완료</Space>} value={totals.done} suffix="건" />
                  </Space>
                  <Progress percent={totals.completion_rate ?? 0} size="small" status="normal" format={() => rate(totals.completion_rate)} />
                </Space>
              </Col>
              <Col xs={24} md={15}>
                <Typography.Text strong>처리가 필요한 항목</Typography.Text>
                <Row gutter={[12, 12]} style={{ marginTop: 8 }}>
                  {ATTENTION.map((key) => {
                    const value = totals[COUNT_OF[key]] as number
                    return (
                      <Col key={key} xs={12} sm={6}>
                        <Statistic title={<Space size={4}>{OPS_STATUS[key].icon}<span>{OPS_STATUS[key].label}</span></Space>} value={value} suffix="건"
                          valueStyle={value ? { color: key === 'FAILED' ? '#cf1322' : '#d46b08' } : { color: '#8c8c8c' }} />
                      </Col>
                    )
                  })}
                </Row>
                {totals.pending === 0 && totals.failed === 0 && <Typography.Text type="success">처리할 항목이 없습니다.</Typography.Text>}
              </Col>
            </Row>
          </Card>

          <Card title="반별 현황 (반을 누르면 아래 처리 목록이 바뀝니다)" size="small">
            <Table
              rowKey="classroom_id"
              size="small"
              pagination={false}
              scroll={{ x: 'max-content' }}
              dataSource={summary.classrooms}
              locale={{ emptyText: <Empty description="볼 수 있는 반이 없습니다. 관리자에게 반 배정을 요청하세요." /> }}
              rowClassName={(row) => (row.classroom_id === classroomId ? 'row-active' : '')}
              onRow={(row) => ({
                onClick: () => selectClassroom(row.classroom_id),
                style: { cursor: 'pointer', fontWeight: row.classroom_id === classroomId ? 600 : undefined },
              })}
              columns={[
                { title: '반', dataIndex: 'classroom_name', className: 'cell-nowrap' },
                { title: '안내 대상', dataIndex: 'total', className: 'cell-number' },
                { title: '완료', dataIndex: 'done', className: 'cell-number' },
                { title: '대기', className: 'cell-number', render: (_, row) => <span title={`미생성 ${row.missing} · 검토 ${row.in_review} · 발송 대기 ${row.ready_to_send}`}>{row.pending}</span> },
                { title: '실패', className: 'cell-number', render: (_, row) => (row.failed ? <Typography.Text type="danger">{row.failed}</Typography.Text> : 0) },
                { title: '완료율', className: 'cell-number', render: (_, row) => rate(row.completion_rate) },
                { title: '비대상', dataIndex: 'exempt', className: 'cell-number' },
              ]}
            />
          </Card>

          {selected && (
            <Card title={`${selected.classroom_name} 처리 목록`} size="small">
              {/* Status filter with this class's counts: the same states as the action buttons. */}
              <div role="group" aria-label="상태 필터" style={{ marginBottom: 12 }}>
                <Radio.Group
                  size="small"
                  optionType="button"
                  value={status ?? 'ALL'}
                  onChange={(event) => { setStatus(event.target.value === 'ALL' ? undefined : event.target.value); setPage(1) }}
                  options={[
                    { value: 'ALL', label: `전체 ${selected.total + selected.exempt}` },
                    ...(Object.keys(OPS_STATUS) as api.ObligationStatus[]).map((value) => ({ value, label: `${OPS_STATUS[value].label} ${selected[COUNT_OF[value]] ?? 0}` })),
                  ]}
                />
              </div>
              <Table
                rowKey={(row) => `${row.lesson_id}-${row.enrollment_id}`}
                size="small"
                loading={itemsLoading}
                dataSource={items?.items ?? []}
                scroll={{ x: true }}
                pagination={{ current: page, pageSize: PAGE_SIZE, total: items?.total ?? 0, hideOnSinglePage: true, showSizeChanger: false, onChange: setPage }}
                locale={{ emptyText: <Empty description={status ? `'${OPS_STATUS[status].label}' 상태인 항목이 없습니다.` : '이 기간에 진행된 수업이 없습니다.'} /> }}
                columns={[
                  { title: '학생', dataIndex: 'student_name', className: 'cell-nowrap' },
                  { title: '수업일', render: (_, row) => `${lessonTitle(row)}${row.topic ? ` · ${row.topic}` : ''}` },
                  { title: '상태', className: 'cell-nowrap', render: (_, row) => <OpsStatusTag status={row.status} /> },
                  { title: '처리 시각', className: 'cell-nowrap', render: (_, row) => (row.processed_at ? new Date(row.processed_at).toLocaleString() : '-') },
                  { title: '사유·참고', render: (_, row) => reason(row) },
                  { title: '조치', className: 'cell-nowrap', render: (_, row) => action(row) },
                ]}
              />
              <Typography.Text type="secondary">
                <ExperimentOutlined /> 안내 대상: 진행된 수업(완료 또는 출결 기록 있음)의 수업일 기준 수강 학생. 휴원·취소·진행 기록 없는 수업은 '안내 대상 아님'으로 따로 표시됩니다.
              </Typography.Text>
            </Card>
          )}
        </>
      )}
    </Space>
  )
}
