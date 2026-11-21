import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Alert, Button, Card, Col, Drawer, Empty, Form, Input, Modal, Popconfirm, Row, Select, Space, Table, Tabs, Tag, Typography } from 'antd'
import { toApiClientError } from '../../shared/api/ApiClientError'
import { todayLocal } from '../../shared/date'
import * as api from './api'
import { PageHeader } from '../../shared/ui/PageHeader'

type Notice = { type: 'success' | 'error'; text: string } | null

const ROLE_LABEL: Record<api.StaffRole, string> = { ADMIN: '관리자', TEACHER: '선생님', ASSISTANT: '조교' }
const ROLE_COLOR: Record<api.StaffRole, string> = { ADMIN: 'purple', TEACHER: 'blue', ASSISTANT: 'cyan' }


function RoleTag({ role }: { role: api.StaffRole }) {
  return <Tag color={ROLE_COLOR[role]}>{ROLE_LABEL[role]}</Tag>
}

function StatusTag({ status }: { status: api.StaffStatus }) {
  return status === 'ACTIVE' ? <Tag color="green">활성</Tag> : <Tag>비활성</Tag>
}

function StaffName({ staff }: { staff: { display_name: string | null; email: string } }) {
  return staff.display_name
    ? <Typography.Text strong>{staff.display_name}</Typography.Text>
    : <Typography.Text type="secondary">이름 미등록</Typography.Text>
}

export function StaffManagementPage() {
  const [staff, setStaff] = useState<api.Staff[]>([])
  const [classrooms, setClassrooms] = useState<api.Classroom[]>([])
  const [notice, setNotice] = useState<Notice>(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)

  const fail = useCallback((error: unknown) => setNotice({ type: 'error', text: toApiClientError(error).message }), [])
  const ok = (text: string) => setNotice({ type: 'success', text })

  const loadBase = useCallback(async () => {
    setLoading(true)
    try {
      const [staffRows, classroomRows] = await Promise.all([api.listStaff(), api.listClassrooms()])
      setStaff(staffRows)
      setClassrooms(classroomRows)
    } catch (error) {
      fail(error)
    } finally {
      setLoading(false)
    }
  }, [fail])

  useEffect(() => { void loadBase() }, [loadBase])

  const shared = { staff, classrooms, loading, saving, setSaving, fail, ok, reload: loadBase }

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <PageHeader title="직원 및 담당 반 관리" description="직원 계정을 만들고 반별 담당 선생님·조교를 배정합니다(관리자 전용)." />
      {notice && <Alert type={notice.type} message={notice.text} showIcon closable onClose={() => setNotice(null)} />}
      <Tabs
        defaultActiveKey="staff"
        items={[
          { key: 'staff', label: '직원 계정', children: <StaffAccountsTab {...shared} /> },
          { key: 'assignments', label: '반별 담당 배정', children: <ClassroomAssignmentsTab {...shared} /> },
        ]}
      />
    </Space>
  )
}

interface TabProps {
  staff: api.Staff[]
  classrooms: api.Classroom[]
  loading: boolean
  saving: boolean
  setSaving: (value: boolean) => void
  fail: (error: unknown) => void
  ok: (text: string) => void
  reload: () => Promise<void>
}

function StaffAccountsTab({ staff, loading, saving, setSaving, fail, ok, reload }: TabProps) {
  const [createForm] = Form.useForm()
  const [nameForm] = Form.useForm()
  const [editing, setEditing] = useState<api.Staff | null>(null)
  const [detail, setDetail] = useState<api.Staff | null>(null)
  const [detailRows, setDetailRows] = useState<api.Assignment[]>([])
  const [detailLoading, setDetailLoading] = useState(false)
  // SEC-10-B: the issued code lives only in this state while the dialog is open.
  const [resetCode, setResetCode] = useState<{ staff: api.Staff; code: string; expiresAt: string } | null>(null)

  const run = async (action: () => Promise<void>) => {
    setSaving(true)
    try { await action() } catch (error) { fail(error) } finally { setSaving(false) }
  }

  const openDetail = async (row: api.Staff) => {
    setDetail(row)
    setDetailRows([])
    setDetailLoading(true)
    try { setDetailRows(await api.listAssignments(row.id)) } catch (error) { fail(error) } finally { setDetailLoading(false) }
  }

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <Card title="직원 등록">
        <Form
          form={createForm}
          layout="vertical"
          onFinish={(values) => run(async () => {
            await api.createStaff(values.display_name, values.email, values.password, values.role)
            createForm.resetFields()
            ok(`${values.display_name.trim()} 직원 계정을 등록했습니다.`)
            await reload()
          })}
        >
          <Row gutter={16}>
            <Col xs={24} md={6}>
              <Form.Item name="display_name" label="이름" rules={[{ required: true, whitespace: true, message: '이름을 입력해주세요.' }, { max: 100 }]}>
                <Input autoComplete="off" placeholder="예: 김민지" />
              </Form.Item>
            </Col>
            <Col xs={24} md={6}>
              <Form.Item name="email" label="이메일" rules={[{ required: true, type: 'email', message: '올바른 이메일을 입력해주세요.' }]}>
                <Input autoComplete="off" />
              </Form.Item>
            </Col>
            <Col xs={24} md={6}>
              <Form.Item name="password" label="초기 비밀번호" rules={[{ required: true, min: 12, message: '12자 이상 입력해주세요.' }]}>
                <Input.Password autoComplete="new-password" />
              </Form.Item>
            </Col>
            <Col xs={24} md={6}>
              <Form.Item name="role" label="역할" initialValue="TEACHER" rules={[{ required: true }]}>
                <Select options={[{ value: 'TEACHER', label: '선생님' }, { value: 'ASSISTANT', label: '조교' }]} />
              </Form.Item>
            </Col>
          </Row>
          <Button type="primary" htmlType="submit" loading={saving}>직원 등록</Button>
        </Form>
      </Card>

      <Card title="직원 목록" extra={<Typography.Text type="secondary">행을 누르면 담당 반을 볼 수 있습니다.</Typography.Text>}>
        <Table
          rowKey="id"
          loading={loading}
          dataSource={staff}
          pagination={false}
          scroll={{ x: true }}
          locale={{ emptyText: <Empty description="등록된 직원이 없습니다." /> }}
          onRow={(row) => ({ onClick: () => void openDetail(row), style: { cursor: 'pointer', opacity: row.status === 'INACTIVE' ? 0.55 : 1 } })}
          columns={[
            { title: '이름', render: (_, row) => <StaffName staff={row} /> },
            { title: '이메일', dataIndex: 'email' },
            { title: '역할', dataIndex: 'role', render: (role) => <RoleTag role={role} /> },
            { title: '상태', dataIndex: 'status', render: (status) => <StatusTag status={status} /> },
            {
              title: '계정 관리',
              render: (_, row) => (
                <Space onClick={(event) => event.stopPropagation()}>
                  <Button size="small" onClick={() => { setEditing(row); nameForm.setFieldsValue({ display_name: row.display_name ?? '' }) }}>이름 수정</Button>
                  {row.status === 'ACTIVE' && (
                    <Popconfirm
                      title={`${api.staffLabel(row)}에게 비밀번호 재설정 코드를 발급할까요?`}
                      description={(
                        <Typography.Paragraph style={{ maxWidth: 320, margin: 0 }}>
                          비밀번호를 잊은 직원용입니다. 코드는 한 번만 표시되고 15분 동안 한 번 쓸 수 있습니다.
                          이전에 발급한 코드는 무효가 됩니다. 본인 계정은 &lsquo;비밀번호 변경&rsquo;을 사용하세요.
                        </Typography.Paragraph>
                      )}
                      okText="발급" cancelText="취소"
                      onConfirm={() => run(async () => {
                        const issued = await api.issueResetCode(row.id)
                        setResetCode({ staff: row, code: issued.code, expiresAt: issued.expires_at })
                      })}
                    >
                      <Button size="small" disabled={saving}>재설정 코드</Button>
                    </Popconfirm>
                  )}
                  <Popconfirm
                    title={`${api.staffLabel(row)} 계정을 ${row.status === 'ACTIVE' ? '비활성화' : '활성화'}하시겠습니까?`}
                    description={row.status === 'ACTIVE' ? '비활성화하면 즉시 로그아웃되고 담당 반에 접근할 수 없습니다.' : undefined}
                    onConfirm={() => run(async () => {
                      await api.updateStaffStatus(row.id, row.status === 'ACTIVE' ? 'INACTIVE' : 'ACTIVE')
                      ok('직원 상태를 변경했습니다.')
                      await reload()
                    })}
                  >
                    <Button size="small" danger={row.status === 'ACTIVE'} disabled={saving}>{row.status === 'ACTIVE' ? '비활성화' : '활성화'}</Button>
                  </Popconfirm>
                  {/* Staff deletion option B (2026-11-20): one warning, then the server decides
                      between removing an unused account and keeping a used one for history. */}
                  <Popconfirm
                    title={`${api.staffLabel(row)} 계정을 삭제하시겠습니까?`}
                    description={(
                      <Typography.Paragraph style={{ maxWidth: 320, margin: 0 }}>
                        삭제하면 즉시 로그아웃되고 다시 로그인할 수 없으며, 직원 목록과 담당 반 배정에서 사라집니다. 되돌릴 수 없습니다.
                        이 직원이 남긴 업무 기록(메시지 확정·발송, 변경 이력 등)에는 이름이 그대로 남습니다.
                      </Typography.Paragraph>
                    )}
                    okText="삭제" okButtonProps={{ danger: true }} cancelText="취소"
                    onConfirm={() => run(async () => {
                      const result = await api.deleteStaff(row.id)
                      ok(result.mode === 'HARD'
                        ? `${api.staffLabel(row)} 계정을 삭제했습니다.`
                        : `${api.staffLabel(row)} 계정을 삭제했습니다. 업무 기록이 있어 기록 속 이름은 남겨 두었습니다.`)
                      await reload()
                    })}
                  >
                    <Button size="small" danger disabled={saving}>삭제</Button>
                  </Popconfirm>
                </Space>
              ),
            },
          ]}
        />
      </Card>

      <Modal
        title="비밀번호 재설정 코드"
        open={resetCode !== null}
        onCancel={() => setResetCode(null)}
        onOk={() => setResetCode(null)}
        okText="전달했습니다"
        cancelButtonProps={{ style: { display: 'none' } }}
        destroyOnHidden
      >
        {resetCode && (
          <Space direction="vertical" style={{ width: '100%' }}>
            <Typography.Text>{api.staffLabel(resetCode.staff)} ({resetCode.staff.email})</Typography.Text>
            <Typography.Title level={3} copyable={{ text: resetCode.code }} style={{ fontFamily: 'monospace', margin: 0 }}>
              {resetCode.code}
            </Typography.Title>
            <Alert
              type="warning" showIcon
              title={`${new Date(resetCode.expiresAt).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' })}까지 한 번만 사용할 수 있습니다.`}
              description="이 창을 닫으면 코드를 다시 볼 수 없습니다. 직원에게 직접(대면·전화) 알려 주고, 메신저·메일에 남기지 마세요. 직원은 로그인 화면의 '재설정 코드로 설정'에서 새 비밀번호를 정합니다."
            />
          </Space>
        )}
      </Modal>

      <Modal
        title="이름 수정"
        open={editing !== null}
        okText="저장"
        cancelText="취소"
        confirmLoading={saving}
        onCancel={() => setEditing(null)}
        onOk={() => nameForm.submit()}
        destroyOnHidden
      >
        <Form
          form={nameForm}
          layout="vertical"
          onFinish={(values) => run(async () => {
            if (!editing) return
            await api.updateStaffName(editing.id, values.display_name)
            setEditing(null)
            ok('이름을 수정했습니다.')
            await reload()
          })}
        >
          <Typography.Paragraph type="secondary">{editing?.email}</Typography.Paragraph>
          <Form.Item name="display_name" label="이름" rules={[{ required: true, whitespace: true, message: '이름을 입력해주세요.' }, { max: 100 }]}>
            <Input autoComplete="off" />
          </Form.Item>
        </Form>
      </Modal>

      <Drawer title={detail ? `${api.staffLabel(detail)} 담당 반` : '담당 반'} open={detail !== null} onClose={() => setDetail(null)} width={420}>
        {detail && (
          <Space direction="vertical" style={{ width: '100%' }}>
            <Space wrap><RoleTag role={detail.role} /><StatusTag status={detail.status} /><Typography.Text type="secondary">{detail.email}</Typography.Text></Space>
            <Table
              rowKey="id"
              size="small"
              loading={detailLoading}
              dataSource={detailRows}
              pagination={false}
              locale={{ emptyText: <Empty description="담당 반이 없습니다. '반별 담당 배정' 탭에서 배정하세요." /> }}
              columns={[
                { title: '반', dataIndex: 'classroom_name' },
                { title: '시작일', dataIndex: 'valid_from' },
              ]}
            />
          </Space>
        )}
      </Drawer>
    </Space>
  )
}

function ClassroomAssignmentsTab({ staff, classrooms, loading, saving, setSaving, fail, ok }: TabProps) {
  const [assignForm] = Form.useForm()
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [rows, setRows] = useState<api.ClassroomStaff[]>([])
  const [rowsLoading, setRowsLoading] = useState(false)
  const latestRequest = useRef(0)

  const selected = classrooms.find((row) => row.id === selectedId) ?? null

  useEffect(() => {
    if (selectedId === null || !classrooms.some((row) => row.id === selectedId)) {
      setSelectedId(classrooms[0]?.id ?? null)
    }
  }, [classrooms, selectedId])

  const loadRows = useCallback(async (classroomId: number) => {
    const request = ++latestRequest.current
    setRowsLoading(true)
    try {
      const result = await api.listClassroomStaff(classroomId)
      if (request === latestRequest.current) setRows(result)
    } catch (error) {
      if (request === latestRequest.current) fail(error)
    } finally {
      if (request === latestRequest.current) setRowsLoading(false)
    }
  }, [fail])

  useEffect(() => {
    if (selectedId === null) { setRows([]); return }
    assignForm.setFieldsValue({ staff_user_id: undefined, valid_from: todayLocal() })
    void loadRows(selectedId)
  }, [selectedId, loadRows, assignForm])

  const openAssigned = useMemo(() => new Set(rows.filter((row) => row.valid_to === null).map((row) => row.staff_user_id)), [rows])
  const candidates = staff.filter((row) => row.role !== 'ADMIN' && row.status === 'ACTIVE' && !openAssigned.has(row.id))

  if (!loading && classrooms.length === 0) {
    return <Card><Empty description="등록된 반이 없습니다. '학생·반 관리' 화면에서 반을 먼저 등록하세요." /></Card>
  }

  return (
    <Row gutter={[16, 16]}>
      <Col xs={24} md={8}>
        <Card title="반 선택">
          <Table
            rowKey="id"
            size="small"
            loading={loading}
            dataSource={classrooms}
            pagination={false}
            showHeader={false}
            onRow={(row) => ({
              onClick: () => setSelectedId(row.id),
              style: { cursor: 'pointer', background: row.id === selectedId ? 'var(--ant-color-primary-bg, #e6f4ff)' : undefined },
            })}
            columns={[{ render: (_, row) => <Typography.Text strong={row.id === selectedId}>{row.name}</Typography.Text> }]}
          />
        </Card>
      </Col>
      <Col xs={24} md={16}>
        <Card title={selected ? `${selected.name} 담당 직원` : '담당 직원'}>
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <Form
              form={assignForm}
              layout="inline"
              initialValues={{ valid_from: todayLocal() }}
              onFinish={async (values) => {
                const target = staff.find((row) => row.id === values.staff_user_id)
                if (!selected || !target || target.role === 'ADMIN') return
                setSaving(true)
                try {
                  await api.createAssignment(selected.id, target.id, target.role, values.valid_from)
                  ok(`${api.staffLabel(target)}님을 ${selected.name}에 배정했습니다.`)
                  assignForm.setFieldsValue({ staff_user_id: undefined })
                  await loadRows(selected.id)
                } catch (error) {
                  fail(error)
                } finally {
                  setSaving(false)
                }
              }}
            >
              <Form.Item name="staff_user_id" rules={[{ required: true, message: '직원을 선택하세요.' }]}>
                <Select
                  aria-label="배정할 직원"
                  showSearch
                  style={{ width: 260 }}
                  placeholder={candidates.length ? '배정할 직원 선택 (이름·이메일 검색)' : '배정 가능한 직원이 없습니다'}
                  disabled={!candidates.length}
                  optionFilterProp="search"
                  options={candidates.map((row) => ({
                    value: row.id,
                    search: `${row.display_name ?? ''} ${row.email}`,
                    label: `${api.staffLabel(row)} · ${ROLE_LABEL[row.role]}${row.display_name ? ` (${row.email})` : ''}`,
                  }))}
                />
              </Form.Item>
              <Form.Item name="valid_from" label="시작일" rules={[{ required: true }]}>
                <Input type="date" />
              </Form.Item>
              <Button type="primary" htmlType="submit" loading={saving} disabled={!selected || !candidates.length}>배정</Button>
            </Form>
            <Table
              rowKey="id"
              loading={rowsLoading}
              dataSource={rows}
              pagination={false}
              scroll={{ x: true }}
              locale={{ emptyText: <Empty description="이 반에 배정된 직원이 없습니다." /> }}
              columns={[
                { title: '이름', render: (_, row) => <StaffName staff={row} /> },
                { title: '이메일', dataIndex: 'email' },
                { title: '역할', dataIndex: 'assignment_role', render: (role) => <RoleTag role={role} /> },
                { title: '상태', dataIndex: 'staff_status', render: (status) => <StatusTag status={status} /> },
                { title: '시작일', dataIndex: 'valid_from' },
                {
                  title: '관리',
                  render: (_, row) => (
                    <Popconfirm
                      title={`${api.staffLabel(row)}님의 ${selected?.name ?? ''} 배정을 해제하시겠습니까?`}
                      description="해제하면 즉시 이 반의 학생 정보에 접근할 수 없습니다."
                      onConfirm={async () => {
                        if (!selected) return
                        setSaving(true)
                        try {
                          await api.removeAssignment(selected.id, row.id)
                          ok('담당 반 배정을 해제했습니다.')
                          await loadRows(selected.id)
                        } catch (error) {
                          fail(error)
                        } finally {
                          setSaving(false)
                        }
                      }}
                    >
                      <Button danger size="small" disabled={saving}>배정 해제</Button>
                    </Popconfirm>
                  ),
                },
              ]}
            />
          </Space>
        </Card>
      </Col>
    </Row>
  )
}
