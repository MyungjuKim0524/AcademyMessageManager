import { useCallback, useEffect, useRef, useState } from 'react'
import { Alert, Button, Card, Col, Empty, Form, Input, Modal, Row, Segmented, Select, Space, Table, Tabs, Tag, Typography } from 'antd'
import { useSearchParams } from 'react-router'
import { toApiClientError } from '../../shared/api/ApiClientError'
import { todayLocal } from '../../shared/date'
import { pickClassroom, positiveId, rememberClassroom } from '../../shared/workingContext'
import { ReturnBanner } from '../../shared/ui/ReturnBanner'
import { useAuth } from '../auth/AuthProvider'
import { AllStudentsCard } from './AllStudentsCard'
import * as api from './api'
import { ClassroomsTab } from './ClassroomsTab'
import { STATUS } from './status'
import { StudentPicker } from './StudentPicker'
import { PageHeader } from '../../shared/ui/PageHeader'

type Notice = { type: 'success' | 'error'; text: string } | null

const today = todayLocal

/**
 * 학생·반 관리. Administrators (2026-11-20): '반 관리' (register, rename, end / resume, delete) and
 * '학생 관리' (registration with the class in one save, then 전체 학생 / 반별 학생). Other staff see
 * the students of their assigned classes only.
 */
export function LearningOpsPage() {
  const { user } = useAuth()
  const admin = user?.role === 'ADMIN'
  const [params] = useSearchParams()
  // `?classroom=` opens that class; `?contact=<student id>` (fix link from 성적 안내) opens the
  // guardian contact editor — administrators only, as the server allows only them to change it.
  const [link] = useState(() => ({ classroomId: positiveId(params.get('classroom')), contactId: positiveId(params.get('contact')) }))
  const [notice, setNotice] = useState<Notice>(null)
  const [classrooms, setClassrooms] = useState<api.Classroom[]>([])
  const [classroomsLoaded, setClassroomsLoaded] = useState(false)
  const [classroomId, setClassroomId] = useState<number | null>(null)
  const [rows, setRows] = useState<api.ClassroomStudent[]>([])
  const [rowsLoading, setRowsLoading] = useState(false)
  const latestRequest = useRef(0)
  const [section, setSection] = useState<'classes' | 'students'>('students')
  const [tab, setTab] = useState<'all' | 'class'>('all')
  // Bumped after anything that changes the all-students list (registration, enrollment, contact).
  const [studentsVersion, setStudentsVersion] = useState(0)
  const [recentStudent, setRecentStudent] = useState<api.Student | null>(null)
  const [studentForm] = Form.useForm()
  const [enrollForm] = Form.useForm()
  const [enrollOpen, setEnrollOpen] = useState(false)

  const fail = useCallback((error: unknown) => setNotice({ type: 'error', text: toApiClientError(error).message }), [])
  const done = useCallback((text: string) => setNotice({ type: 'success', text }), [])

  const loadClassrooms = useCallback(async (preferId?: number) => {
    try {
      const items = await api.classrooms()
      setClassrooms(items)
      setClassroomId((current) => {
        const picked = pickClassroom(items, preferId, current, link.classroomId)
        rememberClassroom(picked)
        return picked
      })
    } catch (error) {
      fail(error)
    } finally {
      setClassroomsLoaded(true)
    }
  }, [fail, link])

  const selectClassroom = (id: number) => { setClassroomId(id); rememberClassroom(id) }

  const loadStudents = useCallback(async (id: number) => {
    const request = ++latestRequest.current
    setRowsLoading(true)
    try {
      const items = await api.students(id)
      if (request === latestRequest.current) setRows(items)
    } catch (error) {
      if (request === latestRequest.current) { setRows([]); fail(error) }
    } finally {
      if (request === latestRequest.current) setRowsLoading(false)
    }
  }, [fail])

  useEffect(() => { void loadClassrooms() }, [loadClassrooms])
  useEffect(() => {
    if (classroomId === null) { setRows([]); return }
    void loadStudents(classroomId)
  }, [classroomId, loadStudents])

  const [pauseTarget, setPauseTarget] = useState<{ row: api.ClassroomStudent; mode: 'pause' | 'resume' } | null>(null)
  const [pauseDate, setPauseDate] = useState(today())
  const [pauseSaving, setPauseSaving] = useState(false)
  useEffect(() => { if (pauseTarget) setPauseDate(today()) }, [pauseTarget])

  const savePause = async () => {
    if (!pauseTarget || classroomId === null || !pauseDate) return
    const { row, mode } = pauseTarget
    setPauseSaving(true)
    try {
      if (mode === 'pause') {
        await api.pause(classroomId, row.enrollment_id, pauseDate)
        done(`${row.name} 학생을 ${pauseDate}부터 휴원 처리했습니다.`)
      } else {
        const open = (await api.pauses(classroomId, row.enrollment_id)).items.find((item) => item.resumed_on === null)
        if (!open) throw new Error('진행 중인 휴원 기록이 없습니다. 관리자에게 문의하세요.')
        await api.resume(classroomId, row.enrollment_id, open.id, pauseDate)
        done(`${row.name} 학생을 ${pauseDate}부터 복귀 처리했습니다.`)
      }
      setPauseTarget(null)
      await loadStudents(classroomId)
    } catch (error) {
      setNotice({ type: 'error', text: error instanceof Error && !('code' in error) ? error.message : toApiClientError(error).message })
    } finally {
      setPauseSaving(false)
    }
  }

  const [contactTarget, setContactTarget] = useState<{ id: number; name: string } | null>(null)
  const [contactForm] = Form.useForm()
  const [contactLoading, setContactLoading] = useState(false)

  const openContact = useCallback(async (row: { id: number; name: string }) => {
    setContactTarget(row)
    setContactLoading(true)
    try {
      const contact = await api.studentContact(row.id)
      setContactTarget({ id: contact.id, name: contact.name })
      contactForm.setFieldsValue({ parent_name: contact.parent_name ?? '', parent_email: contact.parent_email ?? '' })
    } catch (error) {
      setContactTarget(null)
      fail(error)
    } finally {
      setContactLoading(false)
    }
  }, [contactForm, fail])

  useEffect(() => {
    if (admin && link.contactId) void openContact({ id: link.contactId, name: '' })
  }, [admin, link, openContact])

  const saveContact = async (values: { parent_name?: string; parent_email?: string }) => {
    if (!contactTarget) return
    setContactLoading(true)
    try {
      await api.updateStudentContact(contactTarget.id, values.parent_name?.trim() || null, values.parent_email?.trim() || null)
      done(`${contactTarget.name} 학생의 보호자 연락처를 저장했습니다.`)
      setContactTarget(null)
      setStudentsVersion((value) => value + 1)
      if (classroomId !== null) await loadStudents(classroomId)
    } catch (error) {
      fail(error)
    } finally {
      setContactLoading(false)
    }
  }

  /** Registration with the class in one save (the class is optional: it can be added later). */
  const registerStudent = async (values: { name: string; school_name?: string; parent_email?: string; classroom_id?: number; enrolled_at?: string }) => {
    const room = classrooms.find((row) => row.id === values.classroom_id)
    try {
      const created = await api.createStudent(values.name, values.school_name ?? '', values.parent_email,
        room ? { classroom_id: room.id, enrolled_at: values.enrolled_at ?? today() } : undefined)
      done(room
        ? `${created.name} 학생을 등록하고 ${room.name} 반에 수강 등록했습니다.`
        : `${created.name} 학생을 등록했습니다. 수강 반은 '반별 학생'의 '기존 학생 수강 추가'로 지정할 수 있습니다.`)
      setRecentStudent(created)
      // Keep the class and date for the next student of the same class.
      studentForm.resetFields(['name', 'school_name', 'parent_email'])
      setStudentsVersion((value) => value + 1)
      if (room && room.id === classroomId) await loadStudents(room.id)
    } catch (error) { fail(error) }
  }

  const enrollExisting = async (values: { student_id: number; enrolled_at: string }) => {
    if (classroomId === null) return
    try {
      await api.enroll(classroomId, values.student_id, values.enrolled_at)
      done(`수강 등록을 완료했습니다.${current ? ` (${current.name})` : ''}`)
      setEnrollOpen(false)
      setStudentsVersion((value) => value + 1)
      await loadStudents(classroomId)
    } catch (error) { fail(error) }
  }

  const classroomOptions = classrooms.map((row) => ({ value: row.id, label: row.name }))
  const current = classrooms.find((row) => row.id === classroomId)

  const classCard = (
    <Card
      title={current ? `${current.name} 학생 목록` : '학생 목록'}
      extra={classrooms.length > 0 && (
        <Space wrap>
          <Typography.Text type="secondary">{admin ? '반' : `담당 반 ${classrooms.length}개`}</Typography.Text>
          <Select aria-label="반 선택" style={{ width: 220 }} value={classroomId ?? undefined} options={classroomOptions} onChange={selectClassroom} />
          {admin && <Button disabled={classroomId === null} onClick={() => setEnrollOpen(true)}>기존 학생 수강 추가</Button>}
        </Space>
      )}
    >
      {classroomsLoaded && classrooms.length === 0 ? (
        <Empty description={admin ? "운영 중인 반이 없습니다. '반 관리'에서 반을 먼저 등록하세요." : '담당 반이 없습니다. 관리자에게 반 배정을 요청하세요.'} />
      ) : (
        <Table
          rowKey="id"
          pagination={false}
          loading={rowsLoading || !classroomsLoaded}
          dataSource={rows}
          locale={{ emptyText: <Empty description="이 반에 등록된 학생이 없습니다." /> }}
          columns={[
            { title: '학생', dataIndex: 'name' },
            { title: '학교', dataIndex: 'school_name' },
            { title: '상태', dataIndex: 'enrollment_status', render: (status: string) => <Tag color={STATUS[status]?.color}>{STATUS[status]?.label ?? status}</Tag> },
            { title: '등록일', dataIndex: 'enrolled_at' },
            ...(admin ? [{
              title: '보호자 이메일',
              render: (_: unknown, row: api.ClassroomStudent) => row.parent_email ?? <Tag>미등록</Tag>,
            }] : []),
            ...(admin && classroomId !== null ? [{
              title: '메일 주소 변경',
              render: (_: unknown, row: api.ClassroomStudent) => (
                <Button size="small" onClick={() => void openContact(row)}>메일 주소 변경</Button>
              ),
            }, {
              title: '휴원 관리',
              render: (_: unknown, row: api.ClassroomStudent) => row.enrollment_status === 'WITHDRAWN' ? null : (
                <Button size="small" onClick={() => setPauseTarget({ row, mode: row.enrollment_status === 'PAUSED' ? 'resume' : 'pause' })}>
                  {row.enrollment_status === 'PAUSED' ? '복귀 처리' : '휴원 처리'}
                </Button>
              ),
            }] : []),
          ]}
        />
      )}
    </Card>
  )

  const registrationCard = (
    <Card title="학생 등록">
      <Form form={studentForm} name="student" layout="vertical" initialValues={{ enrolled_at: today() }} onFinish={(values) => void registerStudent(values)}>
        <Row gutter={[16, 0]}>
          <Col xs={24} md={8}><Form.Item name="name" label="학생 이름" rules={[{ required: true, whitespace: true }]}><Input /></Form.Item></Col>
          <Col xs={24} md={8}><Form.Item name="school_name" label="학교"><Input /></Form.Item></Col>
          <Col xs={24} md={8}>
            <Form.Item name="parent_email" label="보호자 이메일 (성적 안내 수신)" rules={[{ type: 'email', message: '올바른 이메일을 입력해주세요.' }]}>
              <Input autoComplete="off" maxLength={255} />
            </Form.Item>
          </Col>
          <Col xs={24} md={8}>
            <Form.Item name="classroom_id" label="수강 반 (함께 등록)">
              <Select aria-label="수강 반" allowClear options={classroomOptions} placeholder="반 선택 (나중에 지정해도 됨)" />
            </Form.Item>
          </Col>
          <Col xs={24} md={8}>
            <Form.Item name="enrolled_at" label="수강 등록일" dependencies={['classroom_id']}
              rules={[({ getFieldValue }) => ({ validator: (_, value) => (!getFieldValue('classroom_id') || value ? Promise.resolve() : Promise.reject(new Error('수강 등록일을 입력해주세요.'))) })]}>
              <Input type="date" />
            </Form.Item>
          </Col>
        </Row>
        <Space wrap>
          <Button htmlType="submit" type="primary">학생 등록</Button>
          <Typography.Text type="secondary">수강 반을 고르면 학생 등록과 수강 등록이 한 번에 저장됩니다(둘 중 하나만 저장되는 일은 없음).</Typography.Text>
        </Space>
      </Form>
    </Card>
  )

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <PageHeader title={admin ? '학생·반 관리' : '담당 반 학생'} description={admin ? '반을 등록·종료하고, 학생을 등록하며 반별 수강·휴원·연락처를 관리합니다.' : '담당 반 학생 목록입니다.'} />
      <ReturnBanner />
      {notice && <Alert type={notice.type} message={notice.text} showIcon closable onClose={() => setNotice(null)} />}

      {admin && (
        <Tabs
          activeKey={section}
          onChange={(key) => setSection(key as 'classes' | 'students')}
          items={[{ key: 'classes', label: '반 관리' }, { key: 'students', label: '학생 관리' }]}
          style={{ marginBottom: -16 }}
        />
      )}
      {admin && section === 'classes' && <ClassroomsTab onChanged={(id) => void loadClassrooms(id)} done={done} fail={fail} />}

      {admin && section === 'students' && (
        <>
          {registrationCard}
          <Segmented value={tab} onChange={(value) => setTab(value as 'all' | 'class')}
            options={[{ label: '전체 학생', value: 'all' }, { label: '반별 학생', value: 'class' }]} />
          {tab === 'all' && (
            <AllStudentsCard
              reloadKey={studentsVersion}
              onEditContact={(row) => void openContact(row)}
              onOpenClassroom={(id) => { selectClassroom(id); setTab('class') }}
              onError={fail}
            />
          )}
          {tab === 'class' && classCard}
        </>
      )}
      {!admin && classCard}

      <Modal
        title={current ? `${current.name} 반에 기존 학생 수강 추가` : ''}
        open={enrollOpen}
        okText="수강 등록"
        cancelText="취소"
        onCancel={() => setEnrollOpen(false)}
        onOk={() => enrollForm.submit()}
        destroyOnHidden
      >
        {/* Re-created on every opening: starts with today and the student registered last. */}
        <Form form={enrollForm} name="enrollment" layout="vertical" initialValues={{ enrolled_at: today(), student_id: recentStudent?.id }}
          onFinish={(values) => void enrollExisting(values)}>
          <Form.Item name="student_id" label="학생" rules={[{ required: true, message: '학생을 선택해주세요.' }]}>
            <StudentPicker recent={recentStudent} reloadKey={studentsVersion} onError={fail} />
          </Form.Item>
          <Form.Item name="enrolled_at" label="등록일" rules={[{ required: true }]}><Input type="date" /></Form.Item>
          <Typography.Text type="secondary">이미 등록된 학생이 다른 반도 다닐 때 사용합니다. 새 학생은 위의 '학생 등록'에서 반과 함께 등록하세요.</Typography.Text>
        </Form>
      </Modal>
      <Modal
        title={contactTarget ? `${contactTarget.name || '학생'} 메일 주소 변경` : ''}
        open={contactTarget !== null}
        okText="저장"
        cancelText="취소"
        confirmLoading={contactLoading}
        onCancel={() => setContactTarget(null)}
        onOk={() => contactForm.submit()}
        destroyOnHidden
      >
        {/* A form name keeps field ids unique: the student registration form also has parent_email. */}
        <Form form={contactForm} name="studentContact" layout="vertical" onFinish={(values) => void saveContact(values)}>
          <Form.Item name="parent_name" label="보호자 이름"><Input autoComplete="off" maxLength={100} /></Form.Item>
          <Form.Item name="parent_email" label="보호자 이메일" rules={[{ type: 'email', message: '올바른 이메일을 입력해주세요.' }]}>
            <Input autoComplete="off" maxLength={255} />
          </Form.Item>
          <Typography.Text type="secondary">
            성적 안내 메시지는 이 이메일로 발송됩니다(현재는 모의 발송). 바꾸면 아직 확정하지 않은 기존 메시지는 다시 생성해야 합니다.
          </Typography.Text>
        </Form>
      </Modal>
      <Modal
        title={pauseTarget ? `${pauseTarget.row.name} ${pauseTarget.mode === 'pause' ? '휴원 처리' : '복귀 처리'}` : ''}
        open={pauseTarget !== null}
        okText="저장"
        cancelText="취소"
        confirmLoading={pauseSaving}
        onCancel={() => setPauseTarget(null)}
        onOk={() => void savePause()}
        destroyOnHidden
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          <Typography.Text type="secondary">
            {pauseTarget?.mode === 'pause'
              ? '휴원 시작일부터 복귀 전날까지의 수업·평가는 출결·성적 대상에서 제외됩니다.'
              : '복귀일부터 다시 출결·성적 대상이 됩니다.'}
          </Typography.Text>
          <Input aria-label={pauseTarget?.mode === 'pause' ? '휴원 시작일' : '복귀일'} type="date" value={pauseDate} max={today()} onChange={(event) => setPauseDate(event.target.value)} />
        </Space>
      </Modal>
    </Space>
  )
}
