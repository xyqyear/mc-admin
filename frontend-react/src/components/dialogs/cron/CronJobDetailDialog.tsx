import React, { useState } from 'react'
import { Info, History } from 'lucide-react'
import {
  type ColumnDef,
  getCoreRowModel,
  getPaginationRowModel,
  useReactTable,
} from '@tanstack/react-table'

import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { Spinner } from '@/components/ui/spinner'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'

import { DataTable } from '@/components/common/DataTable'
import { StatusBadge } from '@/components/common/StatusBadge'
import { RefreshButton } from '@/components/common/RefreshButton'
import { useCronJob, useCronJobExecutions, useCronJobNextRunTime } from '@/hooks/queries/base/useCronQueries'
import { CronJobStatusTag, ExecutionStatusTag, NextRunTimeDisplay, CronExpressionDisplay } from '@/components/cron'
import { formatDateTime } from '@/utils/formatUtils'
import type { CronJobExecution } from '@/hooks/api/cronApi'

interface CronJobDetailDialogProps {
  open: boolean
  cronjobId: string | null
  onCancel: () => void
}

const executionColumns: ColumnDef<CronJobExecution, any>[] = [
  {
    accessorKey: 'execution_id',
    header: '执行ID',
    size: 120,
    cell: ({ row }) => (
      <span className="font-mono text-xs">
        {row.original.execution_id.slice(-8)}
      </span>
    ),
  },
  {
    accessorKey: 'status',
    header: '状态',
    size: 80,
    cell: ({ row }) => (
      <ExecutionStatusTag status={row.original.status} size="small" />
    ),
  },
  {
    accessorKey: 'started_at',
    header: '开始时间',
    size: 160,
    cell: ({ row }) => (
      <span className="font-mono text-xs">
        {row.original.started_at ? formatDateTime(row.original.started_at) : '-'}
      </span>
    ),
  },
  {
    accessorKey: 'ended_at',
    header: '结束时间',
    size: 160,
    cell: ({ row }) => (
      <span className="font-mono text-xs">
        {row.original.ended_at ? formatDateTime(row.original.ended_at) : '-'}
      </span>
    ),
  },
  {
    accessorKey: 'duration_ms',
    header: '耗时',
    size: 80,
    cell: ({ row }) => (
      <span className="text-xs">
        {row.original.duration_ms ? `${row.original.duration_ms}ms` : '-'}
      </span>
    ),
  },
  {
    accessorKey: 'messages',
    header: '日志',
    cell: ({ row }) => {
      const messages = row.original.messages
      if (!messages || messages.length === 0) {
        return <span className="text-xs text-muted-foreground">无日志</span>
      }
      return (
        <div className="max-w-xs">
          {messages.slice(0, 2).map((msg, index) => (
            <div key={index} className="text-xs text-muted-foreground truncate">
              {msg}
            </div>
          ))}
          {messages.length > 2 && (
            <span className="text-xs text-muted-foreground">
              ...还有 {messages.length - 2} 条
            </span>
          )}
        </div>
      )
    },
  },
]

const CronJobDetailDialog: React.FC<CronJobDetailDialogProps> = ({
  open,
  cronjobId,
  onCancel,
}) => {
  const [activeTab, setActiveTab] = useState<string>('info')

  const {
    data: jobDetail,
    isLoading: jobLoading,
    error: jobError,
    refetch: refetchJob,
  } = useCronJob(cronjobId)

  const {
    data: executions,
    isLoading: executionsLoading,
    error: executionsError,
    refetch: refetchExecutions,
  } = useCronJobExecutions(cronjobId, 50)

  const {
    data: nextRunTime,
    refetch: refetchNextRun,
  } = useCronJobNextRunTime(cronjobId)

  const table = useReactTable({
    data: executions || [],
    columns: executionColumns,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: { pagination: { pageSize: 10 } },
  })

  const handleRefresh = () => {
    refetchJob()
    refetchExecutions()
    refetchNextRun()
  }

  if (!open || !cronjobId) {
    return null
  }

  return (
      <Dialog open={open} onOpenChange={(o) => { if (!o) onCancel() }}>
        <DialogContent className="sm:max-w-250 max-h-[85vh] overflow-y-auto" showCloseButton={false}>
          <DialogHeader>
            <DialogTitle className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Info className="h-5 w-5" />
                <span>任务详情</span>
                {jobDetail && (
                  <span className="text-sm font-normal text-muted-foreground">- {jobDetail.name}</span>
                )}
              </div>
              <RefreshButton size="sm" onClick={handleRefresh} isRefreshing={jobLoading} />
            </DialogTitle>
          </DialogHeader>

          <Tabs value={activeTab} onValueChange={setActiveTab}>
            <TabsList>
              <TabsTrigger value="info">
                <Info className="mr-1 h-3.5 w-3.5" />
                任务信息
              </TabsTrigger>
              <TabsTrigger value="executions">
                <History className="mr-1 h-3.5 w-3.5" />
                执行历史
                {executions && (
                  <Badge variant="secondary" className="ml-1">{executions.length}</Badge>
                )}
              </TabsTrigger>
            </TabsList>

            <TabsContent value="info">
              <div className="space-y-4 pt-2">
                {jobError && (
                  <Alert variant="destructive">
                    <AlertTitle>加载任务信息失败</AlertTitle>
                    <AlertDescription>{jobError.message}</AlertDescription>
                  </Alert>
                )}

                {jobLoading && (
                  <div className="flex items-center justify-center py-8">
                    <Spinner className="size-6" />
                  </div>
                )}

                {jobDetail && (
                  <>
                    <Card>
                      <CardHeader className="pb-3">
                        <CardTitle className="text-sm">基本信息</CardTitle>
                      </CardHeader>
                      <CardContent>
                        <div className="grid grid-cols-2 gap-3 text-sm">
                          <div className="col-span-2">
                            <span className="text-muted-foreground">任务ID:</span>
                            <span className="ml-2 font-mono">{jobDetail.cronjob_id}</span>
                          </div>
                          <div className="col-span-2">
                            <span className="text-muted-foreground">任务名称:</span>
                            <span className="ml-2">{jobDetail.name}</span>
                          </div>
                          <div>
                            <span className="text-muted-foreground">任务类型:</span>
                            <StatusBadge tone="info" badgeStyle="soft" className="ml-2">
                              {jobDetail.identifier}
                            </StatusBadge>
                          </div>
                          <div>
                            <span className="text-muted-foreground">状态:</span>
                            <span className="ml-2">
                              <CronJobStatusTag status={jobDetail.status} />
                            </span>
                          </div>
                          <div>
                            <span className="text-muted-foreground">执行次数:</span>
                            <span className="ml-2 font-semibold">{jobDetail.execution_count}</span>
                          </div>
                          <div>
                            <span className="text-muted-foreground">创建时间:</span>
                            <span className="ml-2 font-mono text-xs">{formatDateTime(jobDetail.created_at)}</span>
                          </div>
                          <div className="col-span-2">
                            <span className="text-muted-foreground">更新时间:</span>
                            <span className="ml-2 font-mono text-xs">{formatDateTime(jobDetail.updated_at)}</span>
                          </div>
                        </div>
                      </CardContent>
                    </Card>

                    <Card>
                      <CardHeader className="pb-3">
                        <CardTitle className="text-sm">调度配置</CardTitle>
                      </CardHeader>
                      <CardContent className="space-y-3">
                        <div>
                          <span className="text-sm font-medium">Cron 表达式:</span>
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
                            <span className="text-sm font-medium">下次运行:</span>
                            <div className="mt-1">
                              <NextRunTimeDisplay nextRunTime={nextRunTime.next_run_time} />
                            </div>
                          </div>
                        )}
                      </CardContent>
                    </Card>

                    <Card>
                      <CardHeader className="pb-3">
                        <CardTitle className="text-sm">任务参数</CardTitle>
                      </CardHeader>
                      <CardContent>
                        <pre className="bg-muted p-3 rounded text-sm overflow-auto">
                          {JSON.stringify(jobDetail.params, null, 2)}
                        </pre>
                      </CardContent>
                    </Card>
                  </>
                )}
              </div>
            </TabsContent>

            <TabsContent value="executions">
              <div className="space-y-4 pt-2">
                {executionsError && (
                  <Alert variant="destructive">
                    <AlertTitle>加载执行历史失败</AlertTitle>
                    <AlertDescription>{executionsError.message}</AlertDescription>
                  </Alert>
                )}

                <DataTable
                  table={table}
                  isLoading={executionsLoading}
                  rowLabel="条执行记录"
                  paginationVariant="compact"
                  emptyMessage="暂无执行记录"
                />
              </div>
            </TabsContent>
          </Tabs>

          <DialogFooter>
            <Button variant="outline" onClick={onCancel}>
              关闭
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
  )
}

export default CronJobDetailDialog
