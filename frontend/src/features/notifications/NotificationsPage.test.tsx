import { configure, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useAuth } from '../auth/AuthProvider'
import * as classwork from '../classwork/api'
import { NotificationsPage } from './NotificationsPage'
import * as api from './api'
import * as upload from './uploadApi'
import * as ops from '../message-operations/api'

// Text/label queries only: getByRole is extremely slow on antd-heavy screens under jsdom.
configure({ asyncUtilTimeout: 10000 })

vi.mock('../auth/AuthProvider', () => ({ useAuth: vi.fn() }))
vi.mock('../classwork/api', () => ({ listClassrooms: vi.fn(), listLessons: vi.fn(), getProgress: vi.fn() }))
vi.mock('./uploadApi', () => ({ listSheets: vi.fn(), previewUpload: vi.fn(), confirmUpload: vi.fn() }))
vi.mock('../message-operations/api', () => ({ getSummary: vi.fn(), listObligations: vi.fn() }))
vi.mock('./api', () => ({
  listTemplates: vi.fn(), listVariables: vi.fn(), validateTemplate: vi.fn(), createTemplate: vi.fn(), updateTemplate: vi.fn(),
  preview: vi.fn(), createDrafts: vi.fn(), listNotifications: vi.fn(), getNotification: vi.fn(), editNotification: vi.fn(),
  transition: vi.fn(), mockSend: vi.fn(), retryMockSend: vi.fn(),
  batchView: vi.fn(), batchApprove: vi.fn(), batchMockSend: vi.fn(),
}))

const stamp = '2026-11-03T00:00:00Z'
const template: api.Template = { id: 3, name: '기본', body: '{학생명}', is_active: true, version: 1, default_for_class_type: 'REGULAR', created_at: stamp, updated_at: stamp }
const lesson = {
  id: 7, classroom_id: 1, lesson_date: '2026-11-03', session_no: 1, exam_round: null, topic: '이차함수', memo: null,
  status: 'COMPLETED' as const, version: 1, created_at: stamp, updated_at: stamp, attendance_recorded: 1,
}
const item: api.NotificationItem = {
  id: 11, classroom_id: 1, lesson_id: 7, lesson_date: '2026-11-03', session_no: 1, enrollment_id: 1, student_name: '김하나',
  template_id: 3, template_name: '기본', status: 'READY_FOR_REVIEW', recipient: 'p***@example.invalid', version: 3, updated_at: stamp,
}
const detail = (patch: Partial<api.NotificationDetail> = {}): api.NotificationDetail => ({
  ...item, recipient_email: 'parent1@example.invalid', body: '김하나 학생 안내', template_version: 1, created_by: '조교', approved_by: null, approved_at: null,
  source_changed: false, attempts: [], history: [{ event_type: 'NOTIFICATION_CREATED', actor: '조교', created_at: stamp, details: {} }], ...patch,
})

// Source data of the lesson (학습 현황 API): 김하나 present, A/B, 어휘 8 of 10.
const grid: classwork.ClassProgress = {
  classroom_id: 1, date_from: '2026-11-03', date_to: '2026-11-03',
  columns: [{ key: 'lesson:7', kind: 'LESSON', lesson_id: 7, day: '2026-11-03', session_no: 1, exam_round: null, topic: '이차함수', lesson_status: 'COMPLETED',
    assessments: [{ id: 5, title: '어휘', max_score: 10, version: 1 }] }],
  students: [{ enrollment_id: 1, student_id: 11, student_name: '김하나', enrollment_status: 'ACTIVE', cells: [
    { key: 'lesson:7', eligible: true, attendance_status: 'PRESENT', prework_grade: 'A', weekly_grade: 'B', result_version: 1,
      scores: [{ assessment_id: 5, result_status: 'SCORED', score: 8, memo: null, version: 1 }] },
  ] }],
}

const asRole = (role: 'ADMIN' | 'TEACHER' | 'ASSISTANT') => vi.mocked(useAuth).mockReturnValue({
  user: { id: 2, email: 'user@example.invalid', role }, loading: false, login: vi.fn(), logout: vi.fn(),
})

function Where({ withSidebar }: { withSidebar: boolean }) {
  const location = useLocation()
  const navigate = useNavigate()
  return (
    <>
      <div>{`주소: ${location.pathname}${location.search}`}</div>
      {withSidebar && <button type="button" onClick={() => navigate('/notifications?tab=templates')}>사이드바: 템플릿 관리</button>}
    </>
  )
}
const renderPage = (path = '/notifications', withSidebar = false) => render(
  <MemoryRouter initialEntries={[path]}>
    <Routes>
      <Route path="/notifications" element={<><NotificationsPage /><Where withSidebar={withSidebar} /></>} />
      <Route path="*" element={<Where withSidebar={false} />} />
    </Routes>
  </MemoryRouter>,
)

async function openReview() {
  fireEvent.click(await screen.findByText('검토·발송'))
  fireEvent.click(await screen.findByText('한 건씩'))  // the tab opens on the class batch view
  fireEvent.click(await screen.findByText('김하나'))
  return screen.findByLabelText('메시지 본문')
}

/** Picks a workbook and waits until its time-slot sheets are read (one sheet = chosen for you). */
async function chooseWorkbook(file = new File(['x'], '주간.xlsx')) {
  fireEvent.change(await screen.findByLabelText('엑셀 파일'), { target: { files: [file] } })
  await waitFor(() => expect(screen.getByText('미리보기').closest('button')).toBeEnabled())
  return file
}

describe('NotificationsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(classwork.listClassrooms).mockResolvedValue([{ id: 1, name: '수학 A반', class_type: 'REGULAR', is_active: true }])
    vi.mocked(classwork.listLessons).mockResolvedValue([lesson])
    vi.mocked(api.listTemplates).mockResolvedValue([template])
    vi.mocked(api.listVariables).mockResolvedValue([{ name: '학생명', description: '학생 이름' }])
    vi.mocked(api.listNotifications).mockResolvedValue([item])
    vi.mocked(api.getNotification).mockResolvedValue(detail())
    vi.mocked(classwork.getProgress).mockResolvedValue(grid)
    vi.mocked(upload.listSheets).mockResolvedValue([{ name: '10시', class_names: ['중3 토10'], student_rows: 4 }])
    vi.mocked(api.batchView).mockResolvedValue({ lesson_id: 7, classroom_id: 1, items: [] })
  })

  it('previews without saving, shows why students are blocked and saves only ready students', async () => {
    asRole('ASSISTANT')
    vi.mocked(api.preview).mockResolvedValue({
      lesson_id: 7, template_id: 3, template_version: 1, items: [
        { enrollment_id: 1, student_id: 11, student_name: '김하나', ok: true, body: '김하나 학생 출결: 출석', issues: [], warnings: [], existing_notification_id: null },
        { enrollment_id: 2, student_id: 12, student_name: '이두리', ok: false, body: null, issues: ['출결 미입력 (결석으로 간주하지 않습니다)'], warnings: [], existing_notification_id: null },
      ],
    })
    vi.mocked(api.createDrafts).mockResolvedValue({ created: [11], skipped: [] })
    renderPage()

    expect(await screen.findByText('이 단계의 발송은 모의 발송입니다. 실제 문자·이메일은 전송되지 않습니다.')).toBeInTheDocument()
    fireEvent.click(await screen.findByText('누락·예외 생성'))
    // The upload tab stays mounted (hidden) and also has a '미리보기' button: scope to the manual-compose card.
    const composePane = (await screen.findByText('누락·예외 수동 생성')).closest('.ant-card') as HTMLElement
    fireEvent.mouseDown(within(composePane).getByLabelText('수업 선택'))
    fireEvent.click(await screen.findByTitle('2026-11-03 · 이차함수'))
    fireEvent.click(within(composePane).getByText('미리보기'))
    expect(await screen.findByText('출결 미입력 (결석으로 간주하지 않습니다)')).toBeInTheDocument()
    expect(screen.getByText('생성 불가')).toBeInTheDocument()
    expect(screen.getByText('김하나 학생 출결: 출석')).toBeInTheDocument()
    expect(api.createDrafts).not.toHaveBeenCalled()

    fireEvent.click(screen.getByText('선택 학생 초안 저장 (1명)'))
    await waitFor(() => expect(api.createDrafts).toHaveBeenCalledWith(7, 3, [1]))
  })

  // Scenario C (성적 누락) and D (기존 메시지): the reason links to the screen that fixes it, with
  // the way back to this lesson; a student who already has a message is sent to review instead.
  it('links each blocking reason to its fix screen with a way back, and an existing message to review', async () => {
    asRole('ADMIN')
    vi.mocked(api.preview).mockResolvedValue({
      lesson_id: 7, template_id: 3, template_version: 1, items: [
        { enrollment_id: 1, student_id: 11, student_name: '김하나', ok: false, body: null, issues: ["'어휘' 성적 미입력", '보호자 이메일이 등록되어 있지 않습니다'], warnings: [], existing_notification_id: null },
        { enrollment_id: 2, student_id: 12, student_name: '이두리', ok: true, body: '이두리 안내', issues: [], warnings: [], existing_notification_id: 11 },
      ],
    })
    renderPage('/notifications?classroom=1&tab=compose&lesson=7')
    const composePane = (await screen.findByText('누락·예외 수동 생성')).closest('.ant-card') as HTMLElement
    fireEvent.click(within(composePane).getByText('미리보기'))
    expect(await screen.findByText('생성할 수 없는 이유')).toBeInTheDocument()
    expect(screen.getByText('생성 가능 0명 · 이미 메시지 있음 1명 · 생성 불가 1명')).toBeInTheDocument()
    expect(screen.getByText('선택 학생 초안 저장 (0명)').closest('button')).toBeDisabled() // neither can be saved

    fireEvent.click(screen.getByText('성적 입력 (학습 현황)'))
    expect(await screen.findByText(
      '주소: /classes?classroom=1&tab=progress&day=2026-11-03&from=%2Fnotifications%3Fclassroom%3D1%26tab%3Dcompose%26lesson%3D7',
    )).toBeInTheDocument()
  })

  it('sends a student who already has a message to that message in review, and guardian fixes to the contact editor', async () => {
    asRole('ADMIN')
    vi.mocked(api.preview).mockResolvedValue({
      lesson_id: 7, template_id: 3, template_version: 1, items: [
        { enrollment_id: 1, student_id: 11, student_name: '김하나', ok: true, body: '김하나 안내', issues: [], warnings: [], existing_notification_id: 11 },
      ],
    })
    renderPage('/notifications?classroom=1&tab=compose&lesson=7')
    const composePane = (await screen.findByText('누락·예외 수동 생성')).closest('.ant-card') as HTMLElement
    fireEvent.click(within(composePane).getByText('미리보기'))
    fireEvent.click(await screen.findByText('기존 메시지 검토'))
    expect(await screen.findByText('주소: /notifications?classroom=1&tab=review&notification=11')).toBeInTheDocument()
    await waitFor(() => expect(api.getNotification).toHaveBeenCalledWith(11))
    expect(await screen.findByLabelText('메시지 본문')).toHaveValue('김하나 학생 안내')
  })

  it('asks non-administrators to request a guardian e-mail instead of linking to an editor they cannot use', async () => {
    asRole('TEACHER')
    vi.mocked(api.preview).mockResolvedValue({
      lesson_id: 7, template_id: 3, template_version: 1, items: [
        { enrollment_id: 1, student_id: 11, student_name: '김하나', ok: false, body: null, issues: ['보호자 이메일이 등록되어 있지 않습니다'], warnings: [], existing_notification_id: null },
      ],
    })
    renderPage('/notifications?classroom=1&tab=compose&lesson=7')
    const composePane = (await screen.findByText('누락·예외 수동 생성')).closest('.ant-card') as HTMLElement
    fireEvent.click(within(composePane).getByText('미리보기'))
    expect(await screen.findByText('관리자에게 보호자 이메일 등록을 요청하세요.')).toBeInTheDocument()
    expect(screen.queryByText('메일 주소 변경')).not.toBeInTheDocument()
  })

  it('lets an assistant confirm and mock-send with an idempotency key, labelled as not really sent', async () => {
    asRole('ASSISTANT')
    vi.mocked(api.transition).mockResolvedValue(detail({ status: 'APPROVED', version: 4, approved_by: '조교', approved_at: stamp }))
    vi.mocked(api.mockSend).mockResolvedValue({
      notification: detail({ status: 'MOCK_SENT', version: 5, approved_by: '조교', approved_at: stamp }),
      attempt: { id: 1, channel: 'MOCK', result: 'MOCK_SUCCESS', error_code: null, error_message: null, requested_by: '조교', attempted_at: stamp },
      replayed: false,
    })
    renderPage()
    await openReview()
    expect(screen.getByText('parent1@example.invalid')).toBeInTheDocument() // full address before sending

    fireEvent.click(screen.getByText('내용 확정'))
    await waitFor(() => expect(api.transition).toHaveBeenCalledWith(11, 'approve', 3))
    expect(await screen.findByText('내용을 확정했습니다. 이제 모의 발송할 수 있습니다.')).toBeInTheDocument()
    fireEvent.click(await screen.findByText('모의 발송'))
    const confirm = (await screen.findByText('실제 문자·이메일은 전송되지 않으며 결과만 기록됩니다.')).closest('.ant-popover') as HTMLElement
    fireEvent.click(within(confirm).getByText('모의 발송'))
    await waitFor(() => expect(api.mockSend).toHaveBeenCalledTimes(1))
    expect(vi.mocked(api.mockSend).mock.calls[0][1]).toMatch(/^[0-9a-f-]{36}$/)
    expect(await screen.findByText('모의 발송에 성공했습니다. 실제 문자·이메일은 전송되지 않았습니다.')).toBeInTheDocument()
    expect(screen.getAllByText('모의 발송 성공 (실제 미전송)').length).toBeGreaterThan(0)
  })

  it('opens the message linked from 메시지 운영 and retries a failed mock send with a key', async () => {
    asRole('ASSISTANT')
    {
      const failedAt = { id: 1, channel: 'MOCK', result: 'MOCK_FAILURE' as const, error_code: 'MOCK_TEMPORARY_FAILURE', error_message: '모의 발송 실패: 일시적인 발송 오류입니다.', requested_by: '조교', attempted_at: stamp }
      vi.mocked(api.getNotification).mockResolvedValue(detail({ status: 'MOCK_FAILED', approved_by: '조교', approved_at: stamp, attempts: [failedAt] }))
      vi.mocked(api.retryMockSend).mockResolvedValue({
        notification: detail({ status: 'MOCK_SENT', version: 5, approved_by: '조교', approved_at: stamp }),
        attempt: { ...failedAt, id: 2, result: 'MOCK_SUCCESS', error_code: null, error_message: null },
        replayed: false,
      })
      renderPage('/notifications?classroom=1&tab=review&notification=11')
      // Deep link: the review tab opens with that message, no clicks needed.
      const retry = await screen.findByText('모의 발송 재시도')
      expect(api.getNotification).toHaveBeenCalledWith(11)
      fireEvent.click(retry)
      const confirm = (await screen.findByText('모의 발송을 재시도할까요?')).closest('.ant-popover') as HTMLElement
      fireEvent.click(within(confirm).getByText('재시도'))
      await waitFor(() => expect(api.retryMockSend).toHaveBeenCalledTimes(1))
      expect(vi.mocked(api.retryMockSend).mock.calls[0][0]).toBe(11)
      expect(vi.mocked(api.retryMockSend).mock.calls[0][1]).toMatch(/^[0-9a-f-]{36}$/)
      expect(api.mockSend).not.toHaveBeenCalled()
      expect(await screen.findByText('모의 발송에 성공했습니다. 실제 문자·이메일은 전송되지 않았습니다.')).toBeInTheDocument()
    }
  })

  it('shows the five 성적 안내 features as tabs, including 메시지 처리 현황 for the selected class', async () => {
    asRole('ASSISTANT')
    const zero = { total: 0, missing: 0, in_review: 0, ready_to_send: 0, failed: 0, done: 0, pending: 0, exempt: 0, overdue: null, completion_rate: null }
    vi.mocked(ops.getSummary).mockResolvedValue({
      date_from: '2026-11-07', date_to: '2026-11-20', deadline_policy: 'NOT_CONFIGURED', totals: zero,
      classrooms: [{ classroom_id: 1, classroom_name: '수학 A반', class_type: 'REGULAR', ...zero }],
    })
    vi.mocked(ops.listObligations).mockResolvedValue({ items: [], total: 0, limit: 50, offset: 0 })
    renderPage('/notifications?tab=operations')
    for (const tab of ['엑셀 업로드', '검토·발송', '누락·예외 생성', '메시지 처리 현황', '템플릿']) expect(await screen.findByText(tab)).toBeInTheDocument()
    expect(await screen.findByText('수학 A반 처리 목록')).toBeInTheDocument()
    await waitFor(() => expect(ops.listObligations).toHaveBeenCalledWith(1, expect.any(String), expect.any(String), undefined, 50, 0))
  })

  it('keeps the tab and class in the address and keeps the class when a sidebar shortcut changes the tab', async () => {
    asRole('ASSISTANT')
    vi.mocked(classwork.listClassrooms).mockResolvedValue([
      { id: 1, name: '수학 A반', class_type: 'REGULAR', is_active: true },
      { id: 2, name: '수학 B반', class_type: 'REGULAR', is_active: true },
    ])
    renderPage('/notifications?tab=upload', true)
    fireEvent.mouseDown(await screen.findByLabelText('반 선택'))
    fireEvent.click(await screen.findByTitle('수학 B반'))
    expect(await screen.findByText('주소: /notifications?tab=upload&classroom=2')).toBeInTheDocument()
    fireEvent.click(screen.getByText('검토·발송'))
    expect(await screen.findByText('주소: /notifications?tab=review&classroom=2')).toBeInTheDocument()
    // Sidebar shortcut (no classroom in the link): the class stays B and the page is not reset.
    fireEvent.click(screen.getByText('사이드바: 템플릿 관리'))
    expect(await screen.findByText('주소: /notifications?tab=templates')).toBeInTheDocument()
    await waitFor(() => expect(api.listNotifications).toHaveBeenLastCalledWith(2, expect.anything()))
    expect(await screen.findByText('사용 가능한 변수', { exact: false })).toBeInTheDocument()
    expect(vi.mocked(classwork.listLessons)).toHaveBeenLastCalledWith(2)
    expect(vi.mocked(classwork.listClassrooms)).toHaveBeenCalledTimes(1) // not re-mounted
  })

  it('shows the generation source next to the message and walks to the next student', async () => {
    asRole('ASSISTANT')
    const second: api.NotificationItem = { ...item, id: 12, enrollment_id: 2, student_name: '이두리' }
    vi.mocked(api.listNotifications).mockResolvedValue([item, second])
    vi.mocked(api.getNotification).mockImplementation(async (id: number) => (id === 12
      ? detail({ ...second, body: '이두리 학생 안내', recipient_email: 'parent2@example.invalid' }) : detail()))
    vi.mocked(api.transition).mockResolvedValue(detail({ status: 'APPROVED', version: 4, approved_by: '조교', approved_at: stamp }))
    renderPage()
    await openReview()

    // Source (attendance, grades, score, topic) and the message body are visible together.
    expect(await screen.findByText('A / B')).toBeInTheDocument()
    expect(screen.getByText('8 / 10')).toBeInTheDocument()
    expect(screen.getAllByText('출석').length).toBeGreaterThan(0)
    expect(screen.getAllByText('이차함수').length).toBeGreaterThan(0)
    expect(screen.getByLabelText('메시지 본문')).toHaveValue('김하나 학생 안내')
    expect(screen.getByText('1 / 2')).toBeInTheDocument()
    expect(classwork.getProgress).toHaveBeenCalledWith(1, '2026-11-03', '2026-11-03')

    // Confirm and continue with the next student without going back to the list.
    fireEvent.click(screen.getByText('확정 후 다음 학생'))
    await waitFor(() => expect(api.transition).toHaveBeenCalledWith(11, 'approve', 3))
    await waitFor(() => expect(screen.getByLabelText('메시지 본문')).toHaveValue('이두리 학생 안내'))
    expect(screen.getByText('2 / 2')).toBeInTheDocument()
    expect(classwork.getProgress).toHaveBeenCalledTimes(2) // list reloaded after confirming → source fetched again
  })

  it('names the student and recipient in the mock-send check', async () => {
    asRole('ASSISTANT')
    vi.mocked(api.getNotification).mockResolvedValue(detail({ status: 'APPROVED', approved_by: '조교', approved_at: stamp }))
    renderPage()
    await openReview()
    fireEvent.click(await screen.findByText('모의 발송'))
    expect(await screen.findByText('김하나 · parent1@example.invalid · 1건')).toBeInTheDocument()
  })

  it('blocks confirming a draft whose source data changed', async () => {
    asRole('TEACHER')
    vi.mocked(api.getNotification).mockResolvedValue(detail({ source_changed: true }))
    renderPage()
    await openReview()
    expect(await screen.findByText('생성 후 수업·출결·성적 또는 연락처가 바뀌었습니다. 이 메시지는 확정할 수 없으니 취소하고 다시 생성하세요.')).toBeInTheDocument()
    expect(screen.getByText('내용 확정').closest('button')).toBeDisabled()
  })
  it('warns about a confirmed message whose source changed and disables mock send and retry', async () => {
    asRole('ASSISTANT')
    vi.mocked(api.getNotification).mockResolvedValue(detail({ status: 'APPROVED', approved_by: '조교', approved_at: stamp, source_changed: true }))
    renderPage()
    await openReview()
    expect(await screen.findByText('확정 후 수업·출결·성적 또는 연락처가 바뀌었습니다. 이 내용으로는 모의 발송할 수 없으니 메시지를 취소하고 다시 생성하세요.')).toBeInTheDocument()
    expect(screen.getByText('모의 발송').closest('button')).toBeDisabled()
    expect(api.mockSend).not.toHaveBeenCalled()
  })

  it('disables the retry of a failed message whose source changed', async () => {
    asRole('ASSISTANT')
    vi.mocked(api.getNotification).mockResolvedValue(detail({ status: 'MOCK_FAILED', approved_by: '조교', approved_at: stamp, source_changed: true }))
    renderPage()
    await openReview()
    expect(await screen.findByText('모의 발송 재시도')).toBeInTheDocument()
    expect(screen.getByText('모의 발송 재시도').closest('button')).toBeDisabled()
  })

  it('validates templates for administrators with fictional sample data', async () => {
    asRole('ADMIN')
    vi.mocked(api.validateTemplate).mockResolvedValue({ ok: false, errors: ['지원하지 않는 변수: {password}'], variables: [], sample_body: null, sample_issues: [] })
    renderPage()
    fireEvent.click(await screen.findByText('템플릿'))
    fireEvent.click(await screen.findByText('템플릿 등록'))
    fireEvent.change(await screen.findByLabelText('템플릿 본문'), { target: { value: '{password}' } })
    fireEvent.click(screen.getByText('검증·예시 보기'))
    await waitFor(() => expect(api.validateTemplate).toHaveBeenCalledWith('{password}'))
    expect(await screen.findByText('지원하지 않는 변수: {password}')).toBeInTheDocument()
  })
  it('uploads a workbook, asks about unregistered students and confirms with the decisions', async () => {
    asRole('ASSISTANT')
    const row = (patch: Partial<upload.UploadRow>): upload.UploadRow => ({
      key: '10시!2', row: 2, name: '가상학생1', status: 'MATCHED', attendance: 'PRESENT', prework: 'A', weekly: 'B',
      scores: { 어휘: 8 }, issues: [], warnings: [], app_attendance: null, attendance_mismatch: false, returning_available: false, ...patch,
    })
    vi.mocked(upload.previewUpload).mockResolvedValue({
      lesson_date: '2026-11-03', can_confirm: true, blocking: [],
      blocks: [{
        sheet: '10시', row: 1, class_name: '중3 토10', class_type: 'REGULAR', classroom_id: 1, tests: [{ title: '어휘', total: 10 }], issues: [],
        rows: [
          row({}),
          row({ key: '10시!3', row: 3, name: '가상신입', status: 'UNREGISTERED' }),
          row({ key: '10시!4', row: 4, name: '가상복귀', status: 'UNREGISTERED', returning_available: true }),
          row({ key: '10시!5', row: 5, name: '가상불일치', attendance_mismatch: true, warnings: ['출결 불일치: 프로그램 \'지각\', 엑셀 \'출석\''] }),
        ],
      }],
    })
    vi.mocked(upload.confirmUpload).mockResolvedValue({
      lesson_date: '2026-11-03', saved_rows: 3, new_students: 1, returned_students: 0, excluded_rows: 1, attendance_mismatches: ['중3 토10 10시!5'],
      drafts: [{ class_name: '중3 토10', created: 1, skipped: [] }],
    })
    renderPage()

    const file = new File(['x'], '주간.xlsx')
    await chooseWorkbook(file)
    fireEvent.change(screen.getByLabelText('수업일'), { target: { value: '2026-11-03' } })
    fireEvent.click(screen.getByText('미리보기'))
    await waitFor(() => expect(upload.previewUpload).toHaveBeenCalledWith(file, '2026-11-03', ['10시']))
    expect(await screen.findAllByText('미등록 학생')).toHaveLength(2)
    expect(screen.getByText('출결 불일치')).toBeInTheDocument()
    expect(screen.getByText('확정·초안 생성').closest('button')).toBeDisabled()
    // Step 2 summary and Step 3 impact are shown before anything is saved.
    expect(screen.getByText('정상(명단 일치)')).toBeInTheDocument()
    expect(screen.getByText('미등록(결정 필요)')).toBeInTheDocument()
    expect(screen.getByText('주간.xlsx')).toBeInTheDocument()
    expect(screen.getByText('저장할 학생 행')).toBeInTheDocument()
    expect(upload.confirmUpload).not.toHaveBeenCalled()

    const newcomer = screen.getByText('가상신입').closest('tr') as HTMLElement
    fireEvent.click(within(newcomer).getByText('예'))  // 신규 수강생인가요? -> 예
    const unknown = screen.getByText('가상복귀').closest('tr') as HTMLElement
    fireEvent.click(within(unknown).getByText('아니요'))  // 신규? 아니요
    expect(within(unknown).getByText('복귀 학생인가요?')).toBeInTheDocument()
    fireEvent.click(within(unknown).getByText('아니요'))  // 복귀? 아니요 -> 제외
    expect(within(unknown).getByText('오류로 간주해 해당 행은 성적 안내 메시지를 생성하지 않겠습니다.')).toBeInTheDocument()
    // Impact before confirming: 2 matched + 1 new = 3 rows saved.
    expect(within(screen.getByText('3. 변경 확인').closest('.ant-card') as HTMLElement).getByText('3명')).toBeInTheDocument()

    fireEvent.click(screen.getByText('확정·초안 생성'))
    const pop = (await screen.findByText('업로드를 확정할까요?')).closest('.ant-popover') as HTMLElement
    fireEvent.click(within(pop).getByText('확정'))
    await waitFor(() => expect(upload.confirmUpload).toHaveBeenCalledWith(file, '2026-11-03', { '10시!3': 'NEW', '10시!4': 'EXCLUDE' }, ['10시']))
    expect(await screen.findByText('중3 토10: 초안 1건')).toBeInTheDocument()
    // The attendance mismatch got no draft: a red pop-up says so.
    expect(await screen.findByText('메시지 초안을 만들지 못한 학생이 있습니다')).toBeInTheDocument()
    expect(screen.getByText('출결 불일치 1건: 프로그램 출결을 유지했고 초안을 만들지 않았습니다.')).toBeInTheDocument()
  })

  it('does not offer "new student" for a name already registered elsewhere (SEC-01)', async () => {
    asRole('TEACHER')
    vi.mocked(upload.previewUpload).mockResolvedValue({
      lesson_date: '2026-11-03', can_confirm: true, blocking: [],
      blocks: [{
        sheet: '10시', row: 1, class_name: '중3 토10', class_type: 'REGULAR', classroom_id: 1, tests: [], issues: [],
        rows: [{
          key: '10시!2', row: 2, name: '가상동명', status: 'UNREGISTERED', attendance: 'PRESENT', prework: null, weekly: null,
          scores: {}, issues: [], warnings: ['같은 이름(·학교)의 학생이 이미 등록되어 있어 업로드에서 신규로 등록할 수 없습니다'],
          app_attendance: null, attendance_mismatch: false, returning_available: false, existing_student_conflict: true,
        }],
      }],
    })
    renderPage()
    await chooseWorkbook(new File(['x'], '주간.xlsx'))
    fireEvent.click(screen.getByText('미리보기'))
    const rowEl = (await screen.findByText('가상동명')).closest('tr') as HTMLElement
    expect(within(rowEl).getByText('예').closest('button')).toBeDisabled()
    expect(within(rowEl).getByText('같은 이름의 학생이 이미 등록되어 있어 신규로 등록할 수 없습니다. 관리자에게 수강 등록을 요청하세요.')).toBeInTheDocument()
    // The row can still be excluded so the rest of the class is saved.
    fireEvent.click(within(rowEl).getByText('아니요'))
    fireEvent.click(within(rowEl).getByText('아니요'))
    expect(within(rowEl).getByText('제외')).toBeInTheDocument()
    expect(upload.confirmUpload).not.toHaveBeenCalled()
  })

  it('groups preview rows by what to do and filters the rows by a clicked group, without saving', async () => {
    asRole('ASSISTANT')
    const row = (patch: Partial<upload.UploadRow>): upload.UploadRow => ({
      key: '10시!2', row: 2, name: '가상정상', status: 'MATCHED', attendance: 'PRESENT', prework: 'A', weekly: 'B',
      scores: {}, issues: [], warnings: [], app_attendance: null, attendance_mismatch: false, returning_available: false, ...patch,
    })
    vi.mocked(upload.previewUpload).mockResolvedValue({
      lesson_date: '2026-11-03', can_confirm: false, blocking: [],
      blocks: [{
        sheet: '10시', row: 1, class_name: '중3 토10', class_type: 'REGULAR', classroom_id: 1, tests: [], issues: [],
        rows: [
          row({}),
          row({ key: '10시!3', row: 3, name: '가상미등록', status: 'UNREGISTERED' }),
          row({ key: '10시!4', row: 4, name: '가상오류', status: 'INVALID', issues: ["출결 '출첵'는 출석/지각/결석/인정결석 중 하나여야 합니다"] }),
          row({ key: '10시!5', row: 5, name: '메모', status: 'SKIPPED' }),
        ],
      }],
    })
    renderPage()
    await chooseWorkbook()
    fireEvent.click(screen.getByText('미리보기'))
    const step2 = (await screen.findByText('2. 데이터 검증 결과 (저장 전)')).closest('.ant-card') as HTMLElement
    const tile = (label: string) => within(step2).getByText(label).closest('button') as HTMLElement
    expect(within(tile('정상 처리 가능')).getByText('1')).toBeInTheDocument()
    expect(within(tile('확인 필요')).getByText('1')).toBeInTheDocument()
    expect(within(tile('오류')).getByText('1')).toBeInTheDocument()
    expect(within(tile('처리 제외')).getByText('1')).toBeInTheDocument()
    // Step 1 is folded into a summary while the result is checked.
    expect(screen.queryByLabelText('엑셀 파일')).not.toBeInTheDocument()
    expect(screen.getByText('주간.xlsx')).toBeInTheDocument()

    fireEvent.click(tile('오류'))
    expect(await screen.findByText('오류 1행만 표시 중')).toBeInTheDocument()
    expect(screen.getByText('가상오류', { selector: 'td' })).toBeInTheDocument()
    expect(screen.queryByText('가상정상')).not.toBeInTheDocument()
    expect(screen.queryByText('가상미등록')).not.toBeInTheDocument()
    fireEvent.click(screen.getByText('전체 행 보기'))
    expect(await screen.findByText('가상정상')).toBeInTheDocument()
    expect(upload.confirmUpload).not.toHaveBeenCalled()
  })

  it('shows which values corrected in the app a re-upload will replace, before confirming', async () => {
    asRole('ASSISTANT')
    const row = (patch: Partial<upload.UploadRow>): upload.UploadRow => ({
      key: '10시!2', row: 2, name: '가상하나', status: 'MATCHED', attendance: 'PRESENT', prework: 'A', weekly: 'B',
      scores: { 어휘: 8 }, issues: [], warnings: [], app_attendance: 'PRESENT', attendance_mismatch: false, returning_available: false, ...patch,
    })
    vi.mocked(upload.previewUpload).mockResolvedValue({
      lesson_date: '2026-11-03', can_confirm: true, blocking: [],
      blocks: [{
        sheet: '10시', row: 1, class_name: '중3 토10', class_type: 'REGULAR', classroom_id: 1, tests: [{ title: '어휘', total: 12 }], issues: [],
        max_score_changes: [{ title: '어휘', app: '10', upload: '12' }],
        rows: [
          row({ app_changes: [{ field: 'score', label: '어휘', app: '9', upload: '8' }] }),
          row({ key: '10시!3', row: 3, name: '가상둘' }),
        ],
      }],
    })
    renderPage()
    await chooseWorkbook()
    fireEvent.click(screen.getByText('미리보기'))
    expect(await screen.findByText('어휘: 앱 9 → 엑셀 8')).toBeInTheDocument()
    expect(screen.getByText('평가 만점이 엑셀 머리글 값으로 바뀝니다: 어휘 10 → 12')).toBeInTheDocument()
    // The row with a replaced value counts as "확인 필요"; the unchanged one stays "정상".
    const step2 = screen.getByText('2. 데이터 검증 결과 (저장 전)').closest('.ant-card') as HTMLElement
    expect(within(within(step2).getByText('확인 필요').closest('button') as HTMLElement).getByText('1')).toBeInTheDocument()
    expect(within(within(step2).getByText('정상 처리 가능').closest('button') as HTMLElement).getByText('1')).toBeInTheDocument()
    fireEvent.click(screen.getByText('확정·초안 생성'))
    expect(await screen.findByText(/앱에서 입력·수정한 점수·등급 1건이 엑셀 값으로 바뀝니다/)).toBeInTheDocument()
    expect(upload.confirmUpload).not.toHaveBeenCalled()
  })

  it('reports students who already had a draft as duplicate prevention, not as a failure, apart from the save result', async () => {
    asRole('ASSISTANT')
    vi.mocked(upload.previewUpload).mockResolvedValue({
      lesson_date: '2026-11-03', can_confirm: true, blocking: [],
      blocks: [{ sheet: '10시', row: 1, class_name: '중3 토10', class_type: 'REGULAR', classroom_id: 1, tests: [], issues: [], rows: [] }],
    })
    vi.mocked(upload.confirmUpload).mockResolvedValue({
      lesson_date: '2026-11-03', saved_rows: 2, new_students: 0, returned_students: 0, excluded_rows: 0, attendance_mismatches: [],
      drafts: [{ class_name: '중3 토10', created: 0, skipped: ['가상하나: 이미 이 수업·템플릿의 메시지가 있습니다', '가상둘: 이미 이 수업·템플릿의 메시지가 있습니다'] }],
    })
    renderPage()
    await chooseWorkbook()
    fireEvent.click(screen.getByText('미리보기'))
    fireEvent.click(await screen.findByText('확정·초안 생성'))
    const pop = (await screen.findByText('업로드를 확정할까요?')).closest('.ant-popover') as HTMLElement
    fireEvent.click(within(pop).getByText('확정'))

    expect(await screen.findByText("저장 2명 · 안내 초안 0건을 만들었습니다. 이미 초안이 있는 학생 2명은 새로 만들지 않았습니다(중복 방지). '검토·발송'에서 확인하세요.")).toBeInTheDocument()
    expect(screen.getByText('데이터 저장 결과')).toBeInTheDocument()
    expect(screen.getByText('메시지 초안 생성 결과')).toBeInTheDocument()
    expect(screen.getByText('기존 초안 있음(중복 생성 안 함) 2명: 가상하나, 가상둘')).toBeInTheDocument()
    expect(screen.getByText('모두 처리됨')).toBeInTheDocument()
    expect(screen.queryByText('메시지 초안을 만들지 못한 학생이 있습니다')).not.toBeInTheDocument()
    expect(screen.queryByText(/초안 미생성 —/)).not.toBeInTheDocument()
  })

  it('says the save state is unknown when the confirm request gets no answer', async () => {
    asRole('ASSISTANT')
    const { ApiClientError } = await import('../../shared/api/ApiClientError')
    vi.mocked(upload.previewUpload).mockResolvedValue({
      lesson_date: '2026-11-03', can_confirm: true, blocking: [],
      blocks: [{ sheet: '10시', row: 1, class_name: '중3 토10', class_type: 'REGULAR', classroom_id: 1, tests: [], issues: [], rows: [] }],
    })
    vi.mocked(upload.confirmUpload).mockRejectedValue(new ApiClientError('백엔드 API에 연결할 수 없습니다.', 'NETWORK_ERROR'))
    renderPage()
    await chooseWorkbook()
    fireEvent.click(screen.getByText('미리보기'))
    fireEvent.click(await screen.findByText('확정·초안 생성'))
    const pop = (await screen.findByText('업로드를 확정할까요?')).closest('.ant-popover') as HTMLElement
    fireEvent.click(within(pop).getByText('확정'))
    expect(await screen.findByText('저장 실패: 백엔드 API에 연결할 수 없습니다.')).toBeInTheDocument()
    expect(screen.getByText(/저장 여부를 알 수 없습니다/)).toBeInTheDocument()
  })

  it('pops up a red notice listing students whose draft was skipped, with the reason', async () => {
    asRole('ASSISTANT')
    vi.mocked(upload.previewUpload).mockResolvedValue({
      lesson_date: '2026-11-03', can_confirm: true, blocking: [],
      blocks: [{ sheet: '10시', row: 1, class_name: '중3 토10', class_type: 'REGULAR', classroom_id: 1, tests: [], issues: [], rows: [] }],
    })
    vi.mocked(upload.confirmUpload).mockResolvedValue({
      lesson_date: '2026-11-03', saved_rows: 2, new_students: 1, returned_students: 0, excluded_rows: 0, attendance_mismatches: [],
      drafts: [{ class_name: '중3 토10', created: 1, skipped: ['가상신입: 보호자 이메일이 등록되어 있지 않습니다'] }],
    })
    renderPage()

    const file = new File(['x'], '주간.xlsx')
    await chooseWorkbook(file)
    fireEvent.click(screen.getByText('미리보기'))
    fireEvent.click(await screen.findByText('확정·초안 생성'))
    const pop = (await screen.findByText('업로드를 확정할까요?')).closest('.ant-popover') as HTMLElement
    fireEvent.click(within(pop).getByText('확정'))

    const dialog = (await screen.findByText('메시지 초안을 만들지 못한 학생이 있습니다')).closest('.ant-modal') as HTMLElement
    expect(within(dialog).getByText('중3 토10: 초안 미생성 1건')).toBeInTheDocument()
    expect(within(dialog).getByText('가상신입: 보호자 이메일이 등록되어 있지 않습니다')).toBeInTheDocument()
    expect(screen.getByText('저장 2명 · 안내 초안 1건을 만들었습니다. 초안을 만들지 못한 항목 1건이 있습니다 — 사유를 확인하세요.')).toBeInTheDocument()
    // The result card keeps the reason in red after the pop-up is dismissed.
    expect(screen.getByText('초안 미생성 — 가상신입: 보호자 이메일이 등록되어 있지 않습니다')).toBeInTheDocument()
  })

  it('reviews a class lesson on one screen, confirms only the chosen messages and mock-sends the confirmed ones', async () => {
    asRole('ASSISTANT')
    const message = (patch: Partial<api.BatchMessage>): api.BatchMessage => ({
      ...item, body: '김하나 학생 안내\n출결: 출석', source_changed: false, attention: [], ...patch,
    })
    const first = [
      message({}),
      message({ id: 12, enrollment_id: 2, student_name: '박둘', status: 'READY_FOR_REVIEW', body: '박둘 학생 안내\n출결: 결석', attention: ['결석', '미응시'] }),
      message({ id: 13, enrollment_id: 3, student_name: '이셋', status: 'DRAFT', body: '이셋 학생 안내', source_changed: true }),
    ]
    vi.mocked(api.batchView)
      .mockResolvedValueOnce({ lesson_id: 7, classroom_id: 1, items: first })
      .mockResolvedValue({ lesson_id: 7, classroom_id: 1, items: [message({ status: 'APPROVED', version: 4 }), first[1], first[2]] })
    vi.mocked(api.batchApprove).mockResolvedValue([
      { id: 11, student_name: '김하나', outcome: 'APPROVED', code: null, message: null, replayed: false },
      { id: 12, student_name: '박둘', outcome: 'SKIPPED', code: 'VERSION_CONFLICT', message: '다른 사용자가 먼저 변경했습니다.', replayed: false },
    ])
    vi.mocked(api.batchMockSend).mockResolvedValue([
      { id: 11, student_name: '김하나', outcome: 'MOCK_SENT', code: null, message: null, replayed: false },
    ])
    renderPage()
    fireEvent.click(await screen.findByText('검토·발송'))

    // Every body of the lesson is on one screen, with what deserves a second look.
    expect(await screen.findByText(/박둘 학생 안내/)).toBeInTheDocument()
    expect(screen.getByText('미응시')).toBeInTheDocument()
    expect(screen.getByText('원본 변경')).toBeInTheDocument()
    expect(screen.getByText(/바뀐 메시지 1건은 확정·발송할 수 없습니다/)).toBeInTheDocument()
    // Nothing is pre-selected, and a changed message cannot be selected.
    expect(screen.getByText('선택한 0건 확정').closest('button')).toBeDisabled()
    expect(screen.getByLabelText('이셋 확정 선택')).toBeDisabled()
    fireEvent.click(screen.getByLabelText('김하나 확정 선택'))
    fireEvent.click(screen.getByLabelText('박둘 확정 선택'))
    fireEvent.click(screen.getByText('선택한 2건 확정'))
    const approvePop = (await screen.findByText('선택한 2건을 확정할까요?')).closest('.ant-popover') as HTMLElement
    // A hand-picked absent student is allowed, and named in the dialog.
    expect(within(approvePop).getByText(/이 중 결석 1건이 포함되어 있습니다/)).toBeInTheDocument()
    fireEvent.click(within(approvePop).getByText('확정'))
    await waitFor(() => expect(api.batchApprove).toHaveBeenCalledWith(7, [{ id: 11, version: 3 }, { id: 12, version: 3 }]))
    expect(await screen.findByText('박둘: 제외 — 다른 사용자가 먼저 변경했습니다.')).toBeInTheDocument()
    expect(screen.getByText('확정 1건 · 제외 1건')).toBeInTheDocument()

    fireEvent.click(await screen.findByText('확정된 1건 모의 발송'))
    const sendPop = (await screen.findByText('1건을 모의 발송할까요?')).closest('.ant-popover') as HTMLElement
    fireEvent.click(within(sendPop).getByText('모의 발송'))
    await waitFor(() => expect(api.batchMockSend).toHaveBeenCalledWith(7, [{ id: 11, idempotency_key: expect.any(String) }]))
    expect(await screen.findByText('모의 발송 성공 1건 (실제 문자·이메일은 전송되지 않음)')).toBeInTheDocument()
    expect(api.mockSend).not.toHaveBeenCalled()  // one request for the class, not one per message
  })

  it('leaves absent students out of "select all", keeps one ticked by hand and counts them in the dialog', async () => {
    asRole('ASSISTANT')
    const message = (patch: Partial<api.BatchMessage>): api.BatchMessage => ({
      ...item, body: '학생 안내', source_changed: false, attention: [], ...patch,
    })
    vi.mocked(api.batchView).mockResolvedValue({ lesson_id: 7, classroom_id: 1, items: [
      message({}),
      message({ id: 12, enrollment_id: 2, student_name: '박둘', attention: ['결석', '미응시'] }),
      message({ id: 13, enrollment_id: 3, student_name: '이셋', attention: ['인정결석'] }),
      message({ id: 14, enrollment_id: 4, student_name: '최넷' }),
    ] })
    renderPage()
    fireEvent.click(await screen.findByText('검토·발송'))
    expect(await screen.findByText('전체 선택은 결석·인정결석 2명을 빼고 선택합니다. 그 학생에게도 보내려면 직접 체크하세요.')).toBeInTheDocument()
    const selectAll = () => document.querySelector('thead input[type="checkbox"]') as HTMLInputElement

    fireEvent.click(selectAll())
    expect(await screen.findByText('선택한 2건 확정')).toBeInTheDocument()
    expect(screen.getByLabelText('김하나 확정 선택')).toBeChecked()
    expect(screen.getByLabelText('최넷 확정 선택')).toBeChecked()
    expect(screen.getByLabelText('박둘 확정 선택')).not.toBeChecked()
    expect(screen.getByLabelText('이셋 확정 선택')).not.toBeChecked()

    fireEvent.click(selectAll())  // again: clears
    expect(await screen.findByText('선택한 0건 확정')).toBeInTheDocument()

    fireEvent.click(screen.getByLabelText('박둘 확정 선택'))  // an absence chosen by hand is kept
    fireEvent.click(selectAll())
    expect(await screen.findByText('선택한 3건 확정')).toBeInTheDocument()
    expect(screen.getByLabelText('이셋 확정 선택')).not.toBeChecked()
    fireEvent.click(screen.getByText('선택한 3건 확정'))
    const pop = (await screen.findByText('선택한 3건을 확정할까요?')).closest('.ant-popover') as HTMLElement
    expect(within(pop).getByText(/이 중 결석 1건이 포함되어 있습니다\. 보호자에게 이미 연락했는지 확인하세요\./)).toBeInTheDocument()
    expect(api.batchApprove).not.toHaveBeenCalled()
  })

  it('uploads only the chosen time slot and reports rows already equal to the app as skipped', async () => {
    asRole('ASSISTANT')
    vi.mocked(upload.listSheets).mockResolvedValue([
      { name: '10시', class_names: ['중3 토10'], student_rows: 2 },
      { name: '2시', class_names: ['중3 토2'], student_rows: 2 },
    ])
    const row = (patch: Partial<upload.UploadRow>): upload.UploadRow => ({
      key: '2시!2', row: 2, name: '가상같음', status: 'MATCHED', attendance: 'PRESENT', prework: 'A', weekly: 'B',
      scores: {}, issues: [], warnings: [], app_attendance: 'PRESENT', attendance_mismatch: false, returning_available: false, ...patch,
    })
    vi.mocked(upload.previewUpload).mockResolvedValue({
      lesson_date: '2026-11-03', can_confirm: true, blocking: [], selected_sheets: ['2시'],
      blocks: [{
        sheet: '2시', row: 1, class_name: '중3 토2', class_type: 'REGULAR', classroom_id: 1, tests: [], issues: [],
        rows: [row({ unchanged: true }), row({ key: '2시!3', row: 3, name: '가상바뀜' })],
      }],
    })
    vi.mocked(upload.confirmUpload).mockResolvedValue({
      lesson_date: '2026-11-03', saved_rows: 1, unchanged_rows: 1, new_students: 0, returned_students: 0, excluded_rows: 0,
      attendance_mismatches: [], drafts: [{ class_name: '중3 토2', created: 1, skipped: [] }],
    })
    renderPage()

    const file = new File(['x'], '주간.xlsx')
    fireEvent.change(await screen.findByLabelText('엑셀 파일'), { target: { files: [file] } })
    // Two time slots in the file: nothing is chosen for the user, so the preview waits for a choice.
    expect(await screen.findByText('10시 · 반 1개 · 학생 2행')).toBeInTheDocument()
    expect(screen.getByText('미리보기').closest('button')).toBeDisabled()
    // Click the checkbox itself (not its label text). antd's Checkbox.Group registers each option
    // in an effect after it renders and drops unregistered values from onChange, so a click in the
    // same instant the options appear is ignored. Retry only while it is still unchecked.
    const slot2 = screen.getByText('2시 · 반 1개 · 학생 2행').closest('label')!.querySelector('input')!
    await waitFor(() => {
      if (!slot2.checked) fireEvent.click(slot2)
      expect(slot2).toBeChecked()
    })
    await waitFor(() => expect(screen.getByText('미리보기').closest('button')).toBeEnabled())
    fireEvent.click(screen.getByText('미리보기'))
    await waitFor(() => expect(upload.previewUpload).toHaveBeenCalledWith(file, expect.any(String), ['2시']))
    // The row equal to the app is labelled and counted as skipped, not as a save.
    const same = (await screen.findByText('가상같음', { selector: 'td' })).closest('tr') as HTMLElement
    expect(within(same).getByText('변경 없음')).toBeInTheDocument()
    expect(within(screen.getByText('3. 변경 확인').closest('.ant-card') as HTMLElement).getByText('변경 없음(생략)')).toBeInTheDocument()

    fireEvent.click(screen.getByText('확정·초안 생성'))
    const pop = (await screen.findByText('업로드를 확정할까요?')).closest('.ant-popover') as HTMLElement
    fireEvent.click(within(pop).getByText('확정'))
    await waitFor(() => expect(upload.confirmUpload).toHaveBeenCalledWith(file, expect.any(String), {}, ['2시']))
    expect(await screen.findByText("저장 1명 · 변경 없음 1명(기록 생략) · 안내 초안 1건을 만들었습니다. '검토·발송'에서 확인하세요.")).toBeInTheDocument()
    expect(screen.getByText('변경 없음(기록 생략)')).toBeInTheDocument()
  })
})
