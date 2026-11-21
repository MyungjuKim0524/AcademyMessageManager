import { configure, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useAuth } from '../auth/AuthProvider'
import { LearningOpsPage } from './LearningOpsPage'
import * as api from './api'

configure({ asyncUtilTimeout: 10000 })

vi.mock('../auth/AuthProvider', () => ({ useAuth: vi.fn() }))
vi.mock('./api', () => ({
  classrooms: vi.fn(),
  students: vi.fn(),
  allStudents: vi.fn(),
  createClassroom: vi.fn(),
  updateClassroom: vi.fn(),
  deleteClassroom: vi.fn(),
  createStudent: vi.fn(),
  enroll: vi.fn(),
  pauses: vi.fn(),
  pause: vi.fn(),
  resume: vi.fn(),
  studentContact: vi.fn(),
  updateStudentContact: vi.fn(),
}))

const asRole = (role: 'ADMIN' | 'TEACHER') => vi.mocked(useAuth).mockReturnValue({
  user: { id: 2, email: 'user@example.invalid', role },
  loading: false,
  login: vi.fn(),
  logout: vi.fn(),
})

function Where() {
  const location = useLocation()
  return <div>{`이동: ${location.pathname}${location.search}`}</div>
}
const renderPage = (path = '/students') => render(
  <MemoryRouter initialEntries={[path]}>
    <Routes>
      <Route path="/students" element={<LearningOpsPage />} />
      <Route path="*" element={<Where />} />
    </Routes>
  </MemoryRouter>,
)

describe('LearningOpsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(api.students).mockImplementation(async (id: number) => [
      { id, enrollment_id: id + 100, name: id === 10 ? '홍길동' : '성춘향', school_name: null, enrollment_status: 'ACTIVE', enrolled_at: '2026-11-01' },
    ])
    vi.mocked(api.allStudents).mockResolvedValue({ items: [], total: 0, limit: 50, offset: 0 })
  })

  // Administrators land on the all-students tab; the per-class list is the second tab.
  const openClassTab = async () => fireEvent.click(await screen.findByText('반별 학생'))

  it('opens the first assigned classroom automatically and switches between classrooms', async () => {
    asRole('TEACHER')
    vi.mocked(api.classrooms).mockResolvedValue([
      { id: 10, name: '중2 수학', class_type: 'REGULAR', is_active: true },
      { id: 11, name: '고1 영어', class_type: 'REGULAR', is_active: true },
    ])
    renderPage()

    expect(screen.getByRole('heading', { name: '담당 반 학생' })).toBeInTheDocument()
    expect(await screen.findByText('홍길동')).toBeInTheDocument()
    expect(api.students).toHaveBeenCalledWith(10)
    expect(screen.getByText('중2 수학 학생 목록')).toBeInTheDocument()
    expect(screen.queryByText('반 등록')).not.toBeInTheDocument()
    expect(screen.queryByText('직원 배정')).not.toBeInTheDocument()
    expect(screen.queryByText('전체 학생')).not.toBeInTheDocument()
    expect(api.allStudents).not.toHaveBeenCalled() // guardian contact list is admin-only

    fireEvent.mouseDown(screen.getByRole('combobox', { name: '반 선택' }))
    fireEvent.click(await screen.findByTitle('고1 영어'))
    expect(await screen.findByText('성춘향')).toBeInTheDocument()
    expect(api.students).toHaveBeenLastCalledWith(11)
  })

  it('tells a teacher without assignments to ask an administrator', async () => {
    asRole('TEACHER')
    vi.mocked(api.classrooms).mockResolvedValue([])
    renderPage()

    expect(await screen.findByText('담당 반이 없습니다. 관리자에게 반 배정을 요청하세요.')).toBeInTheDocument()
    await waitFor(() => expect(api.students).not.toHaveBeenCalled())
  })
  it('lets an administrator pause and resume an enrollment with dates', async () => {
    asRole('ADMIN')
    const row = { id: 10, enrollment_id: 110, name: '홍길동', school_name: null, enrolled_at: '2026-11-01' }
    const open = { id: 5, enrollment_id: 110, paused_from: '2026-11-05', resumed_on: null, source: 'MANUAL' as const, created_at: '' }
    vi.mocked(api.classrooms).mockResolvedValue([{ id: 10, name: '중2 수학', class_type: 'REGULAR', is_active: true }])
    vi.mocked(api.students)
      .mockResolvedValueOnce([{ ...row, enrollment_status: 'ACTIVE' }])
      .mockResolvedValue([{ ...row, enrollment_status: 'PAUSED' }])
    vi.mocked(api.pause).mockResolvedValue(open)
    vi.mocked(api.pauses).mockResolvedValue({ enrollment_status: 'PAUSED', items: [open] })
    vi.mocked(api.resume).mockResolvedValue({ ...open, resumed_on: '2026-11-10' })
    renderPage()
    await openClassTab()

    fireEvent.click(await screen.findByText('휴원 처리'))
    fireEvent.change(await screen.findByLabelText('휴원 시작일'), { target: { value: '2026-11-05' } })
    fireEvent.click(screen.getByText('저장'))
    await waitFor(() => expect(api.pause).toHaveBeenCalledWith(10, 110, '2026-11-05'))
    expect(await screen.findByText('홍길동 학생을 2026-11-05부터 휴원 처리했습니다.')).toBeInTheDocument()

    fireEvent.click(await screen.findByText('복귀 처리'))
    fireEvent.change(await screen.findByLabelText('복귀일'), { target: { value: '2026-11-10' } })
    fireEvent.click(screen.getByText('저장'))
    await waitFor(() => expect(api.resume).toHaveBeenCalledWith(10, 110, 5, '2026-11-10'))
    expect(api.pauses).toHaveBeenCalledWith(10, 110)
  })

  it('lets an administrator edit an existing student guardian e-mail', async () => {
    asRole('ADMIN')
    vi.mocked(api.classrooms).mockResolvedValue([{ id: 10, name: '중2 수학', class_type: 'REGULAR', is_active: true }])
    vi.mocked(api.students).mockImplementation(async (id: number) => [
      { id, enrollment_id: id + 100, name: '홍길동', school_name: null, enrollment_status: 'ACTIVE', enrolled_at: '2026-11-01', parent_name: null, parent_email: null },
    ])
    vi.mocked(api.studentContact).mockResolvedValue({ id: 10, name: '홍길동', parent_name: '기존보호자', parent_email: null })
    vi.mocked(api.updateStudentContact).mockResolvedValue({ id: 10, name: '홍길동', parent_name: '홍보호자', parent_email: 'parent@example.invalid' })
    renderPage()
    await openClassTab()

    expect(await screen.findByText('미등록')).toBeInTheDocument() // admin list shows missing guardian e-mail
    fireEvent.click(await screen.findByText('메일 주소 변경', { selector: 'button span' })) // the column header has the same text
    await waitFor(() => expect(api.studentContact).toHaveBeenCalledWith(10))
    // Wait until the stored contact has been loaded into the form before editing it.
    await waitFor(() => expect(screen.getByLabelText('보호자 이름')).toHaveValue('기존보호자'))
    fireEvent.change(screen.getByLabelText('보호자 이름'), { target: { value: '홍보호자' } })
    fireEvent.change(screen.getByLabelText('보호자 이메일'), { target: { value: 'parent@example.invalid' } })
    fireEvent.click(screen.getByText('저장'))
    await waitFor(() => expect(api.updateStudentContact).toHaveBeenCalledWith(10, '홍보호자', 'parent@example.invalid'))
    expect(await screen.findByText('홍길동 학생의 보호자 연락처를 저장했습니다.')).toBeInTheDocument()
  })

  it('opens the guardian contact editor from a fix link and returns to the original task', async () => {
    asRole('ADMIN')
    vi.mocked(api.classrooms).mockResolvedValue([{ id: 10, name: '중2 수학', class_type: 'REGULAR', is_active: true }])
    vi.mocked(api.studentContact).mockResolvedValue({ id: 10, name: '홍길동', parent_name: null, parent_email: null })
    vi.mocked(api.updateStudentContact).mockResolvedValue({ id: 10, name: '홍길동', parent_name: null, parent_email: 'parent@example.invalid' })
    renderPage('/students?contact=10&from=%2Fnotifications%3Fclassroom%3D10%26tab%3Dcompose%26lesson%3D7')

    expect(await screen.findByText('홍길동 메일 주소 변경')).toBeInTheDocument()
    expect(api.studentContact).toHaveBeenCalledWith(10)
    fireEvent.change(screen.getByLabelText('보호자 이메일'), { target: { value: 'parent@example.invalid' } })
    fireEvent.click(screen.getByText('저장'))
    await waitFor(() => expect(api.updateStudentContact).toHaveBeenCalledWith(10, null, 'parent@example.invalid'))
    fireEvent.click(await screen.findByText('원래 작업으로 돌아가기'))
    expect(await screen.findByText('이동: /notifications?classroom=10&tab=compose&lesson=7')).toBeInTheDocument()
  })

  it('does not open the contact editor from a link for non-administrators', async () => {
    asRole('TEACHER')
    vi.mocked(api.classrooms).mockResolvedValue([{ id: 10, name: '중2 수학', class_type: 'REGULAR', is_active: true }])
    renderPage('/students?contact=10')
    expect(await screen.findByText('홍길동')).toBeInTheDocument()
    expect(api.studentContact).not.toHaveBeenCalled()
  })

  it('shows every student with their classes, searches by name and opens a class from a tag', async () => {
    asRole('ADMIN')
    vi.mocked(api.classrooms).mockResolvedValue([
      { id: 10, name: '중2 수학', class_type: 'REGULAR', is_active: true },
      { id: 11, name: '고1 영어', class_type: 'REGULAR', is_active: true },
    ])
    vi.mocked(api.allStudents).mockResolvedValue({
      total: 2, limit: 50, offset: 0, items: [
        { id: 7, name: '가상하나', school_name: '가상중', parent_name: null, parent_email: 'p1@example.invalid', enrollments: [
          { enrollment_id: 1, classroom_id: 10, classroom_name: '중2 수학', status: 'ACTIVE', enrolled_at: '2026-11-01' },
          { enrollment_id: 2, classroom_id: 11, classroom_name: '고1 영어', status: 'PAUSED', enrolled_at: '2026-11-02' },
        ] },
        { id: 8, name: '가상둘', school_name: null, parent_name: null, parent_email: null, enrollments: [] },
      ],
    })
    renderPage()

    expect(await screen.findByText('전체 학생 목록 (2명)')).toBeInTheDocument()
    expect(screen.getByText('중2 수학 · 재원')).toBeInTheDocument()
    expect(screen.getByText('고1 영어 · 휴원')).toBeInTheDocument()
    expect(screen.getByText('수강 반 없음')).toBeInTheDocument()
    expect(screen.getByText('p1@example.invalid')).toBeInTheDocument()

    const search = screen.getByLabelText('학생 이름 검색')
    fireEvent.change(search, { target: { value: ' 하나 ' } })
    fireEvent.keyDown(search, { key: 'Enter', code: 'Enter', keyCode: 13 })
    await waitFor(() => expect(api.allStudents).toHaveBeenCalledWith('하나', 50, 0))

    fireEvent.click(screen.getByText('고1 영어 · 휴원'))
    expect(await screen.findByText('고1 영어 학생 목록')).toBeInTheDocument()
    await waitFor(() => expect(api.students).toHaveBeenLastCalledWith(11))
  })

  it('registers a student together with the class in one save, keeping the class for the next one', async () => {
    asRole('ADMIN')
    vi.mocked(api.classrooms).mockResolvedValue([{ id: 10, name: '중2 수학', class_type: 'REGULAR', is_active: true }])
    vi.mocked(api.createStudent).mockResolvedValue({ id: 42, name: '가상신입', school_name: null })
    renderPage()

    const studentCard = (await screen.findByText('학생 등록', { selector: '.ant-card-head-title' })).closest('.ant-card') as HTMLElement
    fireEvent.change(within(studentCard).getByLabelText('학생 이름'), { target: { value: '가상신입' } })
    fireEvent.mouseDown(within(studentCard).getByLabelText('수강 반'))
    fireEvent.click(await screen.findByTitle('중2 수학', { exact: true }))
    fireEvent.change(within(studentCard).getByLabelText('수강 등록일'), { target: { value: '2026-11-19' } })
    fireEvent.click(within(studentCard).getByText('학생 등록', { selector: 'button span' }))
    await waitFor(() => expect(api.createStudent).toHaveBeenCalledWith('가상신입', '', undefined, { classroom_id: 10, enrolled_at: '2026-11-19' }))
    expect(await screen.findByText('가상신입 학생을 등록하고 중2 수학 반에 수강 등록했습니다.')).toBeInTheDocument()
    expect(api.enroll).not.toHaveBeenCalled() // one save, not two requests
    // Name cleared, class and date kept for the next student of the same class.
    expect(within(studentCard).getByLabelText('학생 이름')).toHaveValue('')
    expect(within(studentCard).getByLabelText('수강 등록일')).toHaveValue('2026-11-19')
  })

  it('enrolls an existing student in another class from the class list', async () => {
    asRole('ADMIN')
    vi.mocked(api.classrooms).mockResolvedValue([{ id: 10, name: '중2 수학', class_type: 'REGULAR', is_active: true }])
    vi.mocked(api.createStudent).mockResolvedValue({ id: 42, name: '가상신입', school_name: null })
    vi.mocked(api.enroll).mockResolvedValue({})
    renderPage()

    // Registered without a class first: the class can be added later.
    const studentCard = (await screen.findByText('학생 등록', { selector: '.ant-card-head-title' })).closest('.ant-card') as HTMLElement
    fireEvent.change(within(studentCard).getByLabelText('학생 이름'), { target: { value: '가상신입' } })
    fireEvent.click(within(studentCard).getByText('학생 등록', { selector: 'button span' }))
    await waitFor(() => expect(api.createStudent).toHaveBeenCalledWith('가상신입', '', undefined, undefined))

    await openClassTab()
    fireEvent.click(await screen.findByText('기존 학생 수강 추가'))
    const dialog = (await screen.findByText('중2 수학 반에 기존 학생 수강 추가')).closest('.ant-modal') as HTMLElement
    expect(await within(dialog).findByText('가상신입 (ID 42)')).toBeInTheDocument() // the student just registered
    fireEvent.change(within(dialog).getByLabelText('등록일'), { target: { value: '2026-11-19' } })
    fireEvent.click(within(dialog).getByText('수강 등록', { selector: 'button span' }))
    await waitFor(() => expect(api.enroll).toHaveBeenCalledWith(10, 42, '2026-11-19'))
    expect(await screen.findByText('수강 등록을 완료했습니다. (중2 수학)')).toBeInTheDocument()
  })

  it('manages classes: ends operation, refuses to delete a class with records, renames', async () => {
    asRole('ADMIN')
    const { ApiClientError } = await import('../../shared/api/ApiClientError')
    const used = { id: 10, name: '중2 수학', class_type: 'REGULAR', is_active: true }
    const typo = { id: 11, name: '002 토2', class_type: 'EXAM_PREP', is_active: true }
    const ended = { id: 12, name: '지난 반', class_type: 'REGULAR', is_active: false }
    vi.mocked(api.classrooms).mockImplementation(async (includeInactive?: boolean) => includeInactive ? [used, typo, ended] : [used, typo])
    vi.mocked(api.updateClassroom).mockResolvedValue({ ...used, is_active: false })
    vi.mocked(api.deleteClassroom).mockRejectedValue(new ApiClientError("수강생·수업·평가 기록이 있는 반은 삭제할 수 없습니다. 대신 '운영 종료'를 사용하세요.", 'CLASSROOM_HAS_RECORDS'))
    renderPage()

    fireEvent.click(await screen.findByText('반 관리'))
    expect(await screen.findByText('반 목록 (운영 중 2개)')).toBeInTheDocument()
    expect(screen.queryByText('지난 반')).not.toBeInTheDocument() // ended classes are folded away
    fireEvent.click(screen.getByText('운영 종료된 반도 보기 (1)'))
    expect(await screen.findByText('지난 반')).toBeInTheDocument()
    expect(screen.getByText('다시 운영')).toBeInTheDocument()

    const usedRow = screen.getByText('중2 수학').closest('tr') as HTMLElement
    fireEvent.click(within(usedRow).getByText('삭제'))
    const deletePop = (await screen.findByText('중2 수학 반을 삭제할까요?')).closest('.ant-popover') as HTMLElement
    fireEvent.click(within(deletePop).getByText('삭제'))
    expect(await screen.findByText("수강생·수업·평가 기록이 있는 반은 삭제할 수 없습니다. 대신 '운영 종료'를 사용하세요.")).toBeInTheDocument()

    fireEvent.click(within(usedRow).getByText('운영 종료'))
    const endPop = (await screen.findByText('중2 수학 반을 운영 종료할까요?')).closest('.ant-popover') as HTMLElement
    fireEvent.click(within(endPop).getByText('운영 종료'))
    await waitFor(() => expect(api.updateClassroom).toHaveBeenCalledWith(10, { is_active: false }))
    expect(await screen.findByText('중2 수학 반을 운영 종료했습니다.')).toBeInTheDocument()

    const typoRow = screen.getByText('002 토2').closest('tr') as HTMLElement
    fireEvent.click(within(typoRow).getByText('이름 수정'))
    const dialog = (await screen.findByText('002 토2 이름 수정')).closest('.ant-modal') as HTMLElement
    fireEvent.change(within(dialog).getByLabelText('반 이름'), { target: { value: '00고2 토2' } })
    fireEvent.click(within(dialog).getByText('저장', { selector: 'button span' }))
    await waitFor(() => expect(api.updateClassroom).toHaveBeenCalledWith(11, { name: '00고2 토2' }))
  })
})
