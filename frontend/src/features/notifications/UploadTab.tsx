import { useMemo, useState } from 'react'
import { Alert, Button, Card, Checkbox, Col, Descriptions, Empty, Input, Modal, Popconfirm, Row, Space, Statistic, Steps, Table, Tag, Typography } from 'antd'
import { CheckCircleOutlined, ExclamationCircleFilled, FilterOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router'
import { toApiClientError } from '../../shared/api/ApiClientError'
import { withReturn } from '../../shared/workingContext'
import { todayLocal } from '../classwork/common'
import type { NotificationContext } from './NotificationsPage'
import * as upload from './uploadApi'

const ATTENDANCE: Record<string, string> = { PRESENT: '출석', LATE: '지각', ABSENT: '결석', EXCUSED: '인정결석' }
const EXCLUDE_TEXT = '오류로 간주해 해당 행은 성적 안내 메시지를 생성하지 않겠습니다.'
// Colour is never the only signal: every state also has a text tag.
const ROW_BG: Record<string, string> = { UNREGISTERED: '#fff1f0', INVALID: '#fff1f0', MISMATCH: '#fffbe6' }
/** Server reason (notifications/service.py) when a student already has a message for the lesson and
 *  template: on a re-upload this is duplicate prevention working, not a failure. Only a note whose
 *  sole reason is this one is counted as "기존 초안 있음"; anything else stays a failure. */
const EXISTING_REASON = '이미 이 수업·템플릿의 메시지가 있습니다'
const NO_TEMPLATE = '기본 템플릿이 없습니다'

type Step = 'new' | 'returning'
/** What the user has to do with a row: nothing / decide or check / fix the workbook / nothing (left out). */
type Group = 'ok' | 'check' | 'error' | 'excluded'

const GROUPS: { key: Group; label: string; hint: string; color?: string }[] = [
  { key: 'ok', label: '정상 처리 가능', hint: '저장·초안 생성 대상' },
  { key: 'check', label: '확인 필요', hint: '미등록 학생 결정 · 출결 다름 · 앱에서 고친 점수·등급이 엑셀 값으로 바뀜', color: '#d48806' },
  { key: 'error', label: '오류', hint: '엑셀을 고친 뒤 다시 미리보기', color: '#cf1322' },
  { key: 'excluded', label: '처리 제외', hint: '메모 행 · 제외로 결정한 미등록 학생' },
]

function groupOf(row: upload.UploadRow, decision: upload.Decision | undefined): Group {
  if (row.status === 'INVALID' || row.issues.length > 0) return 'error'
  if (row.status === 'SKIPPED') return 'excluded'
  if (row.status === 'UNREGISTERED') return !decision ? 'check' : decision === 'EXCLUDE' ? 'excluded' : 'ok'
  return row.attendance_mismatch || (row.app_changes?.length ?? 0) > 0 ? 'check' : 'ok'
}

/** "어휘 9 → 8" — the app value the workbook will replace (shown before confirming). */
const changeText = (change: upload.AppChange) => `${change.label}: 앱 ${change.app} → 엑셀 ${change.upload}`

function StatusTag({ row }: { row: upload.UploadRow }) {
  if (row.status === 'MATCHED') {
    if (row.attendance_mismatch) return <Tag color="gold">출결 불일치</Tag>
    // Same values as the app: confirming skips the row (no save, no audit record).
    return row.unchanged ? <Tag>변경 없음</Tag> : <Tag color="green">등록 학생</Tag>
  }
  if (row.status === 'UNREGISTERED') return <Tag color="red">미등록 학생</Tag>
  if (row.status === 'INVALID') return <Tag color="red">오류</Tag>
  return <Tag>건너뜀</Tag>
}

/** Draft notes split into real failures and students who already had a message. */
function splitDrafts(result: upload.UploadResult) {
  return result.drafts.map((d) => ({
    ...d,
    failed: d.skipped.filter((note) => !note.endsWith(`: ${EXISTING_REASON}`)),
    existing: d.skipped.filter((note) => note.endsWith(`: ${EXISTING_REASON}`)),
  }))
}

export function UploadTab({ notify, fail, openReview, openTab, openCompose }: NotificationContext) {
  const navigate = useNavigate()
  const [lessonDate, setLessonDate] = useState(todayLocal())
  const [file, setFile] = useState<File | null>(null)
  // Time-slot sheets of the chosen file; only the selected ones are previewed and saved.
  const [sheetOptions, setSheetOptions] = useState<upload.SheetSummary[] | null>(null)
  const [selectedSheets, setSelectedSheets] = useState<string[]>([])
  const [sheetsLoading, setSheetsLoading] = useState(false)
  const [preview, setPreview] = useState<upload.UploadPreview | null>(null)
  const [decisions, setDecisions] = useState<Record<string, upload.Decision>>({})
  const [steps, setSteps] = useState<Record<string, Step>>({})
  const [result, setResult] = useState<upload.UploadResult | null>(null)
  // Class name → classroom id of the confirmed file, so result items can link to that class.
  const [classIds, setClassIds] = useState<Record<string, number>>({})
  const [busy, setBusy] = useState(false)
  // Red pop-up after confirming when some students got no draft (missing e-mail, mismatch, …).
  const [missedOpen, setMissedOpen] = useState(false)
  // Why the last confirm failed; `unknown` = no server answer, so whether it was saved is unknown.
  const [confirmError, setConfirmError] = useState<{ message: string; unknown: boolean } | null>(null)
  const [inputKey, setInputKey] = useState(0)
  // Step 1 folds into a one-line summary once a preview or result is shown.
  const [fileOpen, setFileOpen] = useState(false)
  const [view, setView] = useState<Group | 'all'>('all')

  const rows = useMemo(() => (preview?.blocks ?? []).flatMap((b) => b.rows.map((row) => ({ block: b, row }))), [preview])
  const unregistered = useMemo(() => rows.filter(({ row }) => row.status === 'UNREGISTERED').map(({ row }) => row), [rows])
  const undecided = unregistered.filter((row) => !decisions[row.key])
  const reset = () => { setPreview(null); setDecisions({}); setSteps({}); setResult(null); setConfirmError(null); setView('all') }

  // Step 2 detail figures: counted from the preview the server returned (nothing is invented here).
  const counts = useMemo(() => ({
    total: rows.filter(({ row }) => row.status !== 'SKIPPED').length,
    matched: rows.filter(({ row }) => row.status === 'MATCHED').length,
    unregistered: unregistered.length,
    invalid: rows.filter(({ row }) => row.status === 'INVALID').length,
    skipped: rows.filter(({ row }) => row.status === 'SKIPPED').length,
    mismatch: rows.filter(({ row }) => row.attendance_mismatch).length,
    replaced: rows.reduce((sum, { row }) => sum + (row.app_changes?.length ?? 0), 0),
    unchanged: rows.filter(({ row }) => row.status === 'MATCHED' && row.unchanged).length,
  }), [rows, unregistered])
  // Step 2 headline: the same rows grouped by what the user has to do (follows the decisions).
  const groups = useMemo(() => {
    const total: Record<Group, number> = { ok: 0, check: 0, error: 0, excluded: 0 }
    for (const { row } of rows) total[groupOf(row, decisions[row.key])] += 1
    return total
  }, [rows, decisions])
  const problems = useMemo(() => rows.filter(({ row }) => row.issues.length > 0), [rows])
  // Step 3: what confirming will write, from the preview plus the decisions made above.
  const impact = useMemo(() => {
    const decided = Object.values(decisions)
    const included = counts.matched + decided.filter((d) => d !== 'EXCLUDE').length
    return {
      saved: included - counts.unchanged,
      newStudents: decided.filter((d) => d === 'NEW').length,
      returning: decided.filter((d) => d === 'RETURNING').length,
      excluded: decided.filter((d) => d === 'EXCLUDE').length,
      classes: (preview?.blocks ?? []).filter((b) => b.rows.some((r) => r.status === 'MATCHED' || r.status === 'UNREGISTERED')).map((b) => b.class_name),
    }
  }, [decisions, counts, preview])
  const current = result ? 3 : !preview ? 0 : !preview.can_confirm || undecided.length > 0 ? 1 : 2
  const drafts = useMemo(() => (result ? splitDrafts(result) : []), [result])
  const draftTotals = useMemo(() => ({
    created: drafts.reduce((sum, d) => sum + d.created, 0),
    failed: drafts.reduce((sum, d) => sum + d.failed.length, 0),
    existing: drafts.reduce((sum, d) => sum + d.existing.length, 0),
    mismatch: result?.attendance_mismatches.length ?? 0,
  }), [drafts, result])

  const chooseFile = async (next: File | null) => {
    setFile(next)
    reset()
    setSheetOptions(null)
    setSelectedSheets([])
    if (!next) return
    setSheetsLoading(true)
    try {
      const sheets = await upload.listSheets(next)
      setSheetOptions(sheets)
      // A file with one time slot (e.g. one class) has nothing to choose; otherwise the user picks.
      setSelectedSheets(sheets.length === 1 ? [sheets[0].name] : [])
    } catch (error) { fail(error) } finally { setSheetsLoading(false) }
  }

  const runPreview = async () => {
    if (!file || selectedSheets.length === 0) return
    setBusy(true)
    reset()
    setFileOpen(false)
    try { setPreview(await upload.previewUpload(file, lessonDate, selectedSheets)) } catch (error) { fail(error) } finally { setBusy(false) }
  }

  const confirm = async () => {
    if (!file || !preview || busy) return
    setBusy(true)
    setConfirmError(null)
    try {
      // Changing the sheet choice clears the preview, so this is the selection that was previewed.
      const saved = await upload.confirmUpload(file, lessonDate, decisions, selectedSheets)
      setClassIds(Object.fromEntries(preview.blocks.filter((b) => b.classroom_id).map((b) => [b.class_name, b.classroom_id!])))
      setResult(saved)
      setPreview(null)
      const parts = splitDrafts(saved)
      const created = saved.drafts.reduce((sum, d) => sum + d.created, 0)
      const missed = parts.reduce((sum, d) => sum + d.failed.length, 0) + saved.attendance_mismatches.length
      const existing = parts.reduce((sum, d) => sum + d.existing.length, 0)
      const already = existing ? ` 이미 초안이 있는 학생 ${existing}명은 새로 만들지 않았습니다(중복 방지).` : ''
      const same = saved.unchanged_rows ? ` · 변경 없음 ${saved.unchanged_rows}명(기록 생략)` : ''
      if (missed > 0) {
        // The data itself was saved: a warning, not an error, with the drafts that need attention.
        notify({ type: 'warning', text: `저장 ${saved.saved_rows}명${same} · 안내 초안 ${created}건을 만들었습니다. 초안을 만들지 못한 항목 ${missed}건이 있습니다 — 사유를 확인하세요.${already}` })
        setMissedOpen(true)
      } else {
        notify({ type: 'success', text: `저장 ${saved.saved_rows}명${same} · 안내 초안 ${created}건을 만들었습니다.${already} '검토·발송'에서 확인하세요.` })
      }
    } catch (error) {
      const apiError = toApiClientError(error)
      notify({ type: 'error', text: apiError.message })
      setConfirmError({ message: apiError.message, unknown: apiError.code === 'NETWORK_ERROR' || apiError.code === 'CLIENT_ERROR' })
    } finally {
      setBusy(false)
    }
  }

  const decide = (key: string, decision: upload.Decision | undefined, step?: Step) => {
    setDecisions((current) => {
      const next = { ...current }
      if (decision) next[key] = decision
      else delete next[key]
      return next
    })
    setSteps((current) => ({ ...current, [key]: step ?? 'new' }))
  }

  const decisionCell = (row: upload.UploadRow) => {
    if (row.status !== 'UNREGISTERED') return null
    const decided = decisions[row.key]
    if (decided) {
      const label = { NEW: '신규 수강생으로 등록', RETURNING: '복귀 처리 (휴원 → 재원)', EXCLUDE: '제외' }[decided]
      return (
        <Space direction="vertical" size={2}>
          <Tag color={decided === 'EXCLUDE' ? 'default' : 'blue'}>{label}</Tag>
          {decided === 'EXCLUDE' && <Typography.Text type="danger">{EXCLUDE_TEXT}</Typography.Text>}
          <Button size="small" onClick={() => decide(row.key, undefined)}>다시 선택</Button>
        </Space>
      )
    }
    if ((steps[row.key] ?? 'new') === 'new') {
      return (
        <Space direction="vertical" size={2}>
          <Space wrap>
            <Typography.Text strong>신규 수강생인가요?</Typography.Text>
            <Button size="small" type="primary" disabled={row.existing_student_conflict} onClick={() => decide(row.key, 'NEW')}>예</Button>
            <Button size="small" onClick={() => setSteps((current) => ({ ...current, [row.key]: 'returning' }))}>아니요</Button>
          </Space>
          {row.existing_student_conflict && <Typography.Text type="secondary">같은 이름의 학생이 이미 등록되어 있어 신규로 등록할 수 없습니다. 관리자에게 수강 등록을 요청하세요.</Typography.Text>}
        </Space>
      )
    }
    return (
      <Space direction="vertical" size={2}>
        <Space wrap>
          <Typography.Text strong>복귀 학생인가요?</Typography.Text>
          <Button size="small" type="primary" disabled={!row.returning_available} onClick={() => decide(row.key, 'RETURNING', 'returning')}>예</Button>
          <Button size="small" onClick={() => decide(row.key, 'EXCLUDE', 'returning')}>아니요</Button>
        </Space>
        {!row.returning_available && <Typography.Text type="secondary">이 반에 휴원 중인 같은 이름의 학생이 없어 복귀로 처리할 수 없습니다.</Typography.Text>}
      </Space>
    )
  }

  const shown = (row: upload.UploadRow) => view === 'all' || groupOf(row, decisions[row.key]) === view
  const fileFolded = (preview !== null || result !== null) && !fileOpen
  // Classes of the result that had attendance mismatches (strings are "<class name> <row key>").
  const mismatchClasses = result
    ? Object.keys(classIds).filter((name) => result.attendance_mismatches.some((m) => m.startsWith(`${name} `)))
    : []
  const fixAttendance = (name: string) => navigate(withReturn(
    `/classes?classroom=${classIds[name]}&tab=attendance&day=${result!.lesson_date}`,
    `/notifications?classroom=${classIds[name]}&tab=compose&day=${result!.lesson_date}`,
  ))

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <Steps
        size="small"
        current={current}
        items={[
          { title: '파일 선택', description: '수업일·엑셀' },
          { title: '데이터 검증', description: '저장 안 함' },
          { title: '변경 확인', description: '명시적 확정' },
          { title: '처리 완료', description: '결과·다음 작업' },
        ]}
      />
      {fileFolded ? (
        <Card title="1. 파일 선택" size="small" extra={<Button size="small" onClick={() => setFileOpen(true)}>파일·수업일 바꾸기</Button>}>
          <Descriptions size="small" column={{ xs: 1, sm: 2, lg: 4 }} items={[
            { key: 'n', label: '파일', children: file?.name ?? '-' },
            { key: 's', label: '크기', children: file ? `${(file.size / 1024).toFixed(1)} KB` : '-' },
            { key: 'd', label: '수업일', children: lessonDate || '-' },
            { key: 't', label: '시간대', children: selectedSheets.join(', ') || '-' },
          ]} />
        </Card>
      ) : (
        <Card title="1. 파일 선택" size="small">
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <Typography.Text type="secondary">
              반 블록(반 이름 | 출결 | 예습 과제 | 주간 과제 | 시험 분야 (문항 수)) 아래에 학생 행이 있는 엑셀(.xlsx)을 올리세요. 파일 하나는 수업일 하루이고, 올릴 시간대(시트)를 골라 그 시트의 반만 처리합니다.
            </Typography.Text>
            <Space wrap>
              <Input aria-label="수업일" type="date" value={lessonDate} max={todayLocal()} onChange={(e) => { setLessonDate(e.target.value); reset() }} style={{ width: 170 }} />
              <input key={inputKey} aria-label="엑셀 파일" type="file" accept=".xlsx" onChange={(e) => void chooseFile(e.target.files?.[0] ?? null)} />
              <Button type="primary" loading={busy && !preview} disabled={!file || !lessonDate || busy || sheetsLoading || selectedSheets.length === 0} onClick={() => void runPreview()}>미리보기</Button>
            </Space>
            {sheetOptions && (
              <Space direction="vertical" size={4} style={{ width: '100%' }}>
                <Typography.Text strong>올릴 시간대(시트)</Typography.Text>
                <Checkbox.Group
                  value={selectedSheets}
                  onChange={(value) => { setSelectedSheets(value as string[]); reset() }}
                  options={sheetOptions.map((sheet) => ({
                    value: sheet.name,
                    label: `${sheet.name} · 반 ${sheet.class_names.length}개 · 학생 ${sheet.student_rows}행`,
                  }))}
                />
                <Typography.Text type={selectedSheets.length === 0 ? 'warning' : 'secondary'}>
                  {selectedSheets.length === 0
                    ? '이번에 올릴 시간대를 고르세요. 고른 시트의 반만 검증·저장합니다.'
                    : '고른 시트의 반만 검증·저장합니다. 고르지 않은 시트는 읽지 않으며, 그 시트의 오류도 이번 업로드를 막지 않습니다. 같은 파일을 여러 번 올려도 앱과 같은 행은 저장·기록 없이 건너뜁니다.'}
                </Typography.Text>
              </Space>
            )}
            {file && sheetsLoading && <Typography.Text type="secondary">시트(시간대) 목록을 읽는 중입니다…</Typography.Text>}
            {file && (
              <Descriptions size="small" column={{ xs: 1, sm: 3 }} items={[
                { key: 'n', label: '파일', children: file.name },
                { key: 's', label: '크기', children: `${(file.size / 1024).toFixed(1)} KB` },
                { key: 'd', label: '수업일', children: lessonDate || '-' },
              ]} />
            )}
            <Typography.Text type="secondary">미리보기는 아무것도 저장하지 않습니다. 고른 시트(시간대)의 반 블록을 찾아 학생을 반 명단과 대조합니다.</Typography.Text>
          </Space>
        </Card>
      )}

      {preview && (
        <>
          <Card title="2. 데이터 검증 결과 (저장 전)" size="small">
            <Space direction="vertical" style={{ width: '100%' }}>
              <Row gutter={[12, 12]}>
                {GROUPS.map((group) => (
                  <Col key={group.key} xs={12} lg={6}>
                    <Card size="small" className={view === group.key ? 'tile-active' : undefined}>
                      <button type="button" className="stat-link" aria-pressed={view === group.key}
                        onClick={() => setView((currentView) => (currentView === group.key ? 'all' : group.key))}>
                        <Statistic title={group.label} value={groups[group.key]} suffix="행"
                          valueStyle={groups[group.key] && group.color ? { color: group.color } : undefined} />
                        <Typography.Text type="secondary" style={{ fontSize: 12 }}>{group.hint}</Typography.Text>
                      </button>
                    </Card>
                  </Col>
                ))}
              </Row>
              <Typography.Text type="secondary">
                세부: 학생 행 {counts.total} · <span>정상(명단 일치)</span> {counts.matched} · <span>미등록(결정 필요)</span> {counts.unregistered} · 출결 다름(앱 값 유지) {counts.mismatch} · 앱 값이 바뀔 점수·등급 {counts.replaced} · 변경 없음(저장·기록 생략) {counts.unchanged} · 오류 행 {counts.invalid} · 건너뜀(메모 행) {counts.skipped}
                {` · 반 블록 ${preview.blocks.length}개 · 시험 열은 반 블록 머리글의 괄호 안 문항 수를 만점으로 사용합니다.`}
              </Typography.Text>
              {view !== 'all' && (
                <Space wrap>
                  <Tag icon={<FilterOutlined />} color="processing">{`${GROUPS.find((g) => g.key === view)!.label} ${groups[view]}행만 표시 중`}</Tag>
                  <Button size="small" onClick={() => setView('all')}>전체 행 보기</Button>
                </Space>
              )}
            </Space>
          </Card>
          {preview.blocking.length > 0 && (
            <Alert type="error" showIcon message="엑셀을 고친 뒤 다시 올려주세요. 아래 오류가 있으면 확정할 수 없습니다." description={<ul style={{ margin: 0 }}>{preview.blocking.map((b) => <li key={b}>{b}</li>)}</ul>} />
          )}
          {problems.length > 0 && (
            <Alert type="error" showIcon message={`행 오류 ${problems.length}건 — 엑셀에서 해당 행을 고친 뒤 다시 미리보기하세요.`}
              description={<ul style={{ margin: 0 }}>{problems.map(({ block, row }) => <li key={row.key}>{`[${block.sheet}] ${block.class_name} · ${row.row}행 ${row.name}: ${row.issues.join(', ')}`}</li>)}</ul>} />
          )}
          {preview.blocks.map((block) => {
            const blockRows = block.rows.filter(shown)
            if (view !== 'all' && blockRows.length === 0 && block.issues.length === 0) return null
            return (
              <Card key={`${block.sheet}-${block.row}`} size="small"
                title={`[${block.sheet}] ${block.class_name} · ${block.class_type === 'EXAM_PREP' ? '내신 대비' : block.class_type === 'REGULAR' ? '정규' : '유형 알 수 없음'}`}>
                {block.issues.map((issue) => <Alert key={issue} type="error" showIcon message={issue} style={{ marginBottom: 8 }} />)}
                {(block.max_score_changes ?? []).length > 0 && (
                  <Alert type="warning" showIcon style={{ marginBottom: 8 }}
                    message={`평가 만점이 엑셀 머리글 값으로 바뀝니다: ${(block.max_score_changes ?? []).map((c) => `${c.title} ${c.app} → ${c.upload}`).join(', ')}`} />
                )}
                <Table
                  rowKey="key"
                  size="small"
                  pagination={false}
                  scroll={{ x: 'max-content' }}
                  dataSource={blockRows}
                  locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={view === 'all' ? '학생 행이 없습니다.' : '이 분류에 해당하는 행이 없습니다.'} /> }}
                  onRow={(row) => ({ style: { background: ROW_BG[row.attendance_mismatch ? 'MISMATCH' : row.status] } })}
                  columns={[
                    { title: '행', dataIndex: 'row', width: 56, className: 'cell-number' },
                    { title: '학생', dataIndex: 'name', className: 'cell-nowrap' },
                    { title: '상태', className: 'cell-nowrap', render: (_, row) => <StatusTag row={row} /> },
                    { title: '출결', className: 'cell-nowrap', render: (_, row) => (row.attendance ? ATTENDANCE[row.attendance] : '-') },
                    { title: '예습/주간', className: 'cell-nowrap', render: (_, row) => `${row.prework ?? '-'} / ${row.weekly ?? '-'}` },
                    ...block.tests.map((test) => ({
                      title: `${test.title} (${test.total})`,
                      className: 'cell-number',
                      render: (_: unknown, row: upload.UploadRow) => (row.scores[test.title] ?? '-'),
                    })),
                    {
                      title: '확인·처리',
                      onCell: () => ({ style: { minWidth: 240 } }),
                      render: (_, row) => (
                        <Space direction="vertical" size={2}>
                          {row.issues.map((m) => <Typography.Text key={m} type="danger">{m}</Typography.Text>)}
                          {row.warnings.map((m) => <Typography.Text key={m} type="warning">{m}</Typography.Text>)}
                          {(row.app_changes ?? []).map((change) => (
                            <Typography.Text key={`${change.field}-${change.label}`} type="warning">{changeText(change)}</Typography.Text>
                          ))}
                          {decisionCell(row)}
                        </Space>
                      ),
                    },
                  ]}
                />
              </Card>
            )
          })}
          <Card title="3. 변경 확인" size="small">
            <Space direction="vertical" style={{ width: '100%' }}>
              {!preview.can_confirm ? (
                <Alert type="error" showIcon message="오류가 있어 저장할 수 없습니다. 엑셀을 고친 뒤 1단계에서 다시 미리보기하세요." />
              ) : (
                <>
                  <Descriptions size="small" column={{ xs: 1, sm: 2, lg: 4 }} items={[
                    { key: 'saved', label: '저장할 학생 행', children: `${impact.saved}명` },
                    { key: 'same', label: '변경 없음(생략)', children: `${counts.unchanged}명` },
                    { key: 'new', label: '신규 수강 등록', children: `${impact.newStudents}명` },
                    { key: 'ret', label: '복귀(휴원→재원)', children: `${impact.returning}명` },
                    { key: 'exc', label: '제외', children: `${impact.excluded}명` },
                  ]} />
                  <Typography.Text>
                    {`반 ${impact.classes.length}개(${impact.classes.join(', ') || '-'})의 ${lessonDate} 1교시 수업에 출결(앱에 기록이 없는 학생만)·과제 등급·시험 점수를 저장하고, 반 유형별 기본 템플릿으로 안내 초안을 만듭니다.`}
                  </Typography.Text>
                  <Typography.Text type="secondary">
                    저장은 전부 반영되거나 전혀 반영되지 않습니다(한 번의 트랜잭션). 초안 생성은 저장 뒤 이어서 진행되며, 만들지 못한 학생은 결과에 사유와 함께 표시됩니다. 같은 파일을 다시 올려도 중복은 생기지 않고, 앱과 같은 행은 저장·기록 없이 건너뜁니다.
                  </Typography.Text>
                </>
              )}
              {confirmError && (
                <Alert type="error" showIcon message={`저장 실패: ${confirmError.message}`}
                  description={confirmError.unknown
                    ? '서버 응답을 받지 못해 저장 여부를 알 수 없습니다. 같은 파일로 다시 미리보기하면 이미 저장된 학생은 "등록 학생"으로, 출결은 앱 기록으로 표시됩니다(재업로드는 중복 없이 갱신).'
                    : '저장은 하나도 반영되지 않았습니다. 사유를 고친 뒤 다시 확정하세요.'} />
              )}
              <Space wrap>
                {undecided.length > 0 && (
                  <Button size="small" type="link" danger onClick={() => setView('check')}>{`미등록 학생 ${undecided.length}명의 처리를 선택해주세요.`}</Button>
                )}
                <Popconfirm
                  title="업로드를 확정할까요?"
                  description={`출결(프로그램에 없는 경우)·과제 등급·시험 점수가 저장되고, 반별 기본 템플릿으로 안내 초안이 만들어집니다.${counts.replaced ? ` 앱에서 입력·수정한 점수·등급 ${counts.replaced}건이 엑셀 값으로 바뀝니다(변경 이력에 남음).` : ''}`}
                  okText="확정" cancelText="닫기" onConfirm={() => void confirm()}
                >
                  <Button type="primary" loading={busy} disabled={!preview.can_confirm || undecided.length > 0 || busy}>확정·초안 생성</Button>
                </Popconfirm>
              </Space>
            </Space>
          </Card>
        </>
      )}

      {result && (
        <Card title={`4. 처리 완료 — ${result.lesson_date} 업로드 결과`} size="small">
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            {/* Two separate outcomes with their own success criteria: the data save (one
                transaction, all or nothing) and draft generation (per student, after the save). */}
            <Row gutter={[16, 16]}>
              <Col xs={24} lg={10}>
                <Card type="inner" size="small" title="데이터 저장 결과" extra={<Tag color="success" icon={<CheckCircleOutlined />}>전부 반영됨</Tag>}>
                  <Descriptions size="small" column={2} items={[
                    { key: 's', label: '저장', children: `${result.saved_rows}명` },
                    { key: 'u', label: '변경 없음(기록 생략)', children: `${result.unchanged_rows ?? 0}명` },
                    { key: 'n', label: '신규 등록', children: `${result.new_students}명` },
                    { key: 'r', label: '복귀', children: `${result.returned_students}명` },
                    { key: 'x', label: '제외', children: `${result.excluded_rows}명` },
                  ]} />
                  <Typography.Text type="secondary">출결·과제·점수가 한 번의 트랜잭션으로 저장되었습니다.</Typography.Text>
                </Card>
              </Col>
              <Col xs={24} lg={14}>
                <Card type="inner" size="small" title="메시지 초안 생성 결과"
                  extra={draftTotals.failed + draftTotals.mismatch > 0
                    ? <Tag color="warning">{`확인 필요 ${draftTotals.failed + draftTotals.mismatch}건`}</Tag>
                    : <Tag color="success" icon={<CheckCircleOutlined />}>모두 처리됨</Tag>}>
                  <Space direction="vertical" size="small" style={{ width: '100%' }}>
                    <Descriptions size="small" column={{ xs: 2, sm: 4 }} items={[
                      { key: 'c', label: '생성', children: `${draftTotals.created}건` },
                      { key: 'e', label: '기존 초안 있음', children: `${draftTotals.existing}건` },
                      { key: 'f', label: '생성 실패', children: <Typography.Text type={draftTotals.failed ? 'danger' : undefined}>{`${draftTotals.failed}건`}</Typography.Text> },
                      { key: 'm', label: '출결 불일치', children: <Typography.Text type={draftTotals.mismatch ? 'warning' : undefined}>{`${draftTotals.mismatch}건`}</Typography.Text> },
                    ]} />
                    {drafts.map((d) => (
                      <Space key={d.class_name} direction="vertical" size={0} style={{ width: '100%' }}>
                        <Space wrap>
                          <Typography.Text strong>{`${d.class_name}: 초안 ${d.created}건`}</Typography.Text>
                          {d.failed.length > 0 && classIds[d.class_name] && !d.failed.some((note) => note.includes(NO_TEMPLATE)) && (
                            <Button size="small" type="link" onClick={() => openCompose({ classroomId: classIds[d.class_name], day: result.lesson_date })}>누락·예외 생성에서 해결</Button>
                          )}
                          {d.failed.some((note) => note.includes(NO_TEMPLATE)) && (
                            <Button size="small" type="link" onClick={() => openTab('templates')}>템플릿 기본 지정</Button>
                          )}
                        </Space>
                        {d.failed.map((s) => <Typography.Text key={s} type="danger">{`초안 미생성 — ${s}`}</Typography.Text>)}
                        {d.existing.length > 0 && (
                          <Typography.Text type="secondary">{`기존 초안 있음(중복 생성 안 함) ${d.existing.length}명: ${d.existing.map((note) => note.slice(0, -(EXISTING_REASON.length + 2))).join(', ')}`}</Typography.Text>
                        )}
                      </Space>
                    ))}
                    {result.attendance_mismatches.length > 0 && (
                      <Alert type="warning" showIcon message={`출결 불일치 ${result.attendance_mismatches.length}건: 프로그램 값을 유지했고 해당 학생의 안내 초안은 만들지 않았습니다. 출결을 확인한 뒤 '누락·예외 생성'으로 만드세요.`}
                        action={mismatchClasses.length > 0 && (
                          <Space direction="vertical" size={4}>
                            {mismatchClasses.map((name) => <Button key={name} size="small" onClick={() => fixAttendance(name)}>{`${name} 출결 확인`}</Button>)}
                          </Space>
                        )} />
                    )}
                  </Space>
                </Card>
              </Col>
            </Row>
            <Space wrap>
              <Button type="primary" onClick={openReview}>검토·발송으로 이동</Button>
              <Button onClick={() => openTab('operations')}>메시지 처리 현황</Button>
              <Button onClick={() => { void chooseFile(null); setInputKey((k) => k + 1); setFileOpen(true) }}>다른 파일 올리기</Button>
            </Space>
          </Space>
        </Card>
      )}

      <Modal
        open={missedOpen && result !== null}
        title={<Space><ExclamationCircleFilled style={{ color: '#ff4d4f' }} /><span>메시지 초안을 만들지 못한 학생이 있습니다</span></Space>}
        onCancel={() => setMissedOpen(false)}
        footer={<Button type="primary" danger onClick={() => setMissedOpen(false)}>확인</Button>}
      >
        {result && (
          <Space direction="vertical" style={{ width: '100%' }}>
            {drafts.filter((d) => d.failed.length > 0).map((d) => (
              <Alert key={d.class_name} type="error" showIcon message={`${d.class_name}: 초안 미생성 ${d.failed.length}건`}
                description={<ul style={{ margin: 0, paddingLeft: 18 }}>{d.failed.map((s) => <li key={s}>{s}</li>)}</ul>} />
            ))}
            {result.attendance_mismatches.length > 0 && (
              <Alert type="error" showIcon message={`출결 불일치 ${result.attendance_mismatches.length}건: 프로그램 출결을 유지했고 초안을 만들지 않았습니다.`}
                description={<ul style={{ margin: 0, paddingLeft: 18 }}>{result.attendance_mismatches.map((s) => <li key={s}>{s}</li>)}</ul>} />
            )}
            <Typography.Text type="secondary">
              엑셀 데이터는 저장되었습니다. 결과 화면의 '누락·예외 생성에서 해결'을 누르면 학생별 사유와 수정 화면 바로가기(보호자 연락처·출결·성적)가 표시됩니다.
            </Typography.Text>
          </Space>
        )}
      </Modal>
    </Space>
  )
}
