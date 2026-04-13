import React, { useState } from 'react'
import { toast } from 'sonner'
import {
  Clock,
  Plus,
  Play,
  Pause,
  Square,
  Info,
  Pencil,
} from 'lucide-react'
import {
  type ColumnDef,
  getCoreRowModel,
  getPaginationRowModel,
  useReactTable,
} from '@tanstack/react-table'

import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'

import PageHeader from '@/components/layout/PageHeader'
import { DataTable } from '@/components/common/DataTable'
import { RefreshButton } from '@/components/common/RefreshButton'
import { EmptyState } from '@/components/common/EmptyState'
import { useRegisteredCronJobs, useAllCronJobs } from '@/hooks/queries/base/useCronQueries'
import { useCronMutations } from '@/hooks/mutations/useCronMutations'
import { CreateCronJobDialog, CronJobDetailDialog } from '@/components/dialogs/cron'
import { CronJobStatusTag, NextRunTimeCell, CronExpressionDisplay, CronJobFilters } from '@/components/cron'
import { useConfirm } from '@/hooks/useConfirm'
import type { CronJob } from '@/hooks/api/cronApi'

const CronManagement: React.FC = () => {
  const { confirm, confirmDialog } = useConfirm()
  const [createDialogOpen, setCreateDialogOpen] = useState(false)
  const [editDialogOpen, setEditDialogOpen] = useState(false)
  const [detailDialogOpen, setDetailDialogOpen] = useState(false)
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null)
  const [filters, setFilters] = useState<{
    identifier?: string
    status: string[]
  }>({
    status: ['active', 'paused'],
  })

  const { data: registeredJobs, isFetching: jobsFetching, refetch: refetchJobs } = useRegisteredCronJobs()
  const { data: cronJobs = [], isLoading: cronJobsLoading, isFetching: cronJobsFetching, error: cronJobsError, refetch: refetchCronJobs } = useAllCronJobs(filters)

  const handleRefresh = async () => {
    try {
      await Promise.all([refetchJobs(), refetchCronJobs()])
      toast.success('刷新成功')
    } catch {
      toast.error('刷新失败')
    }
  }
  const { usePauseCronJob, useResumeCronJob, useCancelCronJob } = useCronMutations()

  const pauseMutation = usePauseCronJob()
  const resumeMutation = useResumeCronJob()
  const cancelMutation = useCancelCronJob()

  const handleViewDetail = (cronjobId: string) => {
    setSelectedJobId(cronjobId)
    setDetailDialogOpen(true)
  }

  const handleEditJob = (cronjobId: string) => {
    setSelectedJobId(cronjobId)
    setEditDialogOpen(true)
  }

  const handlePauseJob = (cronjobId: string) => {
    confirm({
      title: '暂停任务',
      description: '确定要暂停这个定时任务吗？任务将暂停执行直到恢复。',
      confirmText: '确认暂停',
      cancelText: '取消',
      onConfirm: async () => {
        await pauseMutation.mutateAsync(cronjobId)
      },
    })
  }

  const handleResumeJob = (cronjobId: string) => {
    confirm({
      title: '恢复任务',
      description: '确定要恢复这个定时任务吗？任务将重新开始按照计划执行。',
      confirmText: '确认恢复',
      cancelText: '取消',
      onConfirm: async () => {
        await resumeMutation.mutateAsync(cronjobId)
      },
    })
  }

  const handleCancelJob = (cronjobId: string) => {
    confirm({
      title: '取消任务',
      description: '确定要取消这个定时任务吗？任务将被标记为取消并默认隐藏。',
      confirmText: '确认取消',
      cancelText: '取消',
      variant: 'destructive',
      onConfirm: async () => {
        await cancelMutation.mutateAsync(cronjobId)
      },
    })
  }

  const identifierOptions = registeredJobs?.map(job => ({
    label: `${job.identifier} - ${job.description}`,
    value: job.identifier,
  })) || []

  const columns: ColumnDef<CronJob, any>[] = [
    {
      accessorKey: 'name',
      header: '任务名称',
      cell: ({ row }) => (
        <div>
          <div className="font-medium">{row.original.name}</div>
          <div className="text-xs text-muted-foreground">{row.original.identifier}</div>
        </div>
      ),
    },
    {
      accessorKey: 'status',
      header: '状态',
      size: 100,
      cell: ({ row }) => <CronJobStatusTag status={row.original.status} />,
    },
    {
      id: 'cron',
      header: 'Cron 表达式',
      size: 300,
      cell: ({ row }) => (
        <CronExpressionDisplay
          cronExpression={row.original.cron}
          second={row.original.second}
          size="small"
        />
      ),
    },
    {
      id: 'nextRun',
      header: '下次运行',
      size: 140,
      cell: ({ row }) => (
        <NextRunTimeCell
          cronjobId={row.original.cronjob_id}
          status={row.original.status}
        />
      ),
    },
    {
      accessorKey: 'execution_count',
      header: '执行次数',
      size: 80,
      cell: ({ row }) => (
        <span className="font-semibold">{row.original.execution_count}</span>
      ),
    },
    {
      id: 'actions',
      header: '操作',
      size: 220,
      cell: ({ row }) => {
        const record = row.original
        return (
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={() => handleViewDetail(record.cronjob_id)}
              title="详情"
            >
              <Info className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={() => handleEditJob(record.cronjob_id)}
              title="编辑"
            >
              <Pencil className="h-4 w-4" />
            </Button>
            {record.status === 'active' && (
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={() => handlePauseJob(record.cronjob_id)}
                disabled={pauseMutation.isPending}
                title="暂停"
              >
                <Pause className="h-4 w-4" />
              </Button>
            )}
            {(record.status === 'paused' || record.status === 'cancelled') && (
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={() => handleResumeJob(record.cronjob_id)}
                disabled={resumeMutation.isPending}
                title="恢复"
              >
                <Play className="h-4 w-4" />
              </Button>
            )}
            {record.status !== 'cancelled' && (
              <Button
                variant="ghost"
                size="icon-sm"
                className="text-destructive hover:text-destructive"
                onClick={() => handleCancelJob(record.cronjob_id)}
                disabled={cancelMutation.isPending}
                title="取消"
              >
                <Square className="h-4 w-4" />
              </Button>
            )}
          </div>
        )
      },
    },
  ]

  const table = useReactTable({
    data: cronJobs,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: { pagination: { pageSize: 20 } },
    getRowId: (row) => row.cronjob_id,
    autoResetPageIndex: false,
  })

  return (
    <div className="space-y-4">
      <PageHeader
        title="定时任务管理"
        icon={<Clock className="h-5 w-5" />}
        actions={
          <>
            <RefreshButton
              onClick={handleRefresh}
              isRefreshing={jobsFetching || cronJobsFetching}
            />
            <Button onClick={() => setCreateDialogOpen(true)}>
              <Plus className="mr-2 h-4 w-4" />
              创建任务
            </Button>
          </>
        }
      />

      {cronJobsError && (
        <Alert variant="destructive">
          <AlertTitle>加载任务列表失败</AlertTitle>
          <AlertDescription className="flex items-center justify-between">
            <span>{cronJobsError.message || '发生未知错误'}</span>
            <Button size="sm" variant="destructive" onClick={() => refetchCronJobs()}>
              重试
            </Button>
          </AlertDescription>
        </Alert>
      )}

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">
            <div className="flex items-center gap-2">
              <Clock className="h-4 w-4" />
              <span>任务列表</span>
              <span className="text-sm font-normal text-muted-foreground">
                ({cronJobs.length} 个任务)
              </span>
            </div>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <CronJobFilters
            identifierOptions={identifierOptions}
            filters={filters}
            onChange={setFilters}
            onReset={() => setFilters({ status: ['active', 'paused'] })}
            loading={cronJobsLoading}
          />

          <DataTable
            table={table}
            isLoading={cronJobsLoading}
            rowLabel="个任务"
            paginationVariant="compact"
            emptyMessage={
              <EmptyState
                title="暂无定时任务"
                description={<>点击&ldquo;创建任务&rdquo;按钮开始创建定时任务</>}
              />
            }
          />
        </CardContent>
      </Card>

      <CreateCronJobDialog
        open={createDialogOpen}
        onCancel={() => setCreateDialogOpen(false)}
        onSuccess={() => refetchCronJobs()}
      />

      <CreateCronJobDialog
        open={editDialogOpen}
        onCancel={() => {
          setEditDialogOpen(false)
          setSelectedJobId(null)
        }}
        onSuccess={() => refetchCronJobs()}
        isEdit={true}
        cronjobId={selectedJobId || undefined}
      />

      <CronJobDetailDialog
        open={detailDialogOpen}
        cronjobId={selectedJobId}
        onCancel={() => {
          setDetailDialogOpen(false)
          setSelectedJobId(null)
        }}
      />

      {confirmDialog}
    </div>
  )
}

export default CronManagement
