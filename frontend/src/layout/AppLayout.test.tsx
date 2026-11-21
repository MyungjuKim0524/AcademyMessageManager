import { cleanup, configure, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useAuth } from '../features/auth/AuthProvider'
import { AppLayout } from './AppLayout'

configure({ asyncUtilTimeout: 10000 })
vi.mock('../features/auth/AuthProvider', () => ({ useAuth: vi.fn() }))

const asRole = (role: 'ADMIN' | 'TEACHER' | 'ASSISTANT') => vi.mocked(useAuth).mockReturnValue({
  user: { id: 2, email: 'user@example.invalid', role }, loading: false, login: vi.fn(), logout: vi.fn(),
})

function Where() {
  const location = useLocation()
  return <div>{`화면: ${location.pathname}${location.search}`}</div>
}
const renderAt = (path: string) => render(
  <MemoryRouter initialEntries={[path]}>
    <Routes><Route path="/" element={<AppLayout />}><Route path="*" element={<Where />} /><Route index element={<Where />} /></Route></Routes>
  </MemoryRouter>,
)

describe('AppLayout navigation', () => {
  beforeEach(() => vi.clearAllMocks())

  it('groups the menu by job and shows ADMIN-only management to administrators', () => {
    asRole('ADMIN')
    renderAt('/')
    for (const text of ['홈', '학사 운영', '성적 안내', '데이터·시스템 관리', '대시보드', '엑셀 기반 성적 안내 메시지 생성', '출결·성적 분석', '직원·담당 반 배정']) {
      expect(screen.getByText(text)).toBeInTheDocument()
    }
    // The 성적 안내 sub-features are tabs inside that screen, not separate menu entries.
    for (const text of ['엑셀 업로드', '메시지 검토·발송', '누락·예외 생성', '메시지 처리 현황', '템플릿 관리']) {
      expect(screen.queryByText(text)).not.toBeInTheDocument()
    }
    expect(screen.queryByText(/발송 이력/)).not.toBeInTheDocument() // unimplemented placeholder removed
    expect(screen.queryByText('가져오기 이력')).not.toBeInTheDocument() // legacy CSV/XLSX import removed
    expect(screen.getByText('학생·반 관리')).toBeInTheDocument()
  })

  it('hides administrator menus from teachers and assistants', () => {
    asRole('ASSISTANT')
    renderAt('/')
    expect(screen.queryByText('데이터·시스템 관리')).not.toBeInTheDocument()
    expect(screen.queryByText('직원·담당 반 배정')).not.toBeInTheDocument()
    expect(screen.getByText('담당 반 학생')).toBeInTheDocument()
    expect(screen.getByText('user@example.invalid · 조교')).toBeInTheDocument()
  })

  it('opens the 성적 안내 workflow from one menu entry and keeps it highlighted on any tab', () => {
    asRole('TEACHER')
    renderAt('/')
    fireEvent.click(screen.getByText('엑셀 기반 성적 안내 메시지 생성'))
    expect(screen.getByText('화면: /notifications')).toBeInTheDocument()
    cleanup()
    renderAt('/notifications?tab=operations')
    expect(screen.getByText('엑셀 기반 성적 안내 메시지 생성').closest('li')).toHaveClass('ant-menu-item-selected')
  })
})
