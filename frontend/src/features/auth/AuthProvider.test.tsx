import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AxiosError } from 'axios'
import { apiClient } from '../../shared/api/client'
import { AuthProvider, IDLE_NOTICE, useAuth } from './AuthProvider'
import { currentUser, login, logout } from './api'

vi.mock('./api', () => ({ currentUser: vi.fn(), login: vi.fn(), logout: vi.fn() }))

function Harness() {
  const auth = useAuth()
  if (auth.loading) return <span>loading</span>
  return <div>
    <span>{auth.user?.email || 'anonymous'}</span>
    <button onClick={() => void auth.login('admin@example.invalid', 'not-a-real-password')}>login</button>
    <button onClick={() => void auth.logout()}>logout</button>
    <button onClick={() => void apiClient.get('/api/classrooms').catch(() => undefined)}>call api</button>
    {auth.notice && <p>{auth.notice}</p>}
  </div>
}

describe('AuthProvider', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(currentUser).mockRejectedValue(new Error('unauthenticated'))
    vi.mocked(login).mockResolvedValue({
      user: { id: 1, email: 'admin@example.invalid', role: 'ADMIN' },
    })
    vi.mocked(logout).mockResolvedValue(undefined)
  })

  afterEach(() => cleanup())

  it('treats a failed session lookup as anonymous', async () => {
    render(<AuthProvider><Harness /></AuthProvider>)
    expect(await screen.findByText('anonymous')).toBeInTheDocument()
    expect(currentUser).toHaveBeenCalledTimes(1)
    expect(screen.queryByText('요청 처리 중 오류가 발생했습니다.')).not.toBeInTheDocument()
  })

  it('stores only the returned staff profile after login and clears it after logout', async () => {
    const user = userEvent.setup()
    render(<AuthProvider><Harness /></AuthProvider>)
    await screen.findByText('anonymous')
    await user.click(screen.getByRole('button', { name: 'login' }))
    expect(await screen.findByText('admin@example.invalid')).toBeInTheDocument()
    expect(login).toHaveBeenCalledWith('admin@example.invalid', 'not-a-real-password')
    await user.click(screen.getByRole('button', { name: 'logout' }))
    await waitFor(() => expect(screen.getByText('anonymous')).toBeInTheDocument())
  })

  it('ends the session on a server 401 and says why (SEC-05 idle expiry)', async () => {
    const user = userEvent.setup()
    const original = apiClient.defaults.adapter
    apiClient.defaults.adapter = async (config) => {
      throw new AxiosError('Request failed', AxiosError.ERR_BAD_REQUEST, config, {}, {
        status: 401, statusText: 'Unauthorized', headers: {}, config,
        data: { code: 'SESSION_IDLE_EXPIRED', message: 'idle', fields: [] },
      })
    }
    try {
      render(<AuthProvider><Harness /></AuthProvider>)
      await screen.findByText('anonymous')
      await user.click(screen.getByRole('button', { name: 'login' }))
      await screen.findByText('admin@example.invalid')
      await user.click(screen.getByRole('button', { name: 'call api' }))
      expect(await screen.findByText('anonymous')).toBeInTheDocument()
      expect(screen.getByText(IDLE_NOTICE)).toBeInTheDocument()
    } finally {
      apiClient.defaults.adapter = original
    }
  })
})
