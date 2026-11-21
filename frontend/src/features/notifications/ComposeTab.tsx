import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { Alert, Button, Card, Col, Empty, Row, Select, Space, Table, Tag, Typography } from 'antd'
import { CheckCircleOutlined, EditOutlined, StopOutlined, WarningOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router'
import { withReturn } from '../../shared/workingContext'
import { canWriteLessons, lessonTitle } from '../classwork/common'
import * as api from './api'
import type { NotificationContext } from './NotificationsPage'

function ItemStatus({ item }: { item: api.PreviewItem }) {
  if (item.existing_notification_id) return <Tag icon={<WarningOutlined />}>이미 메시지 있음</Tag>
  return item.ok ? <Tag color="green" icon={<CheckCircleOutlined />}>생성 가능</Tag> : <Tag color="red" icon={<StopOutlined />}>생성 불가</Tag>
}

/**
 * 누락·예외 생성. Phase 9.6: the students are listed with their state and reasons, and the selected
 * student's message (or what blocks it, with a link to the screen that fixes it) is shown beside
 * the list — instead of every full message body inside the table.
 */
export function ComposeTab({ classroomId, role, lessons, notify, fail, openReview, openTab, openMessage, focus }: NotificationContext) {
  const navigate = useNavigate()
  const admin = role === 'ADMIN'
  const [templates, setTemplates] = useState<api.Template[]>([])
  // Opened from '메시지 운영' for a missing draft (or from an upload result by day): preselected.
  const [lessonId, setLessonId] = useState<number | undefined>(focus?.lessonId)
  const [templateId, setTemplateId] = useState<number>()
  const [result, setResult] = useState<api.PreviewResponse | null>(null)
  const [selected, setSelected] = useState<number[]>([])
  const [activeId, setActiveId] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const appliedDay = useRef<string | undefined>(undefined)

  useEffect(() => {
    api.listTemplates().then((items) => {
      const active = items.filter((item) => item.is_active)
      setTemplates(active)
      setTemplateId((current) => current ?? active[0]?.id)
    }).catch(fail)
  }, [fail])

  useEffect(() => { if (focus?.lessonId) setLessonId(focus.lessonId) }, [focus?.lessonId])
  // An upload result knows only the lesson day: its first session (where uploads are saved).
  useEffect(() => {
    if (!focus?.day || focus.lessonId || appliedDay.current === focus.day) return
    const onDay = lessons.filter((row) => row.lesson_date === focus.day && row.status !== 'CANCELLED')
    const lesson = onDay.find((row) => row.session_no === 1) ?? onDay[0]
    if (lesson) { appliedDay.current = focus.day; setLessonId(lesson.id) }
  }, [focus?.day, focus?.lessonId, lessons])

  useEffect(() => { setResult(null); setSelected([]); setActiveId(null) }, [lessonId, templateId])

  const items = useMemo(() => result?.items ?? [], [result])
  const usable = useMemo(() => items.filter((item) => item.ok && !item.existing_notification_id), [items])
  const counts = useMemo(() => ({
    ready: usable.length,
    existing: items.filter((item) => item.existing_notification_id).length,
    blocked: items.filter((item) => !item.ok && !item.existing_notification_id).length,
  }), [items, usable])
  const active = items.find((item) => item.enrollment_id === activeId) ?? null
  const lesson = lessons.find((row) => row.id === lessonId)

  const runPreview = async () => {
    if (!lessonId || !templateId) return
    setBusy(true)
    try {
      const data = await api.preview(lessonId, templateId)
      setResult(data)
      setSelected(data.items.filter((item) => item.ok && !item.existing_notification_id).map((item) => item.enrollment_id))
      setActiveId(data.items[0]?.enrollment_id ?? null)
    } catch (error) { fail(error) } finally { setBusy(false) }
  }

  const save = async () => {
    if (!lessonId || !templateId || selected.length === 0) return
    setBusy(true)
    try {
      const saved = await api.createDrafts(lessonId, templateId, selected)
      const skipped = saved.skipped.length ? ` · 건너뜀 ${saved.skipped.length}명` : ''
      notify({ type: 'success', text: `초안 ${saved.created.length}건을 저장했습니다${skipped}. '검토·발송' 탭에서 확인·수정하세요.` })
      setResult(null)
      setSelected([])
      if (saved.created.length) openReview()
    } catch (error) { fail(error) } finally { setBusy(false) }
  }

  /** Where to fix a reason the server gave (texts from notifications/engine.py); null = no screen for it. */
  const fixFor = (item: api.PreviewItem, issue: string): ReactNode => {
    if (!lessonId || !lesson) return null
    const back = `/notifications?classroom=${classroomId}&tab=compose&lesson=${lessonId}`
    const go = (label: string, path: string) => (
      <Button size="small" icon={<EditOutlined />} onClick={() => navigate(withReturn(path, back))}>{label}</Button>
    )
    const ask = (text: string) => <Typography.Text type="secondary">{text}</Typography.Text>
    if (issue.includes('보호자 이메일')) {
      return admin && item.student_id ? go('메일 주소 변경', `/students?contact=${item.student_id}`) : ask('관리자에게 보호자 이메일 등록을 요청하세요.')
    }
    if (issue.startsWith('출결 미입력')) return go('출결 입력', `/classes?classroom=${classroomId}&tab=attendance&lesson=${lessonId}`)
    if (issue.includes('성적 미입력')) return go('성적 입력 (학습 현황)', `/classes?classroom=${classroomId}&tab=progress&day=${lesson.lesson_date}`)
    if (issue.startsWith('수업 주제 미입력')) {
      return canWriteLessons(role) ? go('수업 주제 입력', `/classes?classroom=${classroomId}&tab=lessons`) : ask('선생님·관리자에게 수업 주제 입력을 요청하세요.')
    }
    if (issue.startsWith('생성된 메시지가')) {
      return admin ? <Button size="small" onClick={() => openTab('templates')}>템플릿 확인</Button> : ask('관리자에게 템플릿 확인을 요청하세요.')
    }
    return null
  }

  if (!templates.length) return <Card><Empty description="사용할 수 있는 템플릿이 없습니다. 관리자에게 템플릿 등록을 요청하세요." /></Card>

  return (
    <Card title="누락·예외 수동 생성">
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        <Space wrap>
          <Select aria-label="수업 선택" placeholder="수업 선택" style={{ width: 300 }} value={lessonId}
            options={lessons.map((row) => ({ value: row.id, label: `${lessonTitle(row)}${row.topic ? ` · ${row.topic}` : ''}${row.status === 'CANCELLED' ? ' [취소]' : ''}` }))}
            onChange={setLessonId} />
          <Select aria-label="템플릿 선택" style={{ width: 220 }} value={templateId}
            options={templates.map((row) => ({ value: row.id, label: row.name }))} onChange={setTemplateId} />
          <Button type="primary" loading={busy} disabled={!lessonId || !templateId} onClick={() => void runPreview()}>미리보기</Button>
        </Space>
        <Typography.Text type="secondary">
          보통은 '엑셀 업로드'로 초안이 자동 생성됩니다. 누락된 학생에게만 사용하세요. 미리보기는 저장되지 않으며, 생성 불가 학생은 저장 대상에서 빠집니다. 사유를 고친 뒤 '미리보기'를 다시 누르면 재검증됩니다.
        </Typography.Text>
        {result && (
          <>
            <Space wrap>
              <Typography.Text>{`생성 가능 ${counts.ready}명 · 이미 메시지 있음 ${counts.existing}명 · 생성 불가 ${counts.blocked}명`}</Typography.Text>
              <Button type="primary" loading={busy} disabled={selected.length === 0} onClick={() => void save()}>
                {`선택 학생 초안 저장 (${selected.length}명)`}
              </Button>
            </Space>
            {usable.length === 0 && <Alert type="warning" showIcon message="저장할 수 있는 학생이 없습니다. 학생을 눌러 사유와 수정 화면을 확인하세요." />}
            <Row gutter={[16, 16]}>
              <Col xs={24} lg={10}>
                <Table
                  rowKey="enrollment_id"
                  size="small"
                  dataSource={items}
                  pagination={false}
                  scroll={{ x: 'max-content', y: 520 }}
                  locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="이 수업의 대상 학생이 없습니다." /> }}
                  rowClassName={(row) => (row.enrollment_id === activeId ? 'row-active' : '')}
                  onRow={(row) => ({ onClick: () => setActiveId(row.enrollment_id), style: { cursor: 'pointer' } })}
                  rowSelection={{
                    selectedRowKeys: selected,
                    onChange: (keys) => setSelected(keys as number[]),
                    getCheckboxProps: (row) => ({ disabled: !row.ok || !!row.existing_notification_id, 'aria-label': `${row.student_name ?? row.enrollment_id} 선택` }),
                  }}
                  columns={[
                    { title: '학생', className: 'cell-nowrap', render: (_, row) => row.student_name ?? `수강 #${row.enrollment_id}` },
                    { title: '상태', className: 'cell-nowrap', render: (_, row) => <ItemStatus item={row} /> },
                    {
                      title: '확인 사항',
                      onCell: () => ({ style: { minWidth: 180 } }),
                      render: (_, row) => row.issues.length > 0
                        ? <Typography.Text type="danger">{row.issues.join(' · ')}</Typography.Text>
                        : row.warnings.length > 0 ? <Typography.Text type="warning">{`참고 ${row.warnings.length}건`}</Typography.Text>
                        : <Typography.Text type="secondary">-</Typography.Text>,
                    },
                  ]}
                />
              </Col>
              <Col xs={24} lg={14}>
                {!active ? (
                  <Card size="small"><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="왼쪽 목록에서 학생을 선택하면 메시지 미리보기와 사유를 보여줍니다." /></Card>
                ) : (
                  <Card size="small" title={active.student_name ?? `수강 #${active.enrollment_id}`} extra={<ItemStatus item={active} />}>
                    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                      {active.existing_notification_id && (
                        <Alert type="info" showIcon message="이 수업·템플릿의 메시지가 이미 있어 새로 만들지 않습니다(중복 방지)."
                          action={<Button size="small" onClick={() => openMessage(active.existing_notification_id!)}>기존 메시지 검토</Button>} />
                      )}
                      {active.issues.length > 0 && (
                        <Space direction="vertical" size={6} style={{ width: '100%' }}>
                          <Typography.Text strong>생성할 수 없는 이유</Typography.Text>
                          {active.issues.map((issue) => (
                            <Space key={issue} wrap>
                              <Typography.Text type="danger">{issue}</Typography.Text>
                              {fixFor(active, issue)}
                            </Space>
                          ))}
                        </Space>
                      )}
                      {active.warnings.map((warning) => <Typography.Text key={warning} type="warning">{warning}</Typography.Text>)}
                      {active.ok && active.body
                        ? <pre className="message-preview" style={{ minHeight: 160 }}>{active.body}</pre>
                        : !active.existing_notification_id && <Typography.Text type="secondary">사유를 해결한 뒤 '미리보기'를 다시 누르면 이 학생의 메시지를 확인할 수 있습니다.</Typography.Text>}
                    </Space>
                  </Card>
                )}
              </Col>
            </Row>
          </>
        )}
      </Space>
    </Card>
  )
}
