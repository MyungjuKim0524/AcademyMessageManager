import { apiClient } from '../../shared/api/client'
import { toApiClientError } from '../../shared/api/ApiClientError'
import type { AuthResponse } from './types'

export async function login(email: string, password: string): Promise<AuthResponse> {
  try {
    const { data } = await apiClient.post<AuthResponse>('/api/auth/login', { email, password })
    return data
  } catch (error) {
    throw toApiClientError(error)
  }
}

export async function logout(): Promise<void> {
  try {
    await apiClient.post('/api/auth/logout')
  } catch (error) {
    throw toApiClientError(error)
  }
}

export async function currentUser(): Promise<AuthResponse> {
  try {
    const { data } = await apiClient.get<AuthResponse>('/api/auth/me')
    return data
  } catch (error) {
    throw toApiClientError(error)
  }
}

/** SEC-10-A: change one's own password (current password required; other sessions end). */
export async function changePassword(currentPassword: string, newPassword: string): Promise<{ changed: boolean; other_sessions_revoked: number }> {
  try {
    const { data } = await apiClient.post('/api/auth/password', { current_password: currentPassword, new_password: newPassword })
    return data
  } catch (error) {
    throw toApiClientError(error)
  }
}

/** SEC-10-B: set a new password with the one-time code an administrator handed over. */
export async function completePasswordReset(email: string, code: string, newPassword: string): Promise<void> {
  try {
    await apiClient.post('/api/auth/password-reset', { email, code, new_password: newPassword })
  } catch (error) {
    throw toApiClientError(error)
  }
}
