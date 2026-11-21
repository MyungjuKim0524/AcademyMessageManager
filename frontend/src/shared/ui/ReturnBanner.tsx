import { Alert, Button } from 'antd'
import { RollbackOutlined } from '@ant-design/icons'
import { useNavigate, useSearchParams } from 'react-router'
import { safeReturnPath } from '../workingContext'

/** Shown when a screen was opened to fix something for another task (`?from=`). */
export function ReturnBanner() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const from = safeReturnPath(params.get('from'))
  if (!from) return null
  return (
    <Alert
      type="info"
      showIcon
      message="다른 작업에서 수정하러 왔습니다. 수정을 마치면 원래 작업으로 돌아가 다시 확인하세요."
      action={<Button size="small" type="primary" icon={<RollbackOutlined />} onClick={() => navigate(from)}>원래 작업으로 돌아가기</Button>}
    />
  )
}
