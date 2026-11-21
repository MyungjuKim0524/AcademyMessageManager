import { useState } from 'react'
import { Button, Card, Col, Empty, Form, Input, InputNumber, Modal, Row, Select, Space, Table, Typography } from 'antd'
import { toApiClientError } from '../../shared/api/ApiClientError'
import * as api from './api'
import { LESSON_STATUS, LessonStatusTag, canWriteLessons, todayLocal } from './common'
import type { ClassworkContext } from './ClassworkPage'

const blank = (value: string | undefined | null) => (value && value.trim() ? value.trim() : null)

export function LessonsTab({ classroomId, role, lessons, lessonsLoading, reloadLessons, notify, fail }: ClassworkContext) {
  const [createForm] = Form.useForm()
  const [editForm] = Form.useForm()
  const [editing, setEditing] = useState<api.Lesson | null>(null)
  const [saving, setSaving] = useState(false)
  const writable = canWriteLessons(role)

  const handleError = async (error: unknown) => {
    const apiError = toApiClientError(error)
    if (apiError.code === 'VERSION_CONFLICT') {
      notify({ type: 'warning', text: apiError.message })
      setEditing(null)
      await reloadLessons()
    } else {
      fail(error)
    }
  }

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      {writable && (
        <Card title="수업 등록">
          <Form
            form={createForm}
            layout="vertical"
            initialValues={{ lesson_date: todayLocal(), session_no: 1, status: 'SCHEDULED' }}
            onFinish={async (values) => {
              setSaving(true)
              try {
                const created = await api.createLesson(classroomId, {
                  lesson_date: values.lesson_date, session_no: values.session_no, exam_round: blank(values.exam_round), topic: blank(values.topic),
                  memo: blank(values.memo), status: values.status,
                })
                createForm.resetFields()
                notify({ type: 'success', text: `${created.lesson_date} 수업을 등록했습니다.` })
                await reloadLessons()
              } catch (error) {
                await handleError(error)
              } finally {
                setSaving(false)
              }
            }}
          >
            <Row gutter={16}>
              <Col xs={24} md={5}><Form.Item name="lesson_date" label="수업일" rules={[{ required: true }]}><Input type="date" /></Form.Item></Col>
              <Col xs={12} md={3}><Form.Item name="session_no" label="교시" tooltip="같은 날 같은 반 수업이 여러 번이면 1, 2, 3…으로 구분합니다." rules={[{ required: true }]}><InputNumber min={1} max={9} precision={0} /></Form.Item></Col>
              <Col xs={12} md={4}><Form.Item name="exam_round" label="시험 회차 (선택)"><Input maxLength={50} /></Form.Item></Col>
              <Col xs={24} md={6}><Form.Item name="topic" label="수업 주제"><Input maxLength={200} placeholder="예: 이차함수의 그래프" /></Form.Item></Col>
              <Col xs={24} md={6}>
                <Form.Item name="status" label="상태"><Select options={[{ value: 'SCHEDULED', label: '예정' }, { value: 'COMPLETED', label: '완료' }]} /></Form.Item>
              </Col>
            </Row>
            <Form.Item name="memo" label="수업 메모"><Input.TextArea maxLength={2000} rows={2} /></Form.Item>
            <Button type="primary" htmlType="submit" loading={saving}>수업 등록</Button>
          </Form>
        </Card>
      )}

      <Card title="수업 목록">
        <Table
          rowKey="id"
          size="middle"
          loading={lessonsLoading}
          dataSource={lessons}
          pagination={{ pageSize: 20, hideOnSinglePage: true }}
          scroll={{ x: true }}
          locale={{ emptyText: <Empty description="등록된 수업이 없습니다." /> }}
          columns={[
            { title: '수업일', dataIndex: 'lesson_date' },
            { title: '교시', dataIndex: 'session_no', render: (value) => `${value}교시` },
            { title: '시험 회차', dataIndex: 'exam_round', render: (value) => value ?? '-' },
            { title: '주제', dataIndex: 'topic', render: (value) => value ?? <Typography.Text type="secondary">-</Typography.Text> },
            { title: '상태', dataIndex: 'status', render: (status) => <LessonStatusTag status={status} /> },
            { title: '출결 기록', dataIndex: 'attendance_recorded', render: (count) => `${count}명` },
            ...(writable ? [{
              title: '관리',
              render: (_: unknown, row: api.LessonListItem) => (
                <Button size="small" onClick={() => { setEditing(row); editForm.setFieldsValue({ ...row, exam_round: row.exam_round ?? '', topic: row.topic ?? '', memo: row.memo ?? '' }) }}>수정</Button>
              ),
            }] : []),
          ]}
        />
      </Card>

      <Modal
        title="수업 수정"
        open={editing !== null}
        okText="저장"
        cancelText="취소"
        confirmLoading={saving}
        onCancel={() => setEditing(null)}
        onOk={() => editForm.submit()}
        destroyOnHidden
      >
        <Typography.Paragraph type="secondary">출결이나 평가가 연결된 수업은 날짜·교시·시험 회차를 바꾸거나 취소할 수 없습니다.</Typography.Paragraph>
        <Form
          form={editForm}
          layout="vertical"
          onFinish={async (values) => {
            if (!editing) return
            const next = {
              lesson_date: values.lesson_date, session_no: values.session_no, exam_round: blank(values.exam_round), topic: blank(values.topic),
              memo: blank(values.memo), status: values.status as api.LessonStatus,
            }
            const changed = Object.fromEntries(Object.entries(next).filter(([key, value]) => editing[key as keyof api.Lesson] !== value))
            if (Object.keys(changed).length === 0) { setEditing(null); return }
            setSaving(true)
            try {
              await api.updateLesson(editing.id, { version: editing.version, ...changed })
              setEditing(null)
              notify({ type: 'success', text: '수업 정보를 수정했습니다.' })
              await reloadLessons()
            } catch (error) {
              await handleError(error)
            } finally {
              setSaving(false)
            }
          }}
        >
          <Form.Item name="lesson_date" label="수업일" rules={[{ required: true }]}><Input type="date" /></Form.Item>
          <Form.Item name="session_no" label="교시" rules={[{ required: true }]}><InputNumber min={1} max={9} precision={0} /></Form.Item>
          <Form.Item name="exam_round" label="시험 회차"><Input maxLength={50} /></Form.Item>
          <Form.Item name="topic" label="수업 주제"><Input maxLength={200} /></Form.Item>
          <Form.Item name="status" label="상태">
            <Select options={(Object.keys(LESSON_STATUS) as api.LessonStatus[]).map((value) => ({ value, label: LESSON_STATUS[value].label }))} />
          </Form.Item>
          <Form.Item name="memo" label="수업 메모"><Input.TextArea maxLength={2000} rows={3} /></Form.Item>
        </Form>
      </Modal>
    </Space>
  )
}
