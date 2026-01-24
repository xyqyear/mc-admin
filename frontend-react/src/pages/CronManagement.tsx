import React, { useState } from 'react'
import {
  Card,
  Button,
  Alert,
  Typography,
  Table,
  App,
  Empty,
  Space
} from 'antd'
import {
  PlusOutlined,
  ReloadOutlined,
  ScheduleOutlined,
  PlayCircleOutlined,
  PauseCircleOutlined,
  StopOutlined,
  InfoCircleOutlined,
  EditOutlined
} from '@ant-design/icons'
import PageHeader from '@/components/layout/PageHeader'
import { useRegisteredCronJobs, useAllCronJobs } from '@/hooks/queries/base/useCronQueries'
import { useCronMutations } from '@/hooks/mutations/useCronMutations'
import { CreateCronJobModal, CronJobDetailModal } from '@/components/modals/cron'
import { CronJobStatusTag, NextRunTimeCell, CronExpressionDisplay, CronJobFilters } from '@/components/cron'
import type { CronJob } from '@/hooks/api/cronApi'
import type { TableProps } from 'antd'

const { Text } = Typography

const CronManagement: React.FC = () => {
  const { modal } = App.useApp()
  const [createModalOpen, setCreateModalOpen] = useState(false)
  const [editModalOpen, setEditModalOpen] = useState(false)
  const [detailModalOpen, setDetailModalOpen] = useState(false)
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null)
  const [filters, setFilters] = useState<{
    identifier?: string
    status: string[]
  }>({
    status: ['active', 'paused'] // 默认显示运行中和已暂停的任务
  })

  const { data: registeredJobs, isLoading: jobsLoading, refetch: refetchJobs } = useRegisteredCronJobs()
  const { data: cronJobs = [], isLoading: cronJobsLoading, error: cronJobsError, refetch: refetchCronJobs } = useAllCronJobs(filters)
  const { usePauseCronJob, useResumeCronJob, useCancelCronJob } = useCronMutations()

  const pauseMutation = usePauseCronJob()
  const resumeMutation = useResumeCronJob()
  const cancelMutation = useCancelCronJob()

  const handleFiltersChange = (newFilters: { identifier?: string; status: string[] }) => {
    setFilters(newFilters)
  }

  const handleFiltersReset = () => {
    setFilters({
      status: ['active', 'paused']
    })
  }

  const handleViewDetail = (cronjobId: string) => {
    setSelectedJobId(cronjobId)
    setDetailModalOpen(true)
  }

  const handleEditJob = (cronjobId: string) => {
    setSelectedJobId(cronjobId)
    setEditModalOpen(true)
  }

  const handlePauseJob = (cronjobId: string) => {
    modal.confirm({
      title: '暂停任务',
      content: '确定要暂停这个定时任务吗？任务将暂停执行直到恢复。',
      okText: '确认暂停',
      okType: 'primary',
      cancelText: '取消',
      onOk: async () => {
        await pauseMutation.mutateAsync(cronjobId)
      }
    })
  }

  const handleResumeJob = (cronjobId: string) => {
    modal.confirm({
      title: '恢复任务',
      content: '确定要恢复这个定时任务吗？任务将重新开始按照计划执行。',
      okText: '确认恢复',
      okType: 'primary',
      cancelText: '取消',
      onOk: async () => {
        await resumeMutation.mutateAsync(cronjobId)
      }
    })
  }

  const handleCancelJob = (cronjobId: string) => {
    modal.confirm({
      title: '取消任务',
      content: '确定要取消这个定时任务吗？任务将被标记为取消并默认隐藏。',
      okText: '确认取消',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        await cancelMutation.mutateAsync(cronjobId)
      }
    })
  }


  // 生成任务类型选项
  const identifierOptions = registeredJobs?.map(job => ({
    label: `${job.identifier} - ${job.description}`,
    value: job.identifier
  })) || []

  const columns: TableProps<CronJob>['columns'] = [
    {
      title: '任务名称',
      dataIndex: 'name',
      key: 'name',
      render: (name: string, record: CronJob) => (
        <div>
          <div className="font-medium">{name}</div>
          <Text type="secondary" className="text-xs">
            {record.identifier}
          </Text>
        </div>
      )
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => (
        <CronJobStatusTag status={status} />
      )
    },
    {
      title: 'Cron 表达式',
      key: 'cron',
      width: 300,
      render: (_, record: CronJob) => (
        <CronExpressionDisplay
          cronExpression={record.cron}
          second={record.second}
          size="small"
        />
      )
    },
    {
      title: '下次运行',
      key: 'nextRun',
      width: 140,
      render: (_, record: CronJob) => (
        <NextRunTimeCell
          cronjobId={record.cronjob_id}
          status={record.status}
        />
      )
    },
    {
      title: '执行次数',
      dataIndex: 'execution_count',
      key: 'execution_count',
      width: 80,
      render: (count: number) => (
        <Text strong>{count}</Text>
      )
    },
    {
      title: '操作',
      key: 'actions',
      width: 220,
      render: (_, record: CronJob) => (
        <Space>
          <Button
            icon={<InfoCircleOutlined />}
            size="small"
            onClick={() => handleViewDetail(record.cronjob_id)}
          >
          </Button>
          <Button
            icon={<EditOutlined />}
            size="small"
            onClick={() => handleEditJob(record.cronjob_id)}
          >
          </Button>
          {record.status === 'active' && (
            <Button
              icon={<PauseCircleOutlined />}
              size="small"
              onClick={() => handlePauseJob(record.cronjob_id)}
              loading={pauseMutation.isPending}
            >
            </Button>
          )}
          {(record.status === 'paused' || record.status === 'cancelled') && (
            <Button
              icon={<PlayCircleOutlined />}
              size="small"
              type="primary"
              onClick={() => handleResumeJob(record.cronjob_id)}
              loading={resumeMutation.isPending}
            >
            </Button>
          )}
          {record.status !== 'cancelled' && (
            <Button
              icon={<StopOutlined />}
              size="small"
              danger
              onClick={() => handleCancelJob(record.cronjob_id)}
              loading={cancelMutation.isPending}
            >
            </Button>
          )}
        </Space>
      )
    }
  ]

  return (
    <div className="h-full w-full flex flex-col space-y-4">
      <PageHeader
        title="定时任务管理"
        icon={<ScheduleOutlined />}
        actions={
          <>
            <Button
              icon={<ReloadOutlined />}
              onClick={() => {
                refetchJobs()
                refetchCronJobs()
              }}
              loading={jobsLoading || cronJobsLoading}
            >
              刷新
            </Button>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => setCreateModalOpen(true)}
            >
              创建任务
            </Button>
          </>
        }
      />


      {/* 任务列表加载错误提示 */}
      {cronJobsError && (
        <Alert
          title="加载任务列表失败"
          description={cronJobsError.message || '发生未知错误'}
          type="error"
          showIcon
          closable
          action={
            <Button size="small" danger onClick={() => refetchCronJobs()}>
              重试
            </Button>
          }
        />
      )}

      {/* 任务列表 */}
      <Card
        title={
          <div className="flex items-center space-x-2">
            <ScheduleOutlined />
            <span>任务列表</span>
            <Text type="secondary" className="text-sm font-normal">
              ({cronJobs.length} 个任务)
            </Text>
          </div>
        }
      >
        {/* 任务筛选 */}
        <CronJobFilters
          identifierOptions={identifierOptions}
          filters={filters}
          onChange={handleFiltersChange}
          onReset={handleFiltersReset}
          loading={cronJobsLoading}
        />

        <Table
          dataSource={cronJobs}
          columns={columns}
          rowKey="cronjob_id"
          size="small"
          scroll={{ x: 'max-content' }}
          loading={cronJobsLoading}
          pagination={{
            pageSize: 20,
            showSizeChanger: true,
            showQuickJumper: true,
            pageSizeOptions: ['10', '20', '50'],
            showTotal: (total, range) =>
              `${range[0]}-${range[1]} 共 ${total} 个任务`
          }}
          locale={{
            emptyText: (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={
                  <div className="space-y-2">
                    <div>暂无定时任务</div>
                    <div className="text-sm text-gray-400">
                      点击&ldquo;创建任务&rdquo;按钮开始创建定时任务
                    </div>
                  </div>
                }
              />
            )
          }}
        />
      </Card>

      {/* 创建任务模态框 */}
      <CreateCronJobModal
        open={createModalOpen}
        onCancel={() => setCreateModalOpen(false)}
        onSuccess={() => {
          // 刷新任务列表（会自动应用当前筛选条件）
          refetchCronJobs()
        }}
      />

      {/* 编辑任务模态框 */}
      <CreateCronJobModal
        open={editModalOpen}
        onCancel={() => {
          setEditModalOpen(false)
          setSelectedJobId(null)
        }}
        onSuccess={() => {
          // 刷新任务列表（会自动应用当前筛选条件）
          refetchCronJobs()
        }}
        isEdit={true}
        cronjobId={selectedJobId || undefined}
      />

      {/* 任务详情模态框 */}
      <CronJobDetailModal
        open={detailModalOpen}
        cronjobId={selectedJobId}
        onCancel={() => {
          setDetailModalOpen(false)
          setSelectedJobId(null)
        }}
      />
    </div>
  )
}

export default CronManagement