import { useEffect, useState } from 'react'
import { Alert, Drawer, Empty, Space, Spin, Table, Typography } from 'antd'
import { toApiClientError } from '../../shared/api/ApiClientError'
import * as api from './api'
import { AttendanceTag, GradeTag, LessonStatusTag, lessonTitle } from './common'

export function StudentRecordsDrawer({ classroomId, studentId, onClose }: { classroomId: number; studentId: number | null; onClose: () => void }) {
  const [records, setRecords] = useState<api.StudentRecords | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (studentId === null) return
    let active = true
    setRecords(null)
    setError(null)
    api.getStudentRecords(classroomId, studentId)
      .then((data) => { if (active) setRecords(data) })
      .catch((reason: unknown) => { if (active) setError(toApiClientError(reason).message) })
    return () => { active = false }
  }, [classroomId, studentId])

  return (
    <Drawer title={records ? `${records.student_name} 학습 기록` : '학습 기록'} open={studentId !== null} onClose={onClose} width={560}>
      {error && <Alert type="error" showIcon message={error} />}
      {!records && !error && <Spin />}
      {records && (
        <Space direction="vertical" size="large" style={{ width: '100%' }}>
          <Typography.Text type="secondary">
            수강 {records.enrolled_at} ~ {records.ended_at ?? '현재'} · 미입력은 결석이나 0점이 아닙니다.
          </Typography.Text>
          <Table
            rowKey="lesson_id"
            size="small"
            title={() => '수업 출결'}
            dataSource={records.lessons}
            pagination={false}
            locale={{ emptyText: <Empty description="수업 기록이 없습니다." /> }}
            columns={[
              { title: '수업', render: (_, row) => lessonTitle(row) },
              { title: '주제', render: (_, row) => row.topic ?? '-' },
              { title: '상태', render: (_, row) => <LessonStatusTag status={row.lesson_status} /> },
              { title: '출결', render: (_, row) => <AttendanceTag status={row.attendance_status} /> },
              { title: '예습/주간', render: (_, row) => `${row.prework_grade ?? '-'} / ${row.weekly_grade ?? '-'}` },
            ]}
          />
          <Table
            rowKey="assessment_id"
            size="small"
            title={() => '평가 결과'}
            dataSource={records.assessments}
            pagination={false}
            locale={{ emptyText: <Empty description="평가 기록이 없습니다." /> }}
            columns={[
              { title: '평가', dataIndex: 'title' },
              { title: '평가일', dataIndex: 'assessment_date' },
              { title: '결과', render: (_, row) => <GradeTag status={row.result_status} score={row.score} max={row.max_score} /> },
            ]}
          />
        </Space>
      )}
    </Drawer>
  )
}
