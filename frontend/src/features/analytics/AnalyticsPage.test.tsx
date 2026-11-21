import { configure, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useAuth } from '../auth/AuthProvider'
import * as classwork from '../classwork/api'
import * as learningops from '../learningops/api'
import { AnalyticsPage } from './AnalyticsPage'
import * as api from './api'

configure({ asyncUtilTimeout: 10000 })
vi.mock('../auth/AuthProvider', () => ({ useAuth: vi.fn() }))
vi.mock('../classwork/api', () => ({ listClassrooms: vi.fn() }))
vi.mock('../learningops/api', () => ({ students: vi.fn() }))
vi.mock('./api', () => ({
  getAttendance: vi.fn(), getStudentAttendance: vi.fn(), getGrades: vi.fn(), getAssessment: vi.fn(), getStudentGrades: vi.fn(),
  getWatchlist: vi.fn(), getStudentReport: vi.fn(),
}))
const noWatch: api.Watchlist = { classroom_id: 1, window_from: '2026-08-21', window_to: '2026-11-20', rules: ['규칙'], students: [] }

const counts = (patch: Partial<api.AttendanceCounts> = {}): api.AttendanceCounts => ({
  target: 16, recorded: 12, unrecorded: 4, present: 5, late: 3, absent: 2, excused: 2, outside_records: 1,
  record_rate: 75, attendance_rate: 80, ...patch,
})
const attendance: api.AttendanceAnalytics = {
  classroom_id: 1, date_from: '2026-10-01', date_to: '2026-10-31', counted_until: '2026-10-31',
  policy: { held_lesson: '진행된 수업', attendance_rate: '(출석 + 지각) ÷ (입력된 출결 − 인정결석)' },
  summary: counts(), held_lessons: 5, not_held_lessons: 1,
  students: [
    { enrollment_id: 1, student_id: 11, student_name: '가상하나', enrollment_status: 'ACTIVE', ...counts({ target: 5, recorded: 3, unrecorded: 2, record_rate: 60, attendance_rate: 100 }) },
    { enrollment_id: 2, student_id: 12, student_name: '가상둘', enrollment_status: 'WITHDRAWN', ...counts({ target: 0, recorded: 0, unrecorded: 0, record_rate: null, attendance_rate: null }) },
  ],
  lessons: [{ lesson_id: 7, lesson_date: '2026-10-15', session_no: 1, topic: '이차함수', target: 2, recorded: 1, unrecorded: 1 }],
}
const stats = (patch: Partial<api.AssessmentStats> = {}): api.AssessmentStats => ({
  assessment_id: 5, title: '어휘', assessment_date: '2026-10-05', max_score: 10, lesson_id: 7, upcoming: false,
  target: 4, scored: 2, not_taken: 1, missing: 1, outside_records: 1, entry_rate: 75, average: 5.67, average_count: 3, average_percent: 56.7, ...patch,
})

function Where() {
  const location = useLocation()
  return <div>{`이동: ${location.pathname}${location.search}`}</div>
}
const renderPage = (path = '/analytics?classroom=1&from=2026-10-01&to=2026-10-31') => render(
  <MemoryRouter initialEntries={[path]}>
    <Routes>
      <Route path="/analytics" element={<AnalyticsPage />} />
      <Route path="*" element={<Where />} />
    </Routes>
  </MemoryRouter>,
)

describe('AnalyticsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(useAuth).mockReturnValue({ user: { id: 2, email: 'user@example.invalid', role: 'TEACHER' }, loading: false, login: vi.fn(), logout: vi.fn() })
    vi.mocked(classwork.listClassrooms).mockResolvedValue([{ id: 1, name: '중3 토10', class_type: 'REGULAR', is_active: true }])
    vi.mocked(api.getAttendance).mockResolvedValue(attendance)
    vi.mocked(learningops.students).mockResolvedValue([])
    vi.mocked(api.getWatchlist).mockResolvedValue(noWatch)
  })

  it('shows the attendance figures from the server, the distribution in words and the excluded lessons', async () => {
    renderPage()
    expect(await screen.findByText('75.0%')).toBeInTheDocument() // record rate
    expect(screen.getByText('80.0%')).toBeInTheDocument() // attendance rate
    expect(api.getAttendance).toHaveBeenCalledWith({ classroomId: 1, dateFrom: '2026-10-01', dateTo: '2026-10-31' })
    expect(screen.getByText('진행 기록이 없는 지난 수업 1개는 집계에서 빠졌습니다.')).toBeInTheDocument()
    expect(screen.getByText('수강 기간 밖 기록 1건은 대상·비율에 넣지 않았습니다.')).toBeInTheDocument()
    // Distribution legend carries state names and counts (colour is never the only signal).
    expect(screen.getByLabelText('입력된 출결 12건의 상태 분포')).toBeInTheDocument()
    const legend = document.querySelector('.chart-legend') as HTMLElement
    expect(within(legend).getByText('인정결석')).toBeInTheDocument()
    expect(within(legend).getByText('41.7%')).toBeInTheDocument() // 5 of 12 present
    // A student with nothing to take shows "대상 없음", never 0%.
    const row = screen.getByText('가상둘').closest('tr') as HTMLElement
    expect(within(row).getByText('대상 없음')).toBeInTheDocument()
    expect(within(row).getByText('계산 불가')).toBeInTheDocument()
    // Missing attendance links to that lesson's entry screen.
    fireEvent.click(screen.getByText('출결 입력'))
    expect(await screen.findByText('이동: /classes?classroom=1&tab=attendance&lesson=7')).toBeInTheDocument()
  })

  it("opens a student's lesson-by-lesson attendance and keeps the student in the address", async () => {
    vi.mocked(api.getStudentAttendance).mockResolvedValue({
      classroom_id: 1, student_id: 11, student_name: '가상하나', enrollment_id: 1, date_from: '2026-10-01', date_to: '2026-10-31',
      counted_until: '2026-10-31', summary: counts({ target: 2, recorded: 1, unrecorded: 1, record_rate: 50 }),
      rows: [
        { lesson_id: 7, lesson_date: '2026-10-15', session_no: 1, topic: null, eligible: true, status: 'LATE' },
        { lesson_id: 8, lesson_date: '2026-10-16', session_no: 2, topic: null, eligible: true, status: null },
      ],
    })
    renderPage()
    fireEvent.click(await screen.findByText('가상하나'))
    expect(await screen.findByText('가상하나 수업별 출결')).toBeInTheDocument()
    expect(api.getStudentAttendance).toHaveBeenCalledWith(11, { classroomId: 1, dateFrom: '2026-10-01', dateTo: '2026-10-31' })
    const missing = screen.getByText('2026-10-16 2교시').closest('tr') as HTMLElement
    expect(within(missing).getByText('미입력')).toBeInTheDocument() // not entered ≠ absent
    fireEvent.click(within(missing).getByText('출결 입력'))
    expect(await screen.findByText('이동: /classes?classroom=1&tab=attendance&lesson=8')).toBeInTheDocument()
  })

  it('explains an empty period with a way to the entry screen, and shows server errors as they are', async () => {
    vi.mocked(api.getAttendance).mockResolvedValueOnce({ ...attendance, summary: counts({ target: 0, recorded: 0, unrecorded: 0, present: 0, late: 0, absent: 0, excused: 0, outside_records: 0, record_rate: null, attendance_rate: null }), students: [], lessons: [], not_held_lessons: 0 })
    renderPage()
    expect(await screen.findByText(/기간에 진행된 수업이 없습니다/)).toBeInTheDocument()
    fireEvent.click(screen.getByText('출결 관리로 이동'))
    expect(await screen.findByText('이동: /classes?classroom=1&tab=attendance')).toBeInTheDocument()
  })

  it('does not query an impossible period', async () => {
    renderPage('/analytics?classroom=1&from=2026-10-31&to=2026-10-01')
    expect(await screen.findByText('시작일이 종료일보다 늦습니다. 기간을 고쳐주세요.')).toBeInTheDocument()
    expect(api.getAttendance).not.toHaveBeenCalled()
  })

  it('shows the server message when access is denied', async () => {
    const { ApiClientError } = await import('../../shared/api/ApiClientError')
    vi.mocked(api.getAttendance).mockRejectedValue(new ApiClientError('담당 반에만 접근할 수 있습니다.', 'CLASSROOM_ACCESS_DENIED'))
    renderPage()
    expect(await screen.findByText('담당 반에만 접근할 수 있습니다.')).toBeInTheDocument()
  })

  it('summarises each session for the class, separates missing from zero and opens a session', async () => {
    vi.mocked(api.getGrades).mockResolvedValue({
      classroom_id: 1, date_from: '2026-10-01', date_to: '2026-10-31',
      assessments: [stats(), stats({ assessment_id: 6, title: '기말', upcoming: true, scored: 0, not_taken: 0, missing: 4, outside_records: 0, entry_rate: null, average: null, average_count: 0, average_percent: null })],
    })
    vi.mocked(api.getAssessment).mockResolvedValue({
      classroom_id: 1, stats: stats(),
      rows: [
        { enrollment_id: 1, student_id: 11, student_name: '가상하나', eligible: true, status: 'SCORED', score: 0, percent: 0 },
        { enrollment_id: 2, student_id: 12, student_name: '가상둘', eligible: true, status: 'MISSING', score: null, percent: null },
      ],
    })
    renderPage('/analytics?tab=grades&classroom=1&from=2026-10-01&to=2026-10-31')
    expect(await screen.findByText('5.67점 (3명)')).toBeInTheDocument()
    expect(screen.getByText('점수 0 · 미응시 0 · 미입력 4 / 대상 4 (평가 전)')).toBeInTheDocument() // upcoming
    expect(screen.getByText('점수 없음')).toBeInTheDocument()

    fireEvent.click(screen.getByText('어휘', { selector: 'a' }))
    expect(await screen.findByText('점수 미입력 1명 — 0점이 아니라 아직 입력하지 않은 것입니다.')).toBeInTheDocument()
    await waitFor(() => expect(api.getAssessment).toHaveBeenCalledWith(5))
    fireEvent.click(screen.getByText('성적 입력 (학습 현황)'))
    expect(await screen.findByText('이동: /classes?classroom=1&tab=progress&day=2026-10-05')).toBeInTheDocument()
  })

  it('lists students who need attention with every reason, and opens their report', async () => {
    vi.mocked(api.getGrades).mockResolvedValue({ classroom_id: 1, date_from: '2026-10-01', date_to: '2026-10-31', assessments: [] })
    vi.mocked(api.getWatchlist).mockResolvedValue({
      ...noWatch, rules: ['학생별 최근 기록으로 판단합니다.', '점수: 같은 평가 항목의 최근 4회 중 3회 이상 같은 회차 반 평균보다 15%p 이상 낮음'],
      students: [{ enrollment_id: 2, student_id: 12, student_name: '가상둘', reasons: [
        { code: 'LOW_SCORE', title: '어휘', count: 3, text: '어휘: 최근 4회 중 3회 반 평균보다 15%p 이상 낮음' },
        { code: 'ABSENCE', title: null, count: 2, text: '최근 4회 수업 중 결석·미응시 2회 (결석 1, 미응시 1)' },
      ] }],
    })
    vi.mocked(api.getStudentReport).mockResolvedValue({
      classroom_id: 1, student_id: 12, student_name: '가상둘', enrollment_id: 2, date_from: '2026-10-01', date_to: '2026-10-31',
      categories: [], attendance: counts({ target: 0, recorded: 0, unrecorded: 0, present: 0, late: 0, absent: 0, excused: 0, outside_records: 0, record_rate: null, attendance_rate: null }),
      lessons: [], watch_reasons: [],
    })
    renderPage('/analytics?tab=grades&classroom=1&from=2026-10-01&to=2026-10-31')

    expect(await screen.findByText('관심 필요 학생 (학생별 최근 4회 기준)')).toBeInTheDocument()
    expect(screen.getByText('2026-08-21 ~ 2026-11-20 기록에서 판단')).toBeInTheDocument()
    const item = screen.getByText('가상둘').closest('.ant-list-item') as HTMLElement
    expect(within(item).getByText('어휘: 최근 4회 중 3회 반 평균보다 15%p 이상 낮음')).toBeInTheDocument()
    expect(within(item).getByText('최근 4회 수업 중 결석·미응시 2회 (결석 1, 미응시 1)')).toBeInTheDocument()
    fireEvent.click(screen.getByText('판단 기준'))
    expect(await screen.findByText('점수: 같은 평가 항목의 최근 4회 중 3회 이상 같은 회차 반 평균보다 15%p 이상 낮음')).toBeInTheDocument()
    fireEvent.click(within(item).getByText('리포트 보기'))
    await waitFor(() => expect(api.getStudentReport).toHaveBeenCalledWith(12, { classroomId: 1, dateFrom: '2026-10-01', dateTo: '2026-10-31' }))
  })

  it('reports a student per 평가 항목 against the class average of each session, with homework and attendance', async () => {
    vi.mocked(api.getGrades).mockResolvedValue({ classroom_id: 1, date_from: '2026-10-01', date_to: '2026-10-31', assessments: [] })
    vi.mocked(learningops.students).mockResolvedValue([{ id: 11, enrollment_id: 1, name: '가상하나', school_name: null, enrollment_status: 'ACTIVE', enrolled_at: '2026-01-01' }])
    const point = (patch: Partial<api.ReportPoint>): api.ReportPoint => ({
      assessment_id: 5, title: '어휘', assessment_date: '2026-10-05', max_score: 10, lesson_id: 7, eligible: true, status: 'SCORED',
      score: 6, percent: 60, class_average_percent: 75, diff: -15, ...patch,
    })
    vi.mocked(api.getStudentReport).mockResolvedValue({
      classroom_id: 1, student_id: 11, student_name: '가상하나', enrollment_id: 1, date_from: '2026-10-01', date_to: '2026-10-31',
      categories: [{ title: '어휘', scored_count: 2, average_diff: -12.5, points: [point({}), point({ assessment_id: 6, assessment_date: '2026-10-12', score: 7, percent: 70, class_average_percent: 80, diff: -10 })] }],
      attendance: counts({ target: 2, recorded: 2, unrecorded: 0, present: 1, late: 1, absent: 0, excused: 0, outside_records: 0, record_rate: 100, attendance_rate: 100 }),
      lessons: [
        { lesson_id: 7, lesson_date: '2026-10-05', session_no: 1, topic: null, eligible: true, status: 'PRESENT', prework: 'A', weekly: 'C' },
        { lesson_id: 8, lesson_date: '2026-10-12', session_no: 1, topic: null, eligible: true, status: 'LATE', prework: null, weekly: 'B' },
      ],
      watch_reasons: [{ code: 'HOMEWORK_C', title: null, count: 2, text: '최근 4회 수업 중 주간 과제 C 등급 2회' }],
    })
    renderPage('/analytics?tab=grades&classroom=1&from=2026-10-01&to=2026-10-31&student=11')

    expect(await screen.findByText('어휘 · 반 평균 대비 −12.5%p (점수 2회)')).toBeInTheDocument()
    expect(screen.getByLabelText('가상하나 학생의 어휘 만점 대비 점수(%)와 반 평균')).toBeInTheDocument()
    expect(screen.getByText('실선: 학생 · 점선: 같은 회차 반 평균')).toBeInTheDocument()
    expect(screen.getByText('−15.0%p')).toBeInTheDocument()
    expect(screen.getByText('가상하나: 관심 필요 (최근 기록 기준)')).toBeInTheDocument()
    expect(screen.getByText('최근 4회 수업 중 주간 과제 C 등급 2회')).toBeInTheDocument()
    expect(screen.getByText('출결: 출석률 100.0% · 출석 1 · 지각 1 · 결석 0 · 인정결석 0 · 미입력 0')).toBeInTheDocument()
    const lessons = screen.getByText('수업별 출결·과제').closest('.ant-card') as HTMLElement
    const lessonRow = within(lessons).getByText('2026-10-12').closest('tr') as HTMLElement
    expect(within(lessonRow).getByText('지각')).toBeInTheDocument()
  })
})
