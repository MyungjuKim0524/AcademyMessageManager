import { Alert, Button, Card, Collapse, Empty, List, Select, Space, Spin, Table, Tag, Typography } from 'antd'
import { useNavigate } from 'react-router'
import * as learningops from '../learningops/api'
import * as api from './api'
import type { Period } from './AnalyticsPage'
import { TrendChart } from './charts'
import { LoadError, rateText, scoreText, useLoad } from './common'

const STATUS: Record<api.GradeStatus, { label: string; color?: string }> = {
  SCORED: { label: '점수', color: 'blue' },
  NOT_TAKEN: { label: '미응시' },
  MISSING: { label: '미입력', color: 'orange' },
  UPCOMING: { label: '예정' },
}
const StatusTag = ({ status }: { status: api.GradeStatus }) => <Tag color={STATUS[status].color}>{STATUS[status].label}</Tag>
const ATTENDANCE: Record<string, { label: string; color?: string }> = {
  PRESENT: { label: '출석', color: 'green' }, LATE: { label: '지각', color: 'gold' }, ABSENT: { label: '결석', color: 'red' }, EXCUSED: { label: '인정결석', color: 'purple' },
}
/** "+8.0%p" / "−12.5%p": the position against the class average of the same session. */
const diffText = (diff: number | null) => (diff === null ? '-' : `${diff > 0 ? '+' : diff < 0 ? '−' : '±'}${Math.abs(diff).toFixed(1)}%p`)
const GradeTag = ({ grade }: { grade?: string | null }) => (grade ? <Tag color={grade === 'C' ? 'red' : grade === 'A' ? 'green' : undefined}>{grade}</Tag> : <Typography.Text type="secondary">-</Typography.Text>)

/**
 * 성적 분석 (2026-11-20 redesign): first who needs attention and why (rule-based, every reason
 * visible), then one student's learning report — each 평가 항목 against the class average of the
 * same session (a fair view of growth, since sessions differ in difficulty), homework and
 * attendance. The per-session class summary stays below for checking a single test.
 */
export function GradesPanel({ period, studentId, assessmentId, onStudent, onAssessment }: {
  period: Period; studentId: number | null; assessmentId: number | null
  onStudent: (id: number | null) => void; onAssessment: (id: number | null) => void
}) {
  const navigate = useNavigate()
  const { classroomId, dateFrom, dateTo } = period
  const watch = useLoad(() => api.getWatchlist(classroomId), [classroomId])
  const result = useLoad(() => api.getGrades(period), [classroomId, dateFrom, dateTo])
  const detail = useLoad(assessmentId ? () => api.getAssessment(assessmentId) : null, [assessmentId])
  const students = useLoad(() => learningops.students(classroomId), [classroomId])
  const report = useLoad(studentId ? () => api.getStudentReport(studentId, period) : null, [studentId, classroomId, dateFrom, dateTo])
  // Scores are entered in 학습 현황, one day at a time.
  const openScores = (day: string) => navigate(`/classes?classroom=${classroomId}&tab=progress&day=${day}`)

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <Card size="small" title="관심 필요 학생 (학생별 최근 4회 기준)"
        extra={watch.data && <Typography.Text type="secondary">{`${watch.data.window_from} ~ ${watch.data.window_to} 기록에서 판단`}</Typography.Text>}>
        {watch.loading && !watch.data ? <Spin /> : watch.error ? <LoadError message={watch.error} onRetry={watch.reload} /> : watch.data && (
          <Space direction="vertical" style={{ width: '100%' }}>
            <List
              size="small"
              dataSource={watch.data.students}
              locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="기준에 해당하는 학생이 없습니다." /> }}
              renderItem={(row) => (
                <List.Item actions={[<Button key="r" size="small" type={row.student_id === studentId ? 'primary' : 'default'} onClick={() => onStudent(row.student_id)}>리포트 보기</Button>]}>
                  <Space direction="vertical" size={2}>
                    <Typography.Text strong>{row.student_name}</Typography.Text>
                    <Space size={[4, 4]} wrap>{row.reasons.map((reason) => <Tag key={reason.text} color="volcano">{reason.text}</Tag>)}</Space>
                  </Space>
                </List.Item>
              )}
            />
            <Collapse size="small" items={[{
              key: 'rules', label: '판단 기준',
              children: <ul style={{ margin: 0, paddingLeft: 18 }}>{watch.data.rules.map((rule) => <li key={rule}>{rule}</li>)}</ul>,
            }]} />
          </Space>
        )}
      </Card>

      <Card size="small" title="학생 학습 리포트">
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Select aria-label="학생 선택" placeholder="학생 선택" style={{ width: 240 }} showSearch optionFilterProp="label" allowClear
            value={studentId ?? undefined} loading={students.loading}
            options={(students.data ?? []).map((row) => ({ value: row.id, label: row.name }))}
            onChange={(value) => onStudent(value ?? null)} />
          {students.error && <LoadError message={students.error} onRetry={students.reload} />}
          {studentId === null ? (
            <Typography.Text type="secondary">학생을 고르면 기간 안의 평가 항목별 성적(같은 회차 반 평균과 비교), 과제 등급, 출결을 보여줍니다.</Typography.Text>
          ) : report.loading && !report.data ? <Spin /> : report.error ? <LoadError message={report.error} onRetry={report.reload} /> : report.data && (
            <StudentReportView report={report.data} openScores={openScores} />
          )}
        </Space>
      </Card>

      <ClassSummary result={result} detail={detail} assessmentId={assessmentId} onAssessment={onAssessment} openScores={openScores}
        openGrades={() => navigate(`/classes?classroom=${classroomId}&tab=grades`)} />
    </Space>
  )
}

function StudentReportView({ report, openScores }: { report: api.StudentReport; openScores: (day: string) => void }) {
  const a = report.attendance
  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      {report.watch_reasons.length > 0 && (
        <Alert type="warning" showIcon message={`${report.student_name}: 관심 필요 (최근 기록 기준)`}
          description={<ul style={{ margin: 0, paddingLeft: 18 }}>{report.watch_reasons.map((r) => <li key={r.text}>{r.text}</li>)}</ul>} />
      )}
      <Typography.Text>
        {`출결: 출석률 ${rateText(a.attendance_rate, '계산 불가')} · 출석 ${a.present} · 지각 ${a.late} · 결석 ${a.absent} · 인정결석 ${a.excused} · 미입력 ${a.unrecorded}`}
      </Typography.Text>

      {report.categories.length === 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="이 기간에 평가가 없습니다." />
      ) : report.categories.map((category) => {
        const points = category.points
          .filter((p) => p.status === 'SCORED' && p.percent !== null)
          .map((p) => ({
            key: p.assessment_id, label: p.title, date: p.assessment_date, percent: p.percent!, compare: p.class_average_percent,
            detail: `${p.assessment_date} ${p.title}: ${scoreText(p.score)} / ${p.max_score}점 (${rateText(p.percent)}) · 반 평균 ${rateText(p.class_average_percent, '-')} · 반 대비 ${diffText(p.diff)}`,
          }))
        return (
          <Card key={category.title} type="inner" size="small"
            title={`${category.title} · 반 평균 대비 ${diffText(category.average_diff)} (점수 ${category.scored_count}회)`}>
            {points.length > 0 && (
              <>
                <TrendChart points={points} ariaLabel={`${report.student_name} 학생의 ${category.title} 만점 대비 점수(%)와 반 평균`} />
                <Typography.Paragraph type="secondary" style={{ margin: '4px 0 8px' }}>
                  {points.length === 1
                    ? '점수가 1건뿐이라 변화(추이)를 판단할 수 없습니다.'
                    : '회차마다 난이도가 달라 점수 자체보다 같은 회차 반 평균과의 차이(반 대비)의 흐름을 보세요.'}
                </Typography.Paragraph>
              </>
            )}
            <Table rowKey="assessment_id" size="small" pagination={false} dataSource={category.points} scroll={{ x: 'max-content' }}
              columns={[
                { title: '평가일', dataIndex: 'assessment_date', className: 'cell-nowrap' },
                { title: '상태', className: 'cell-nowrap', render: (_, p) => <StatusTag status={p.status} /> },
                { title: '점수 / 만점', className: 'cell-number', render: (_, p) => `${scoreText(p.score)} / ${p.max_score}` },
                { title: '만점 대비', className: 'cell-number', render: (_, p) => rateText(p.percent, '-') },
                { title: '반 평균', className: 'cell-number', render: (_, p) => rateText(p.class_average_percent, '-') },
                { title: '반 대비', className: 'cell-number', render: (_, p) => diffText(p.diff) },
                { title: '', className: 'cell-nowrap', render: (_, p) => p.status !== 'UPCOMING' && (
                  <Button size="small" type="link" onClick={() => openScores(p.assessment_date)}>학습 현황</Button>) },
              ]} />
          </Card>
        )
      })}

      <Card type="inner" size="small" title="수업별 출결·과제">
        <Table rowKey="lesson_id" size="small" pagination={false} dataSource={report.lessons} scroll={{ x: 'max-content' }}
          locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="이 기간에 진행된 수업이 없습니다." /> }}
          columns={[
            { title: '수업일', className: 'cell-nowrap', render: (_, row) => `${row.lesson_date}${row.session_no > 1 ? ` ${row.session_no}교시` : ''}` },
            { title: '출결', className: 'cell-nowrap', render: (_, row) => row.status ? <Tag color={ATTENDANCE[row.status].color}>{ATTENDANCE[row.status].label}</Tag> : <Tag color="orange">미입력</Tag> },
            { title: '예습 과제', className: 'cell-nowrap', render: (_, row) => <GradeTag grade={row.prework} /> },
            { title: '주간 과제', className: 'cell-nowrap', render: (_, row) => <GradeTag grade={row.weekly} /> },
          ]} />
      </Card>
    </Space>
  )
}

function ClassSummary({ result, detail, assessmentId, onAssessment, openScores, openGrades }: {
  result: ReturnType<typeof useLoad<api.GradeAnalytics>>; detail: ReturnType<typeof useLoad<api.AssessmentDetail>>
  assessmentId: number | null; onAssessment: (id: number | null) => void; openScores: (day: string) => void; openGrades: () => void
}) {
  if (result.loading && !result.data) return <Spin description="성적 통계를 계산하고 있습니다." />
  if (result.error) return <LoadError message={result.error} onRetry={result.reload} />
  const data = result.data
  if (!data) return null
  return (
    <>
      <Card size="small" title="회차별 반 요약 (평가를 누르면 학생별 점수)">
        <Table rowKey="assessment_id" size="small" pagination={false} dataSource={data.assessments} scroll={{ x: 'max-content' }}
          rowClassName={(row) => (row.assessment_id === assessmentId ? 'row-active' : '')}
          onRow={(row) => ({ onClick: () => onAssessment(row.assessment_id), style: { cursor: 'pointer' } })}
          locale={{ emptyText: (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="이 기간에 평가가 없습니다.">
              <Button onClick={openGrades}>평가 관리로 이동</Button>
            </Empty>) }}
          columns={[
            { title: '평가', className: 'cell-keep-all', onCell: () => ({ style: { minWidth: 140 } }), render: (_, row) => (
              <Space size={4}><Typography.Link>{row.title}</Typography.Link>{row.upcoming && <Tag>예정</Tag>}</Space>) },
            { title: '평가일', dataIndex: 'assessment_date', className: 'cell-nowrap' },
            { title: '만점', dataIndex: 'max_score', className: 'cell-number' },
            { title: '평균', className: 'cell-number', render: (_, row) => (row.average === null ? '점수 없음' : `${row.average}점 (${row.average_count}명)`) },
            { title: '평균/만점', className: 'cell-number', render: (_, row) => rateText(row.average_percent, '-') },
            { title: '입력 현황', className: 'cell-nowrap', render: (_, row) => `점수 ${row.scored} · 미응시 ${row.not_taken} · 미입력 ${row.missing} / 대상 ${row.target}${row.upcoming ? ' (평가 전)' : ''}` },
          ]} />
        <Typography.Paragraph type="secondary" style={{ margin: '8px 0 0' }}>
          평균은 입력된 점수만 사용합니다(0점 포함, 미응시·미입력 제외). 회차마다 만점과 난이도가 달라 평균을 서로 비교하지 마세요. '미입력'이 남아 있으면 학습 현황에서 입력하세요.
        </Typography.Paragraph>
      </Card>

      {assessmentId !== null && (
        <Card size="small" title={detail.data ? `${detail.data.stats.title} (${detail.data.stats.assessment_date}, 만점 ${detail.data.stats.max_score})` : '평가 상세'}
          extra={<Space>
            {detail.data && !detail.data.stats.upcoming && <Button size="small" onClick={() => openScores(detail.data!.stats.assessment_date)}>성적 입력 (학습 현황)</Button>}
            <Button size="small" onClick={() => onAssessment(null)}>닫기</Button>
          </Space>}>
          {detail.loading && !detail.data ? <Spin /> : detail.error ? <LoadError message={detail.error} onRetry={detail.reload} /> : detail.data && (
            <Space direction="vertical" style={{ width: '100%' }}>
              {detail.data.stats.missing > 0 && !detail.data.stats.upcoming && (
                <Alert type="warning" showIcon message={`점수 미입력 ${detail.data.stats.missing}명 — 0점이 아니라 아직 입력하지 않은 것입니다.`} />
              )}
              <Table rowKey="enrollment_id" size="small" pagination={false} dataSource={detail.data.rows} scroll={{ x: 'max-content' }}
                columns={[
                  { title: '학생', dataIndex: 'student_name', className: 'cell-nowrap' },
                  { title: '상태', className: 'cell-nowrap', render: (_, row) => <Space size={4}><StatusTag status={row.status} />{!row.eligible && <Tag>수강 기간 밖</Tag>}</Space> },
                  { title: '점수', className: 'cell-number', render: (_, row) => scoreText(row.score) },
                  { title: '만점 대비', className: 'cell-number', render: (_, row) => rateText(row.percent, '-') },
                ]} />
            </Space>
          )}
        </Card>
      )}
    </>
  )
}
