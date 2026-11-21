import { Alert, Button, Card, Col, Empty, Row, Space, Spin, Statistic, Table, Tag, Tooltip, Typography } from 'antd'
import { InfoCircleOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router'
import { AttendanceTag, lessonTitle } from '../classwork/common'
import * as api from './api'
import type { Period } from './AnalyticsPage'
import { ATTENDANCE_COLORS, StackedBar } from './charts'
import { LoadError, rateText, useLoad } from './common'

const STATES = [
  { key: 'present', status: 'PRESENT', label: '출석' },
  { key: 'late', status: 'LATE', label: '지각' },
  { key: 'absent', status: 'ABSENT', label: '결석' },
  { key: 'excused', status: 'EXCUSED', label: '인정결석' },
] as const

const lessonName = (row: { lesson_date: string; session_no: number; topic: string | null }) =>
  `${lessonTitle({ lesson_date: row.lesson_date, session_no: row.session_no, exam_round: null })}${row.topic ? ` · ${row.topic}` : ''}`

export function AttendancePanel({ period, studentId, onStudent }: {
  period: Period; studentId: number | null; onStudent: (id: number | null) => void
}) {
  const navigate = useNavigate()
  const { classroomId, dateFrom, dateTo } = period
  const result = useLoad(() => api.getAttendance(period), [classroomId, dateFrom, dateTo])
  const history = useLoad(studentId ? () => api.getStudentAttendance(studentId, period) : null, [studentId, classroomId, dateFrom, dateTo])
  const openAttendance = (lessonId: number) => navigate(`/classes?classroom=${classroomId}&tab=attendance&lesson=${lessonId}`)

  if (result.loading && !result.data) return <Spin description="출결 통계를 계산하고 있습니다." />
  if (result.error) return <LoadError message={result.error} onRetry={result.reload} />
  const data = result.data
  if (!data) return null
  const s = data.summary
  const missingLessons = data.lessons.filter((row) => row.unrecorded > 0)

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      {data.not_held_lessons > 0 && (
        <Alert type="warning" showIcon
          message={`진행 기록이 없는 지난 수업 ${data.not_held_lessons}개는 집계에서 빠졌습니다.`}
          description="'예정' 상태이고 출결이 하나도 없는 수업입니다. 실제로 진행했다면 수업을 완료로 바꾸거나 출결을 입력하세요."
          action={<Button size="small" onClick={() => navigate(`/classes?classroom=${classroomId}&tab=lessons`)}>수업 목록 확인</Button>} />
      )}
      {s.target === 0 && data.students.length === 0 ? (
        <Card size="small">
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={`${dateFrom} ~ ${dateTo} 기간에 진행된 수업이 없습니다. (오늘 이후 수업은 아직 집계하지 않습니다.)`}>
            <Button onClick={() => navigate(`/classes?classroom=${classroomId}&tab=attendance`)}>출결 관리로 이동</Button>
          </Empty>
        </Card>
      ) : (
        <>
          <Row gutter={[12, 12]}>
            <Col xs={12} lg={6}><Card size="small"><Statistic title="출결 대상" value={s.target} suffix="건" />
              <span className="metric-hint">{`진행된 수업 ${data.held_lessons}개 × 그날 수강생`}</span></Card></Col>
            <Col xs={12} lg={6}><Card size="small"><Statistic title="출결 입력 완료율" value={rateText(s.record_rate)} />
              <span className="metric-hint">{`입력 ${s.recorded} / 대상 ${s.target}`}</span></Card></Col>
            <Col xs={12} lg={6}><Card size="small">
              <Statistic title={<Space size={4}>출석률<Tooltip title={data.policy.attendance_rate}><InfoCircleOutlined aria-label="출석률 계산 방법" /></Tooltip></Space>}
                value={rateText(s.attendance_rate, '계산 불가')} />
              <span className="metric-hint">(출석+지각) ÷ (입력−인정결석)</span></Card></Col>
            <Col xs={12} lg={6}><Card size="small"><Statistic title="미입력" value={s.unrecorded} suffix="건"
              valueStyle={s.unrecorded ? { color: '#d46b08' } : undefined} />
              <span className="metric-hint">결석으로 세지 않음</span></Card></Col>
          </Row>

          <Card size="small" title="입력된 출결 상태 분포">
            {s.recorded === 0 ? (
              <Typography.Text type="secondary">입력된 출결이 없어 분포를 표시할 수 없습니다.</Typography.Text>
            ) : (
              <StackedBar ariaLabel={`입력된 출결 ${s.recorded}건의 상태 분포`}
                segments={STATES.map((state) => ({ key: state.key, label: state.label, value: s[state.key], color: ATTENDANCE_COLORS[state.status] }))} />
            )}
            {s.outside_records > 0 && (
              <Typography.Paragraph type="secondary" style={{ margin: '8px 0 0' }}>
                {`수강 기간 밖 기록 ${s.outside_records}건은 대상·비율에 넣지 않았습니다.`}
              </Typography.Paragraph>
            )}
          </Card>

          {missingLessons.length > 0 && (
            <Card size="small" title={`출결 미입력 수업 ${missingLessons.length}개`}>
              <Table rowKey="lesson_id" size="small" pagination={false} dataSource={missingLessons} scroll={{ x: 'max-content' }}
                columns={[
                  { title: '수업', className: 'cell-nowrap', render: (_, row) => lessonName(row) },
                  { title: '미입력', className: 'cell-number', render: (_, row) => `${row.unrecorded} / ${row.target}명` },
                  { title: '', className: 'cell-nowrap', render: (_, row) => <Button size="small" onClick={() => openAttendance(row.lesson_id)}>출결 입력</Button> },
                ]} />
            </Card>
          )}

          <Card size="small" title="학생별 출결 (학생을 누르면 수업별 이력)">
            <Table rowKey="enrollment_id" size="small" pagination={false} dataSource={data.students} scroll={{ x: 'max-content' }}
              rowClassName={(row) => (row.student_id === studentId ? 'row-active' : '')}
              onRow={(row) => ({ onClick: () => onStudent(row.student_id), style: { cursor: 'pointer' } })}
              locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="이 기간에 출결 대상 학생이 없습니다." /> }}
              columns={[
                { title: '학생', className: 'cell-nowrap', render: (_, row) => (
                  <Space size={4}><Typography.Link>{row.student_name}</Typography.Link>{row.enrollment_status !== 'ACTIVE' && <Tag>{row.enrollment_status === 'PAUSED' ? '휴원' : '퇴원'}</Tag>}</Space>) },
                { title: '대상', dataIndex: 'target', className: 'cell-number' },
                { title: '미입력', dataIndex: 'unrecorded', className: 'cell-number', sorter: (a, b) => a.unrecorded - b.unrecorded },
                ...STATES.map((state) => ({
                  title: state.label, dataIndex: state.key, className: 'cell-number',
                  sorter: (a: api.StudentAttendance, b: api.StudentAttendance) => a[state.key] - b[state.key],
                })),
                { title: '출결 입력 완료율', className: 'cell-number', render: (_, row) => rateText(row.record_rate) },
                { title: '출석률', className: 'cell-number', render: (_, row) => rateText(row.attendance_rate, '계산 불가') },
              ]} />
          </Card>
        </>
      )}

      {studentId !== null && (
        <Card size="small" title={history.data ? `${history.data.student_name} 수업별 출결` : '수업별 출결'}
          extra={<Button size="small" onClick={() => onStudent(null)}>닫기</Button>}>
          {history.loading && !history.data ? <Spin /> : history.error ? <LoadError message={history.error} onRetry={history.reload} /> : history.data && (
            <Space direction="vertical" style={{ width: '100%' }}>
              <Typography.Text type="secondary">
                {`대상 ${history.data.summary.target}건 · 미입력 ${history.data.summary.unrecorded}건 · 출결 입력 완료율 ${rateText(history.data.summary.record_rate)} · 출석률 ${rateText(history.data.summary.attendance_rate, '계산 불가')}`}
              </Typography.Text>
              <Table rowKey="lesson_id" size="small" pagination={false} dataSource={history.data.rows} scroll={{ x: 'max-content' }}
                locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="이 기간에 이 학생의 출결 대상 수업이 없습니다(휴원·수강 기간 밖 포함)." /> }}
                columns={[
                  { title: '수업', className: 'cell-nowrap', render: (_, row) => lessonName(row) },
                  { title: '출결', className: 'cell-nowrap', render: (_, row) => (
                    <Space size={4}><AttendanceTag status={row.status} />{!row.eligible && <Tag>수강 기간 밖</Tag>}</Space>) },
                  { title: '', className: 'cell-nowrap', render: (_, row) => (
                    <Button size="small" type="link" onClick={() => openAttendance(row.lesson_id)}>{row.status ? '출결 화면' : '출결 입력'}</Button>) },
                ]} />
            </Space>
          )}
        </Card>
      )}
    </Space>
  )
}
