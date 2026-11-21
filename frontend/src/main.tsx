import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import 'antd/dist/reset.css'
import { AppProviders } from './app/AppProviders'
import { RouterProvider } from 'react-router/dom'
import { router } from './app/router'
import { AppErrorBoundary } from './app/AppErrorBoundary'
import './index.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AppErrorBoundary><AppProviders><RouterProvider router={router} /></AppProviders></AppErrorBoundary>
  </StrictMode>,
)
