import { QueryClientProvider } from '@tanstack/react-query'
import { App as AntApp, ConfigProvider } from 'antd'
import type { PropsWithChildren } from 'react'
import { createQueryClient } from './queryClient'
import { AuthProvider } from '../features/auth/AuthProvider'

const queryClient = createQueryClient()

export function AppProviders({ children }: PropsWithChildren) {
  return (
    <ConfigProvider
      theme={{
        token: {
          colorPrimary: '#2557a7',
          borderRadius: 8,
          colorBgLayout: '#f4f6fa',
          fontFamily: "Pretendard, 'Noto Sans KR', system-ui, sans-serif",
        },
      }}
    >
      <AntApp>
        <QueryClientProvider client={queryClient}><AuthProvider>{children}</AuthProvider></QueryClientProvider>
      </AntApp>
    </ConfigProvider>
  )
}
