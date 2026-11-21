import { render,screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe,expect,it } from 'vitest'
import { ComingSoonPage } from './ComingSoonPage'
import { NotFoundPage } from './NotFoundPage'
describe('route states',()=>{it('shows coming soon state',()=>{render(<ComingSoonPage title="학생 관리"/>);expect(screen.getByText('현재 웹 전환 준비 중인 기능입니다.')).toBeInTheDocument()});it('shows 404 page',()=>{render(<MemoryRouter><NotFoundPage/></MemoryRouter>);expect(screen.getByText('요청한 페이지를 찾을 수 없습니다.')).toBeInTheDocument()})})
