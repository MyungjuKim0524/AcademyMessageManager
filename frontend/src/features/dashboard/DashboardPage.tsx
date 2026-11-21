import { useCallback, useEffect, useState } from 'react'
import { Alert, Button, Card, Col, Empty, List, Row, Space, Spin, Tag, Typography } from 'antd'
import { CalendarOutlined, CloseCircleOutlined, CloudUploadOutlined, EditOutlined, MinusCircleOutlined, SendOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router'
import { toApiClientError } from '../../shared/api/ApiClientError'
import { todayLocal } from '../../shared/date'
import { PageHeader } from '../../shared/ui/PageHeader'
import * as classwork from '../classwork/api'
import { LessonStatusTag, lessonTitle } from '../classwork/common'
import * as ops from '../message-operations/api'

/** Today's lessons per classroom, counted from the 학습 현황 grid of that day (existing API). */
type TodayLesson = {
  classroomId: number; classroomName: string; lessonId: number; title: string; topic: string | null
  status: classwork.LessonStatus; eligible: number; recorded: number
}
type TodayState = { lessons: TodayLesson[]; noLesson: { id: number; name: string }[] }
type Section<T> = { data: T | null; error: string | null; loading: boolean }
const idle = <T,>(): Section<T> => ({ data: null, error: null, loading: true })

/** What the next step of a to-do row is, and where it is done (that class and that lesson). */
const TODO_ACTION: Record<ops.TodoItem['next_action'], { label: string; tab: 'review' | 'compose' }> = {
  RETRY: { label: '실패 건 재시도', tab: 'review' },
  SEND: { label: '모의 발송', tab: 'review' },
  REVIEW: { label: '검토·확정', tab: 'review' },
  COMPOSE: { label: '초안 만들기', tab: 'compose' },
}
const TODO_SHOWN = 8

async function loadToday(day: string): Promise<TodayState> {
  const classrooms = await classwork.listClassrooms()
  const grids = await Promise.all(classrooms.map((c) => classwork.getProgress(c.id, day, day)))
  const lessons: TodayLesson[] = []
  const noLesson: { id: number; name: string }[] = []
  classrooms.forEach((classroom, index) => {
    const grid = grids[index]
    const columns = grid.columns.filter((column) => column.kind === 'LESSON')
    if (columns.length === 0) noLesson.push({ id: classroom.id, name: classroom.name })
    for (const column of columns) {
      const position = grid.columns.indexOf(column)
      const cells = grid.students.map((student) => student.cells[position])
      lessons.push({
        classroomId: classroom.id,
        classroomName: classroom.name,
        lessonId: column.lesson_id!,
        title: lessonTitle({ lesson_date: column.day, session_no: column.session_no ?? 1, exam_round: column.exam_round }),
        topic: column.topic,
        status: column.lesson_status!,
        eligible: cells.filter((cell) => cell.eligible).length,
        recorded: cells.filter((cell) => cell.eligible && cell.attendance_status !== null).length,
      })
    }
  })
  return { lessons, noLesson }
}

export function DashboardPage() {
  const navigate = useNavigate()
  const [day] = useState(todayLocal)
  const [today, setToday] = useState<Section<TodayState>>(idle)
  const [todo, setTodo] = useState<Section<ops.TodoItem[]>>(idle)

  // Each section loads and fails on its own; a failed section shows an error, never a fake 0.
  const load = useCallback(() => {
    setToday(idle()); setTodo(idle())
    loadToday(day)
      .then((data) => setToday({ data, error: null, loading: false }))
      .catch((error) => setToday({ data: null, error: toApiClientError(error).message, loading: false }))
    ops.getTodo()
      .then((data) => setTodo({ data: data.items, error: null, loading: false }))
      .catch((error) => setTodo({ data: null, error: toApiClientError(error).message, loading: false }))
  }, [day])

  useEffect(() => { load() }, [load])

  const needAttendance = today.data?.lessons.filter((l) => l.status !== 'CANCELLED' && l.recorded < l.eligible) ?? []
  const openTodo = (row: ops.TodoItem) =>
    navigate(`/notifications?classroom=${row.classroom_id}&tab=${TODO_ACTION[row.next_action].tab}&lesson=${row.lesson_id}`)

  const failed = (section: Section<unknown>) => section.error && (
    <Alert type="error" showIcon message={section.error} action={<Button size="small" onClick={load}>다시 시도</Button>} />
  )

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <PageHeader title="대시보드" description={`오늘(${day}) 수업과 아직 끝나지 않은 성적 안내입니다. 담당 반 데이터만 보여 줍니다.`} />

      <Card size="small" title="빠른 작업">
        <Space wrap>
          <Button type="primary" icon={<CalendarOutlined />} onClick={() => navigate('/classes')}>출결 입력</Button>
          <Button icon={<CloudUploadOutlined />} onClick={() => navigate('/notifications?tab=upload')}>엑셀 업로드</Button>
          {/* '발송 실패 확인' removed (2026-11-20): failed sends lead the 성적 안내 할 일 list below,
              per class and lesson. A review shortcut stays out (user request, Phase 9.6). */}
        </Space>
      </Card>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={14}>
          <Card size="small" title={`오늘 수업 (${day})`} extra={<Typography.Text type="secondary">출결 = 수업일 기준 수강 학생 중 기록된 수</Typography.Text>}>
            {today.loading ? <Spin /> : failed(today) || (
              <Space direction="vertical" style={{ width: '100%' }}>
                {needAttendance.length > 0 && (
                  <Alert type="warning" showIcon message={`출결 입력이 끝나지 않은 수업 ${needAttendance.length}개`} />
                )}
                <List
                  size="small"
                  dataSource={today.data?.lessons ?? []}
                  locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="오늘 등록된 수업이 없습니다. 출결 탭의 '오늘 수업 시작'으로 만들 수 있습니다." /> }}
                  renderItem={(lesson) => (
                    // Phase 9.6: opens this class and this lesson's attendance, not the first class.
                    <List.Item actions={[
                      <Button key="go" size="small" type={lesson.status !== 'CANCELLED' && lesson.recorded < lesson.eligible ? 'primary' : 'default'}
                        onClick={() => navigate(`/classes?classroom=${lesson.classroomId}&tab=attendance&lesson=${lesson.lessonId}`)}>
                        {lesson.status !== 'CANCELLED' && lesson.recorded < lesson.eligible ? '출결 입력' : '출결 보기'}
                      </Button>,
                    ]}>
                      <Space wrap>
                        <Typography.Text strong>{lesson.classroomName}</Typography.Text>
                        <span>{`${lesson.title}${lesson.topic ? ` · ${lesson.topic}` : ''}`}</span>
                        <LessonStatusTag status={lesson.status} />
                        {lesson.status === 'CANCELLED' ? null : lesson.recorded < lesson.eligible
                          ? <Tag color="orange" icon={<MinusCircleOutlined />}>{`출결 ${lesson.recorded}/${lesson.eligible}명`}</Tag>
                          : <Tag color="green">{`출결 완료 ${lesson.recorded}/${lesson.eligible}명`}</Tag>}
                      </Space>
                    </List.Item>
                  )}
                />
                {(today.data?.noLesson.length ?? 0) > 0 && (
                  <Typography.Text type="secondary">{`오늘 수업이 없는 반: ${today.data!.noLesson.map((c) => c.name).join(', ')}`}</Typography.Text>
                )}
              </Space>
            )}
          </Card>
        </Col>
        <Col xs={24} xl={10}>
          {/* 2026-11-20: which class lesson, what is unfinished, and one button to the place where
              it is done — instead of four totals over all classes. */}
          <Card size="small" title="성적 안내 할 일" extra={<Button size="small" type="link" onClick={() => navigate('/notifications?tab=operations')}>메시지 처리 현황</Button>}>
            {todo.loading ? <Spin /> : failed(todo) || (
              <Space direction="vertical" style={{ width: '100%' }}>
                <Typography.Text type="secondary">
                  아직 끝나지 않은 성적 안내를 반·수업별로 보여 줍니다(최근 3개월 수업). 급한 순서: 발송 실패 → 발송 대기 → 검토 대기 → 안내 없음.
                </Typography.Text>
                <List
                  size="small"
                  dataSource={(todo.data ?? []).slice(0, TODO_SHOWN)}
                  locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="처리할 성적 안내가 없습니다." /> }}
                  renderItem={(row, index) => (
                    <List.Item actions={[
                      <Button key="go" size="small" type={index === 0 ? 'primary' : 'default'} onClick={() => openTodo(row)}>
                        {TODO_ACTION[row.next_action].label}
                      </Button>,
                    ]}>
                      <Space direction="vertical" size={2}>
                        <Space wrap size={4}>
                          <Typography.Text strong>{row.classroom_name}</Typography.Text>
                          <Typography.Text>{`${lessonTitle({ lesson_date: row.lesson_date, session_no: row.session_no, exam_round: null })} 수업`}</Typography.Text>
                        </Space>
                        <Space wrap size={4}>
                          {row.failed > 0 && <Tag color="red" icon={<CloseCircleOutlined />}>{`발송 실패 ${row.failed}건`}</Tag>}
                          {row.ready_to_send > 0 && <Tag color="blue" icon={<SendOutlined />}>{`발송 대기 ${row.ready_to_send}건`}</Tag>}
                          {row.in_review > 0 && <Tag color="gold" icon={<EditOutlined />}>{`검토 대기 ${row.in_review}건`}</Tag>}
                          {row.missing > 0 && (
                            <Tag icon={<MinusCircleOutlined />}>
                              {`안내 없음 ${row.missing}명${row.missing_no_email || row.missing_no_attendance
                                ? ` (${[row.missing_no_email ? `이메일 없음 ${row.missing_no_email}` : '', row.missing_no_attendance ? `출결 미입력 ${row.missing_no_attendance}` : ''].filter(Boolean).join(' · ')})`
                                : ''}`}
                            </Tag>
                          )}
                        </Space>
                      </Space>
                    </List.Item>
                  )}
                />
                {(todo.data?.length ?? 0) > TODO_SHOWN && (
                  <Button size="small" type="link" onClick={() => navigate('/notifications?tab=operations')}>{`외 ${todo.data!.length - TODO_SHOWN}개 수업 — 메시지 처리 현황에서 보기`}</Button>
                )}
              </Space>
            )}
          </Card>
        </Col>
      </Row>
    </Space>
  )
}
