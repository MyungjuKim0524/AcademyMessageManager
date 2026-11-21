import { configure, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useAuth } from '../auth/AuthProvider'
import { MessageOperationsPage } from './MessageOperationsPage'
import * as api from './api'
import * as notifications from '../notifications/api'

configure({ asyncUtilTimeout: 10000 })
vi.mock('../auth/AuthProvider', () => ({ useAuth: vi.fn() }))
vi.mock('./api', () => ({ getSummary: vi.fn(), listObligations: vi.fn() }))
vi.mock('../notifications/api', () => ({ retryMockSend: vi.fn() }))

const counts = (patch: Partial<api.Counts> = {}): api.Counts => ({
  total: 4, missing: 1, in_review: 0, ready_to_send: 0, failed: 1, done: 2, pending: 1, exempt: 1, overdue: null, completion_rate: 50, ...patch,
})
const summary: api.Summary = {
  date_from: '2026-11-07', date_to: '2026-11-20', deadline_policy: 'NOT_CONFIGURED', totals: counts(),
  classrooms: [
    { classroom_id: 1, classroom_name: '중3 토10', class_type: 'REGULAR', ...counts() },
    { classroom_id: 2, classroom_name: '00고2 토10', class_type: 'EXAM_PREP', ...counts({ total: 0, missing: 0, failed: 0, done: 0, pending: 0, exempt: 0, completion_rate: null }) },
  ],
}
const base: api.Obligation = {
  lesson_id: 7, enrollment_id: 1, classroom_id: 1, classroom_name: '중3 토10', student_id: 11, student_name: '가상하나',
  lesson_date: '2026-11-15', session_no: 1, exam_round: null, topic: '이차함수', lesson_status: 'COMPLETED', obligated: true,
  exempt_reason: null, exempt_reason_label: null, status: 'DONE', notification_id: 21, notification_status: 'MOCK_SENT', template_name: '기본',
  active_messages: 1, processed_at: '2026-11-15T10:00:00Z', attempt_count: 1, failure: null, hints: [], next_action: 'VIEW_HISTORY', overdue: null,
}
const page: api.ObligationPage = {
  total: 4, limit: 50, offset: 0, items: [
    base,
    { ...base, enrollment_id: 2, student_name: '가상둘', status: 'FAILED', notification_id: 22, notification_status: 'MOCK_FAILED', next_action: 'RETRY',
      failure: { code: 'MOCK_TEMPORARY_FAILURE', category: 'SENDER', category_label: '모의 발송기 일시 실패', message: '모의 발송 실패: 일시적인 발송 오류입니다.', attempted_at: '2026-11-15T10:00:00Z' } },
    { ...base, enrollment_id: 3, student_name: '가상셋', status: 'MISSING', notification_id: null, notification_status: null, next_action: 'CREATE_DRAFT', hints: ['보호자 이메일 없음'], processed_at: null },
    { ...base, enrollment_id: 4, student_name: '가상넷', status: 'EXEMPT', obligated: false, exempt_reason: 'NOT_ELIGIBLE', exempt_reason_label: '휴원·수강 대상 아님', notification_id: null, next_action: 'NONE', processed_at: null },
  ],
}

function Where() {
  const location = useLocation()
  return <div>{`이동: ${location.pathname}${location.search}`}</div>
}

const renderPage = (path = '/message-operations') => render(
  <MemoryRouter initialEntries={[path]}>
    <Routes>
      <Route path="/message-operations" element={<MessageOperationsPage />} />
      <Route path="/notifications" element={<Where />} />
      <Route path="/students" element={<Where />} />
    </Routes>
  </MemoryRouter>,
)

const rowOf = (name: string) => screen.getByText(name).closest('tr') as HTMLElement
const asRole = (role: 'ADMIN' | 'TEACHER' | 'ASSISTANT') => vi.mocked(useAuth).mockReturnValue({
  user: { id: 2, email: 'user@example.invalid', role }, loading: false, login: vi.fn(), logout: vi.fn(),
})

describe('MessageOperationsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    asRole('TEACHER')
    vi.mocked(api.getSummary).mockResolvedValue(summary)
    vi.mocked(api.listObligations).mockResolvedValue(page)
  })

  it('shows totals, per-class rows and the processing list with statuses in words, labelled as mock', async () => {
    renderPage()
    expect(await screen.findByText('중3 토10 처리 목록')).toBeInTheDocument()
    expect(screen.getByText("모의 발송 기준 현황입니다. 실제 문자·이메일은 전송되지 않으며, '완료'는 실제 학부모 수신을 뜻하지 않습니다.")).toBeInTheDocument()
    expect(screen.getByText('처리 기한 정책: 미설정 (기한 초과 판정 안 함) · 최대 3개월')).toBeInTheDocument()
    expect(screen.getAllByText('50%').length).toBeGreaterThan(0)
    // A class with nothing due shows "대상 없음", never 0%.
    expect(within(rowOf('00고2 토10')).getByText('대상 없음')).toBeInTheDocument()
    // The list is requested on its own after the summary, so wait for the call instead of
    // asserting it in the same tick (it raced under a busy run).
    await waitFor(() => expect(api.listObligations).toHaveBeenCalledWith(1, expect.any(String), expect.any(String), undefined, 50, 0))
    await screen.findByText('가상둘') // the list arrives in its own request after the summary
    expect(within(rowOf('가상둘')).getByText('모의 발송 실패')).toBeInTheDocument()
    expect(within(rowOf('가상둘')).getByText('모의 발송기 일시 실패: 모의 발송 실패: 일시적인 발송 오류입니다.')).toBeInTheDocument()
    expect(within(rowOf('가상셋')).getByText('보호자 이메일 없음')).toBeInTheDocument()
    expect(within(rowOf('가상넷')).getByText('휴원·수강 대상 아님')).toBeInTheDocument()
  })

  it('filters by status and switches classroom from the per-class table', async () => {
    renderPage()
    await screen.findByText('중3 토10 처리 목록')
    // Phase 9.6: the filter is a row of status buttons carrying the selected class's counts.
    const filter = screen.getByLabelText('상태 필터')
    expect(within(filter).getByText('전체 5')).toBeInTheDocument() // 4 due + 1 not due
    fireEvent.click(within(filter).getByText('모의 발송 실패 1'))
    await waitFor(() => expect(api.listObligations).toHaveBeenLastCalledWith(1, expect.any(String), expect.any(String), 'FAILED', 50, 0))
    fireEvent.click(screen.getByText('00고2 토10'))
    await waitFor(() => expect(api.listObligations).toHaveBeenLastCalledWith(2, expect.any(String), expect.any(String), 'FAILED', 50, 0))
    expect(window.sessionStorage.getItem('learningops.workingClassroom')).toBe('2')
  })

  it('summarises work still to do first, with completion as the supporting figure', async () => {
    renderPage()
    const card = (await screen.findByText(/^전체 반 요약/)).closest('.ant-card') as HTMLElement
    expect(within(card).getByText('처리가 필요한 항목')).toBeInTheDocument()
    expect(within(card).getByText('초안 미생성')).toBeInTheDocument()
    expect(within(card).getByText('모의 발송 실패')).toBeInTheDocument()
    expect(within(card).getByText('50%')).toBeInTheDocument()
  })

  it('opens the class being worked on in another screen', async () => {
    window.sessionStorage.setItem('learningops.workingClassroom', '2')
    renderPage()
    await screen.findByText('00고2 토10 처리 목록')
    expect(api.listObligations).toHaveBeenCalledWith(2, expect.any(String), expect.any(String), undefined, 50, 0)
  })

  it('links a missing guardian e-mail to the contact editor for administrators only', async () => {
    asRole('ADMIN')
    renderPage()
    await screen.findByText('가상셋')
    fireEvent.click(within(rowOf('가상셋')).getByText('메일 주소 변경'))
    expect(await screen.findByText('이동: /students?contact=11&from=%2Fmessage-operations')).toBeInTheDocument()
  })

  it('retries a failed mock send once per click with an idempotency key, then refreshes', async () => {
    vi.mocked(notifications.retryMockSend).mockResolvedValue({
      replayed: false,
      attempt: { id: 3, channel: 'MOCK', result: 'MOCK_SUCCESS', error_code: null, error_message: null, requested_by: '조교', attempted_at: '' },
      notification: {} as notifications.NotificationDetail,
    })
    renderPage()
    await screen.findByText('가상둘')
    fireEvent.click(within(rowOf('가상둘')).getByText('재시도'))
    const confirm = (await screen.findByText('모의 발송을 재시도할까요?')).closest('.ant-popover') as HTMLElement
    fireEvent.click(within(confirm).getByText('재시도'))
    await waitFor(() => expect(notifications.retryMockSend).toHaveBeenCalledTimes(1))
    expect(vi.mocked(notifications.retryMockSend).mock.calls[0][0]).toBe(22)
    expect(vi.mocked(notifications.retryMockSend).mock.calls[0][1]).toMatch(/^[0-9a-f-]{36}$/)
    expect(await screen.findByText('가상둘 메시지를 다시 모의 발송했습니다(성공). 실제 문자·이메일은 전송되지 않았습니다.')).toBeInTheDocument()
    await waitFor(() => expect(api.getSummary).toHaveBeenCalledTimes(2))
  })

  it('shows a changed-source refusal as a warning instead of retrying blindly', async () => {
    const { ApiClientError } = await import('../../shared/api/ApiClientError')
    vi.mocked(notifications.retryMockSend).mockRejectedValue(new ApiClientError('메시지 생성 후 수업·출결·성적 또는 연락처가 바뀌어 재시도할 수 없습니다.', 'SOURCE_CHANGED'))
    renderPage()
    await screen.findByText('가상둘')
    fireEvent.click(within(rowOf('가상둘')).getByText('재시도'))
    const confirm = (await screen.findByText('모의 발송을 재시도할까요?')).closest('.ant-popover') as HTMLElement
    fireEvent.click(within(confirm).getByText('재시도'))
    expect(await screen.findByText('메시지 생성 후 수업·출결·성적 또는 연락처가 바뀌어 재시도할 수 없습니다.')).toBeInTheDocument()
  })

  it('links follow-up actions to the existing 성적 안내 screens', async () => {
    renderPage()
    await screen.findByText('가상셋')
    fireEvent.click(within(rowOf('가상셋')).getByText('초안 생성'))
    expect(await screen.findByText('이동: /notifications?classroom=1&tab=compose&lesson=7')).toBeInTheDocument()
  })

  it('opens a finished message history in the review screen', async () => {
    renderPage()
    await screen.findByText('가상하나')
    fireEvent.click(within(rowOf('가상하나')).getByText('이력 보기'))
    expect(await screen.findByText('이동: /notifications?classroom=1&tab=review&notification=21')).toBeInTheDocument()
  })

  it('preselects the status filter from the link (dashboard "발송 실패 확인")', async () => {
    renderPage('/message-operations?status=FAILED')
    await waitFor(() => expect(api.listObligations).toHaveBeenCalledWith(1, expect.any(String), expect.any(String), 'FAILED', 50, 0))
  })

  it('works as the 처리 현황 tab: no own page header, follows and changes the page class', async () => {
    const onSelect = vi.fn()
    render(
      <MemoryRouter initialEntries={['/notifications?tab=operations']}>
        <Routes><Route path="/notifications" element={<MessageOperationsPage embedded classroomId={2} onSelectClassroom={onSelect} />} /></Routes>
      </MemoryRouter>,
    )
    expect(await screen.findByText('00고2 토10 처리 목록')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: '메시지 처리 현황' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByText('중3 토10'))
    expect(onSelect).toHaveBeenCalledWith(1)
  })

  it('shows an empty state when the staff member has no classrooms, and errors from the server', async () => {
    vi.mocked(api.getSummary).mockResolvedValueOnce({ ...summary, totals: counts({ total: 0, completion_rate: null }), classrooms: [] })
    renderPage()
    expect(await screen.findByText('볼 수 있는 반이 없습니다. 관리자에게 반 배정을 요청하세요.')).toBeInTheDocument()
    expect(api.listObligations).not.toHaveBeenCalled()
  })
})
