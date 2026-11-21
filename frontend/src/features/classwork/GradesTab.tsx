import { useCallback, useEffect, useMemo, useState } from 'react'
import { Alert, Button, Card, Empty, Form, Input, InputNumber, Modal, Select, Space, Table, Tag, Typography } from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import { toApiClientError } from '../../shared/api/ApiClientError'
import * as api from './api'
import { canWriteGrades, lessonTitle, todayLocal } from './common'
import type { ClassworkContext } from './ClassworkPage'

export { draftError } from './scoreRules'

/** One 평가 항목 (e.g. 어휘): the assessment sessions that share a name, newest first. */
type Category = { title: string; sessions: api.AssessmentListItem[] }

/**
 * 평가 관리: assessments grouped by 평가 항목 (2026-11-20).
 *
 * A score always belongs to one dated session (어휘 on 11-07, 어휘 on 11-14…), because the max score,
 * the students due and 미응시 differ per session; the workbook upload creates one session per test
 * column and lesson day. The 항목 is the session name (the workbook's test column), so the list is
 * grouped by name to show which 항목 the class has; sessions are created and corrected here, and
 * scores are viewed and corrected in the 학습 현황 grid.
 */
export function GradesTab({ classroomId, role, lessons, notify, fail }: ClassworkContext) {
  const [assessments, setAssessments] = useState<api.AssessmentListItem[]>([])
  const [listLoading, setListLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [editing, setEditing] = useState<api.Assessment | null>(null)
  const [creating, setCreating] = useState(false)
  const [createForm] = Form.useForm()
  const [editForm] = Form.useForm()
  const writable = canWriteGrades(role)

  const loadList = useCallback(async () => {
    setListLoading(true)
    try { setAssessments(await api.listAssessments(classroomId)) } catch (error) { fail(error) } finally { setListLoading(false) }
  }, [classroomId, fail])

  useEffect(() => { void loadList() }, [loadList])

  const categories = useMemo<Category[]>(() => {
    const groups = new Map<string, api.AssessmentListItem[]>()
    for (const row of assessments) groups.set(row.title, [...(groups.get(row.title) ?? []), row])
    return [...groups.entries()]
      .map(([title, sessions]) => ({ title, sessions: [...sessions].sort((a, b) => b.assessment_date.localeCompare(a.assessment_date) || b.id - a.id) }))
      .sort((a, b) => a.title.localeCompare(b.title, 'ko'))
  }, [assessments])
  const [expanded, setExpanded] = useState<string[] | null>(null)
  // All 항목 open at first (the sessions are what is edited); the user can fold them.
  const expandedKeys = expanded ?? categories.map((c) => c.title)

  const lessonOptions = lessons.filter((row) => row.status !== 'CANCELLED').map((row) => ({ value: row.id, label: `${lessonTitle(row)}${row.topic ? ` · ${row.topic}` : ''}` }))
  const lessonLabel = (id: number | null) => {
    if (id === null) return '연결 수업 없음'
    const lesson = lessons.find((row) => row.id === id)
    return lesson ? lessonTitle(lesson) : `수업 #${id}`
  }

  // Phase 9.6: most assessments come from the Excel upload, so the manual registration form opens
  // in a window (like 평가 수정) and the list keeps the full width.
  return (
    <>
      <Card
        title={`평가 항목 ${categories.length}개 · 회차 ${assessments.length}개`}
        size="small"
        extra={writable && <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreating(true)}>평가 등록</Button>}
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          <Typography.Text type="secondary">
            평가 항목은 엑셀 반 블록의 시험 열 이름(예: 어휘)입니다. 엑셀을 올릴 때마다 수업일별 회차가 하나씩 만들어지고, 점수는 그 회차에 저장됩니다(회차마다 만점·응시 대상이 다를 수 있음). 점수 확인·입력·수정은 '학습 현황' 탭에서 합니다.
          </Typography.Text>
          {!writable && <Alert type="info" showIcon message="평가를 등록·수정할 권한이 없습니다." />}
          <Table
            rowKey="title"
            size="small"
            loading={listLoading}
            dataSource={categories}
            pagination={false}
            scroll={{ x: 'max-content' }}
            expandable={{
              expandedRowKeys: expandedKeys,
              onExpandedRowsChange: (keys) => setExpanded(keys as string[]),
              expandedRowRender: (category) => (
                <Table
                  rowKey="id"
                  size="small"
                  dataSource={category.sessions}
                  pagination={false}
                  columns={[
                    { title: '평가일', dataIndex: 'assessment_date', className: 'cell-nowrap', width: 110 },
                    { title: '연결 수업', className: 'cell-nowrap', render: (_, row) => lessonLabel(row.lesson_id) },
                    { title: '만점', dataIndex: 'max_score', className: 'cell-number', width: 80 },
                    { title: '입력 현황', className: 'cell-nowrap', render: (_, row) => `점수 ${row.scored}명 · 미응시 ${row.not_taken}명` },
                    ...(writable ? [{
                      title: '관리',
                      width: 100,
                      className: 'cell-nowrap',
                      render: (_: unknown, row: api.AssessmentListItem) => (
                        <Button size="small" onClick={() => { setEditing(row); editForm.setFieldsValue({ title: row.title, max_score: row.max_score }) }}>평가 수정</Button>
                      ),
                    }] : []),
                  ]}
                />
              ),
            }}
            locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="등록된 평가가 없습니다. 엑셀 업로드나 '평가 등록'으로 만들 수 있습니다." /> }}
            columns={[
              { title: '평가 항목', dataIndex: 'title', className: 'cell-keep-all', onCell: () => ({ style: { minWidth: 160 } }) },
              { title: '회차', className: 'cell-number', width: 70, render: (_, c) => `${c.sessions.length}회` },
              {
                title: '만점', className: 'cell-nowrap',
                render: (_, c) => {
                  const values = [...new Set(c.sessions.map((s) => s.max_score))].sort((a, b) => a - b)
                  return values.length === 1 ? values[0] : <Space size={4}>{values.join(' · ')}<Tag>회차마다 다름</Tag></Space>
                },
              },
              { title: '최근 평가일', className: 'cell-nowrap', render: (_, c) => c.sessions[0]?.assessment_date ?? '-' },
            ]}
          />
        </Space>
      </Card>
      <Modal
        title="평가 등록"
        open={creating}
        okText="등록"
        cancelText="취소"
        confirmLoading={saving}
        onCancel={() => setCreating(false)}
        onOk={() => createForm.submit()}
        destroyOnHidden
      >
        <Form
          form={createForm}
          name="assessmentCreate"
          layout="vertical"
          initialValues={{ assessment_date: todayLocal() }}
          onFinish={async (values) => {
            setSaving(true)
            try {
              const created = await api.createAssessment(classroomId, {
                title: values.title, assessment_date: values.assessment_date, max_score: values.max_score, lesson_id: values.lesson_id ?? null,
              })
              createForm.resetFields()
              setCreating(false)
              notify({ type: 'success', text: `${created.title} 평가를 등록했습니다. 점수는 '학습 현황'에서 입력·수정하세요.` })
              await loadList()
            } catch (error) { fail(error) } finally { setSaving(false) }
          }}
        >
          <Form.Item name="title" label="평가명" rules={[{ required: true, whitespace: true, message: '평가명을 입력해주세요.' }]}
            extra="기존 평가 항목의 회차를 추가하려면 이름을 똑같이 입력하세요(아래 항목을 누르면 입력됩니다). 다른 이름은 새 항목이 됩니다.">
            <Input maxLength={100} placeholder="예: 3단원 평가" />
          </Form.Item>
          {categories.length > 0 && (
            <Space size={[4, 4]} wrap style={{ marginBottom: 12 }}>
              {categories.map((c) => (
                <Tag key={c.title} style={{ cursor: 'pointer' }} onClick={() => createForm.setFieldsValue({ title: c.title, max_score: c.sessions[0]?.max_score })}>{c.title}</Tag>
              ))}
            </Space>
          )}
          <Space wrap>
            <Form.Item name="assessment_date" label="평가일" rules={[{ required: true }]}><Input type="date" /></Form.Item>
            <Form.Item name="max_score" label="만점" rules={[{ required: true, message: '만점을 입력해주세요.' }]}>
              <InputNumber min={0.01} max={9999.99} precision={2} step={1} />
            </Form.Item>
          </Space>
          <Form.Item name="lesson_id" label="연결 수업 (선택)"><Select allowClear options={lessonOptions} placeholder="수업과 연결하지 않음" /></Form.Item>
        </Form>
      </Modal>
      <Modal
        title="평가 수정"
        open={editing !== null}
        okText="저장"
        cancelText="취소"
        confirmLoading={saving}
        onCancel={() => setEditing(null)}
        onOk={() => editForm.submit()}
        destroyOnHidden
      >
        <Typography.Paragraph type="secondary">입력된 점수보다 낮은 만점으로는 바꿀 수 없습니다.</Typography.Paragraph>
        <Form
          form={editForm}
          layout="vertical"
          onFinish={async (values) => {
            if (!editing) return
            const changes: { title?: string; max_score?: number } = {}
            if (values.title.trim() !== editing.title) changes.title = values.title
            if (values.max_score !== editing.max_score) changes.max_score = values.max_score
            if (Object.keys(changes).length === 0) { setEditing(null); return }
            setSaving(true)
            try {
              await api.updateAssessment(editing.id, { version: editing.version, ...changes })
              setEditing(null)
              notify({ type: 'success', text: '평가 정보를 수정했습니다.' })
              await loadList()
            } catch (error) {
              const apiError = toApiClientError(error)
              notify({ type: apiError.code === 'VERSION_CONFLICT' ? 'warning' : 'error', text: apiError.message })
            } finally { setSaving(false) }
          }}
        >
          <Form.Item name="title" label="평가명" rules={[{ required: true, whitespace: true }]}><Input maxLength={100} /></Form.Item>
          <Form.Item name="max_score" label="만점" rules={[{ required: true }]}><InputNumber min={0.01} max={9999.99} precision={2} /></Form.Item>
        </Form>
      </Modal>
    </>
  )
}
