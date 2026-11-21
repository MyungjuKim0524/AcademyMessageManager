import { useCallback, useEffect, useState } from 'react'
import { Button, Card, Checkbox, Col, Empty, Form, Input, Modal, Popconfirm, Row, Select, Space, Table, Tag, Typography } from 'antd'
import * as api from './api'

const TYPE: Record<string, string> = { REGULAR: '정규', EXAM_PREP: '시험 대비' }

type Props = {
  /** Called after any change so the page reloads the classes used by 학생 관리. */
  onChanged: (preferId?: number) => void
  done: (text: string) => void
  fail: (error: unknown) => void
}

/**
 * 반 관리 (administrators, 2026-11-20): register, rename, end / resume operation, delete.
 * Ending a class keeps every record (lessons, scores, messages) and only hides it from daily
 * screens and uploads; only a class without any record can be deleted (e.g. a typo).
 */
export function ClassroomsTab({ onChanged, done, fail }: Props) {
  const [rows, setRows] = useState<api.Classroom[]>([])
  const [loading, setLoading] = useState(false)
  const [showEnded, setShowEnded] = useState(false)
  const [renaming, setRenaming] = useState<api.Classroom | null>(null)
  const [busy, setBusy] = useState(false)
  const [renameForm] = Form.useForm()

  const load = useCallback(async () => {
    setLoading(true)
    try { setRows(await api.classrooms(true)) } catch (error) { fail(error) } finally { setLoading(false) }
  }, [fail])

  useEffect(() => { void load() }, [load])

  const run = async (work: () => Promise<unknown>, text: string, preferId?: number) => {
    setBusy(true)
    try {
      await work()
      done(text)
      await load()
      onChanged(preferId)
      return true
    } catch (error) {
      fail(error)
      return false
    } finally {
      setBusy(false)
    }
  }

  const shown = showEnded ? rows : rows.filter((row) => row.is_active)
  const ended = rows.filter((row) => !row.is_active).length

  return (
    <Row gutter={[16, 16]}>
      <Col xs={24} lg={8}>
        <Card title="반 등록">
          {/* Form names keep field ids unique: the student form also has a "name" field. */}
          <Form name="classroom" layout="vertical" onFinish={async (values) => {
            try {
              const created = await api.createClassroom(values.name, values.class_type)
              done(`${created.name} 반을 등록했습니다.`)
              await load()
              onChanged(created.id)
            } catch (error) { fail(error) }
          }}>
            <Form.Item name="name" label="반 이름" rules={[{ required: true, whitespace: true }]}
              extra="엑셀 반 블록의 이름과 글자 그대로 같아야 업로드됩니다. 예: 중3 토10, 00고2 토2">
              <Input />
            </Form.Item>
            <Form.Item name="class_type" label="유형" initialValue="REGULAR">
              <Select options={[{ value: 'REGULAR', label: '정규' }, { value: 'EXAM_PREP', label: '시험 대비' }]} />
            </Form.Item>
            <Button htmlType="submit" type="primary">반 등록</Button>
          </Form>
        </Card>
      </Col>
      <Col xs={24} lg={16}>
        <Card
          title={`반 목록 (운영 중 ${rows.length - ended}개)`}
          extra={<Checkbox checked={showEnded} onChange={(event) => setShowEnded(event.target.checked)}>{`운영 종료된 반도 보기 (${ended})`}</Checkbox>}
        >
          <Table
            rowKey="id"
            size="small"
            loading={loading}
            dataSource={shown}
            pagination={false}
            scroll={{ x: 'max-content' }}
            locale={{ emptyText: <Empty description="등록된 반이 없습니다. 왼쪽에서 반을 등록하세요." /> }}
            columns={[
              { title: '반 이름', dataIndex: 'name', className: 'cell-nowrap' },
              { title: '유형', className: 'cell-nowrap', render: (_, row) => TYPE[row.class_type] ?? row.class_type },
              { title: '상태', className: 'cell-nowrap', render: (_, row) => row.is_active ? <Tag color="green">운영 중</Tag> : <Tag>운영 종료</Tag> },
              {
                title: '관리',
                className: 'cell-nowrap',
                render: (_, row) => (
                  <Space wrap>
                    <Button size="small" disabled={busy} onClick={() => { setRenaming(row); renameForm.setFieldsValue({ name: row.name }) }}>이름 수정</Button>
                    {row.is_active ? (
                      <Popconfirm
                        title={`${row.name} 반을 운영 종료할까요?`}
                        description="수업·출결·성적·메시지 기록은 그대로 남고, 수업·업로드·안내 화면에서만 숨겨집니다. 언제든 다시 운영할 수 있습니다."
                        okText="운영 종료" cancelText="닫기"
                        onConfirm={() => void run(() => api.updateClassroom(row.id, { is_active: false }), `${row.name} 반을 운영 종료했습니다.`)}
                      >
                        <Button size="small" disabled={busy}>운영 종료</Button>
                      </Popconfirm>
                    ) : (
                      <Button size="small" disabled={busy}
                        onClick={() => void run(() => api.updateClassroom(row.id, { is_active: true }), `${row.name} 반을 다시 운영합니다.`, row.id)}>다시 운영</Button>
                    )}
                    <Popconfirm
                      title={`${row.name} 반을 삭제할까요?`}
                      description="잘못 등록한 빈 반만 삭제됩니다. 수강생·수업·평가 기록이 있으면 삭제되지 않으니 '운영 종료'를 사용하세요."
                      okText="삭제" okButtonProps={{ danger: true }} cancelText="닫기"
                      onConfirm={() => void run(() => api.deleteClassroom(row.id), `${row.name} 반을 삭제했습니다.`)}
                    >
                      <Button size="small" danger disabled={busy}>삭제</Button>
                    </Popconfirm>
                  </Space>
                ),
              },
            ]}
          />
        </Card>
      </Col>
      <Modal
        title={renaming ? `${renaming.name} 이름 수정` : ''}
        open={renaming !== null}
        okText="저장"
        cancelText="취소"
        confirmLoading={busy}
        onCancel={() => setRenaming(null)}
        onOk={() => renameForm.submit()}
        destroyOnHidden
      >
        <Form form={renameForm} name="classroomRename" layout="vertical" onFinish={async (values) => {
          if (!renaming) return
          if (values.name.trim() === renaming.name) { setRenaming(null); return }
          const ok = await run(() => api.updateClassroom(renaming.id, { name: values.name.trim() }), `반 이름을 '${values.name.trim()}'(으)로 바꿨습니다.`)
          if (ok) setRenaming(null)
        }}>
          <Form.Item name="name" label="반 이름" rules={[{ required: true, whitespace: true, message: '반 이름을 입력해주세요.' }]}><Input maxLength={100} /></Form.Item>
          <Typography.Text type="secondary">엑셀의 반 이름도 같이 바꿔야 다음 업로드에서 이 반으로 저장됩니다. 기존 기록은 그대로 이 반에 남습니다.</Typography.Text>
        </Form>
      </Modal>
    </Row>
  )
}
