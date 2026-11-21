import type { AxiosRequestConfig } from 'axios'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { apiClient } from '../../shared/api/client'
import { STUDENT_PAGE_SIZE, students, type ClassroomStudent } from './api'

vi.mock('../../shared/api/client', () => ({ apiClient: { get: vi.fn() } }))

const fictional = (n: number): ClassroomStudent => ({
  id: n, enrollment_id: 1000 + n, name: `가상학생${n}`, school_name: null, enrollment_status: 'ACTIVE', enrolled_at: '2026-01-01',
})

/** A server holding `count` students ordered by id, answering limit/offset like the real API. */
function serve(count: number) {
  const all = Array.from({ length: count }, (_, i) => fictional(i + 1))
  vi.mocked(apiClient.get).mockImplementation(async (_url: string, config?: AxiosRequestConfig) => {
    const { limit, offset } = config!.params as { limit: number; offset: number }
    return { data: { items: all.slice(offset, offset + limit), limit, offset } }
  })
}

describe('students (class list, all pages)', () => {
  beforeEach(() => vi.clearAllMocks())

  it.each([
    [0, 1], [1, 1], [50, 1], [51, 1], [99, 1], [100, 2], [101, 2], [250, 3],
  ])('returns all %i students without gaps or duplicates (%i request(s))', async (count, requests) => {
    serve(count)
    const rows = await students(7)
    expect(rows).toHaveLength(count)
    expect(rows.map((row) => row.id)).toEqual(Array.from({ length: count }, (_, i) => i + 1)) // order kept
    expect(apiClient.get).toHaveBeenCalledTimes(requests)
    vi.mocked(apiClient.get).mock.calls.forEach(([url, config], page) => {
      expect(url).toBe('/api/classrooms/7/students')
      expect(config).toEqual({ params: { limit: STUDENT_PAGE_SIZE, offset: page * STUDENT_PAGE_SIZE } })
    })
  })

  it('keeps a row once when it appears on two pages (an enrolment added while paging)', async () => {
    const first = Array.from({ length: 100 }, (_, i) => fictional(i + 1))
    vi.mocked(apiClient.get)
      .mockResolvedValueOnce({ data: { items: first } })
      .mockResolvedValueOnce({ data: { items: [fictional(100), fictional(101)] } }) // 100 shifted onto page 2
    const rows = await students(7)
    expect(rows.map((row) => row.id)).toEqual(Array.from({ length: 101 }, (_, i) => i + 1))
  })

  it('fails as a whole when a later page fails, instead of returning a partial list', async () => {
    vi.mocked(apiClient.get)
      .mockResolvedValueOnce({ data: { items: Array.from({ length: 100 }, (_, i) => fictional(i + 1)) } })
      .mockRejectedValueOnce(new Error('network down'))
    await expect(students(7)).rejects.toThrow('network down')
  })
})
