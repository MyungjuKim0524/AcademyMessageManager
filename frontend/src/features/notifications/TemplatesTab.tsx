import { useCallback, useEffect, useState } from 'react'
import { Alert, Button, Card, Collapse, Empty, Form, Input, List, Modal, Select, Space, Switch, Table, Tag, Typography } from 'antd'
import { toApiClientError } from '../../shared/api/ApiClientError'
import * as api from './api'
import type { NotificationContext } from './NotificationsPage'

export function TemplatesTab({ role, notify, fail }: NotificationContext) {
  const admin = role === 'ADMIN'
  const [templates, setTemplates] = useState<api.Template[]>([])
  const [variables, setVariables] = useState<api.TemplateVariable[]>([])
  const [editing, setEditing] = useState<api.Template | 'new' | null>(null)
  const [check, setCheck] = useState<api.TemplateValidation | null>(null)
  const [busy, setBusy] = useState(false)
  const [form] = Form.useForm()

  const load = useCallback(async () => {
    try {
      const [items, vars] = await Promise.all([api.listTemplates(), api.listVariables()])
      setTemplates(items)
      setVariables(vars)
    } catch (error) { fail(error) }
  }, [fail])

  useEffect(() => { void load() }, [load])

  const openEditor = (target: api.Template | 'new') => {
    setEditing(target)
    setCheck(null)
    form.setFieldsValue(target === 'new' ? { name: '', body: '' } : { name: target.name, body: target.body })
  }

  const validate = async () => {
    try { setCheck(await api.validateTemplate(form.getFieldValue('body') ?? '')) } catch (error) { fail(error) }
  }

  const save = async (values: { name: string; body: string }) => {
    setBusy(true)
    try {
      if (editing === 'new') await api.createTemplate(values.name, values.body)
      else if (editing) await api.updateTemplate(editing.id, { version: editing.version, name: values.name, body: values.body })
      notify({ type: 'success', text: '템플릿을 저장했습니다. 이미 만든 메시지의 본문은 바뀌지 않습니다.' })
      setEditing(null)
      await load()
    } catch (error) {
      const apiError = toApiClientError(error)
      if (apiError.fields.length) setCheck({ ok: false, errors: apiError.fields.map((f) => f.message), variables: [], sample_body: null, sample_issues: [] })
      notify({ type: 'error', text: apiError.message })
    } finally { setBusy(false) }
  }

  const toggle = async (row: api.Template, active: boolean) => {
    try {
      await api.updateTemplate(row.id, { version: row.version, is_active: active })
      await load()
    } catch (error) { fail(error) }
  }

  const setDefault = async (row: api.Template, value: api.ClassType | 'NONE') => {
    try {
      await api.updateTemplate(row.id, { version: row.version, default_for_class_type: value })
      notify({ type: 'success', text: value === 'NONE' ? '기본 지정을 해제했습니다.' : `${row.name}을(를) ${value === 'REGULAR' ? '정규' : '내신 대비'} 기본 템플릿으로 지정했습니다.` })
      await load()
    } catch (error) { fail(error) }
  }

  // Variables matter while writing a template: a folded panel under the list and an open one in
  // the editor, instead of a column that squeezed the template list (Phase 9.6).
  const variableList = (
    <List size="small" dataSource={variables} renderItem={(item) => (
      <List.Item><Space size={8} wrap><Typography.Text code>{`{${item.name}}`}</Typography.Text><Typography.Text type="secondary">{item.description}</Typography.Text></Space></List.Item>
    )} />
  )
  const variablePanel = (open: boolean) => (
    <Collapse size="small" defaultActiveKey={open ? ['vars'] : []} items={[{ key: 'vars', label: `사용 가능한 변수 (${variables.length}개)`, children: variableList }]} />
  )

  return (
    <>
      <Card title="템플릿" extra={admin && <Button type="primary" onClick={() => openEditor('new')}>템플릿 등록</Button>}>
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Table
            rowKey="id"
            dataSource={templates}
            pagination={false}
            scroll={{ x: 'max-content' }}
            locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={admin ? "템플릿이 없습니다. '템플릿 등록'으로 만드세요." : '템플릿이 없습니다. 관리자에게 등록을 요청하세요.'} /> }}
            expandable={{ expandedRowRender: (row) => <Typography.Paragraph style={{ whiteSpace: 'pre-wrap', marginBottom: 0 }}>{row.body}</Typography.Paragraph> }}
            columns={[
              { title: '이름', dataIndex: 'name', className: 'cell-keep-all', onCell: () => ({ style: { minWidth: 180 } }) },
              { title: '버전', dataIndex: 'version', className: 'cell-number', width: 72, render: (value: number) => `v${value}` },
              {
                title: '엑셀 업로드 기본',
                width: 170,
                className: 'cell-nowrap',
                render: (_, row) => admin ? (
                  <Select<api.ClassType | 'NONE'>
                    aria-label={`${row.name} 기본 지정`}
                    size="small"
                    style={{ width: 130 }}
                    value={row.default_for_class_type ?? 'NONE'}
                    disabled={!row.is_active}
                    onChange={(value) => void setDefault(row, value)}
                    options={[{ value: 'NONE', label: '지정 안 함' }, { value: 'REGULAR', label: '정규 기본' }, { value: 'EXAM_PREP', label: '내신 대비 기본' }]}
                  />
                ) : row.default_for_class_type ? <Tag color="blue">{row.default_for_class_type === 'REGULAR' ? '정규 기본' : '내신 대비 기본'}</Tag> : '-',
              },
              {
                title: '사용',
                width: 96,
                className: 'cell-nowrap',
                render: (_, row) => admin
                  ? <Switch aria-label={`${row.name} 사용 여부`} checked={row.is_active} checkedChildren="사용" unCheckedChildren="중지" onChange={(checked) => void toggle(row, checked)} />
                  : <Tag color={row.is_active ? 'green' : 'default'}>{row.is_active ? '사용' : '중지'}</Tag>,
              },
              ...(admin ? [{ title: '관리', width: 80, className: 'cell-nowrap', render: (_: unknown, row: api.Template) => <Button size="small" onClick={() => openEditor(row)}>수정</Button> }] : []),
            ]}
          />
          {!admin && <Typography.Text type="secondary">템플릿 등록·수정은 관리자만 할 수 있습니다. 행을 펼치면 본문을 볼 수 있습니다.</Typography.Text>}
          {variablePanel(false)}
        </Space>
      </Card>
      <Modal title={editing === 'new' ? '템플릿 등록' : '템플릿 수정'} open={editing !== null} onCancel={() => setEditing(null)} onOk={() => form.submit()}
        okText="저장" cancelText="취소" confirmLoading={busy} width={720} destroyOnHidden>
        <Form form={form} layout="vertical" onFinish={(values) => void save(values)}>
          <Form.Item name="name" label="템플릿 이름" rules={[{ required: true, whitespace: true }]}><Input maxLength={100} /></Form.Item>
          <Form.Item name="body" label="본문" rules={[{ required: true, whitespace: true }]}><Input.TextArea aria-label="템플릿 본문" rows={8} maxLength={2000} showCount /></Form.Item>
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            {variablePanel(true)}
            <Button onClick={() => void validate()}>검증·예시 보기</Button>
          </Space>
        </Form>
        {check && (check.ok ? (
          <Alert style={{ marginTop: 12 }} type="success" showIcon message="사용할 수 있는 템플릿입니다. (가상 데이터 예시)"
            description={<Typography.Paragraph style={{ whiteSpace: 'pre-wrap', marginBottom: 0 }}>{check.sample_body}</Typography.Paragraph>} />
        ) : (
          <Alert style={{ marginTop: 12 }} type="error" showIcon message="템플릿을 확인해주세요." description={check.errors.join('\n')} />
        ))}
      </Modal>
    </>
  )
}
