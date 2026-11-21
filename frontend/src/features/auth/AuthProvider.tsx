import { createContext, useContext, useEffect, useMemo, useRef, useState, type PropsWithChildren } from 'react'
import axios from 'axios'
import { apiClient } from '../../shared/api/client'
import { currentUser, login as loginRequest, logout as logoutRequest } from './api'
import type { CurrentStaff } from './types'

interface AuthContextValue {
  user: CurrentStaff | null
  loading: boolean
  /** Why the user was signed out by the server (idle / expired session), shown on the login page. */
  notice?: string | null
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

/** Requests whose 401 is an answer, not a sign that the session ended. */
const OWN_401 = ['/api/auth/login', '/api/auth/password-reset']
export const IDLE_NOTICE = '오랫동안 사용하지 않아 로그아웃되었습니다. 다시 로그인해주세요.'
export const EXPIRED_NOTICE = '세션이 만료되었습니다. 다시 로그인해주세요.'

export function AuthProvider({ children }: PropsWithChildren) {
  const [user, setUser] = useState<CurrentStaff | null>(null)
  const [loading, setLoading] = useState(true)
  const [notice, setNotice] = useState<string | null>(null)
  const signedIn = useRef(false)
  signedIn.current = user !== null

  useEffect(() => {
    let active = true
    currentUser()
      .then(({ user: value }) => { if (active) setUser(value) })
      .catch(() => { if (active) setUser(null) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

  // SEC-05 (Phase 11-4-B): the server decides when a session ends (idle or absolute expiry,
  // log-out elsewhere, deactivation). Any 401 while signed in ends it here too, so the next
  // screen is the login page with the reason instead of a broken page.
  useEffect(() => {
    const id = apiClient.interceptors.response.use(undefined, (error) => {
      const url = axios.isAxiosError(error) ? error.config?.url ?? '' : ''
      if (axios.isAxiosError(error) && error.response?.status === 401 && signedIn.current && !OWN_401.some((path) => url.endsWith(path))) {
        const code = (error.response.data as { code?: string } | undefined)?.code
        setNotice(code === 'SESSION_IDLE_EXPIRED' ? IDLE_NOTICE : EXPIRED_NOTICE)
        setUser(null)
      }
      return Promise.reject(error)
    })
    return () => apiClient.interceptors.response.eject(id)
  }, [])

  const value = useMemo<AuthContextValue>(() => ({
    user,
    loading,
    notice,
    login: async (email, password) => {
      const result = await loginRequest(email, password)
      setNotice(null)
      setUser(result.user)
    },
    logout: async () => {
      try { await logoutRequest() } finally { setUser(null) }
    },
  }), [loading, notice, user])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext)
  if (!value) throw new Error('AuthProvider가 필요합니다.')
  return value
}
