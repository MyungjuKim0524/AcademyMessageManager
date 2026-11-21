import { useEffect, useRef, useState } from 'react'
import { Alert, Button } from 'antd'
import { toApiClientError } from '../../shared/api/ApiClientError'

/** "대상 없음" when a rate has no denominator — never 0%. */
export const rateText = (value: number | null, none = '대상 없음') => (value === null ? none : `${value.toFixed(1)}%`)
export const scoreText = (value: number | null) => (value === null ? '-' : String(value))

type Load<T> = { data: T | null; loading: boolean; error: string | null; reload: () => void }

/** Fetch with "latest request wins" (a slow answer for an old filter never replaces a newer one). */
export function useLoad<T>(fetcher: (() => Promise<T>) | null, deps: unknown[]): Load<T> {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [version, setVersion] = useState(0)
  const latest = useRef(0)
  useEffect(() => {
    if (!fetcher) { setData(null); setError(null); setLoading(false); return }
    const request = ++latest.current
    setLoading(true)
    setError(null)
    fetcher()
      .then((value) => { if (request === latest.current) setData(value) })
      .catch((reason) => { if (request === latest.current) { setData(null); setError(toApiClientError(reason).message) } })
      .finally(() => { if (request === latest.current) setLoading(false) })
  }, [...deps, version]) // `fetcher` is rebuilt each render; `deps` say when it really changes
  return { data, loading, error, reload: () => setVersion((v) => v + 1) }
}

/** The server's own message (e.g. no access to this class) — the cause is never guessed. */
export function LoadError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return <Alert type="error" showIcon message={message} action={<Button size="small" onClick={onRetry}>다시 시도</Button>} />
}
