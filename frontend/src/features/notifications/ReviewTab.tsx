import { useCallback, useEffect, useRef, useState } from 'react'
import { Alert, Button, Card, Col, Descriptions, Empty, Input, Popconfirm, Row, Segmented, Select, Space, Spin, Table, Tag, Timeline, Typography } from 'antd'
import { LeftOutlined, RightOutlined } from '@ant-design/icons'
import { toApiClientError } from '../../shared/api/ApiClientError'
import * as classwork from '../classwork/api'
import { AttendanceTag, lessonTitle } from '../classwork/common'
import * as api from './api'
import { BatchReview } from './BatchReview'
import { EVENT_LABEL, STATUS, StatusTag, canApprove, newRequestKey } from './common'
import type { NotificationContext } from './NotificationsPage'

const EDITABLE: api.NotificationStatus[] = ['DRAFT', 'READY_FOR_REVIEW']

/** What the message was generated from: the lesson's current attendance, grades and scores. */
type Source = { cell: classwork.ProgressCell | null; column: classwork.ProgressColumn | null }

/**
 * Phase 9.5: list on the left, and on the right the generation source next to the message, so a
 * message can be checked without opening another screen; previous/next moves through the list.
 * Source data reuses the existing 학습 현황 API (one request per lesson day, cached while the
 * list is unchanged); a request counter keeps a slow answer from showing another student's data.
 */
export function ReviewTab({ classroomId, classroomName, role, lessons, notify, fail, focus }: NotificationContext) {
  // 2026-11-20: a class lesson is reviewed, confirmed and mock-sent together by default; the
  // one-by-one view stays for editing, revoking, cancelling and messages opened from elsewhere.
  const [mode, setMode] = useState<'batch' | 'single'>(focus?.notificationId ? 'single' : 'batch')
  const [status, setStatus] = useState<api.NotificationStatus>()
  const [lessonId, setLessonId] = useState<number>()
  const [rows, setRows] = useState<api.NotificationItem[]>([])
  const [loading, setLoading] = useState(false)
  const [detail, setDetail] = useState<api.NotificationDetail | null>(null)
  const [source, setSource] = useState<Source | null | 'error'>(null)
  const [body, setBody] = useState('')
  const [busy, setBusy] = useState(false)
  const sendKey = useRef<string | null>(null)
  const latest = useRef(0)
  const grids = useRef(new Map<string, Promise<classwork.ClassProgress>>())

  const load = useCallback(async () => {
    setLoading(true)
    grids.current.clear() // data may have changed: fetch the source again
    try { setRows(await api.listNotifications(classroomId, { lessonId, status })) } catch (error) { fail(error) } finally { setLoading(false) }
  }, [classroomId, lessonId, status, fail])

  useEffect(() => { void load() }, [load])

  const loadSource = useCallback(async (data: api.NotificationDetail, request: number) => {
    setSource(null)
    try {
      const day = data.lesson_date
      if (!grids.current.has(day)) grids.current.set(day, classwork.getProgress(classroomId, day, day))
      const grid = await grids.current.get(day)!
      if (request !== latest.current) return
      const index = grid.columns.findIndex((c) => c.lesson_id === data.lesson_id)
      const student = grid.students.find((s) => s.enrollment_id === data.enrollment_id)
      setSource({ column: grid.columns[index] ?? null, cell: index >= 0 && student ? student.cells[index] : null })
    } catch {
      grids.current.delete(data.lesson_date)
      if (request === latest.current) setSource('error')
    }
  }, [classroomId])

  const show = useCallback((data: api.NotificationDetail) => {
    const request = ++latest.current
    setDetail(data); setBody(data.body)
    void loadSource(data, request)
  }, [loadSource])

  const open = useCallback(async (id: number) => {
    try { show(await api.getNotification(id)); sendKey.current = null } catch (error) { fail(error) }
  }, [fail, show])

  // Opened from '메시지 처리 현황' with a message id: show that message straight away.
  useEffect(() => { if (focus?.notificationId) { setMode('single'); void open(focus.notificationId) } }, [focus?.notificationId, open])

  const position = detail ? rows.findIndex((row) => row.id === detail.id) : -1
  const step = (offset: number) => {
    const next = rows[position + offset]
    if (next) void open(next.id)
  }

  const act = async (work: () => Promise<api.NotificationDetail>, success: string, thenNext = false) => {
    setBusy(true)
    try {
      const data = await work()
      notify({ type: 'success', text: success })
      await load()
      const next = rows[position + 1]
      if (thenNext && next) await open(next.id)
      else show(data)
    } catch (error) {
      const apiError = toApiClientError(error)
      notify({ type: apiError.code.endsWith('CONFLICT') || apiError.code === 'SOURCE_CHANGED' ? 'warning' : 'error', text: apiError.message })
      if (detail && ['VERSION_CONFLICT', 'SOURCE_CHANGED', 'INVALID_TRANSITION'].includes(apiError.code)) await open(detail.id)
    } finally {
      setBusy(false)
    }
  }

  const runMockSend = async (retry = false) => {
    if (!detail) return
    sendKey.current ??= newRequestKey() // the same key is reused if this click is retried
    setBusy(true)
    try {
      const result = await (retry ? api.retryMockSend : api.mockSend)(detail.id, sendKey.current)
      sendKey.current = null
      show(result.notification)
      notify(result.attempt.result === 'MOCK_SUCCESS'
        ? { type: 'success', text: '모의 발송에 성공했습니다. 실제 문자·이메일은 전송되지 않았습니다.' }
        : { type: 'error', text: `모의 발송 실패: ${result.attempt.error_message ?? result.attempt.error_code}` })
      await load()
    } catch (error) {
      const apiError = toApiClientError(error)
      if (apiError.code !== 'CLIENT_ERROR') sendKey.current = null
      notify({ type: apiError.code === 'SOURCE_CHANGED' ? 'warning' : 'error', text: apiError.message })
      if (apiError.code.endsWith('CONFLICT') || ['ALREADY_MOCK_SENT', 'NOT_FAILED'].includes(apiError.code)) await open(detail.id)
    } finally {
      setBusy(false)
    }
  }

  const approver = canApprove(role)
  const editable = !!detail && EDITABLE.includes(detail.status)
  const dirty = !!detail && body.trim() !== detail.body
  const lesson = detail ? lessons.find((row) => row.id === detail.lesson_id) : undefined
  const sendCheck = detail && (
    <Space direction="vertical" size={2}>
      <Typography.Text>{`${detail.student_name} · ${detail.recipient_email} · 1건`}</Typography.Text>
      <Typography.Text>실제 문자·이메일은 전송되지 않으며 결과만 기록됩니다.</Typography.Text>
    </Space>
  )
  const modeSwitch = (
    <Segmented aria-label="검토 방식" value={mode} onChange={(value) => setMode(value as 'batch' | 'single')}
      options={[{ label: '반 일괄 처리', value: 'batch' }, { label: '한 건씩', value: 'single' }]} />
  )

  if (mode === 'batch') {
    return (
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        {modeSwitch}
        <BatchReview key={classroomId} role={role} lessons={lessons} notify={notify} fail={fail} initialLessonId={focus?.lessonId}
          onOpen={(id) => { setMode('single'); void open(id) }} />
      </Space>
    )
  }

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
    {modeSwitch}
    <Row gutter={[16, 16]}>
      <Col xs={24} lg={9}>
        <Card title="메시지 목록" size="small">
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <Space wrap>
              <Select aria-label="상태 필터" allowClear placeholder="전체 상태" style={{ width: 180 }} value={status} onChange={setStatus}
                options={(Object.keys(STATUS) as api.NotificationStatus[]).map((value) => ({ value, label: STATUS[value].label }))} />
              <Select aria-label="수업 필터" allowClear placeholder="전체 수업" style={{ width: 180 }} value={lessonId} onChange={setLessonId}
                options={lessons.map((row) => ({ value: row.id, label: lessonTitle(row) }))} />
              <Button onClick={() => void load()}>새로고침</Button>
            </Space>
            <Table
              rowKey="id"
              size="small"
              loading={loading}
              dataSource={rows}
              pagination={{ pageSize: 20, hideOnSinglePage: true }}
              scroll={{ x: true }}
              locale={{ emptyText: <Empty description="메시지가 없습니다. '엑셀 업로드'나 '누락·예외 생성'에서 초안을 만드세요." /> }}
              onRow={(row) => ({ onClick: () => void open(row.id), style: { cursor: 'pointer', background: row.id === detail?.id ? '#e6f4ff' : undefined } })}
              columns={[
                { title: '학생', dataIndex: 'student_name' },
                { title: '수업', render: (_, row) => lessonTitle({ lesson_date: row.lesson_date, session_no: row.session_no, exam_round: null }) },
                { title: '상태', render: (_, row) => <StatusTag status={row.status} /> },
              ]}
            />
          </Space>
        </Card>
      </Col>

      <Col xs={24} lg={15}>
        {!detail ? (
          <Card size="small"><Empty description="왼쪽 목록에서 학생을 선택하면 생성 근거와 메시지를 함께 보여줍니다." /></Card>
        ) : (
          <Card
            size="small"
            title={`${detail.student_name} · ${lessonTitle({ lesson_date: detail.lesson_date, session_no: detail.session_no, exam_round: null })}`}
            extra={(
              <Space>
                <Typography.Text type="secondary">{position >= 0 ? `${position + 1} / ${rows.length}` : ''}</Typography.Text>
                <Button size="small" icon={<LeftOutlined />} disabled={position <= 0 || busy} onClick={() => step(-1)}>이전</Button>
                <Button size="small" disabled={position < 0 || position >= rows.length - 1 || busy} onClick={() => step(1)}>다음 <RightOutlined /></Button>
              </Space>
            )}
          >
            <Row gutter={[16, 16]}>
              <Col xs={24} md={10}>
                <Typography.Title level={5}>생성 근거</Typography.Title>
                <Descriptions size="small" column={1} className="review-source" items={[
                  { key: 'c', label: '반', children: classroomName ?? '-' },
                  { key: 'l', label: '수업', children: lessonTitle({ lesson_date: detail.lesson_date, session_no: detail.session_no, exam_round: lesson?.exam_round ?? null }) },
                  { key: 't', label: '수업 주제', children: lesson?.topic || (source && source !== 'error' ? source.column?.topic : null) || <Typography.Text type="secondary">미입력</Typography.Text> },
                  { key: 'p', label: '템플릿', children: detail.template_name },
                  ...(source === null ? [{ key: 'x', label: '출결·성적', children: <Spin size="small" /> }]
                    : source === 'error' ? [{ key: 'x', label: '출결·성적', children: <Typography.Text type="danger">근거 데이터를 불러오지 못했습니다.</Typography.Text> }]
                    : [
                      { key: 'a', label: '출결', children: <AttendanceTag status={source.cell?.attendance_status ?? null} /> },
                      { key: 'g', label: '예습/주간', children: `${source.cell?.prework_grade ?? '-'} / ${source.cell?.weekly_grade ?? '-'}` },
                      ...(source.column?.assessments ?? []).map((assessment) => {
                        const score = source.cell?.scores.find((s) => s.assessment_id === assessment.id)
                        return {
                          key: `s${assessment.id}`,
                          label: assessment.title,
                          children: !score ? <Typography.Text type="secondary">미입력</Typography.Text>
                            : score.result_status === 'NOT_TAKEN' ? '미응시' : `${score.score} / ${assessment.max_score}`,
                        }
                      }),
                    ]),
                ]} />
                {source !== null && source !== 'error' && (
                  <Typography.Text type="secondary">현재 저장된 값입니다. 생성 후 값이 바뀌면 오른쪽에 경고가 표시됩니다.</Typography.Text>
                )}
              </Col>
              <Col xs={24} md={14} className="review-body">
                <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                  <Descriptions size="small" column={1} items={[
                    { key: 's', label: '상태', children: <StatusTag status={detail.status} /> },
                    { key: 'r', label: '수신 주소', children: detail.recipient_email },
                    { key: 'a', label: '확정자', children: detail.approved_by ? `${detail.approved_by} · ${new Date(detail.approved_at ?? '').toLocaleString()}` : '-' },
                  ]} />
                  {detail.source_changed && (
                    <Alert type="warning" showIcon message={editable
                      ? '생성 후 수업·출결·성적 또는 연락처가 바뀌었습니다. 이 메시지는 확정할 수 없으니 취소하고 다시 생성하세요.'
                      : '확정 후 수업·출결·성적 또는 연락처가 바뀌었습니다. 이 내용으로는 모의 발송할 수 없으니 메시지를 취소하고 다시 생성하세요.'} />
                  )}
                  <Input.TextArea aria-label="메시지 본문" value={body} onChange={(event) => setBody(event.target.value)} rows={9} maxLength={2000} showCount disabled={!editable || busy} />
                  {!editable && detail.status === 'APPROVED' && <Typography.Text type="secondary">확정된 본문은 수정할 수 없습니다. 수정하려면 확정을 취소하세요.</Typography.Text>}
                  <Space wrap>
                    {editable && <Button disabled={!dirty || busy} onClick={() => void act(() => api.editNotification(detail.id, detail.version, body), '본문을 저장했습니다.')}>본문 저장</Button>}
                    {detail.status === 'DRAFT' && <Button disabled={dirty || busy} onClick={() => void act(() => api.transition(detail.id, 'submit', detail.version), '검토를 요청했습니다.')}>검토 요청</Button>}
                    {approver && editable && (
                      <>
                        <Button type="primary" disabled={dirty || busy || detail.source_changed} onClick={() => void act(() => api.transition(detail.id, 'approve', detail.version), '내용을 확정했습니다. 이제 모의 발송할 수 있습니다.')}>내용 확정</Button>
                        {position >= 0 && position < rows.length - 1 && (
                          <Button disabled={dirty || busy || detail.source_changed} onClick={() => void act(() => api.transition(detail.id, 'approve', detail.version), '내용을 확정했습니다. 다음 학생으로 이동합니다.', true)}>확정 후 다음 학생</Button>
                        )}
                      </>
                    )}
                    {approver && detail.status === 'APPROVED' && (
                      <>
                        <Popconfirm title="모의 발송을 실행할까요?" description={sendCheck} okText="모의 발송" cancelText="닫기" onConfirm={() => void runMockSend()}>
                          <Button type="primary" loading={busy} disabled={detail.source_changed}>모의 발송</Button>
                        </Popconfirm>
                        <Button disabled={busy} onClick={() => void act(() => api.transition(detail.id, 'revoke', detail.version), '확정을 취소했습니다.')}>확정 취소</Button>
                      </>
                    )}
                    {(editable || (approver && ['APPROVED', 'MOCK_FAILED'].includes(detail.status))) && (
                      <Popconfirm title="이 메시지를 취소할까요?" okText="메시지 취소" cancelText="닫기" onConfirm={() => void act(() => api.transition(detail.id, 'cancel', detail.version), '메시지를 취소했습니다.')}>
                        <Button danger disabled={busy}>메시지 취소</Button>
                      </Popconfirm>
                    )}
                  </Space>
                  {detail.status === 'MOCK_FAILED' && approver && (
                    <Space direction="vertical" size={4}>
                      <Popconfirm title="모의 발송을 재시도할까요?" description="확정된 본문 그대로 다시 모의 발송합니다. 이전 실패 기록은 남습니다. 실제 문자·이메일은 전송되지 않습니다." okText="재시도" cancelText="닫기" onConfirm={() => void runMockSend(true)}>
                        <Button type="primary" loading={busy} disabled={detail.source_changed}>모의 발송 재시도</Button>
                      </Popconfirm>
                      <Typography.Text type="secondary">생성 후 출결·성적·연락처가 바뀌었다면 재시도할 수 없습니다. 이때는 메시지를 취소하고 다시 생성하세요.</Typography.Text>
                    </Space>
                  )}
                </Space>
              </Col>
            </Row>

            <Typography.Title level={5}>모의 발송 시도</Typography.Title>
            {detail.attempts.length === 0 ? <Typography.Text type="secondary">시도 없음</Typography.Text> : (
              <Table rowKey="id" size="small" pagination={false} dataSource={detail.attempts} scroll={{ x: true }} columns={[
                { title: '시각', render: (_, a) => new Date(a.attempted_at).toLocaleString() },
                { title: '결과', render: (_, a) => a.result === 'MOCK_SUCCESS' ? <Tag color="cyan">모의 성공 (실제 미전송)</Tag> : <Tag color="red">모의 실패</Tag> },
                { title: '사유', render: (_, a) => a.error_message ?? '-' },
                { title: '요청자', render: (_, a) => a.requested_by ?? '-' },
              ]} />
            )}
            <Typography.Title level={5} style={{ marginTop: 16 }}>처리 이력</Typography.Title>
            <Timeline items={detail.history.map((event) => ({
              children: `${new Date(event.created_at).toLocaleString()} · ${EVENT_LABEL[event.event_type] ?? event.event_type} · ${event.actor ?? '-'}`,
            }))} />
          </Card>
        )}
      </Col>
    </Row>
    </Space>
  )
}
