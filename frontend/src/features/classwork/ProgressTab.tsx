import { useCallback, useEffect, useMemo, useState } from 'react'
import { Alert, Button, Card, Checkbox, Empty, Input, InputNumber, Modal, Radio, Select, Space, Table, Tag, Typography } from 'antd'
import { toApiClientError } from '../../shared/api/ApiClientError'
import * as api from './api'
import { ATTENDANCE, LessonStatusTag, canWriteAttendance, canWriteScores, shiftDay, todayLocal } from './common'
import type { ClassworkContext } from './ClassworkPage'
import { draftError, type ScoreDraft } from './scoreRules'

const GRADE_OPTIONS = [
  { label: 'A', value: 'A' }, { label: 'B', value: 'B' }, { label: 'C', value: 'C' }, { label: '미입력', value: '' },
]
const INELIGIBLE_BG = '#f5f5f5'

const shortDay = (day: string) => day.slice(5)

function columnTitle(column: api.ProgressColumn) {
  if (column.kind === 'ASSESSMENT') return `${shortDay(column.day)} 평가`
  return `${shortDay(column.day)}${(column.session_no ?? 1) > 1 ? ` ${column.session_no}교시` : ''}${column.exam_round ? ` (${column.exam_round})` : ''}`
}

const scoreValue = (score: api.ProgressScore | undefined) =>
  !score ? '-' : score.result_status === 'NOT_TAKEN' ? '미응시' : String(score.score)

type Target = { student: api.ProgressStudent; column: api.ProgressColumn; cell: api.ProgressCell }

/** Whether a cell can be opened for correction at all (permissions are checked per field). */
function cellOpenable(column: api.ProgressColumn, cell: api.ProgressCell, role?: string) {
  if (!cell.eligible || column.day > todayLocal()) return false
  if (column.kind === 'ASSESSMENT') return canWriteScores(role)
  return column.lesson_status !== 'CANCELLED' && canWriteAttendance(role)
}

/**
 * 학습 현황 — one day at a time, laid out like the academy workbook:
 * 학생 | 예습 과제 | 주간 과제 | one column per test (시험 종목). Clicking a cell opens the
 * correction window for that student and lesson (attendance is also editable there).
 */
export function ProgressTab({ classroomId, role, notify, fail, openStudent, active, focus }: ClassworkContext & { active: boolean }) {
  // A deep link (e.g. "성적 입력" from 성적 안내) opens the lesson day it is about.
  const [day, setDay] = useState(focus?.day ?? todayLocal())
  const [grid, setGrid] = useState<api.ClassProgress | null>(null)
  const [lessonKey, setLessonKey] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [target, setTarget] = useState<Target | null>(null)

  const load = useCallback(async () => {
    if (!day) return
    setLoading(true)
    try { setGrid(await api.getProgress(classroomId, day, day)) } catch (error) { setGrid(null); fail(error) } finally { setLoading(false) }
  }, [classroomId, day, fail])

  // Reload when the day changes and whenever the tab is shown again
  // (attendance may have been entered in the 출결 tab meanwhile).
  useEffect(() => { if (active) void load() }, [active, load])

  const lessonColumns = useMemo(() => (grid?.columns ?? []).filter((c) => c.kind === 'LESSON'), [grid])
  const testColumns = useMemo(() => (grid?.columns ?? []).filter((c) => c.kind === 'ASSESSMENT'), [grid])
  // Same-day sessions (2교시 …) are picked one at a time; default: the first one not cancelled.
  useEffect(() => {
    setLessonKey((current) => (lessonColumns.some((c) => c.key === current) ? current
      : (lessonColumns.find((c) => c.lesson_status !== 'CANCELLED') ?? lessonColumns[0])?.key ?? null))
  }, [lessonColumns])
  const lesson = lessonColumns.find((c) => c.key === lessonKey) ?? null
  const indexOf = useCallback((key: string) => (grid?.columns ?? []).findIndex((c) => c.key === key), [grid])

  const columns = useMemo(() => {
    const cellProps = (column: api.ProgressColumn) => (row: api.ProgressStudent) => {
      const cell = row.cells[indexOf(column.key)]
      const openable = cellOpenable(column, cell, role)
      return {
        style: { background: cell.eligible ? undefined : INELIGIBLE_BG, cursor: openable ? 'pointer' : undefined },
        onClick: openable ? () => setTarget({ student: row, column, cell }) : undefined,
        title: openable ? `${row.student_name} 기록 수정` : undefined,
      }
    }
    const show = (row: api.ProgressStudent, column: api.ProgressColumn, label: string, value: (cell: api.ProgressCell) => string) => {
      const cell = row.cells[indexOf(column.key)]
      const text = value(cell)
      if (!cell.eligible && text === '-') return <Typography.Text type="secondary">대상 아님</Typography.Text>
      return <span aria-label={`${row.student_name} ${label}`}>{text}</span>
    }
    const scoreColumn = (column: api.ProgressColumn, assessment: api.ProgressAssessment) => ({
      key: `${column.key}:${assessment.id}`,
      title: `${assessment.title} (${assessment.max_score})`,
      onCell: cellProps(column),
      render: (_: unknown, row: api.ProgressStudent) => show(row, column, assessment.title,
        (cell) => scoreValue(cell.scores.find((s) => s.assessment_id === assessment.id))),
    })
    return [
      {
        title: '학생',
        fixed: 'left' as const,
        width: 110,
        render: (_: unknown, row: api.ProgressStudent) => (
          <Space direction="vertical" size={0}>
            <Typography.Link onClick={() => openStudent(row.student_id)}>{row.student_name}</Typography.Link>
            {row.enrollment_status !== 'ACTIVE' && <Typography.Text type="secondary" style={{ fontSize: 12 }}>{row.enrollment_status === 'PAUSED' ? '휴원' : '퇴원'}</Typography.Text>}
          </Space>
        ),
      },
      ...(lesson ? [
        { key: 'prework', title: '예습 과제', onCell: cellProps(lesson), render: (_: unknown, row: api.ProgressStudent) => show(row, lesson, '예습 과제', (cell) => cell.prework_grade ?? '-') },
        { key: 'weekly', title: '주간 과제', onCell: cellProps(lesson), render: (_: unknown, row: api.ProgressStudent) => show(row, lesson, '주간 과제', (cell) => cell.weekly_grade ?? '-') },
        ...lesson.assessments.map((assessment) => scoreColumn(lesson, assessment)),
      ] : []),
      ...testColumns.map((column) => scoreColumn(column, column.assessments[0])),
    ]
  }, [lesson, testColumns, indexOf, role, openStudent])

  const nothing = grid !== null && lessonColumns.length === 0 && testColumns.length === 0
  return (
    <Card size="small">
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        <Space wrap>
          <Button onClick={() => setDay((d) => shiftDay(d, -1))}>◀ 전날</Button>
          <Input aria-label="조회일" type="date" value={day} onChange={(e) => e.target.value && setDay(e.target.value)} style={{ width: 160 }} />
          <Button onClick={() => setDay((d) => shiftDay(d, 1))}>다음날 ▶</Button>
          <Button onClick={() => setDay(todayLocal())}>오늘</Button>
          <Button loading={loading} onClick={() => void load()}>새로고침</Button>
          {lessonColumns.length > 1 && (
            <Select aria-label="교시 선택" style={{ width: 200 }} value={lessonKey ?? undefined} onChange={setLessonKey}
              options={lessonColumns.map((c) => ({ value: c.key, label: `${columnTitle(c)}${c.lesson_status === 'CANCELLED' ? ' [취소]' : ''}` }))} />
          )}
        </Space>
        {lesson && (
          <Space wrap>
            <Typography.Text strong>{`${day}${(lesson.session_no ?? 1) > 1 ? ` ${lesson.session_no}교시` : ''} 수업`}</Typography.Text>
            {lesson.topic && <Typography.Text>{lesson.topic}</Typography.Text>}
            {lesson.lesson_status && lesson.lesson_status !== 'COMPLETED' && <LessonStatusTag status={lesson.lesson_status} />}
          </Space>
        )}
        <Typography.Text type="secondary">
          칸을 누르면 그 학생의 과제 등급·시험 점수(출결 포함)를 고칠 수 있습니다. "-"는 미입력이며 0점이 아닙니다. 회색 칸은 휴원·수강 기간 밖입니다. 출결 현황은 '출결' 탭에서 확인하세요.
        </Typography.Text>
        {nothing ? <Empty description="이 날짜에는 수업이나 평가가 없습니다." /> : (
          <Table
            rowKey="enrollment_id"
            size="small"
            bordered
            loading={loading}
            dataSource={grid?.students ?? []}
            columns={columns}
            pagination={false}
            scroll={{ x: 'max-content' }}
            locale={{ emptyText: <Empty description="표시할 학생이 없습니다." /> }}
          />
        )}
      </Space>
      {target && (
        <RecordEditor
          key={`${target.student.enrollment_id}-${target.column.key}`}
          target={target}
          role={role}
          onClose={() => setTarget(null)}
          onSaved={async (text) => { setTarget(null); notify({ type: 'success', text }); await load() }}
        />
      )}
    </Card>
  )
}

function RecordEditor({ target, role, onClose, onSaved }: {
  target: Target; role?: string; onClose: () => void; onSaved: (text: string) => Promise<void>
}) {
  const { student, column, cell } = target
  const lesson = column.kind === 'LESSON'
  const attendanceWritable = lesson && canWriteAttendance(role)
  const gradesWritable = canWriteScores(role)
  const [attendance, setAttendance] = useState<api.AttendanceStatus | null>(cell.attendance_status)
  const [prework, setPrework] = useState<api.AssignmentGrade | null>(cell.prework_grade)
  const [weekly, setWeekly] = useState<api.AssignmentGrade | null>(cell.weekly_grade)
  const stored = (id: number) => cell.scores.find((s) => s.assessment_id === id)
  const [scores, setScores] = useState<Record<number, ScoreDraft>>(() => Object.fromEntries(column.assessments.map((a) => {
    const s = stored(a.id)
    return [a.id, { notTaken: s?.result_status === 'NOT_TAKEN', score: s?.result_status === 'SCORED' ? s.score : null, memo: s?.memo ?? '' }]
  })))
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  // Grade / score changes are confirmed once before saving (attendance alone is saved directly).
  const [confirmLines, setConfirmLines] = useState<string[] | null>(null)

  const scoreLabel = (draft: ScoreDraft | null, s?: api.ProgressScore) => {
    if (draft) return draft.notTaken ? '미응시' : draft.score === null ? '미입력' : String(draft.score)
    if (!s) return '미입력'
    return s.result_status === 'NOT_TAKEN' ? '미응시' : String(s.score)
  }
  const gradeChangeLines = () => [
    ...(lesson && prework !== cell.prework_grade ? [`예습 과제: ${cell.prework_grade ?? '미입력'} → ${prework ?? '미입력'}`] : []),
    ...(lesson && weekly !== cell.weekly_grade ? [`주간 과제: ${cell.weekly_grade ?? '미입력'} → ${weekly ?? '미입력'}`] : []),
    ...column.assessments.filter((a) => scoreChanged(a)).map((a) =>
      `${a.title}: ${scoreLabel(null, stored(a.id))} → ${scoreLabel(scores[a.id])}`),
  ]

  const scoreChanged = (a: api.ProgressAssessment) => {
    const draft = scores[a.id]
    const s = stored(a.id)
    if (!s) return draft.notTaken || draft.score !== null
    return (draft.notTaken ? 'NOT_TAKEN' : 'SCORED') !== s.result_status || (draft.notTaken ? null : draft.score) !== s.score
  }
  const scoreErrors = Object.fromEntries(column.assessments.flatMap((a) => {
    const message = scoreChanged(a) ? draftError(scores[a.id], stored(a.id) ?? null, a.max_score) : null
    return message ? [[a.id, message]] : []
  })) as Record<number, string>

  const requestSave = () => {
    setError(null)
    if (Object.keys(scoreErrors).length > 0) { setError('표시된 점수 오류를 먼저 고쳐주세요.'); return }
    const lines = gradeChangeLines()
    if (lines.length > 0) setConfirmLines(lines)
    else void save()
  }

  const save = async () => {
    setConfirmLines(null)
    const changedScores = column.assessments.filter(scoreChanged)
    setSaving(true)
    try {
      if (lesson) {
        const body: api.RecordUpdate = {}
        if (attendance !== cell.attendance_status && attendance !== null) body.attendance_status = attendance
        if (prework !== cell.prework_grade) body.prework_grade = prework
        if (weekly !== cell.weekly_grade) body.weekly_grade = weekly
        if (Object.keys(body).length > 0) body.result_version = cell.result_version
        if (changedScores.length > 0) {
          body.scores = changedScores.map((a) => ({
            assessment_id: a.id,
            result_status: scores[a.id].notTaken ? 'NOT_TAKEN' : 'SCORED',
            score: scores[a.id].notTaken ? null : scores[a.id].score,
            version: stored(a.id)?.version ?? null,
          }))
        }
        if (Object.keys(body).length === 0) { onClose(); return }
        if (!cell.attendance_status && !body.attendance_status && (body.prework_grade || body.weekly_grade)) {
          setError('출결을 먼저 선택해야 과제 등급을 기록할 수 있습니다.')
          return
        }
        await api.updateRecord(column.lesson_id!, student.enrollment_id, body)
      } else {
        const a = column.assessments[0]
        if (changedScores.length === 0) { onClose(); return }
        const draft = scores[a.id]
        await api.saveGrades(a.id, [{
          enrollment_id: student.enrollment_id,
          result_status: draft.notTaken ? 'NOT_TAKEN' : 'SCORED',
          score: draft.notTaken ? null : draft.score,
          memo: draft.memo.trim() || null,
          version: stored(a.id)?.version ?? null,
        }])
      }
      await onSaved(`${student.student_name} ${columnTitle(column)} 기록을 저장했습니다.`)
    } catch (reason) {
      const apiError = toApiClientError(reason)
      setError(`${apiError.message}${apiError.fields.length ? ` (${apiError.fields.map((f) => f.message).join(', ')})` : ''} 저장되지 않았습니다.`)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      open
      title={`${student.student_name} · ${columnTitle(column)}${column.topic ? ` · ${column.topic}` : ''}`}
      okText="저장"
      cancelText="닫기"
      confirmLoading={saving}
      onOk={requestSave}
      onCancel={onClose}
    >
      <Modal
        open={confirmLines !== null}
        title="과제·성적 데이터를 정말 변경할까요?"
        okText="변경"
        okButtonProps={{ danger: true }}
        cancelText="취소"
        onOk={() => void save()}
        onCancel={() => setConfirmLines(null)}
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          <Typography.Text strong>{`${student.student_name} · ${columnTitle(column)}`}</Typography.Text>
          <ul style={{ margin: 0, paddingLeft: 18 }}>{(confirmLines ?? []).map((line) => <li key={line}>{line}</li>)}</ul>
          <Typography.Text type="secondary">변경 이력이 남고, 이미 만든 안내 초안은 다시 생성해야 합니다.</Typography.Text>
        </Space>
      </Modal>
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        {error && <Alert type="error" showIcon message={error} />}
        {!gradesWritable && <Alert type="info" showIcon message="과제 등급·점수를 수정할 권한이 없습니다." />}
        {lesson && (
          <Space direction="vertical" size={4}>
            <Typography.Text strong>출결</Typography.Text>
            <Radio.Group
              aria-label="출결"
              optionType="button"
              disabled={!attendanceWritable || saving}
              value={attendance}
              onChange={(e) => setAttendance(e.target.value)}
              options={(Object.keys(ATTENDANCE) as api.AttendanceStatus[]).map((key) => ({ label: ATTENDANCE[key].label, value: key }))}
            />
            {cell.attendance_status === null && <Tag>미입력</Tag>}
          </Space>
        )}
        {lesson && (
          <Space wrap size="large">
            {([['예습 과제', prework, setPrework], ['주간 과제', weekly, setWeekly]] as const).map(([label, value, set]) => (
              <Space key={label} direction="vertical" size={4}>
                <Typography.Text strong>{label}</Typography.Text>
                <Radio.Group
                  aria-label={label}
                  optionType="button"
                  disabled={!gradesWritable || saving}
                  value={value ?? ''}
                  onChange={(e) => set(e.target.value === '' ? null : e.target.value)}
                  options={GRADE_OPTIONS}
                />
              </Space>
            ))}
          </Space>
        )}
        {column.assessments.length === 0 && lesson && <Typography.Text type="secondary">이 수업에 연결된 평가가 없습니다.</Typography.Text>}
        {column.assessments.map((a) => (
          <Space key={a.id} direction="vertical" size={2}>
            <Typography.Text strong>{`${a.title} (만점 ${a.max_score})`}</Typography.Text>
            <Space>
              <InputNumber
                aria-label={`${a.title} 점수`}
                min={0}
                step={0.5}
                disabled={!gradesWritable || saving || scores[a.id].notTaken}
                value={scores[a.id].notTaken ? null : scores[a.id].score}
                status={scoreErrors[a.id] ? 'error' : undefined}
                onChange={(value) => setScores((current) => ({ ...current, [a.id]: { ...current[a.id], score: value === null ? null : Number(value) } }))}
              />
              <Checkbox
                disabled={!gradesWritable || saving}
                checked={scores[a.id].notTaken}
                onChange={(e) => setScores((current) => ({ ...current, [a.id]: { ...current[a.id], notTaken: e.target.checked } }))}
              >
                미응시
              </Checkbox>
            </Space>
            {scoreErrors[a.id] && <Typography.Text type="danger">{scoreErrors[a.id]}</Typography.Text>}
          </Space>
        ))}
        <Typography.Text type="secondary">저장하면 변경 이력이 남고, 이미 만든 안내 초안은 '원본 변경'으로 확정이 막혀 다시 생성해야 합니다.</Typography.Text>
      </Space>
    </Modal>
  )
}
