import axios from 'axios'
import { apiClient } from './client'

/**
 * The demo backend runs on a free Render instance that sleeps after ~15 idle minutes and takes
 * 30-60 s to start again. The regular 10 s request timeout gives up long before that, so the
 * login page wakes the server with /api/health first (no database work, no rate limit) and
 * only sends the real login request once the server answers. The login request itself is
 * never retried: repeated failed logins would trip the login rate limit.
 */
export const WAKE_MAX_WAIT_MS = 90_000
export const WAKE_RETRY_MS = 3_000
const PING_TIMEOUT_MS = 10_000

/** True when the API process answered. A 4xx still proves it is up; 5xx (proxy/startup) does not. */
export async function pingServer(): Promise<boolean> {
  try {
    await apiClient.get('/api/health', { timeout: PING_TIMEOUT_MS })
    return true
  } catch (error) {
    return axios.isAxiosError(error) && !!error.response && error.response.status < 500
  }
}

let inFlight: Promise<boolean> | null = null

/** Pings until the server answers or WAKE_MAX_WAIT_MS passes. Concurrent callers share one loop. */
export function waitForServer(): Promise<boolean> {
  inFlight ??= (async () => {
    const deadline = Date.now() + WAKE_MAX_WAIT_MS
    try {
      for (;;) {
        if (await pingServer()) return true
        if (Date.now() >= deadline) return false
        await new Promise((resolve) => setTimeout(resolve, WAKE_RETRY_MS))
      }
    } finally {
      inFlight = null
    }
  })()
  return inFlight
}
