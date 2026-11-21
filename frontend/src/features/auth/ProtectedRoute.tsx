import { Result, Spin } from 'antd'
import type { ReactNode } from 'react'
import { Navigate } from 'react-router'
import { useAuth } from './AuthProvider'
import type { StaffRole } from './types'

export function ProtectedRoute({ children, roles }: { children: ReactNode; roles?: StaffRole[] }) {
  const { user, loading } = useAuth()
  if (loading) return <div className="route-loading"><Spin description="인증 상태를 확인하고 있습니다." /></div>
  if (!user) return <Navigate to="/login" replace />
  if (roles && !roles.includes(user.role)) {
    return <Result status="403" title="접근 권한이 없습니다" subTitle="담당자에게 권한을 확인해주세요." />
  }
  return children
}
