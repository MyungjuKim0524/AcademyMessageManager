import { Alert, Button, Card, Form, Input, Typography } from 'antd'
import { useEffect, useState } from 'react'
import { Navigate, useNavigate } from 'react-router'
import { ApiClientError } from '../../shared/api/ApiClientError'
import { pingServer, waitForServer } from '../../shared/api/serverWake'
import { completePasswordReset } from './api'
import { useAuth } from './AuthProvider'

export const MIN_PASSWORD = 12
export const WAKING_NOTICE = '서버를 준비하는 중입니다. 서버가 쉬고 있었다면 30초~1분 정도 걸립니다.'
export const SERVER_DOWN_NOTICE = '서버가 아직 응답하지 않습니다. 잠시 후 다시 시도해주세요.'
export const SLOW_SERVER_NOTICE = '서버 응답이 늦어 요청을 처리하지 못했습니다. 잠시 후 다시 시도해주세요.'

/** unknown: not confirmed yet; waking: pinging a sleeping server; down: gave up waiting. */
type ServerState = 'unknown' | 'ready' | 'waking' | 'down'

export function LoginPage() {
  const { user, login, notice } = useAuth()
  const navigate = useNavigate()
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [resetting, setResetting] = useState(false)
  const [resetDone, setResetDone] = useState(false)
  const [server, setServer] = useState<ServerState>('unknown')

  // Start waking the (possibly sleeping) server while the user is still typing.
  useEffect(() => {
    let active = true
    void pingServer().then((up) => {
      if (!active) return
      if (up) { setServer('ready'); return }
      setServer('waking')
      void waitForServer().then((ok) => { if (active) setServer(ok ? 'ready' : 'down') })
    })
    return () => { active = false }
  }, [])

  if (user) return <Navigate to="/" replace />

  /** Waits for the server before a request that must not be retried (login, reset). */
  const ensureServer = async (): Promise<boolean> => {
    if (server === 'ready') return true
    setServer('waking')
    const ok = await waitForServer()
    setServer(ok ? 'ready' : 'down')
    return ok
  }

  /** A timeout on the real request: show why, and re-check the server before the next try. */
  const failureMessage = (reason: unknown, fallback: string): string => {
    if (!(reason instanceof ApiClientError)) return fallback
    if (reason.code === 'NETWORK_ERROR') {
      setServer('unknown')
      return SLOW_SERVER_NOTICE
    }
    return reason.message
  }

  const submit = async (values: { email: string; password: string }) => {
    setSubmitting(true)
    setError('')
    try {
      if (!(await ensureServer())) return
      await login(values.email, values.password)
      navigate('/', { replace: true })
    } catch (reason) {
      setError(failureMessage(reason, '로그인하지 못했습니다.'))
    } finally {
      setSubmitting(false)
    }
  }

  // SEC-10-B: a member who forgot the password gets a one-time code from an administrator (in
  // person) and sets a new password here. Nothing is sent by e-mail or text message.
  const reset = async (values: { email: string; code: string; new_password: string }) => {
    setSubmitting(true)
    setError('')
    try {
      if (!(await ensureServer())) return
      await completePasswordReset(values.email, values.code, values.new_password)
      setResetDone(true)
      setResetting(false)
    } catch (reason) {
      setError(failureMessage(reason, '비밀번호를 설정하지 못했습니다.'))
    } finally {
      setSubmitting(false)
    }
  }

  return <main className="login-shell">
    <Card className="login-card">
      <Typography.Title level={2}>{resetting ? '재설정 코드로 비밀번호 설정' : '직원 로그인'}</Typography.Title>
      <Typography.Paragraph type="secondary">
        {resetting ? '관리자에게 받은 일회용 재설정 코드(15분 유효)를 입력하세요.' : '관리자·교사·조교 계정만 사용할 수 있습니다.'}
      </Typography.Paragraph>
      {notice && !resetting && <Alert type="warning" title={notice} showIcon style={{ marginBottom: 12 }} />}
      {resetDone && !resetting && <Alert type="success" title="비밀번호를 설정했습니다. 새 비밀번호로 로그인하세요." showIcon style={{ marginBottom: 12 }} />}
      {server === 'waking' && <Alert type="info" title={WAKING_NOTICE} showIcon style={{ marginBottom: 12 }} />}
      {server === 'down' && <Alert type="warning" title={SERVER_DOWN_NOTICE} showIcon style={{ marginBottom: 12 }} />}
      {error && <Alert type="error" title={error} showIcon style={{ marginBottom: 12 }} />}
      {resetting ? (
        <Form layout="vertical" onFinish={reset} requiredMark={false}>
          <Form.Item name="email" label="이메일" rules={[{ required: true, type: 'email' }]}>
            <Input autoComplete="username" maxLength={255} />
          </Form.Item>
          <Form.Item name="code" label="재설정 코드" rules={[{ required: true, message: '재설정 코드를 입력해주세요.' }]}>
            <Input autoComplete="one-time-code" maxLength={32} placeholder="예: ABCDE-FGHJK" />
          </Form.Item>
          <Form.Item name="new_password" label="새 비밀번호" rules={[{ required: true, min: MIN_PASSWORD, message: `${MIN_PASSWORD}자 이상 입력해주세요.` }]}>
            <Input.Password autoComplete="new-password" maxLength={1024} />
          </Form.Item>
          <Form.Item
            name="confirm" label="새 비밀번호 확인" dependencies={['new_password']}
            rules={[{ required: true, message: '한 번 더 입력해주세요.' }, ({ getFieldValue }) => ({
              validator: (_, value) => (!value || value === getFieldValue('new_password') ? Promise.resolve() : Promise.reject(new Error('새 비밀번호가 서로 다릅니다.'))),
            })]}
          >
            <Input.Password autoComplete="new-password" maxLength={1024} />
          </Form.Item>
          <Button htmlType="submit" type="primary" loading={submitting} block>비밀번호 설정</Button>
          <Button type="link" block onClick={() => { setResetting(false); setError('') }}>로그인으로 돌아가기</Button>
        </Form>
      ) : (
        <Form layout="vertical" onFinish={submit} requiredMark={false}>
          <Form.Item name="email" label="이메일" rules={[{ required: true, type: 'email' }]}>
            <Input autoComplete="username" maxLength={255} />
          </Form.Item>
          <Form.Item name="password" label="비밀번호" rules={[{ required: true }]}>
            <Input.Password autoComplete="current-password" maxLength={1024} />
          </Form.Item>
          <Button htmlType="submit" type="primary" loading={submitting} block>로그인</Button>
          <Button type="link" block onClick={() => { setResetting(true); setResetDone(false); setError('') }}>
            비밀번호를 잊었나요? 재설정 코드로 설정
          </Button>
        </Form>
      )}
    </Card>
  </main>
}
