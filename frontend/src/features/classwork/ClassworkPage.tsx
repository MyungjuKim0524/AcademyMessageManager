import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Alert, Card, Empty, Select, Space, Spin, Tabs, Typography } from 'antd'
import { useSearchParams } from 'react-router'
import { toApiClientError } from '../../shared/api/ApiClientError'
import { pickClassroom, positiveId, rememberClassroom } from '../../shared/workingContext'
import { ReturnBanner } from '../../shared/ui/ReturnBanner'
import { useAuth } from '../auth/AuthProvider'
import * as api from './api'
import type { Notice } from './common'
import { AttendanceTab } from './AttendanceTab'
import { GradesTab } from './GradesTab'
import { LessonsTab } from './LessonsTab'
import { ProgressTab } from './ProgressTab'
import { StudentRecordsDrawer } from './StudentRecordsDrawer'
import { PageHeader } from '../../shared/ui/PageHeader'

export interface ClassworkContext {
  classroomId: number
  role: string | undefined
  lessons: api.LessonListItem[]
  lessonsLoading: boolean
  reloadLessons: () => Promise<void>
  notify: (notice: Notice) => void
  fail: (error: unknown) => void
  openStudent: (studentId: number) => void
  /** Deep link (`?lesson=` / `?day=`) from another screen; only for the classroom it was opened with. */
  focus?: { lessonId?: number; day?: string }
}

const TABS = ['attendance', 'progress', 'lessons', 'grades']
const DAY = /^\d{4}-\d{2}-\d{2}$/

/**
 * `/classes?classroom=&tab=&lesson=&day=&from=` — the classroom and tab are kept in the address
 * (replace, no extra history) so a link back here, or a bookmark, opens the same class and tab.
 */
export function ClassworkPage() {
  const { user } = useAuth()
  const [params, setParams] = useSearchParams()
  const [link] = useState(() => ({
    classroomId: positiveId(params.get('classroom')),
    tab: TABS.includes(params.get('tab') ?? '') ? params.get('tab')! : undefined,
    lessonId: positiveId(params.get('lesson')),
    day: DAY.test(params.get('day') ?? '') ? params.get('day')! : undefined,
  }))
  const [classrooms, setClassrooms] = useState<api.Classroom[]>([])
  const [classroomId, setClassroomId] = useState<number | null>(null)
  const [loaded, setLoaded] = useState(false)
  const [lessons, setLessons] = useState<api.LessonListItem[]>([])
  const [lessonsLoading, setLessonsLoading] = useState(false)
  const lessonsRequest = useRef(0)
  const [notice, setNotice] = useState<Notice>(null)
  const [studentId, setStudentId] = useState<number | null>(null)
  // Class-day workflow: attendance first (the front desk calls parents of late/absent
  // students), grades and scores later — so 출결 is the default tab.
  const [tab, setTab] = useState(link.tab ?? 'attendance')
  const [focus, setFocus] = useState<ClassworkContext['focus']>({ lessonId: link.lessonId, day: link.day })

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
      try {
        const items = await api.listClassrooms()
        setClassrooms(items)
        const picked = pickClassroom(items, link.classroomId)
        setClassroomId(picked)
        rememberClassroom(picked)
        // A link to a classroom this person cannot see is not followed; drop its lesson/day too.
        if (link.classroomId && picked !== link.classroomId) setFocus(undefined)
      } catch (error) {
        fail(error)
      } finally {
        setLoaded(true)
      }
    })()
  }, [fail, link])

  const reloadLessons = useCallback(async () => {
    if (classroomId === null) return
    const request = ++lessonsRequest.current
    setLessonsLoading(true)
    try {
      const items = await api.listLessons(classroomId)
      // A slower answer for the previously selected class must not replace this class's lessons.
      if (request === lessonsRequest.current) setLessons(items)
    } catch (error) {
      if (request === lessonsRequest.current) fail(error)
    } finally {
      if (request === lessonsRequest.current) setLessonsLoading(false)
    }
  }, [classroomId, fail])

  useEffect(() => {
    setLessons([])
    void reloadLessons()
  }, [reloadLessons])

  // Only this classroom's lessons ever reach the tabs, even for the render right after switching.
  const classLessons = useMemo(() => lessons.filter((row) => row.classroom_id === classroomId), [lessons, classroomId])

  const changeClassroom = (value: number) => {
    setNotice(null)
    setFocus(undefined)
    setLessons([])
    setClassroomId(value)
    rememberClassroom(value)
    writeLink({ classroom: String(value), lesson: null, day: null })
  }
  const changeTab = (value: string) => {
    setTab(value)
    writeLink({ tab: value })
  }

  if (!loaded) return <Spin description="담당 반을 불러오고 있습니다." />

  const context: ClassworkContext | null = classroomId === null ? null : {
    classroomId, role: user?.role, lessons: classLessons, lessonsLoading, reloadLessons, notify: setNotice, fail, openStudent: setStudentId, focus,
  }

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <PageHeader title="수업·출결·성적" description="수업 시작 때 출결을 먼저 기록하고, 과제·점수는 학습 현황에서 확인·수정합니다." />
      <ReturnBanner />
      {notice && <Alert type={notice.type} message={notice.text} showIcon closable onClose={() => setNotice(null)} />}
      {classrooms.length === 0 || context === null ? (
        <Card><Empty description={user?.role === 'ADMIN' ? '등록된 반이 없습니다. 학생·반 관리에서 반을 먼저 등록하세요.' : '담당 반이 없습니다. 관리자에게 반 배정을 요청하세요.'} /></Card>
      ) : (
        <>
          <Space wrap>
            <Typography.Text strong>반</Typography.Text>
            <Select
              aria-label="반 선택"
              style={{ width: 240 }}
              value={classroomId}
              options={classrooms.map((row) => ({ value: row.id, label: row.name }))}
              onChange={changeClassroom}
            />
          </Space>
          <Tabs
            key={classroomId}
            activeKey={tab}
            onChange={changeTab}
            items={[
              { key: 'attendance', label: '출결', children: <AttendanceTab {...context} /> },
              { key: 'progress', label: '학습 현황', children: <ProgressTab {...context} active={tab === 'progress'} /> },
              { key: 'lessons', label: '수업', children: <LessonsTab {...context} /> },
              { key: 'grades', label: '평가 관리', children: <GradesTab {...context} /> },
            ]}
          />
          <StudentRecordsDrawer classroomId={context.classroomId} studentId={studentId} onClose={() => setStudentId(null)} />
        </>
      )}
    </Space>
  )
}
