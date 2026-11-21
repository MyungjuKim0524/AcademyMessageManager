import axios from 'axios'

export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '',
  timeout: 10_000,
  withCredentials: true,
  withXSRFToken: true,
  xsrfCookieName: import.meta.env.VITE_CSRF_COOKIE || 'academy_csrf',
  xsrfHeaderName: 'X-CSRF-Token',
})
