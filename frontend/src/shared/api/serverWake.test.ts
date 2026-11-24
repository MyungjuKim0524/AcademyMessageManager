import { AxiosError, AxiosHeaders } from 'axios'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { apiClient } from './client'
import { pingServer, waitForServer, WAKE_MAX_WAIT_MS } from './serverWake'

vi.mock('./client', () => ({ apiClient: { get: vi.fn() } }))

const networkError = () => new AxiosError('timeout of 10000ms exceeded', 'ECONNABORTED')
const httpError = (status: number) => new AxiosError('failed', 'ERR_BAD_RESPONSE', undefined, undefined, {
  status, statusText: '', headers: {}, config: { headers: new AxiosHeaders() }, data: {},
})

describe('serverWake', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
  })
  afterEach(() => vi.useRealTimers())

  it('treats any answer below 500 as a running server', async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: { status: 'UP' } })
    expect(await pingServer()).toBe(true)
    vi.mocked(apiClient.get).mockRejectedValueOnce(httpError(404))
    expect(await pingServer()).toBe(true)
    vi.mocked(apiClient.get).mockRejectedValueOnce(httpError(503))
    expect(await pingServer()).toBe(false)
    vi.mocked(apiClient.get).mockRejectedValueOnce(networkError())
    expect(await pingServer()).toBe(false)
    expect(apiClient.get).toHaveBeenCalledWith('/api/health', { timeout: 10_000 })
  })

  it('keeps pinging a sleeping server until it wakes', async () => {
    vi.mocked(apiClient.get)
      .mockRejectedValueOnce(networkError())
      .mockRejectedValueOnce(networkError())
      .mockResolvedValue({ data: { status: 'UP' } })
    const result = waitForServer()
    await vi.runAllTimersAsync()
    expect(await result).toBe(true)
    expect(apiClient.get).toHaveBeenCalledTimes(3)
  })

  it('gives up after the maximum wait', async () => {
    vi.mocked(apiClient.get).mockRejectedValue(networkError())
    const result = waitForServer()
    await vi.advanceTimersByTimeAsync(WAKE_MAX_WAIT_MS + 10_000)
    expect(await result).toBe(false)
  })

  it('shares one wake loop between concurrent callers', async () => {
    vi.mocked(apiClient.get).mockRejectedValueOnce(networkError()).mockResolvedValue({ data: { status: 'UP' } })
    const first = waitForServer()
    const second = waitForServer()
    expect(second).toBe(first)
    await vi.runAllTimersAsync()
    expect(await first).toBe(true)
    expect(apiClient.get).toHaveBeenCalledTimes(2)
  })
})
