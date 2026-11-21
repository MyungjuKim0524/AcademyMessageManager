import { useCallback, useEffect, useRef, useState } from 'react'
import { Button, Card, Empty, Input, Space, Table, Tag, Typography } from 'antd'
import * as api from './api'
import { STATUS } from './status'

const PAGE_SIZE = 50

type Props = {
  /** Changing this reloads the current page (after a registration, enrollment or contact edit). */
  reloadKey: number
  onEditContact: (row: { id: number; name: string }) => void
  onOpenClassroom: (classroomId: number) => void
  onError: (error: unknown) => void
}

/** Administrators only: every student with the classes they are enrolled in. */
export function AllStudentsCard({ reloadKey, onEditContact, onOpenClassroom, onError }: Props) {
  const [query, setQuery] = useState('')
  const [page, setPage] = useState(1)
  const [data, setData] = useState<api.StudentPage | null>(null)
  const [loading, setLoading] = useState(false)
  const latest = useRef(0)

  const load = useCallback(async (q: string, pageNo: number) => {
    const request = ++latest.current
    setLoading(true)
    try {
      const result = await api.allStudents(q, PAGE_SIZE, (pageNo - 1) * PAGE_SIZE)
      if (request === latest.current) setData(result)
    } catch (error) {
      if (request === latest.current) onError(error)
    } finally {
      if (request === latest.current) setLoading(false)
    }
  }, [onError])

  useEffect(() => { void load(query, page) }, [load, query, page, reloadKey])

  return (
    <Card
      title={`전체 학생 목록${data ? ` (${data.total}명)` : ''}`}
      extra={(
        <Input.Search aria-label="학생 이름 검색" placeholder="이름 검색" allowClear style={{ width: 220 }}
          onSearch={(value) => { setPage(1); setQuery(value.trim()) }} />
      )}
    >
      <Table
        rowKey="id"
        size="middle"
        loading={loading}
        dataSource={data?.items ?? []}
        locale={{ emptyText: <Empty description={query ? `'${query}'와(과) 일치하는 학생이 없습니다.` : '등록된 학생이 없습니다. 위의 학생 등록에서 등록하세요.'} /> }}
        pagination={{ current: page, pageSize: PAGE_SIZE, total: data?.total ?? 0, showSizeChanger: false, hideOnSinglePage: true, onChange: setPage }}
        columns={[
          { title: 'ID', dataIndex: 'id', width: 70 },
          { title: '학생', dataIndex: 'name' },
          { title: '학교', dataIndex: 'school_name', render: (value: string | null) => value ?? '-' },
          {
            title: '수강 반',
            render: (_: unknown, row: api.StudentListItem) => row.enrollments.length === 0
              ? <Typography.Text type="secondary">수강 반 없음</Typography.Text>
              : (
                <Space size={[4, 4]} wrap>
                  {row.enrollments.map((item) => item.classroom_active === false ? (
                    // An ended class keeps its history but has no class list to open.
                    <Tag key={item.enrollment_id} title={`운영 종료된 반 (등록일 ${item.enrolled_at})`}>
                      {item.classroom_name} · 운영 종료
                    </Tag>
                  ) : (
                    <Tag key={item.enrollment_id} color={STATUS[item.status]?.color} style={{ cursor: 'pointer' }}
                      title={`${item.classroom_name} 반별 목록 보기 (등록일 ${item.enrolled_at})`}
                      onClick={() => onOpenClassroom(item.classroom_id)}>
                      {item.classroom_name} · {STATUS[item.status]?.label ?? item.status}
                    </Tag>
                  ))}
                </Space>
              ),
          },
          { title: '보호자 이메일', render: (_: unknown, row: api.StudentListItem) => row.parent_email ?? <Tag>미등록</Tag> },
          {
            title: '메일 주소 변경',
            render: (_: unknown, row: api.StudentListItem) => (
              <Button size="small" onClick={() => onEditContact(row)}>메일 주소 변경</Button>
            ),
          },
        ]}
      />
    </Card>
  )
}
