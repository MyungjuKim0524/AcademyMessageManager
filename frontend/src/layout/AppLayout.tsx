import {
  BarChartOutlined, CalendarOutlined, CloudUploadOutlined, DashboardOutlined, HomeOutlined, TeamOutlined, UserSwitchOutlined,
} from '@ant-design/icons'
import { Button, Layout, Menu, Typography } from 'antd'
import type { MenuProps } from 'antd'
import { useState } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router'
import '../App.css'
import { useAuth } from '../features/auth/AuthProvider'
import { PasswordChangeModal } from '../features/auth/PasswordChangeModal'

const { Sider, Content } = Layout
const ROLE_LABEL: Record<string, string> = { ADMIN: '관리자', TEACHER: '선생님', ASSISTANT: '조교' }

/**
 * Phase 9.5: menu grouped by job, not by feature. Only implemented screens are listed (the
 * "발송 이력 · 준비 중" placeholder was removed). ADMIN-only groups follow the server RBAC.
 */
function menuItems(admin: boolean): MenuProps['items'] {
  return [
    { type: 'group', label: '홈', children: [{ key: '/', icon: <HomeOutlined />, label: '대시보드' }] },
    {
      type: 'group', label: '학사 운영', children: [
        { key: '/students', icon: <TeamOutlined />, label: admin ? '학생·반 관리' : '담당 반 학생' },
        { key: '/classes', icon: <CalendarOutlined />, label: '수업·출결·성적' },
        { key: '/analytics', icon: <BarChartOutlined />, label: '출결·성적 분석' },
      ],
    },
    // One entry for the whole workflow; 업로드·검토·누락·처리 현황·템플릿 are tabs inside it.
    {
      type: 'group', label: '성적 안내', children: [
        { key: '/notifications', icon: <CloudUploadOutlined />, label: '엑셀 기반 성적 안내 메시지 생성' },
      ],
    },
    ...(admin ? [{
      type: 'group' as const, label: '데이터·시스템 관리', children: [
        { key: '/staff', icon: <UserSwitchOutlined />, label: '직원·담당 반 배정' },
      ],
    }] : []),
  ]
}

function selectedKey(pathname: string) {
  return pathname === '/message-operations' ? '/notifications' : pathname
}

export function AppLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const { user, logout } = useAuth()
  const [passwordOpen, setPasswordOpen] = useState(false)
  return (
    <Layout className="app-layout">
      <Sider breakpoint="lg" collapsedWidth="0" theme="light" width={272} className="app-sider">
        <div className="brand">
          <Typography.Text strong><DashboardOutlined /> Academy LearningOps</Typography.Text>
          <small>{user?.display_name || user?.email} · {ROLE_LABEL[user?.role ?? ''] ?? user?.role}</small>
        </div>
        <Menu mode="inline" selectedKeys={[selectedKey(location.pathname)]} items={menuItems(user?.role === 'ADMIN')} onClick={({ key }) => navigate(key)} />
        <Button className="logout-button" type="text" onClick={() => setPasswordOpen(true)}>비밀번호 변경</Button>
        <Button className="logout-button" onClick={() => void logout().then(() => navigate('/login', { replace: true }))}>로그아웃</Button>
        <PasswordChangeModal open={passwordOpen} onClose={() => setPasswordOpen(false)} />
      </Sider>
      <Content className="app-content"><div className="page-container"><Outlet /></div></Content>
    </Layout>
  )
}
