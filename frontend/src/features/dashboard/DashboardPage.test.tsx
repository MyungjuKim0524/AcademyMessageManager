import { configure, fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useAuth } from '../auth/AuthProvider'
import * as classwork from '../classwork/api'
import * as ops from '../message-operations/api'
import { todayLocal } from '../../shared/date'
import { DashboardPage } from './DashboardPage'

configure({ asyncUtilTimeout: 10000 })
vi.mock('../auth/AuthProvider', () => ({ useAuth: vi.fn() }))
vi.mock('../classwork/api', () => ({ listClassrooms: vi.fn(), getProgress: vi.fn() }))
vi.mock('../message-operations/api', () => ({ getTodo: vi.fn() }))

const day = todayLocal()
const asRole = (role: 'ADMIN' | 'TEACHER' | 'ASSISTANT') => vi.mocked(useAuth).mockReturnValue({
  user: { id: 2, email: 'user@example.invalid', role }, loading: false, login: vi.fn(), logout: vi.fn(),
})
const cell = (attendance: classwork.AttendanceStatus | null, eligible = true): classwork.ProgressCell => ({
  key: 'lesson:7', eligible, attendance_status: attendance, prework_grade: null, weekly_grade: null, result_version: null, scores: [],
})
// Class 1 has today's lesson with 1 of 2 students recorded (1 student paused); class 2 has none.
const today: classwork.ClassProgress = {
  classroom_id: 1, date_from: day, date_to: day,
  columns: [{ key: 'lesson:7', kind: 'LESSON', lesson_id: 7, day, session_no: 1, exam_round: null, topic: '이차함수', lesson_status: 'COMPLETED', assessments: [] }],
  students: [
    { enrollment_id: 1, student_id: 11, student_name: '가상하나', enrollment_status: 'ACTIVE', cells: [cell('PRESENT')] },
    { enrollment_id: 2, student_id: 12, student_name: '가상둘', enrollment_status: 'ACTIVE', cells: [cell(null)] },
    { enrollment_id: 3, student_id: 13, student_name: '가상셋', enrollment_status: 'PAUSED', cells: [cell(null, false)] },
  ],
}
// Unfinished notices per class lesson, most urgent first (as the server orders them).
const todo = (patch: Partial<ops.TodoItem>): ops.TodoItem => ({
  classroom_id: 1, classroom_name: '중3 토10', lesson_id: 7, lesson_date: '2026-11-14', session_no: 1,
  failed: 0, ready_to_send: 0, in_review: 0, missing: 0, missing_no_email: 0, missing_no_attendance: 0, next_action: 'REVIEW', ...patch,
})
const todoItems = [
  todo({ failed: 1, in_review: 2, next_action: 'RETRY' }),
  todo({ classroom_id: 2, classroom_name: '00고2 토10', lesson_id: 8, missing: 3, missing_no_email: 2, missing_no_attendance: 1, next_action: 'COMPOSE' }),
]

function Where() {
  const location = useLocation()
  return <div>{`이동: ${location.pathname}${location.search}`}</div>
}
const renderPage = () => render(
  <MemoryRouter initialEntries={['/']}>
    <Routes>
      <Route path="/" element={<DashboardPage />} />
      <Route path="*" element={<Where />} />
    </Routes>
  </MemoryRouter>,
)

describe('DashboardPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(classwork.listClassrooms).mockResolvedValue([
      { id: 1, name: '중3 토10', class_type: 'REGULAR', is_active: true },
      { id: 2, name: '00고2 토10', class_type: 'EXAM_PREP', is_active: true },
    ])
    vi.mocked(classwork.getProgress).mockImplementation(async (id: number) => (id === 1 ? today : { ...today, classroom_id: 2, columns: [], students: [] }))
    vi.mocked(ops.getTodo).mockResolvedValue({ date_from: '2026-08-20', date_to: day, items: todoItems })
  })

  it("counts today's attendance from eligible students only and shows message work, for the visible classes", async () => {
    asRole('TEACHER')
    renderPage()
    expect(await screen.findByText('출결 1/2명')).toBeInTheDocument() // the paused student is not counted
    expect(screen.getByText('출결 입력이 끝나지 않은 수업 1개')).toBeInTheDocument()
    expect(screen.getByText('오늘 수업이 없는 반: 00고2 토10')).toBeInTheDocument()
    expect(classwork.getProgress).toHaveBeenCalledWith(1, day, day)
    expect(await screen.findByText('발송 실패 1건')).toBeInTheDocument()
  })

  it('lists unfinished notices per class lesson with what is left and why, most urgent first', async () => {
    asRole('TEACHER')
    renderPage()
    const first = (await screen.findByText('발송 실패 1건')).closest('.ant-list-item') as HTMLElement
    expect(within(first).getByText('중3 토10')).toBeInTheDocument()
    expect(within(first).getByText('2026-11-14 수업')).toBeInTheDocument()
    expect(within(first).getByText('검토 대기 2건')).toBeInTheDocument()
    const second = screen.getByText('안내 없음 3명 (이메일 없음 2 · 출결 미입력 1)').closest('.ant-list-item') as HTMLElement
    expect(within(second).getByText('00고2 토10')).toBeInTheDocument()
    fireEvent.click(within(first).getByText('실패 건 재시도'))
    expect(await screen.findByText('이동: /notifications?classroom=1&tab=review&lesson=7')).toBeInTheDocument()
  })

  it('opens 누락·예외 생성 for that lesson when only messages are missing, and says when nothing is left', async () => {
    asRole('TEACHER')
    vi.mocked(ops.getTodo).mockResolvedValueOnce({ date_from: '2026-08-20', date_to: day, items: [todoItems[1]] })
    renderPage()
    fireEvent.click(await screen.findByText('초안 만들기'))
    expect(await screen.findByText('이동: /notifications?classroom=2&tab=compose&lesson=8')).toBeInTheDocument()
  })

  it('says there is nothing to do when every notice is finished', async () => {
    asRole('TEACHER')
    vi.mocked(ops.getTodo).mockResolvedValueOnce({ date_from: '2026-08-20', date_to: day, items: [] })
    renderPage()
    expect(await screen.findByText('처리할 성적 안내가 없습니다.')).toBeInTheDocument()
  })

  it("opens today's lesson attendance for that class, and a message count as a filtered list", async () => {
    asRole('ASSISTANT')
    renderPage()
    const item = (await screen.findByText('출결 1/2명')).closest('.ant-list-item') as HTMLElement
    fireEvent.click(within(item).getByText('출결 입력'))
    expect(await screen.findByText('이동: /classes?classroom=1&tab=attendance&lesson=7')).toBeInTheDocument()
  })

  it('shows an error instead of an empty list when a section cannot be loaded, and retries', async () => {
    asRole('ASSISTANT')
    const { ApiClientError } = await import('../../shared/api/ApiClientError')
    vi.mocked(ops.getTodo).mockRejectedValueOnce(new ApiClientError('요청을 처리하지 못했습니다.', 'HTTP_500'))
    renderPage()
    expect(await screen.findByText('요청을 처리하지 못했습니다.')).toBeInTheDocument()
    expect(screen.queryByText('처리할 성적 안내가 없습니다.')).not.toBeInTheDocument()
    fireEvent.click(screen.getByText('다시 시도'))
    expect(await screen.findByText('발송 실패 1건')).toBeInTheDocument()
  })

  it('links quick actions to the work screens (no legacy import card, no review or failure shortcut)', async () => {
    asRole('ADMIN')
    renderPage()
    await screen.findByText('출결 1/2명')
    expect(screen.queryByText('최근 CSV/XLSX 가져오기')).not.toBeInTheDocument() // legacy import removed
    expect(screen.queryByText('메시지 검토·발송')).not.toBeInTheDocument() // removed from quick actions
    expect(screen.queryByText('발송 실패 확인')).not.toBeInTheDocument() // now in 성적 안내 할 일
    fireEvent.click(screen.getByText('엑셀 업로드'))
    expect(await screen.findByText('이동: /notifications?tab=upload')).toBeInTheDocument()
  })
})
