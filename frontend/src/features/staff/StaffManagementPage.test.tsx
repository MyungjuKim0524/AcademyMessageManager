import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { StaffManagementPage } from './StaffManagementPage'
import * as api from './api'

vi.mock('./api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./api')>()
  return {
    staffLabel: actual.staffLabel,
    listStaff: vi.fn(),
    listClassrooms: vi.fn(),
    listAssignments: vi.fn(),
    listClassroomStaff: vi.fn(),
    createStaff: vi.fn(),
    updateStaffName: vi.fn(),
    updateStaffStatus: vi.fn(),
    deleteStaff: vi.fn(),
    createAssignment: vi.fn(),
    removeAssignment: vi.fn(),
    issueResetCode: vi.fn(),
  }
})

const stamp = '2026-11-17T00:00:00Z'
const staff = (id: number, display_name: string | null, role: api.StaffRole, status: api.StaffStatus = 'ACTIVE'): api.Staff => ({
  id, display_name, role, status, email: `user${id}@example.invalid`, created_at: stamp, updated_at: stamp,
})

describe('StaffManagementPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(api.listStaff).mockResolvedValue([])
    vi.mocked(api.listClassrooms).mockResolvedValue([])
    vi.mocked(api.listAssignments).mockResolvedValue([])
    vi.mocked(api.listClassroomStaff).mockResolvedValue([])
  })

  it('loads the staff account controls with a required name field', async () => {
    render(<StaffManagementPage />)

    expect(screen.getByRole('heading', { name: '직원 및 담당 반 관리' })).toBeInTheDocument()
    expect(screen.getByLabelText('이름')).toHaveAttribute('autocomplete', 'off')
    expect(screen.getByLabelText('이메일')).toHaveAttribute('autocomplete', 'off')
    expect(screen.getByLabelText('초기 비밀번호')).toHaveAttribute('autocomplete', 'new-password')
    await waitFor(() => expect(api.listStaff).toHaveBeenCalledOnce())
    expect(api.listClassrooms).toHaveBeenCalledOnce()
    expect(screen.getByRole('button', { name: /직원 등록/ })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: '반별 담당 배정' })).toBeInTheDocument()
  })

  it('shows staff names and falls back for accounts without a name', async () => {
    vi.mocked(api.listStaff).mockResolvedValue([staff(1, null, 'ADMIN'), staff(2, '김민지', 'TEACHER')])
    render(<StaffManagementPage />)

    const named = await screen.findByText('김민지')
    const table = named.closest('table') as HTMLElement
    expect(within(table).getByText('이름 미등록')).toBeInTheDocument()
    expect(within(table).getByText('선생님')).toBeInTheDocument()
    expect(within(table).getByText('관리자')).toBeInTheDocument()
  })

  it('deletes a staff account only after one warning and says when the name stays on records', async () => {
    vi.mocked(api.listStaff)
      .mockResolvedValueOnce([staff(1, '관리자', 'ADMIN'), staff(2, '김민지', 'TEACHER')])
      .mockResolvedValue([staff(1, '관리자', 'ADMIN')])
    vi.mocked(api.deleteStaff).mockResolvedValue({ staff_id: 2, mode: 'SOFT' })
    render(<StaffManagementPage />)

    const row = (await screen.findByText('김민지')).closest('tr') as HTMLElement
    fireEvent.click(within(row).getByText('삭제', { selector: 'button span' }))
    const warning = (await screen.findByText('김민지 계정을 삭제하시겠습니까?')).closest('.ant-popover') as HTMLElement
    expect(within(warning).getByText(/되돌릴 수 없습니다/)).toBeInTheDocument()
    expect(within(warning).getByText(/이름이 그대로 남습니다/)).toBeInTheDocument()
    expect(api.deleteStaff).not.toHaveBeenCalled() // nothing happens before the warning is confirmed
    fireEvent.click(within(warning).getByText('삭제', { selector: 'button span' }))
    await waitFor(() => expect(api.deleteStaff).toHaveBeenCalledWith(2))
    expect(await screen.findByText('김민지 계정을 삭제했습니다. 업무 기록이 있어 기록 속 이름은 남겨 두었습니다.')).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByText('김민지')).not.toBeInTheDocument())
  })

  it('issues a password reset code only for active staff after confirmation and shows it once', async () => {
    vi.mocked(api.listStaff).mockResolvedValue([
      staff(1, '원장', 'ADMIN'),
      staff(2, '김민지', 'TEACHER'),
      staff(3, '박조교', 'ASSISTANT', 'INACTIVE'),
    ])
    vi.mocked(api.issueResetCode).mockResolvedValue({ staff_id: 2, code: 'ABCDE-FGHJK', expires_at: '2026-11-21T09:15:00Z' })
    render(<StaffManagementPage />)

    const row = (await screen.findByText('김민지')).closest('tr') as HTMLElement
    const inactiveRow = screen.getByText('박조교').closest('tr') as HTMLElement
    expect(within(inactiveRow).queryByText('재설정 코드', { selector: 'button span' })).not.toBeInTheDocument()

    fireEvent.click(within(row).getByText('재설정 코드', { selector: 'button span' }))
    const confirm = (await screen.findByText('김민지에게 비밀번호 재설정 코드를 발급할까요?')).closest('.ant-popover') as HTMLElement
    expect(api.issueResetCode).not.toHaveBeenCalled()
    fireEvent.click(within(confirm).getByText('발급', { selector: 'button span' }))
    await waitFor(() => expect(api.issueResetCode).toHaveBeenCalledWith(2))

    const dialog = (await screen.findByText('ABCDE-FGHJK')).closest('.ant-modal') as HTMLElement
    expect(within(dialog).getByText(/이 창을 닫으면 코드를 다시 볼 수 없습니다/)).toBeInTheDocument()
    fireEvent.click(within(dialog).getByText('전달했습니다', { selector: 'button span' }))
    // jsdom never finishes antd's closing animation, so end it by hand; destroyOnHidden then drops the code.
    await waitFor(() => {
      fireEvent.animationEnd(dialog)
      fireEvent.transitionEnd(dialog)
      expect(screen.queryByText('ABCDE-FGHJK')).not.toBeInTheDocument()
    })
  })

  it('assigns staff per classroom and only offers active, unassigned non-admin staff', async () => {
    vi.mocked(api.listClassrooms).mockResolvedValue([
      { id: 10, name: '중2 수학', class_type: 'REGULAR', is_active: true },
      { id: 11, name: '고1 영어', class_type: 'REGULAR', is_active: true },
    ])
    vi.mocked(api.listStaff).mockResolvedValue([
      staff(1, '원장', 'ADMIN'),
      staff(2, '김민지', 'TEACHER'),
      staff(3, '박조교', 'ASSISTANT', 'INACTIVE'),
      staff(4, '이배정', 'TEACHER'),
    ])
    vi.mocked(api.listClassroomStaff).mockResolvedValue([{
      id: 99, classroom_id: 10, staff_user_id: 4, assignment_role: 'TEACHER', valid_from: '2026-11-01',
      valid_to: null, email: 'user4@example.invalid', display_name: '이배정', staff_status: 'ACTIVE',
    }])
    vi.mocked(api.createAssignment).mockResolvedValue({})

    render(<StaffManagementPage />)
    await waitFor(() => expect(api.listStaff).toHaveBeenCalled())
    fireEvent.click(screen.getByRole('tab', { name: '반별 담당 배정' }))

    await waitFor(() => expect(api.listClassroomStaff).toHaveBeenCalledWith(10))
    expect(await screen.findByText('중2 수학 담당 직원')).toBeInTheDocument()
    // getByRole is avoided below: jsdom style resolution makes it take minutes on this antd-heavy screen.
    const assignedRow = (await screen.findByText('배정 해제')).closest('tr') as HTMLElement
    expect(within(assignedRow).getByText('이배정')).toBeInTheDocument()

    fireEvent.mouseDown(screen.getByLabelText('배정할 직원'))
    expect(await screen.findByTitle(/김민지/)).toBeInTheDocument()
    expect(screen.queryByTitle(/원장/)).not.toBeInTheDocument()
    expect(screen.queryByTitle(/박조교/)).not.toBeInTheDocument()
    expect(screen.queryByTitle(/이배정/)).not.toBeInTheDocument()

    fireEvent.click(screen.getByTitle(/김민지/))
    fireEvent.click(screen.getByText('배정'))
    await waitFor(() => expect(api.createAssignment).toHaveBeenCalledWith(10, 2, 'TEACHER', expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/)))
    expect(await screen.findByText('김민지님을 중2 수학에 배정했습니다.')).toBeInTheDocument()

    fireEvent.click(screen.getByText('고1 영어'))
    await waitFor(() => expect(api.listClassroomStaff).toHaveBeenCalledWith(11))
  })
})
