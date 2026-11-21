import { lazy, Suspense, type ReactNode } from 'react'
import { createBrowserRouter, Navigate, useLocation } from 'react-router'
import { Spin } from 'antd'
import { AppLayout } from '../layout/AppLayout'
import { ComingSoonPage } from '../pages/ComingSoonPage'
import { NotFoundPage } from '../pages/NotFoundPage'
import { LoginPage } from '../features/auth/LoginPage'
import { ProtectedRoute } from '../features/auth/ProtectedRoute'

const DashboardPage=lazy(()=>import('../features/dashboard/DashboardPage').then(m=>({default:m.DashboardPage})))
const MessagePreviewPage=lazy(()=>import('../features/message-preview/MessagePreviewPage').then(m=>({default:m.MessagePreviewPage})))
const LearningOpsPage=lazy(()=>import('../features/learningops/LearningOpsPage').then(m=>({default:m.LearningOpsPage})))
const StaffManagementPage=lazy(()=>import('../features/staff/StaffManagementPage').then(m=>({default:m.StaffManagementPage})))
const NotificationsPage=lazy(()=>import('../features/notifications/NotificationsPage').then(m=>({default:m.NotificationsPage})))
const AnalyticsPage=lazy(()=>import('../features/analytics/AnalyticsPage').then(m=>({default:m.AnalyticsPage})))
const ClassworkPage=lazy(()=>import('../features/classwork/ClassworkPage').then(m=>({default:m.ClassworkPage})))
const loading=<div className="route-loading"><Spin description="화면을 불러오고 있습니다." /></div>
const suspend=(node:ReactNode)=><Suspense fallback={loading}>{node}</Suspense>

/** 메시지 처리 현황 is now a tab of 성적 안내; old links and bookmarks (incl. `?status=`) still work. */
function MessageOperationsRedirect(){const location=useLocation();const params=new URLSearchParams(location.search);params.set('tab','operations');return <Navigate replace to={`/notifications?${params}`}/>}

export const router=createBrowserRouter([
 {path:'/login',element:<LoginPage/>},
 {path:'/',element:<ProtectedRoute><AppLayout/></ProtectedRoute>,children:[
  {index:true,element:suspend(<DashboardPage/>)},
  {path:'messages/preview',element:suspend(<MessagePreviewPage/>)},
  {path:'students',element:suspend(<LearningOpsPage/>)},
  {path:'staff',element:<ProtectedRoute roles={['ADMIN']}>{suspend(<StaffManagementPage/>)}</ProtectedRoute>},
  {path:'classes',element:suspend(<ClassworkPage/>)},
  {path:'analytics',element:suspend(<AnalyticsPage/>)},
  {path:'notifications',element:suspend(<NotificationsPage/>)},
  {path:'message-operations',element:<MessageOperationsRedirect/>},
  {path:'deliveries',element:<ComingSoonPage title="발송 이력"/>},
  {path:'*',element:<NotFoundPage/>},
]}])
