import React, { useState } from 'react'
import {
  Modal,
  Card,
  Descriptions,
  Table,
  Button,
  Typography,
  Tag,
  Alert,
  Tabs,
  Empty,
  Space
} from 'antd'
import {
  InfoCircleOutlined,
  HistoryOutlined,
  ReloadOutlined,
  CloseOutlined
} from '@ant-design/icons'
import { useCronJob, useCronJobExecutions, useCronJobNextRunTime } from '@/hooks/queries/base/useCronQueries'
import { CronJobStatusTag, ExecutionStatusTag, NextRunTimeDisplay, CronExpressionDisplay } from '@/components/cron'
import { formatDateTime } from '@/utils/formatUtils'
import type { CronJobExecution } from '@/hooks/api/cronApi'
import type { TableProps } from 'antd'

const { Text, Paragraph } = Typography

interface CronJobDetailModalProps {
  open: boolean
  cronjobId: string | null
  onCancel: () => void
}

const CronJobDetailModal: React.FC<CronJobDetailModalProps> = ({
  open,
  cronjobId,
  onCancel
}) => {
  const [activeTab, setActiveTab] = useState<string>('info')

  const {
    data: jobDetail,
    isLoading: jobLoading,
    error: jobError,
    refetch: refetchJob
  } = useCronJob(cronjobId)

  const {
    data: executions,
    isLoading: executionsLoading,
    error: executionsError,
    refetch: refetchExecutions
  } = useCronJobExecutions(cronjobId, 50)

  const {
    data: nextRunTime,
    refetch: refetchNextRun
  } = useCronJobNextRunTime(cronjobId)

  const handleRefresh = () => {
    refetchJob()
    refetchExecutions()
    refetchNextRun()
  }

  const executionsColumns: TableProps<CronJobExecution>['columns'] = [
    {
      title: '执行ID',
      dataIndex: 'execution_id',
      key: 'execution_id',
      width: 120,
      render: (id: string) => (
        <Text className="font-mono text-xs">{id.slice(-8)}</Text>
      )
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 80,
      render: (status: string) => (
        <ExecutionStatusTag status={status} size="small" />
      )
    },
    {
      title: '开始时间',
      dataIndex: 'started_at',
      key: 'started_at',
      width: 160,
      render: (time: string) => (
        <Text className="font-mono text-xs">
          {time ? formatDateTime(time) : '-'}
        </Text>
      )
    },
    {
      title: '结束时间',
      dataIndex: 'ended_at',
      key: 'ended_at',
      width: 160,
      render: (time: string) => (
        <Text className="font-mono text-xs">
          {time ? formatDateTime(time) : '-'}
        </Text>
      )
    },
    {
      title: '耗时',
      dataIndex: 'duration_ms',
      key: 'duration_ms',
      width: 80,
      render: (duration: number) => (
        <Text className="text-xs">
          {duration ? `${duration}ms` : '-'}
        </Text>
      )
    },
    {
      title: '日志',
      dataIndex: 'messages',
      key: 'messages',
      render: (messages: string[]) => (
        messages.length > 0 ? (
          <div className="max-w-xs">
            {messages.slice(0, 2).map((msg, index) => (
              <div key={index} className="text-xs text-gray-600 truncate">
                {msg}
              </div>
            ))}
            {messages.length > 2 && (
              <Text type="secondary" className="text-xs">
                ...还有 {messages.length - 2} 条
              </Text>
            )}
          </div>
        ) : (
          <Text type="secondary" className="text-xs">无日志</Text>
        )
      )
    }
  ]

  if (!open || !cronjobId) {
    return null
  }

  const tabItems = [
    {
      key: 'info',
      label: (
        <Space>
          <InfoCircleOutlined />
          <span>任务信息</span>
        </Space>
      ),
      children: (
        <div className="space-y-4">
          {jobError && (
            <Alert
              message="加载任务信息失败"
              description={jobError.message}
              type="error"
              showIcon
              closable
            />
          )}

          {jobDetail && (
            <>
              <Descriptions
                title="基本信息"
                bordered
                size="small"
                column={2}
              >
                <Descriptions.Item label="任务ID" span={2}>
                  <Text className="font-mono">{jobDetail.cronjob_id}</Text>
                </Descriptions.Item>
                <Descriptions.Item label="任务名称" span={2}>
                  {jobDetail.name}
                </Descriptions.Item>
                <Descriptions.Item label="任务类型">
                  <Tag color="blue">{jobDetail.identifier}</Tag>
                </Descriptions.Item>
                <Descriptions.Item label="状态">
                  <CronJobStatusTag status={jobDetail.status} />
                </Descriptions.Item>
                <Descriptions.Item label="执行次数">
                  <Text strong>{jobDetail.execution_count}</Text>
                </Descriptions.Item>
                <Descriptions.Item label="创建时间">
                  <Text className="font-mono text-sm">
                    {formatDateTime(jobDetail.created_at)}
                  </Text>
                </Descriptions.Item>
                <Descriptions.Item label="更新时间" span={2}>
                  <Text className="font-mono text-sm">
                    {formatDateTime(jobDetail.updated_at)}
                  </Text>
                </Descriptions.Item>
              </Descriptions>

              <Card title="调度配置" size="small">
                <div className="space-y-3">
                  <div>
                    <Text strong>Cron 表达式:</Text>
                    <div className="mt-1">
                      <CronExpressionDisplay
                        cronExpression={jobDetail.cron}
                        second={jobDetail.second}
                        showTooltip={true}
                      />
                    </div>
                  </div>

                  {jobDetail.status.toLowerCase() === 'active' && nextRunTime && (
                    <div>
                      <Text strong>下次运行:</Text>
                      <div className="mt-1">
                        <NextRunTimeDisplay nextRunTime={nextRunTime.next_run_time} />
                      </div>
                    </div>
                  )}
                </div>
              </Card>

              <Card title="任务参数" size="small">
                <Paragraph>
                  <pre className="bg-gray-50 p-3 rounded text-sm overflow-auto">
                    {JSON.stringify(jobDetail.params, null, 2)}
                  </pre>
                </Paragraph>
              </Card>
            </>
          )}
        </div>
      )
    },
    {
      key: 'executions',
      label: (
        <Space>
          <HistoryOutlined />
          <span>执行历史</span>
          {executions && (
            <Tag>{executions.length}</Tag>
          )}
        </Space>
      ),
      children: (
        <div className="space-y-4">
          {executionsError && (
            <Alert
              message="加载执行历史失败"
              description={executionsError.message}
              type="error"
              showIcon
              closable
            />
          )}

          <Table
            dataSource={executions}
            columns={executionsColumns}
            rowKey="execution_id"
            size="small"
            loading={executionsLoading}
            pagination={{
              pageSize: 10,
              showSizeChanger: false,
              showTotal: (total, range) =>
                `${range[0]}-${range[1]} 共 ${total} 条执行记录`
            }}
            locale={{
              emptyText: (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description="暂无执行记录"
                />
              )
            }}
          />
        </div>
      )
    }
  ]

  return (
    <Modal
      title={
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <InfoCircleOutlined />
            <span>任务详情</span>
            {jobDetail && (
              <Text type="secondary">- {jobDetail.name}</Text>
            )}
          </div>
          <Button
            className="mr-6"
            icon={<ReloadOutlined />}
            onClick={handleRefresh}
            loading={jobLoading}
          >
            刷新
          </Button>
        </div>
      }
      open={open}
      onCancel={onCancel}
      footer={[
        <Button key="close" icon={<CloseOutlined />} onClick={onCancel}>
          关闭
        </Button>
      ]}
      width={1000}
      destroyOnHidden
    >
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={tabItems}
      />
    </Modal>
  )
}

export default CronJobDetailModal