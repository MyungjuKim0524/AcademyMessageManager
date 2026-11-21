import { useMutation, useQuery } from '@tanstack/react-query'
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Col,
  Flex,
  Form,
  Input,
  InputNumber,
  Row,
  Select,
  Space,
  Spin,
  Tag,
  Typography,
} from 'antd'
import { ApiClientError } from '../../shared/api/ApiClientError'
import { PageHeader } from '../../shared/ui/PageHeader'
import { createMessagePreview, fetchHealth } from './api'
import type { MessagePreviewRequest } from './types'

const { Text, Title } = Typography

const formFieldNames = new Set<keyof MessagePreviewRequest>([
  'studentName', 'className', 'classType', 'lessonDate', 'testRound', 'attendance',
  'preGrade', 'weeklyGrade', 'correctCount', 'totalCount', 'includePreGrade',
  'includeWeeklyGrade', 'includeTestResult',
])

const initialValues: MessagePreviewRequest = {
  studentName: '샘플학생1',
  className: 'CLASS-DEMO',
  classType: 'REGULAR',
  lessonDate: new Date().toISOString().slice(0, 10),
  testRound: '1회차',
  attendance: 'PRESENT',
  preGrade: 'A',
  weeklyGrade: 'B',
  correctCount: 13,
  totalCount: 39,
  includePreGrade: true,
  includeWeeklyGrade: true,
  includeTestResult: true,
}

export function MessagePreviewPage() {
  const [form] = Form.useForm<MessagePreviewRequest>()
  const health = useQuery({ queryKey: ['api-health'], queryFn: fetchHealth, retry: false })
  const preview = useMutation({ mutationFn: createMessagePreview })

  const handleSubmit = (values: MessagePreviewRequest) => {
    preview.reset()
    preview.mutate(values, {
      onError: (error) => {
        if (error instanceof ApiClientError && error.fields.length > 0) {
          form.setFields(
            error.fields
              .filter((field) => formFieldNames.has(field.field as keyof MessagePreviewRequest))
              .map((field) => ({ name: field.field as keyof MessagePreviewRequest, errors: [field.message] })),
          )
        }
      },
    })
  }

  return (
    <main className="page-stack">
      <PageHeader
        title="학습 안내 메시지 미리보기"
        description="Swing 업무 흐름과 동일한 Service·Domain을 REST API로 호출하는 웹 전환 기능입니다(Java 호환 유지)."
        extra={<ApiStatus status={health.data?.status} isPending={health.isPending} hasError={health.isError} />}
      />

      <Row gutter={[24, 24]} align="stretch">
        <Col xs={24} lg={14}>
          <Card title="수업 및 학습 정보" className="content-card">
            <Form form={form} layout="vertical" initialValues={initialValues} onFinish={handleSubmit}>
              <Row gutter={16}>
                <Col xs={24} sm={12}>
                  <Form.Item label="학생 이름" name="studentName" rules={[{ required: true, message: '학생 이름을 입력해주세요.' }, { max: 100 }]}>
                    <Input maxLength={100} autoComplete="off" />
                  </Form.Item>
                </Col>
                <Col xs={24} sm={12}>
                  <Form.Item label="반 이름" name="className" rules={[{ required: true, message: '반 이름을 입력해주세요.' }, { max: 100 }]}>
                    <Input maxLength={100} autoComplete="off" />
                  </Form.Item>
                </Col>
                <Col xs={24} sm={12}>
                  <Form.Item label="수업 유형" name="classType" rules={[{ required: true }]}>
                    <Select options={[{ value: 'REGULAR', label: '정규' }, { value: 'EXAM_PREP', label: '시험 대비' }]} />
                  </Form.Item>
                </Col>
                <Col xs={24} sm={12}>
                  <Form.Item label="수업일" name="lessonDate" rules={[{ required: true, message: '수업일을 선택해주세요.' }]}>
                    <Input type="date" />
                  </Form.Item>
                </Col>
                <Col xs={24} sm={12}>
                  <Form.Item label="시험 회차" name="testRound">
                    <Input maxLength={50} />
                  </Form.Item>
                </Col>
                <Col xs={24} sm={12}>
                  <Form.Item label="출결" name="attendance" rules={[{ required: true }]}>
                    <Select options={[{ value: 'PRESENT', label: '출석' }, { value: 'ABSENT', label: '결석' }, { value: 'LATE', label: '지각' }]} />
                  </Form.Item>
                </Col>
                <Col xs={12} sm={6}>
                  <Form.Item label="사전 성취도" name="preGrade">
                    <Select allowClear options={['A', 'B', 'C'].map((value) => ({ value }))} />
                  </Form.Item>
                </Col>
                <Col xs={12} sm={6}>
                  <Form.Item label="주간 성취도" name="weeklyGrade">
                    <Select allowClear options={['A', 'B', 'C'].map((value) => ({ value }))} />
                  </Form.Item>
                </Col>
                <Col xs={12} sm={6}>
                  <Form.Item label="정답 수" name="correctCount">
                    <InputNumber min={0} max={10000} precision={0} className="full-width" />
                  </Form.Item>
                </Col>
                <Col xs={12} sm={6}>
                  <Form.Item label="전체 문항" name="totalCount">
                    <InputNumber min={1} max={10000} precision={0} className="full-width" />
                  </Form.Item>
                </Col>
              </Row>

              <Flex gap="middle" wrap className="option-row">
                <Form.Item name="includePreGrade" valuePropName="checked" noStyle><Checkbox>사전 성취도 포함</Checkbox></Form.Item>
                <Form.Item name="includeWeeklyGrade" valuePropName="checked" noStyle><Checkbox>주간 성취도 포함</Checkbox></Form.Item>
                <Form.Item name="includeTestResult" valuePropName="checked" noStyle><Checkbox>시험 결과 포함</Checkbox></Form.Item>
              </Flex>

              <Button type="primary" htmlType="submit" size="large" block loading={preview.isPending}>
                메시지 미리보기 생성
              </Button>
            </Form>
          </Card>
        </Col>

        <Col xs={24} lg={10}>
          <Card title="생성 결과" className="content-card result-card">
            {preview.isIdle && <EmptyResult />}
            {preview.isPending && <Spin description="메시지를 생성하고 있습니다." />}
            {preview.isError && (
              <Alert
                type="error"
                showIcon
                message="메시지를 생성하지 못했습니다."
                description={preview.error instanceof Error ? preview.error.message : '요청을 다시 확인해주세요.'}
              />
            )}
            {preview.isSuccess && <pre className="message-preview">{preview.data.message}</pre>}
          </Card>
        </Col>
      </Row>

      <Text className="page-footnote">
        브라우저 입력값과 생성 메시지는 localStorage 또는 sessionStorage에 저장하지 않습니다.
      </Text>
    </main>
  )
}

function ApiStatus({ status, isPending, hasError }: { status?: string; isPending: boolean; hasError: boolean }) {
  if (isPending) return <Tag>API 확인 중</Tag>
  if (hasError) return <Tag color="error">API 연결 실패</Tag>
  return <Tag color="success">API {status}</Tag>
}

function EmptyResult() {
  return (
    <Space orientation="vertical" size="small">
      <Title level={4}>아직 생성된 메시지가 없습니다.</Title>
      <Text type="secondary">왼쪽 입력값을 확인하고 미리보기 생성 버튼을 눌러주세요.</Text>
    </Space>
  )
}
