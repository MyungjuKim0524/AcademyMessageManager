import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useAuth } from './AuthProvider'
import { ProtectedRoute } from './ProtectedRoute'

vi.mock('./AuthProvider', () => ({ useAuth: vi.fn() }))

function renderRoute(roles?: Array<'ADMIN' | 'TEACHER' | 'ASSISTANT'>) {
  return render(<MemoryRouter initialEntries={['/private']}><Routes>
    <Route path="/login" element={<div>login-page</div>} />
    <Route path="/private" element={<ProtectedRoute roles={roles}><div>private-page</div></ProtectedRoute>} />
  </Routes></MemoryRouter>)
}

afterEach(() => vi.clearAllMocks())

describe('ProtectedRoute', () => {
  it('redirects an unauthenticated user to login', async () => {
    vi.mocked(useAuth).mockReturnValue({ user: null, loading: false, login: vi.fn(), logout: vi.fn() })
    renderRoute()
    expect(await screen.findByText('login-page')).toBeInTheDocument()
  })

  it('renders 403 for a role outside the allowlist', () => {
    vi.mocked(useAuth).mockReturnValue({
      user: { id: 2, email: 'teacher@example.invalid', role: 'TEACHER' },
      loading: false,
      login: vi.fn(),
      logout: vi.fn(),
    })
    renderRoute(['ADMIN'])
    expect(screen.getByText('접근 권한이 없습니다')).toBeInTheDocument()
  })

  it('renders the protected content for an allowed role', () => {
    vi.mocked(useAuth).mockReturnValue({
      user: { id: 1, email: 'admin@example.invalid', role: 'ADMIN' },
      loading: false,
      login: vi.fn(),
      logout: vi.fn(),
    })
    renderRoute(['ADMIN'])
    expect(screen.getByText('private-page')).toBeInTheDocument()
  })
})
