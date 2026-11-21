import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Alert, Card, Empty, Select, Space, Spin, Tabs, Typography } from 'antd'
import { useSearchParams } from 'react-router'
import { toApiClientError } from '../../shared/api/ApiClientError'
import { pickClassroom, positiveId, rememberClassroom } from '../../shared/workingContext'
import { useAuth } from '../auth/AuthProvider'
import * as classwork from '../classwork/api'
import { MessageOperationsPage } from '../message-operations/MessageOperationsPage'
import { ComposeTab } from './ComposeTab'
import { ReviewTab } from './ReviewTab'
import { TemplatesTab } from './TemplatesTab'
import { UploadTab } from './UploadTab'
import { PageHeader } from '../../shared/ui/PageHeader'

export type Notice = { type: 'success' | 'error' | 'warning' | 'info'; text: string } | null

export interface NotificationContext {
  classroomId: number
  classroomName?: string
  role: string | undefined
  lessons: classwork.LessonListItem[]
  notify: (notice: Notice) => void
  fail: (error: unknown) => void
  openReview: () => void
  /** Switch to another 성적 안내 tab (e.g. 템플릿 from an upload result). */
  openTab: (tab: string) => void
  /** Open 누락·예외 생성 for a class and lesson (or lesson day, as the upload result only knows the date). */
  openCompose: (target: { classroomId?: number; lessonId?: number; day?: string }) => void
  /** Open one message in 검토·발송 (e.g. a student who already has a message). */
  openMessage: (notificationId: number) => void
  /** Deep link: lesson (or day) to compose for / message to open. */
  focus?: { lessonId?: number; notificationId?: number; day?: string }
}

const TABS = ['upload', 'review', 'compose', 'operations', 'templates']

/**
 * `/notifications?classroom=&tab=&lesson=&notification=`. Phase 9.6: the address is the source of
 * the tab and classroom, and the page writes them back (replace) — so the sidebar highlights the
 * tab really shown, a sidebar shortcut switches tabs without resetting the class or the work in
 * progress, and a return link brings back the same class and tab.
 */
export function NotificationsPage() {
  const { user } = useAuth()
  const [params, setParams] = useSearchParams()
  const [classrooms, setClassrooms] = useState<classwork.Classroom[]>([])
  const [lessons, setLessons] = useState<classwork.LessonListItem[]>([])
  const lessonsRequest = useRef(0)
  const [loaded, setLoaded] = useState(false)
  const [notice, setNotice] = useState<Notice>(null)
  const [reviewVersion, setReviewVersion] = useState(0)

  const wantedTab = params.get('tab')
  const tab = wantedTab && TABS.includes(wantedTab) ? wantedTab : 'upload'
  const linkedClassroom = positiveId(params.get('classroom'))
  const classroomId = loaded ? pickClassroom(classrooms, linkedClassroom) : null
  const lessonParam = params.get('lesson')
  const notificationParam = params.get('notification')
  const dayParam = params.get('day')
  const focus = useMemo<NotificationContext['focus']>(() => ({
    lessonId: positiveId(lessonParam),
    notificationId: positiveId(notificationParam),
    day: dayParam && /^\d{4}-\d{2}-\d{2}$/.test(dayParam) ? dayParam : undefined,
  }), [lessonParam, notificationParam, dayParam])

  const fail = useCallback((error: unknown) => setNotice({ type: 'error', text: toApiClientError(error).message }), [])

  const writeLink = useCallback((patch: Record<string, string | null>) => {
    setParams((current) => {
      const next = new URLSearchParams(current)
      for (const [name, value] of Object.entries(patch)) {
        if (value === null) next.delete(name)
        else next.set(name, value)
      }
      return next
    }, { replace: true })
  }, [setParams])

  useEffect(() => {
    void (async () => {
      try { setClassrooms(await classwork.listClassrooms()) } catch (error) { fail(error) } finally { setLoaded(true) }
    })()
  }, [fail])

  useEffect(() => { rememberClassroom(classroomId) }, [classroomId])

  useEffect(() => {
    if (classroomId === null) return
    const request = ++lessonsRequest.current
    setLessons([])
    classwork.listLessons(classroomId)
      .then((items) => { if (request === lessonsRequest.current) setLessons(items) })
      .catch((error) => { if (request === lessonsRequest.current) fail(error) })
  }, [classroomId, fail])

  // Only the selected class's lessons reach the tabs, even in the render right after switching.
  const classLessons = useMemo(() => lessons.filter((row) => row.classroom_id === classroomId), [lessons, classroomId])

  if (!loaded) return <Spin description="담당 반을 불러오고 있습니다." />
  const openTab = (value: string) => writeLink({ tab: value })
  const context: NotificationContext | null = classroomId === null ? null : {
    classroomId, classroomName: classrooms.find((row) => row.id === classroomId)?.name, role: user?.role, lessons: classLessons, notify: setNotice, fail, focus,
    openReview: () => { setReviewVersion((v) => v + 1); writeLink({ tab: 'review', notification: null }) },
    openTab,
    openCompose: ({ classroomId: target, lessonId, day }) => writeLink({
      tab: 'compose', classroom: target ? String(target) : String(classroomId), lesson: lessonId ? String(lessonId) : null, day: day ?? null, notification: null,
    }),
    openMessage: (id) => writeLink({ tab: 'review', notification: String(id), lesson: null, day: null }),
  }

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <PageHeader title="엑셀 기반 성적 안내 메시지 생성" description="엑셀 업로드로 초안을 만들고, 검토·확정 후 모의 발송하며, 처리 현황에서 남은 일을 확인합니다." />
      <Alert type="info" showIcon message="이 단계의 발송은 모의 발송입니다. 실제 문자·이메일은 전송되지 않습니다." />
      {notice && <Alert type={notice.type} message={notice.text} showIcon closable onClose={() => setNotice(null)} />}
      {context === null ? (
        <Card><Empty description={user?.role === 'ADMIN' ? '등록된 반이 없습니다.' : '담당 반이 없습니다. 관리자에게 반 배정을 요청하세요.'} /></Card>
      ) : (
        <>
          <Space wrap>
            <Typography.Text strong>반</Typography.Text>
            <Select aria-label="반 선택" style={{ width: 240 }} value={classroomId}
              options={classrooms.map((row) => ({ value: row.id, label: row.name }))}
              onChange={(value) => {
                setNotice(null)
                rememberClassroom(value)
                writeLink({ classroom: String(value), lesson: null, day: null, notification: null })
              }} />
          </Space>
          {/* Class-scoped tabs restart when the class changes. An upload covers several classes,
              so its preview/result survives a class switch (Phase 9.6: the result links each
              class to 누락·예외 생성). Templates are not class-scoped either. */}
          <Tabs
            activeKey={tab}
            onChange={openTab}
            items={[
              { key: 'upload', label: '엑셀 업로드', children: <UploadTab {...context} /> },
              { key: 'review', label: '검토·발송', children: <ReviewTab key={`${classroomId}-${reviewVersion}`} {...context} /> },
              { key: 'compose', label: '누락·예외 생성', children: <ComposeTab key={classroomId} {...context} /> },
              {
                key: 'operations',
                label: '메시지 처리 현황',
                children: (
                  <MessageOperationsPage embedded classroomId={classroomId}
                    onSelectClassroom={(id) => { rememberClassroom(id); writeLink({ classroom: String(id), lesson: null, day: null, notification: null }) }} />
                ),
              },
              { key: 'templates', label: '템플릿', children: <TemplatesTab {...context} /> },
            ]}
          />
        </>
      )}
    </Space>
  )
}
