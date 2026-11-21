import { configure, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useAuth } from '../auth/AuthProvider'
import { ClassworkPage } from './ClassworkPage'
import * as api from './api'
import { todayLocal } from './common'
import { draftError } from './GradesTab'

// Queries avoid getByRole: jsdom style resolution makes it extremely slow on antd-heavy screens.
// The tabbed tables also take >1s to appear under jsdom, so allow longer async waits.
configure({ asyncUtilTimeout: 10000 })
vi.mock('../auth/AuthProvider', () => ({ useAuth: vi.fn() }))
vi.mock('./api', () => ({
  listClassrooms: vi.fn(), listLessons: vi.fn(), createLesson: vi.fn(), updateLesson: vi.fn(),
  getAttendance: vi.fn(), saveAttendance: vi.fn(), listAssessments: vi.fn(), createAssessment: vi.fn(),
  updateAssessment: vi.fn(), getGrades: vi.fn(), saveGrades: vi.fn(), getStudentRecords: vi.fn(),
  getProgress: vi.fn(), updateRecord: vi.fn(), startTodayLesson: vi.fn(),
}))

const stamp = '2026-11-03T00:00:00Z'
const lesson: api.LessonListItem = {
  id: 7, classroom_id: 1, lesson_date: '2026-11-03', session_no: 1, exam_round: null, topic: '이차함수', memo: null,
  status: 'COMPLETED', version: 1, created_at: stamp, updated_at: stamp, attendance_recorded: 1,
}
const roster: api.AttendanceRoster = {
  lesson, changed: null,
  summary: { eligible: 2, recorded: 1, unrecorded: 1, present: 1, absent: 0, late: 0, excused: 0 },
  items: [
    { enrollment_id: 1, student_id: 11, student_name: '김하나', school_name: null, eligible: true, record: { status: 'PRESENT', memo: null, version: 3, updated_at: stamp } },
    { enrollment_id: 2, student_id: 12, student_name: '이두리', school_name: null, eligible: true, record: null },
  ],
}
const assessment: api.AssessmentListItem = {
  id: 5, classroom_id: 1, lesson_id: null, title: '단원 평가', assessment_date: '2026-11-03', max_score: 10,
  version: 1, created_at: stamp, updated_at: stamp, scored: 0, not_taken: 0,
}
const gradeRoster: api.GradeRoster = {
  assessment, changed: null,
  summary: { eligible: 1, scored: 0, not_taken: 0, unrecorded: 1 },
  items: [{ enrollment_id: 1, student_id: 11, student_name: '김하나', school_name: null, eligible: true, record: null }],
}

// 학습 현황: one lesson with a linked 어휘 test, and one stand-alone 모의고사.
const progress: api.ClassProgress = {
  classroom_id: 1, date_from: '2026-10-23', date_to: '2026-11-19',
  columns: [
    { key: 'lesson:7', kind: 'LESSON', lesson_id: 7, day: '2026-11-03', session_no: 1, exam_round: null, topic: '이차함수', lesson_status: 'COMPLETED',
      assessments: [{ id: 5, title: '어휘', max_score: 10, version: 1 }] },
    { key: 'assessment:9', kind: 'ASSESSMENT', lesson_id: null, day: '2026-11-05', session_no: null, exam_round: null, topic: null, lesson_status: null,
      assessments: [{ id: 9, title: '모의고사', max_score: 100, version: 1 }] },
  ],
  students: [
    { enrollment_id: 1, student_id: 11, student_name: '김하나', enrollment_status: 'ACTIVE', cells: [
      { key: 'lesson:7', eligible: true, attendance_status: 'PRESENT', prework_grade: 'A', weekly_grade: null, result_version: 3, scores: [] },
      { key: 'assessment:9', eligible: true, attendance_status: null, prework_grade: null, weekly_grade: null, result_version: null,
        scores: [{ assessment_id: 9, result_status: 'SCORED', score: 80, memo: '오답 노트', version: 2 }] },
    ] },
    { enrollment_id: 2, student_id: 12, student_name: '이두리', enrollment_status: 'ACTIVE', cells: [
      { key: 'lesson:7', eligible: false, attendance_status: null, prework_grade: null, weekly_grade: null, result_version: null, scores: [] },
      { key: 'assessment:9', eligible: true, attendance_status: null, prework_grade: null, weekly_grade: null, result_version: null, scores: [] },
    ] },
  ],
}

const asRole = (role: 'ADMIN' | 'TEACHER' | 'ASSISTANT') => vi.mocked(useAuth).mockReturnValue({
  user: { id: 2, email: 'user@example.invalid', role }, loading: false, login: vi.fn(), logout: vi.fn(),
})

const rowOf = (text: string) => screen.getByText(text).closest('tr') as HTMLElement

function Where() {
  const location = useLocation()
  return <div>{`이동: ${location.pathname}${location.search}`}</div>
}
const renderPage = (path = '/classes') => render(
  <MemoryRouter initialEntries={[path]}>
    <Routes>
      <Route path="/classes" element={<><ClassworkPage /><Where /></>} />
      <Route path="*" element={<Where />} />
    </Routes>
  </MemoryRouter>,
)

describe('ClassworkPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(api.listClassrooms).mockResolvedValue([{ id: 1, name: '수학 A반', class_type: 'REGULAR', is_active: true }])
    vi.mocked(api.listLessons).mockResolvedValue([lesson])
    vi.mocked(api.getAttendance).mockResolvedValue(roster)
    vi.mocked(api.saveAttendance).mockResolvedValue({ ...roster, changed: 1 })
    vi.mocked(api.listAssessments).mockResolvedValue([assessment])
    vi.mocked(api.getGrades).mockResolvedValue(gradeRoster)
    vi.mocked(api.saveGrades).mockResolvedValue({ ...gradeRoster, changed: 1 })
    vi.mocked(api.getProgress).mockResolvedValue(progress)
    vi.mocked(api.updateRecord).mockResolvedValue({ changed: 2 })
  })

  const openProgressCell = async (label: string) => {
    fireEvent.click(await screen.findByText('학습 현황'))
    fireEvent.click(await screen.findByLabelText(label))
    return (await screen.findByText('저장하면 변경 이력이 남고', { exact: false })).closest('.ant-modal') as HTMLElement
  }

  it('shows unrecorded students separately from absences and saves only changed rows with versions', async () => {
    asRole('TEACHER')
    renderPage()

    await screen.findByText('이두리')
    expect(api.getAttendance).toHaveBeenCalledWith(7)
    expect(within(rowOf('이두리')).getByText('미입력')).toBeInTheDocument()
    expect(within(rowOf('김하나')).getAllByText('출석').length).toBeGreaterThan(0)
    // Unrecorded students are pre-selected as present on screen, but nothing is stored yet.
    expect(within(rowOf('이두리')).getByText('저장 안 됨')).toBeInTheDocument()
    expect(within(rowOf('김하나')).queryByText('저장 안 됨')).not.toBeInTheDocument()
    expect(screen.getByText('출결 저장 (1건)')).toBeInTheDocument()
    expect(api.saveAttendance).not.toHaveBeenCalled()

    fireEvent.click(within(rowOf('이두리')).getByText('결석'))
    fireEvent.click(screen.getByText('출결 저장 (1건)'))
    await waitFor(() => expect(api.saveAttendance).toHaveBeenCalledWith(7, [
      { enrollment_id: 2, status: 'ABSENT', memo: null, version: null },
    ]))
    expect(await screen.findByText('출결 1건을 저장했습니다.')).toBeInTheDocument()
  })

  it('records EXCUSED separately and labels same-day sessions', async () => {
    asRole('TEACHER')
    const second = { ...lesson, id: 8, session_no: 2, topic: '보충' }
    vi.mocked(api.listLessons).mockResolvedValue([second, lesson])
    vi.mocked(api.getAttendance).mockResolvedValue({ ...roster, lesson: second })
    renderPage()
    await screen.findByText('이두리')
    expect(api.getAttendance).toHaveBeenCalledWith(8)
    expect(screen.getAllByText('2026-11-03 2교시 · 보충').length).toBeGreaterThan(0)
    fireEvent.click(within(rowOf('이두리')).getByText('인정결석'))
    fireEvent.click(screen.getByText('출결 저장 (1건)'))
    await waitFor(() => expect(api.saveAttendance).toHaveBeenCalledWith(8, [
      { enrollment_id: 2, status: 'EXCUSED', memo: null, version: null },
    ]))
  })

  it('maps a server version conflict back to the student row', async () => {
    asRole('TEACHER')
    const { ApiClientError } = await import('../../shared/api/ApiClientError')
    vi.mocked(api.saveAttendance).mockRejectedValue(
      new ApiClientError('다른 사용자가 먼저 변경했습니다.', 'VERSION_CONFLICT', [{ field: 'items.0.version', message: '새로고침 후 다시 시도해주세요.' }]),
    )
    renderPage()
    await screen.findByText('김하나')
    fireEvent.click(within(rowOf('김하나')).getByText('지각'))
    fireEvent.click(screen.getByText('출결 저장 (2건)'))  // 김하나 changed + 이두리 pre-selected
    expect(await screen.findByText('새로고침 후 다시 시도해주세요.')).toBeInTheDocument()
    expect(screen.getByText('다른 사용자가 먼저 변경했습니다. 저장되지 않았습니다.')).toBeInTheDocument()
  })

  it('shows one day as 학생 | 과제 | 시험 종목 columns, blanks as not entered (never zero) and ineligible cells', async () => {
    asRole('TEACHER')
    renderPage()
    await screen.findByText('이두리') // 출결 is the first, default tab
    fireEvent.click(screen.getByText('학습 현황'))
    expect(await screen.findByLabelText('김하나 예습 과제')).toHaveTextContent('A')
    expect(api.getProgress).toHaveBeenCalledWith(1, todayLocal(), todayLocal()) // one day at a time
    // antd may render the header twice (scrollable table with a fixed column), so allow ≥1.
    for (const header of ['예습 과제', '주간 과제', '어휘 (10)', '모의고사 (100)']) expect(screen.getAllByText(header).length).toBeGreaterThan(0)
    expect(screen.getByLabelText('김하나 주간 과제')).toHaveTextContent('-')
    expect(screen.getByLabelText('김하나 어휘')).toHaveTextContent('-')
    expect(screen.getByLabelText('김하나 모의고사')).toHaveTextContent('80')
    expect(screen.getAllByText('대상 아님').length).toBeGreaterThan(0) // 이두리 is outside the period for the lesson
  })

  it('validates scores before saving and corrects attendance, grades and a score of one cell at once', async () => {
    asRole('TEACHER')
    renderPage()
    await screen.findByText('이두리')
    const dialog = await openProgressCell('김하나 어휘')
    const input = within(dialog).getByLabelText('어휘 점수')
    expect((input as HTMLInputElement).value).toBe('') // missing score is blank, not 0

    fireEvent.change(input, { target: { value: '11' } })
    expect(await within(dialog).findByText('만점(10)을 넘을 수 없습니다.')).toBeInTheDocument()
    fireEvent.click(within(dialog).getByText('저장'))
    expect(await within(dialog).findByText('표시된 점수 오류를 먼저 고쳐주세요.')).toBeInTheDocument()
    expect(api.updateRecord).not.toHaveBeenCalled()

    fireEvent.change(input, { target: { value: '9.5' } })
    fireEvent.click(within(dialog).getByText('지각'))
    const weekly = within(dialog).getByText('주간 과제').closest('.ant-space') as HTMLElement
    fireEvent.click(within(weekly).getByText('B'))
    fireEvent.click(within(dialog).getByText('저장'))
    // Grade/score changes ask once before saving, listing before → after.
    const confirm = (await screen.findByText('과제·성적 데이터를 정말 변경할까요?')).closest('.ant-modal') as HTMLElement
    expect(within(confirm).getByText('주간 과제: 미입력 → B')).toBeInTheDocument()
    expect(within(confirm).getByText('어휘: 미입력 → 9.5')).toBeInTheDocument()
    expect(api.updateRecord).not.toHaveBeenCalled()
    fireEvent.click(within(confirm).getByText('변경'))
    await waitFor(() => expect(api.updateRecord).toHaveBeenCalledWith(7, 1, {
      attendance_status: 'LATE', weekly_grade: 'B', result_version: 3,
      scores: [{ assessment_id: 5, result_status: 'SCORED', score: 9.5, version: null }],
    }))
    expect(await screen.findByText('김하나 11-03 기록을 저장했습니다.')).toBeInTheDocument()
  })

  it('corrects a stand-alone assessment score through the grade API, keeping its memo', async () => {
    asRole('TEACHER')
    renderPage()
    await screen.findByText('이두리')
    const dialog = await openProgressCell('김하나 모의고사')
    fireEvent.change(within(dialog).getByLabelText('모의고사 점수'), { target: { value: '85' } })
    fireEvent.click(within(dialog).getByText('저장'))
    const confirm = (await screen.findByText('과제·성적 데이터를 정말 변경할까요?')).closest('.ant-modal') as HTMLElement
    expect(within(confirm).getByText('모의고사: 80 → 85')).toBeInTheDocument()
    fireEvent.click(within(confirm).getByText('변경'))
    await waitFor(() => expect(api.saveGrades).toHaveBeenCalledWith(9, [
      { enrollment_id: 1, result_status: 'SCORED', score: 85, memo: '오답 노트', version: 2 },
    ]))
    expect(api.updateRecord).not.toHaveBeenCalled()
  })

  it('hides lesson editing from assistants but lets them manage assessments and correct attendance, grades and scores', async () => {
    asRole('ASSISTANT')
    renderPage()
    await screen.findByText('이두리')
    expect(screen.getByText('출결 저장 (1건)')).toBeInTheDocument()
    fireEvent.click(screen.getByText('수업'))
    expect(await screen.findByText('수업 목록')).toBeInTheDocument()
    expect(screen.queryByText('수업 등록')).not.toBeInTheDocument()
    fireEvent.click(screen.getByText('평가 관리'))
    // 2026-11-19 decision: assistants may create and edit assessments too.
    // (Phase 9.6: registration opens from a button in the list header instead of a side card.)
    expect(await screen.findByText('평가 등록', { selector: 'button span' })).toBeInTheDocument()
    expect(screen.getByText('평가 수정')).toBeInTheDocument()
    expect(screen.queryByText('평가를 등록·수정할 권한이 없습니다.')).not.toBeInTheDocument()

    // In 학습 현황 an assistant may fix attendance, grades and scores (2026-11-19 decision).
    const dialog = await openProgressCell('김하나 어휘')
    expect(within(dialog).queryByText('과제 등급·점수를 수정할 권한이 없습니다.')).not.toBeInTheDocument()
    expect(within(dialog).getByLabelText('어휘 점수')).not.toBeDisabled()
    // Attendance-only corrections are saved without the grade confirmation.
    fireEvent.click(within(dialog).getByText('지각'))
    fireEvent.click(within(dialog).getByText('저장'))
    await waitFor(() => expect(api.updateRecord).toHaveBeenCalledWith(7, 1, { attendance_status: 'LATE', result_version: 3 }))
    expect(screen.queryByText('과제·성적 데이터를 정말 변경할까요?')).not.toBeInTheDocument()
  })

  it('groups assessment sessions by 평가 항목 and fills an existing 항목 when adding a session', async () => {
    asRole('TEACHER')
    vi.mocked(api.listAssessments).mockResolvedValue([
      { ...assessment, id: 21, title: '어휘', assessment_date: '2026-11-07', max_score: 10, scored: 4, not_taken: 1 },
      { ...assessment, id: 22, title: '어휘', assessment_date: '2026-11-14', max_score: 10, scored: 5, not_taken: 0 },
      { ...assessment, id: 23, title: '문법, 문학, 독서', assessment_date: '2026-11-07', max_score: 15, scored: 5, not_taken: 0 },
      { ...assessment, id: 24, title: '문법, 문학, 독서', assessment_date: '2026-11-14', max_score: 20, scored: 5, not_taken: 0 },
    ])
    renderPage()
    await screen.findByText('이두리')
    fireEvent.click(screen.getByText('평가 관리'))

    expect(await screen.findByText('평가 항목 2개 · 회차 4개')).toBeInTheDocument()
    const vocab = screen.getByText('어휘', { selector: 'td' }).closest('tr') as HTMLElement
    expect(within(vocab).getByText('2회')).toBeInTheDocument()
    expect(within(vocab).getByText('2026-11-14')).toBeInTheDocument() // latest session
    const reading = screen.getByText('문법, 문학, 독서', { selector: 'td' }).closest('tr') as HTMLElement
    expect(within(reading).getByText('회차마다 다름')).toBeInTheDocument() // 15 · 20
    // Sessions are listed under their 항목, newest first, each with its own entry status.
    expect(screen.getByText('점수 4명 · 미응시 1명')).toBeInTheDocument()

    fireEvent.click(screen.getByText('평가 등록', { selector: 'button span' }))
    const dialog = (await screen.findByLabelText('평가명')).closest('.ant-modal') as HTMLElement
    fireEvent.click(within(dialog).getByText('어휘'))
    expect(within(dialog).getByLabelText('평가명')).toHaveValue('어휘')
  })

  it('registers an assessment from the window opened above the full-width list, keeping validation', async () => {
    asRole('TEACHER')
    vi.mocked(api.createAssessment).mockResolvedValue({ ...assessment, id: 6, title: '3단원 평가' })
    renderPage()
    await screen.findByText('이두리')
    fireEvent.click(screen.getByText('평가 관리'))
    expect(await screen.findByText('점수 0명 · 미응시 0명')).toBeInTheDocument()
    fireEvent.click(screen.getByText('평가 등록', { selector: 'button span' }))
    const dialog = (await screen.findByLabelText('평가명')).closest('.ant-modal') as HTMLElement
    fireEvent.click(within(dialog).getByText('등록'))
    expect(await within(dialog).findByText('평가명을 입력해주세요.')).toBeInTheDocument()
    expect(api.createAssessment).not.toHaveBeenCalled()
    fireEvent.change(within(dialog).getByLabelText('평가명'), { target: { value: '3단원 평가' } })
    fireEvent.change(within(dialog).getByLabelText('평가일'), { target: { value: '2026-11-03' } })
    fireEvent.change(within(dialog).getByLabelText('만점'), { target: { value: '20' } })
    fireEvent.click(within(dialog).getByText('등록'))
    await waitFor(() => expect(api.createAssessment).toHaveBeenCalledWith(1, { title: '3단원 평가', assessment_date: '2026-11-03', max_score: 20, lesson_id: null }))
    expect(await screen.findByText("3단원 평가 평가를 등록했습니다. 점수는 '학습 현황'에서 입력·수정하세요.")).toBeInTheDocument()
  })

  it('lets an assistant correct a score after confirming the change', async () => {
    asRole('ASSISTANT')
    renderPage()
    await screen.findByText('이두리')
    const dialog = await openProgressCell('김하나 어휘')
    fireEvent.change(within(dialog).getByLabelText('어휘 점수'), { target: { value: '7' } })
    const prework = within(dialog).getByText('예습 과제').closest('.ant-space') as HTMLElement
    fireEvent.click(within(prework).getByText('B'))
    fireEvent.click(within(dialog).getByText('저장'))
    const confirm = (await screen.findByText('과제·성적 데이터를 정말 변경할까요?')).closest('.ant-modal') as HTMLElement
    expect(within(confirm).getByText('예습 과제: A → B')).toBeInTheDocument()
    fireEvent.click(within(confirm).getByText('변경'))
    await waitFor(() => expect(api.updateRecord).toHaveBeenCalledWith(7, 1, {
      prework_grade: 'B', result_version: 3,
      scores: [{ assessment_id: 5, result_status: 'SCORED', score: 7, version: null }],
    }))
  })

  it("lets an assistant start today's lesson with one click and go straight to attendance", async () => {
    asRole('ASSISTANT')
    const today = { ...lesson, id: 20, lesson_date: todayLocal(), topic: null }
    vi.mocked(api.listLessons).mockResolvedValueOnce([]).mockResolvedValue([today, lesson])
    vi.mocked(api.startTodayLesson).mockResolvedValue({ lesson: today, created: true })
    vi.mocked(api.getAttendance).mockResolvedValue({ ...roster, lesson: today })
    renderPage()

    fireEvent.click(await screen.findByText('오늘 수업 시작'))
    await waitFor(() => expect(api.startTodayLesson).toHaveBeenCalledWith(1))
    expect(await screen.findByText(`오늘(${todayLocal()}) 수업을 시작했습니다. 출결을 입력하세요.`)).toBeInTheDocument()
    await waitFor(() => expect(api.getAttendance).toHaveBeenCalledWith(20))
    expect(await screen.findByText('이두리')).toBeInTheDocument()
    // Once today's lesson exists the button disappears.
    expect(screen.queryByText('오늘 수업 시작')).not.toBeInTheDocument()
  })

  it('never shows or saves the previous class roster after switching class (slow answer for the old class)', async () => {
    asRole('TEACHER')
    vi.mocked(api.listClassrooms).mockResolvedValue([
      { id: 1, name: '수학 A반', class_type: 'REGULAR', is_active: true },
      { id: 2, name: '수학 B반', class_type: 'REGULAR', is_active: true },
    ])
    const lessonB = { ...lesson, id: 70, classroom_id: 2, topic: 'B반 수업' }
    let releaseA: (value: api.LessonListItem[]) => void = () => undefined
    vi.mocked(api.listLessons).mockImplementation((id: number) => (id === 1
      ? new Promise((resolve) => { releaseA = resolve })
      : Promise.resolve([lessonB])))
    const rosterB: api.AttendanceRoster = {
      ...roster, lesson: lessonB,
      items: [{ enrollment_id: 9, student_id: 19, student_name: '박비반', school_name: null, eligible: true, record: null }],
    }
    vi.mocked(api.getAttendance).mockImplementation(async (id: number) => (id === 70 ? rosterB : roster))
    renderPage()

    // Switch to B while A's lesson list is still loading, then let A's (stale) answer arrive.
    fireEvent.mouseDown(await screen.findByLabelText('반 선택'))
    fireEvent.click(await screen.findByTitle('수학 B반'))
    expect(await screen.findByText('박비반')).toBeInTheDocument()
    releaseA([lesson])
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(screen.queryByText('이두리')).not.toBeInTheDocument()
    expect(api.getAttendance).not.toHaveBeenCalledWith(7)
    fireEvent.click(screen.getByText('출결 저장 (1건)'))
    await waitFor(() => expect(api.saveAttendance).toHaveBeenCalledWith(70, [{ enrollment_id: 9, status: 'PRESENT', memo: null, version: null }]))
    // The chosen class is kept in the address (and remembered for other screens).
    expect(screen.getByText(/이동: \/classes\?classroom=2/)).toBeInTheDocument()
    expect(window.sessionStorage.getItem('learningops.workingClassroom')).toBe('2')
  })

  it('opens the linked class, tab and day from a fix link and offers the way back', async () => {
    asRole('TEACHER')
    vi.mocked(api.listClassrooms).mockResolvedValue([
      { id: 1, name: '수학 A반', class_type: 'REGULAR', is_active: true },
      { id: 2, name: '수학 B반', class_type: 'REGULAR', is_active: true },
    ])
    vi.mocked(api.listLessons).mockResolvedValue([{ ...lesson, classroom_id: 2 }])
    renderPage('/classes?classroom=2&tab=progress&day=2026-11-03&from=%2Fnotifications%3Fclassroom%3D2%26tab%3Dcompose%26lesson%3D7')
    await waitFor(() => expect(api.getProgress).toHaveBeenCalledWith(2, '2026-11-03', '2026-11-03'))
    fireEvent.click(await screen.findByText('원래 작업으로 돌아가기'))
    expect(await screen.findByText('이동: /notifications?classroom=2&tab=compose&lesson=7')).toBeInTheDocument()
  })

  it('ignores a link to a class the staff member cannot see', async () => {
    asRole('TEACHER')
    renderPage('/classes?classroom=99&lesson=500')
    await screen.findByText('이두리')
    expect(api.listLessons).toHaveBeenCalledWith(1)
    expect(api.getAttendance).not.toHaveBeenCalledWith(500)
  })

  it('tells a teacher without classrooms to ask for an assignment', async () => {
    asRole('TEACHER')
    vi.mocked(api.listClassrooms).mockResolvedValue([])
    renderPage()
    expect(await screen.findByText('담당 반이 없습니다. 관리자에게 반 배정을 요청하세요.')).toBeInTheDocument()
    expect(api.listLessons).not.toHaveBeenCalled()
  })
})

describe('draftError', () => {
  it('distinguishes empty, zero, not-taken and invalid scores', () => {
    expect(draftError({ notTaken: false, score: null, memo: '' }, null, 10)).toBeNull()
    expect(draftError({ notTaken: false, score: 0, memo: '' }, null, 10)).toBeNull()
    expect(draftError({ notTaken: true, score: null, memo: '' }, null, 10)).toBeNull()
    expect(draftError({ notTaken: false, score: -1, memo: '' }, null, 10)).toBe('0 이상의 점수를 입력해주세요.')
    expect(draftError({ notTaken: false, score: 1.234, memo: '' }, null, 10)).toBe('소수점 둘째 자리까지 입력할 수 있습니다.')
    expect(draftError({ notTaken: false, score: null, memo: '' }, { result_status: 'SCORED', score: 3, memo: null, version: 1, updated_at: '' }, 10))
      .toBe('점수를 입력하거나 미응시를 선택하세요.')
  })
})
