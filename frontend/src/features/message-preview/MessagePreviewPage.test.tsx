import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiClientError } from '../../shared/api/ApiClientError'
import { createMessagePreview, fetchHealth } from './api'
import { MessagePreviewPage } from './MessagePreviewPage'

vi.mock('./api', () => ({
  createMessagePreview: vi.fn(),
  fetchHealth: vi.fn(),
}))

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(<QueryClientProvider client={client}><MessagePreviewPage /></QueryClientProvider>)
}

describe('MessagePreviewPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(fetchHealth).mockResolvedValue({ status: 'UP' })
    vi.mocked(createMessagePreview).mockResolvedValue({ message: '생성된 학습 안내 메시지' })
  })

  afterEach(() => cleanup())

  it('백엔드 상태와 메시지 생성 결과를 표시한다', async () => {
    const user = userEvent.setup()
    renderPage()

    expect(await screen.findByText('API UP')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '메시지 미리보기 생성' }))

    await waitFor(() => expect(createMessagePreview).toHaveBeenCalledOnce())
    expect(await screen.findByText('생성된 학습 안내 메시지')).toBeInTheDocument()
  })

  it('필수 입력값이 비어 있으면 API를 호출하지 않는다', async () => {
    const user = userEvent.setup()
    renderPage()

    const studentName = await screen.findByLabelText('학생 이름')
    await user.clear(studentName)
    await user.click(screen.getByRole('button', { name: '메시지 미리보기 생성' }))

    expect(await screen.findByText('학생 이름을 입력해주세요.')).toBeInTheDocument()
    expect(createMessagePreview).not.toHaveBeenCalled()
  })

  it('API 연결 실패를 사용자 메시지로 표시한다', async () => {
    vi.mocked(createMessagePreview).mockRejectedValue(
      new ApiClientError('백엔드 API에 연결할 수 없습니다. 서버 실행 상태를 확인해주세요.', 'NETWORK_ERROR'),
    )
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('button', { name: '메시지 미리보기 생성' }))

    expect(await screen.findByText('백엔드 API에 연결할 수 없습니다. 서버 실행 상태를 확인해주세요.')).toBeInTheDocument()
  })
})
