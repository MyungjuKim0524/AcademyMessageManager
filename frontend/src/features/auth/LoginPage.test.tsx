import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiClientError } from '../../shared/api/ApiClientError'
import { changePassword, completePasswordReset } from './api'
import { useAuth } from './AuthProvider'
import { LoginPage } from './LoginPage'
import { PasswordChangeModal } from './PasswordChangeModal'

vi.mock('./api', () => ({ completePasswordReset: vi.fn(), changePassword: vi.fn() }))
vi.mock('./AuthProvider', () => ({ useAuth: vi.fn() }))

const fill = (label: string, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } })

describe('LoginPage (Phase 11-4-B)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(useAuth).mockReturnValue({ user: null, loading: false, notice: null, login: vi.fn(), logout: vi.fn() })
  })
  afterEach(() => cleanup())

  it('says why the server ended the session', () => {
    vi.mocked(useAuth).mockReturnValue({ user: null, loading: false, notice: '오랫동안 사용하지 않아 로그아웃되었습니다. 다시 로그인해주세요.', login: vi.fn(), logout: vi.fn() })
    render(<MemoryRouter><LoginPage /></MemoryRouter>)
    expect(screen.getByText('오랫동안 사용하지 않아 로그아웃되었습니다. 다시 로그인해주세요.')).toBeInTheDocument()
  })

  it('sets a new password with an administrator-issued code', async () => {
    vi.mocked(completePasswordReset).mockResolvedValue(undefined)
    render(<MemoryRouter><LoginPage /></MemoryRouter>)
    fireEvent.click(screen.getByText('비밀번호를 잊었나요? 재설정 코드로 설정'))
    fill('이메일', 'teacher@example.invalid')
    fill('재설정 코드', 'ABCDE-FGHJK')
    fill('새 비밀번호', 'a brand new passphrase')
    fill('새 비밀번호 확인', 'something different!!')
    fireEvent.click(screen.getByText('비밀번호 설정', { selector: 'button span' }))
    expect(await screen.findByText('새 비밀번호가 서로 다릅니다.')).toBeInTheDocument()
    expect(completePasswordReset).not.toHaveBeenCalled()
    fill('새 비밀번호 확인', 'a brand new passphrase')
    fireEvent.click(screen.getByText('비밀번호 설정', { selector: 'button span' }))
    await waitFor(() => expect(completePasswordReset).toHaveBeenCalledWith('teacher@example.invalid', 'ABCDE-FGHJK', 'a brand new passphrase'))
    expect(await screen.findByText('비밀번호를 설정했습니다. 새 비밀번호로 로그인하세요.')).toBeInTheDocument()
  })

  it('shows the server message when the code is wrong or expired', async () => {
    vi.mocked(completePasswordReset).mockRejectedValue(new ApiClientError('이메일 또는 재설정 코드가 올바르지 않거나 만료되었습니다.', 'RESET_FAILED'))
    render(<MemoryRouter><LoginPage /></MemoryRouter>)
    fireEvent.click(screen.getByText('비밀번호를 잊었나요? 재설정 코드로 설정'))
    fill('이메일', 'teacher@example.invalid')
    fill('재설정 코드', 'WRONG-CODE0')
    fill('새 비밀번호', 'a brand new passphrase')
    fill('새 비밀번호 확인', 'a brand new passphrase')
    fireEvent.click(screen.getByText('비밀번호 설정', { selector: 'button span' }))
    expect(await screen.findByText('이메일 또는 재설정 코드가 올바르지 않거나 만료되었습니다.')).toBeInTheDocument()
  })
})

describe('PasswordChangeModal (Phase 11-4-B)', () => {
  beforeEach(() => vi.clearAllMocks())
  afterEach(() => cleanup())

  it('changes the password and reports the other sessions that were signed out', async () => {
    vi.mocked(changePassword)
      .mockRejectedValueOnce(new ApiClientError('현재 비밀번호가 올바르지 않습니다.', 'INVALID_CURRENT_PASSWORD'))
      .mockResolvedValue({ changed: true, other_sessions_revoked: 2 })
    render(<PasswordChangeModal open onClose={vi.fn()} />)
    fill('현재 비밀번호', 'not my password')
    fill('새 비밀번호', 'a brand new passphrase')
    fill('새 비밀번호 확인', 'a brand new passphrase')
    fireEvent.click(screen.getByText('변경', { selector: 'button span' }))
    expect(await screen.findByText('현재 비밀번호가 올바르지 않습니다.')).toBeInTheDocument()
    fill('현재 비밀번호', 'correct horse battery staple')
    fireEvent.click(screen.getByText('변경', { selector: 'button span' }))
    await waitFor(() => expect(changePassword).toHaveBeenLastCalledWith('correct horse battery staple', 'a brand new passphrase'))
    expect(await screen.findByText('비밀번호를 변경했습니다.')).toBeInTheDocument()
    expect(screen.getByText('다른 기기·브라우저의 로그인 2건을 해제했습니다.')).toBeInTheDocument()
  })

  it('checks the new password length before calling the server', async () => {
    render(<PasswordChangeModal open onClose={vi.fn()} />)
    fill('현재 비밀번호', 'correct horse battery staple')
    fill('새 비밀번호', 'short')
    fill('새 비밀번호 확인', 'short')
    fireEvent.click(screen.getByText('변경', { selector: 'button span' }))
    expect(await screen.findByText('12자 이상 입력해주세요.')).toBeInTheDocument()
    expect(changePassword).not.toHaveBeenCalled()
  })
})
