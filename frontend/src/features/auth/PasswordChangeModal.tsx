import { Alert, Form, Input, Modal } from 'antd'
import { useState } from 'react'
import { ApiClientError } from '../../shared/api/ApiClientError'
import { changePassword } from './api'
import { MIN_PASSWORD } from './LoginPage'

/** SEC-10-A (Phase 11-4-B): change one's own password. Other devices are signed out. */
export function PasswordChangeModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [form] = Form.useForm()
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [done, setDone] = useState<number | null>(null)

  const close = () => {
    form.resetFields()
    setError('')
    setDone(null)
    onClose()
  }

  const submit = async (values: { current_password: string; new_password: string }) => {
    setSaving(true)
    setError('')
    try {
      const result = await changePassword(values.current_password, values.new_password)
      form.resetFields()
      setDone(result.other_sessions_revoked)
    } catch (reason) {
      setError(reason instanceof ApiClientError ? reason.message : '비밀번호를 변경하지 못했습니다.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      title="비밀번호 변경"
      open={open}
      onCancel={close}
      okText={done === null ? '변경' : '닫기'}
      cancelButtonProps={{ style: done === null ? undefined : { display: 'none' } }}
      confirmLoading={saving}
      onOk={() => (done === null ? form.submit() : close())}
      destroyOnHidden
    >
      {done !== null ? (
        <Alert
          type="success" showIcon title="비밀번호를 변경했습니다."
          description={done > 0 ? `다른 기기·브라우저의 로그인 ${done}건을 해제했습니다.` : '이 브라우저의 로그인은 그대로 유지됩니다.'}
        />
      ) : (
        <Form form={form} layout="vertical" onFinish={submit} requiredMark={false}>
          {error && <Alert type="error" title={error} showIcon style={{ marginBottom: 12 }} />}
          <Form.Item name="current_password" label="현재 비밀번호" rules={[{ required: true, message: '현재 비밀번호를 입력해주세요.' }]}>
            <Input.Password autoComplete="current-password" maxLength={1024} />
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
        </Form>
      )}
    </Modal>
  )
}
