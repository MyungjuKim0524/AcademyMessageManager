import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Alert, Button, Card, Empty, Input, Radio, Select, Space, Table, Tag, Typography } from 'antd'
import { toApiClientError } from '../../shared/api/ApiClientError'
import * as api from './api'
import { ATTENDANCE, AttendanceTag, LessonStatusTag, canWriteAttendance, lessonTitle, rowErrors, todayLocal } from './common'
import type { ClassworkContext } from './ClassworkPage'

type Draft = { status: api.AttendanceStatus | null; memo: string }

const lessonLabel = (lesson: api.Lesson) => `${lessonTitle(lesson)}${lesson.topic ? ` · ${lesson.topic}` : ''}`

function defaultLesson(lessons: api.LessonListItem[]) {
  const today = todayLocal()
  return lessons.find((row) => row.status !== 'CANCELLED' && row.lesson_date <= today) ?? lessons[0]
}

export function AttendanceTab({ classroomId, role, lessons, lessonsLoading, reloadLessons, notify, fail, openStudent, focus }: ClassworkContext) {
  // A deep link (dashboard "출결 입력", a fix link from 성적 안내) opens that lesson.
  const [lessonId, setLessonId] = useState<number | null>(focus?.lessonId ?? null)
  const rosterRequest = useRef(0)
  const [starting, setStarting] = useState(false)
  // Attendance is taken first at the start of class: when there is no lesson for today yet,
  // anyone who records attendance (assistants too) can create it with one click.
  const canStartToday = canWriteAttendance(role) && !lessonsLoading && !lessons.some((row) => row.lesson_date === todayLocal())
  const startToday = async () => {
    setStarting(true)
    try {
      const started = await api.startTodayLesson(classroomId)
      await reloadLessons()
      setLessonId(started.lesson.id)
      notify({ type: 'success', text: started.created ? `오늘(${started.lesson.lesson_date}) 수업을 시작했습니다. 출결을 입력하세요.` : '이미 등록된 오늘 수업을 열었습니다.' })
    } catch (error) { fail(error) } finally { setStarting(false) }
  }
  const startButton = canStartToday && (
    <Button type="primary" loading={starting} onClick={() => void startToday()}>오늘 수업 시작</Button>
  )
  const [roster, setRoster] = useState<api.AttendanceRoster | null>(null)
  const [drafts, setDrafts] = useState<Record<number, Draft>>({})
  const [errors, setErrors] = useState<Record<number, string[]>>({})
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (lessons.length === 0) return // still loading: keep a linked lesson until the list arrives
    if (lessonId === null || !lessons.some((row) => row.id === lessonId)) {
      // `?day=` (e.g. attendance mismatch from an upload): that day's first session, not cancelled.
      const onDay = focus?.day ? lessons.filter((row) => row.lesson_date === focus.day && row.status !== 'CANCELLED') : []
      const linked = onDay.find((row) => row.session_no === 1) ?? onDay[0]
      setLessonId((linked ?? defaultLesson(lessons))?.id ?? null)
    }
  }, [lessons, lessonId, focus?.day])

  const applyRoster = useCallback((data: api.AttendanceRoster) => {
    setRoster(data)
    setErrors({})
    // Unrecorded students are pre-selected as PRESENT on screen only. Nothing is stored until
    // the user saves, so "not entered" in the database never silently becomes "present".
    const recordable = canWriteAttendance(role) && data.lesson.status !== 'CANCELLED' && data.lesson.lesson_date <= todayLocal()
    setDrafts(Object.fromEntries(data.items.map((row) => [row.enrollment_id, {
      status: row.record?.status ?? (recordable && row.eligible ? 'PRESENT' : null),
      memo: row.record?.memo ?? '',
    }])))
  }, [role])

  const load = useCallback(async (id: number) => {
    // Only the last requested lesson is shown, so a slow answer for another lesson cannot be
    // edited and saved under the lesson now selected.
    const request = ++rosterRequest.current
    setLoading(true)
    try {
      const data = await api.getAttendance(id)
      if (request === rosterRequest.current) applyRoster(data)
    } catch (error) {
      if (request === rosterRequest.current) { setRoster(null); fail(error) }
    } finally {
      if (request === rosterRequest.current) setLoading(false)
    }
  }, [applyRoster, fail])

  // Load only a lesson of this classroom's list (a stale or foreign link id is never opened).
  const lessonKnown = lessonId !== null && lessons.some((row) => row.id === lessonId)
  useEffect(() => { if (lessonId !== null && lessonKnown) void load(lessonId) }, [lessonId, lessonKnown, load])

  const lesson = roster?.lesson
  const today = todayLocal()
  const blockedReason = !lesson ? null
    : lesson.status === 'CANCELLED' ? '취소된 수업에는 출결을 기록할 수 없습니다.'
    : lesson.lesson_date > today ? '아직 진행되지 않은 수업입니다. 수업일 이후에 출결을 기록하세요.'
    : !canWriteAttendance(role) ? '출결을 기록할 권한이 없습니다.' : null
  const editable = blockedReason === null

  const pending = useMemo(() => (roster?.items ?? []).filter((row) => {
    const draft = drafts[row.enrollment_id]
    if (!draft || draft.status === null || !row.eligible) return false
    return draft.status !== row.record?.status || (draft.memo.trim() || null) !== (row.record?.memo ?? null)
  }), [roster, drafts])
  const pendingIds = useMemo(() => new Set(pending.map((row) => row.enrollment_id)), [pending])

  const setDraft = (enrollmentId: number, patch: Partial<Draft>) =>
    setDrafts((current) => ({ ...current, [enrollmentId]: { ...current[enrollmentId], ...patch } }))

  const save = async () => {
    if (!lesson || pending.length === 0) return
    const items: api.AttendanceInput[] = pending.map((row) => ({
      enrollment_id: row.enrollment_id,
      status: drafts[row.enrollment_id].status as api.AttendanceStatus,
      memo: drafts[row.enrollment_id].memo.trim() || null,
      version: row.record?.version ?? null,
    }))
    setSaving(true)
    try {
      const saved = await api.saveAttendance(lesson.id, items)
      applyRoster(saved)
      notify({ type: 'success', text: `출결 ${saved.changed ?? items.length}건을 저장했습니다.` })
    } catch (error) {
      const apiError = toApiClientError(error)
      setErrors(rowErrors(apiError.fields, items))
      if (apiError.code === 'VERSION_CONFLICT' || apiError.code === 'ATTENDANCE_CONFLICT') {
        notify({ type: 'warning', text: `${apiError.message} 저장되지 않았습니다.` })
      } else {
        notify({ type: 'error', text: `${apiError.message} 저장되지 않았습니다.` })
      }
    } finally {
      setSaving(false)
    }
  }

  if (!lessonsLoading && lessons.length === 0) {
    return (
      <Card>
        <Empty description={canStartToday ? "등록된 수업이 없습니다. '오늘 수업 시작'을 누르면 오늘 수업이 만들어지고 바로 출결을 입력할 수 있습니다." : '등록된 수업이 없습니다.'}>
          {startButton}
        </Empty>
      </Card>
    )
  }

  const summary = roster?.summary
  return (
    <Card
      title="출결 입력"
      extra={
        <Space wrap>
          {startButton}
          <Select
            aria-label="수업 선택"
            style={{ width: 320 }}
            value={lessonId ?? undefined}
            loading={lessonsLoading}
            options={lessons.map((row) => ({ value: row.id, label: `${lessonLabel(row)}${row.status === 'CANCELLED' ? ' [취소]' : ''}` }))}
            onChange={(value) => setLessonId(value)}
          />
        </Space>
      }
    >
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        {lesson && (
          <Space wrap>
            <LessonStatusTag status={lesson.status} />
            <Typography.Text>{lessonLabel(lesson)}</Typography.Text>
            {summary && (
              <Typography.Text type="secondary">
                대상 {summary.eligible}명 · 기록 {summary.recorded}명 · <Typography.Text strong>미입력 {summary.unrecorded}명</Typography.Text> · 출석 {summary.present} · 지각 {summary.late} · 결석 {summary.absent} · 인정결석 {summary.excused}
              </Typography.Text>
            )}
          </Space>
        )}
        {blockedReason && <Alert type="info" showIcon message={blockedReason} />}
        {/* Phase 9.6: one line per student — the four choices never wrap (the table scrolls
            sideways on narrow screens instead), and "저장 안 됨" sits next to the stored record,
            which is kept because a pre-selected 출석 is not stored until saved. */}
        <Table
          rowKey="enrollment_id"
          size="middle"
          loading={loading}
          dataSource={roster?.items ?? []}
          pagination={false}
          scroll={{ x: 'max-content' }}
          rowClassName={(row) => (pendingIds.has(row.enrollment_id) ? 'row-pending' : '')}
          locale={{ emptyText: <Empty description="이 수업의 출결 대상 학생이 없습니다." /> }}
          columns={[
            {
              title: '학생',
              width: 140,
              render: (_, row) => (
                <Space direction="vertical" size={0}>
                  <Typography.Link onClick={() => openStudent(row.student_id)}>{row.student_name}</Typography.Link>
                  {!row.eligible && <Typography.Text type="secondary">수강 기간 아님 (기존 기록)</Typography.Text>}
                </Space>
              ),
            },
            {
              title: '저장된 기록',
              width: 170,
              className: 'cell-nowrap',
              render: (_, row) => (
                <Space size={4}>
                  <AttendanceTag status={row.record?.status ?? null} />
                  {pendingIds.has(row.enrollment_id) && <Tag color="warning">저장 안 됨</Tag>}
                </Space>
              ),
            },
            {
              title: '출결 입력',
              className: 'cell-nowrap',
              render: (_, row) => (
                <Radio.Group
                  aria-label={`${row.student_name} 출결`}
                  optionType="button"
                  buttonStyle="solid"
                  disabled={!editable || !row.eligible || saving}
                  value={drafts[row.enrollment_id]?.status ?? undefined}
                  onChange={(event) => setDraft(row.enrollment_id, { status: event.target.value })}
                  options={(['PRESENT', 'LATE', 'ABSENT', 'EXCUSED'] as const).map((value) => ({
                    value,
                    label: <span>{ATTENDANCE[value].icon} {ATTENDANCE[value].label}</span>,
                  }))}
                />
              ),
            },
            {
              title: '메모',
              onCell: () => ({ style: { minWidth: 200 } }),
              render: (_, row) => (
                <Space direction="vertical" size={0} style={{ width: '100%' }}>
                  <Input
                    aria-label={`${row.student_name} 메모`}
                    maxLength={500}
                    disabled={!editable || !row.eligible || saving}
                    value={drafts[row.enrollment_id]?.memo ?? ''}
                    onChange={(event) => setDraft(row.enrollment_id, { memo: event.target.value })}
                  />
                  {errors[row.enrollment_id]?.map((message) => <Typography.Text key={message} type="danger">{message}</Typography.Text>)}
                </Space>
              ),
            },
          ]}
        />
        {editable && (
          <Space wrap className="sticky-actions">
            {roster?.summary.unrecorded ? (
              <Typography.Text type="secondary">
                {`미입력 학생 ${roster.summary.unrecorded}명은 '출석'으로 미리 선택되어 있습니다. 지각·결석 학생만 바꾼 뒤 저장하세요. 저장하기 전에는 기록되지 않습니다.`}
              </Typography.Text>
            ) : null}
            <Button type="primary" loading={saving} disabled={pending.length === 0} onClick={() => void save()}>
              {`출결 저장 (${pending.length}건)`}
            </Button>
            {lessonId !== null && <Button disabled={saving} onClick={() => void load(lessonId)}>새로고침</Button>}
          </Space>
        )}
      </Space>
    </Card>
  )
}
