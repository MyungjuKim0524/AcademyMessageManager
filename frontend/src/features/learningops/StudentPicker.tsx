import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Select } from 'antd'
import * as api from './api'

const label = (row: api.Student) => `${row.name}${row.school_name ? ` · ${row.school_name}` : ''} (ID ${row.id})`

type Props = {
  value?: number
  onChange?: (value: number | undefined) => void
  /** A just-registered student, so it can be shown even before it appears in the search results. */
  recent?: api.Student | null
  /** Changing this reloads the list (e.g. after a student was registered). */
  reloadKey?: number
  onError: (error: unknown) => void
}

/** Pick a student by name instead of typing an internal student ID. */
export function StudentPicker({ value, onChange, recent, reloadKey, onError }: Props) {
  const [found, setFound] = useState<api.Student[]>([])
  const [loading, setLoading] = useState(false)
  const latest = useRef(0)
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  const search = useCallback(async (query: string) => {
    const request = ++latest.current
    setLoading(true)
    try {
      const page = await api.allStudents(query, 20)
      if (request === latest.current) setFound(page.items)
    } catch (error) {
      if (request === latest.current) onError(error)
    } finally {
      if (request === latest.current) setLoading(false)
    }
  }, [onError])

  useEffect(() => { void search('') }, [search, reloadKey])
  useEffect(() => () => clearTimeout(timer.current), [])

  const options = useMemo(() => {
    const rows = recent && !found.some((row) => row.id === recent.id) ? [recent, ...found] : found
    return rows.map((row) => ({ value: row.id, label: label(row) }))
  }, [found, recent])

  return (
    <Select
      aria-label="학생 선택"
      showSearch={{
        filterOption: false,
        onSearch: (query) => {
          clearTimeout(timer.current)
          timer.current = setTimeout(() => void search(query), 300)
        },
      }}
      allowClear
      placeholder="학생 이름으로 검색"
      loading={loading}
      notFoundContent={loading ? '검색 중…' : '일치하는 학생이 없습니다. 먼저 학생 등록을 하세요.'}
      value={value}
      onChange={(next) => onChange?.(next ?? undefined)}
      options={options}
      style={{ width: '100%' }}
    />
  )
}
