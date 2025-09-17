import React from 'react'
import { Form, Select, Space, Button } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'

interface CronJobFiltersProps {
  identifierOptions: { label: string; value: string }[]
  filters: {
    identifier?: string
    status: string[]
  }
  onChange: (filters: { identifier?: string; status: string[] }) => void
  onReset: () => void
  loading?: boolean
}

const statusOptions = [
  { label: '运行中', value: 'active' },
  { label: '已暂停', value: 'paused' },
  { label: '已取消', value: 'cancelled' }
]

const CronJobFilters: React.FC<CronJobFiltersProps> = ({
  identifierOptions,
  filters,
  onChange,
  onReset,
  loading = false
}) => {
  const handleIdentifierChange = (value?: string) => {
    onChange({
      ...filters,
      identifier: value
    })
  }

  const handleStatusChange = (values: string[]) => {
    onChange({
      ...filters,
      status: values
    })
  }

  const handleReset = () => {
    onReset()
  }

  return (
    <div className="pl-2 rounded-lg mb-4">
      <Form layout="inline" className="gap-4">
        <Form.Item label="任务类型" className="mb-0">
          <Select
            placeholder="选择任务类型"
            style={{ minWidth: 160 }}
            allowClear
            value={filters.identifier}
            onChange={handleIdentifierChange}
            options={identifierOptions}
          />
        </Form.Item>

        <Form.Item label="任务状态" className="mb-0">
          <Select
            mode="multiple"
            placeholder="选择状态"
            style={{ minWidth: 200 }}
            value={filters.status}
            onChange={handleStatusChange}
            options={statusOptions}
            maxTagCount="responsive"
          />
        </Form.Item>

        <Form.Item className="mb-0">
          <Space>
            <Button
              icon={<ReloadOutlined />}
              onClick={handleReset}
              loading={loading}
            >
              重置
            </Button>
          </Space>
        </Form.Item>
      </Form>
    </div>
  )
}

export default CronJobFilters