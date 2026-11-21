import { useCallback, useEffect, useState } from 'react'
import { Alert, Button, Card, Empty, Input, Select, Space, Spin, Tabs, Typography } from 'antd'
import { useSearchParams } from 'react-router'
import { toApiClientError } from '../../shared/api/ApiClientError'
import { shiftDay, todayLocal } from '../../shared/date'
import { PageHeader } from '../../shared/ui/PageHeader'
import { pickClassroom, positiveId, rememberClassroom } from '../../shared/workingContext'
import { useAuth } from '../auth/AuthProvider'
import * as classwork from '../classwork/api'
import { AttendancePanel } from './AttendancePanel'
import { GradesPanel } from './GradesPanel'

const DAY = /^\d{4}-\d{2}-\d{2}$/
const MAX_DAYS = 366

export type Period = { classroomId: number; dateFrom: string; dateTo: string }

/**
 * 출결·성적 분석 — `/analytics?tab=attendance|grades&classroom&from&to&student&assessment`.
 * The filters live in the address (replace), so a link or a return keeps the same view; the
 * class follows the working classroom of the other screens.
 */
export function AnalyticsPage() {
  const { user } = useAuth()
  const [params, setParams] = useSearchParams()
  const [classrooms, setClassrooms] = useState<classwork.Classroom[]>([])
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const today = todayLocal()
  const tab = params.get('tab') === 'grades' ? 'grades' : 'attendance'
  const dateFrom = DAY.test(params.get('from') ?? '') ? params.get('from')! : shiftDay(today, -27)
  const dateTo = DAY.test(params.get('to') ?? '') ? params.get('to')! : today
  const classroomId = loaded ? pickClassroom(classrooms, positiveId(params.get('classroom'))) : null
  const studentId = positiveId(params.get('student')) ?? null
  const assessmentId = positiveId(params.get('assessment')) ?? null

  const write = useCallback((patch: Record<string, string | null>) => {
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
    classwork.listClassrooms()
      .then(setClassrooms)
      .catch((reason) => setError(toApiClientError(reason).message))
      .finally(() => setLoaded(true))
  }, [])
  useEffect(() => { rememberClassroom(classroomId) }, [classroomId])

  const days = (Date.parse(dateTo) - Date.parse(dateFrom)) / 86_400_000
  const periodProblem = Number.isNaN(days) ? '조회 기간을 입력하세요.'
    : days < 0 ? '시작일이 종료일보다 늦습니다. 기간을 고쳐주세요.'
    : days >= MAX_DAYS ? '한 번에 최대 1년까지 조회할 수 있습니다.' : null
  const period: Period | null = classroomId !== null && !periodProblem ? { classroomId, dateFrom, dateTo } : null
  const setRange = (from: string, to: string) => write({ from, to, student: null, assessment: null })

  if (!loaded) return <Spin description="담당 반을 불러오고 있습니다." />

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <PageHeader title="출결·성적 분석" description="반과 기간을 골라 출결 기록 상태와 평가 결과를 확인하고, 빠진 기록은 입력 화면으로 바로 이동합니다." />
      {error && <Alert type="error" showIcon message={error} />}
      {classrooms.length === 0 ? (
        <Card><Empty description={user?.role === 'ADMIN' ? '등록된 반이 없습니다. 학생·반 관리에서 반을 먼저 등록하세요.' : '담당 반이 없습니다. 관리자에게 반 배정을 요청하세요.'} /></Card>
      ) : (
        <>
          <Card size="small">
            <Space wrap size="middle">
              <Space>
                <Typography.Text strong>반</Typography.Text>
                <Select aria-label="반 선택" style={{ width: 220 }} value={classroomId ?? undefined}
                  options={classrooms.map((row) => ({ value: row.id, label: row.name }))}
                  onChange={(value) => { rememberClassroom(value); write({ classroom: String(value), student: null, assessment: null }) }} />
              </Space>
              <Space wrap>
                <Typography.Text strong>기간</Typography.Text>
                <Input aria-label="시작일" type="date" value={dateFrom} style={{ width: 150 }}
                  onChange={(e) => e.target.value && setRange(e.target.value, dateTo)} />
                <span>~</span>
                <Input aria-label="종료일" type="date" value={dateTo} style={{ width: 150 }}
                  onChange={(e) => e.target.value && setRange(dateFrom, e.target.value)} />
                <Button onClick={() => setRange(shiftDay(today, -27), today)}>최근 4주</Button>
                <Button onClick={() => setRange(shiftDay(today, -90), today)}>최근 3개월</Button>
              </Space>
            </Space>
          </Card>
          {periodProblem && <Alert type="warning" showIcon message={periodProblem} />}
          <Tabs
            activeKey={tab}
            onChange={(key) => write({ tab: key })}
            items={[
              {
                key: 'attendance', label: '출결 분석',
                children: period && <AttendancePanel key={`${period.classroomId}`} period={period} studentId={studentId}
                  onStudent={(id) => write({ student: id ? String(id) : null })} />,
              },
              {
                key: 'grades', label: '성적 분석',
                children: period && <GradesPanel key={`${period.classroomId}`} period={period} studentId={studentId} assessmentId={assessmentId}
                  onStudent={(id) => write({ student: id ? String(id) : null })}
                  onAssessment={(id) => write({ assessment: id ? String(id) : null })} />,
              },
            ]}
          />
        </>
      )}
    </Space>
  )
}
