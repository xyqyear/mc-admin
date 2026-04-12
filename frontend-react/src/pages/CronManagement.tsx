import React, { useState } from 'react'
import {
  Clock,
  RotateCw,
  Plus,
  Play,
  Pause,
  Square,
  Info,
  Pencil,
} from 'lucide-react'
import {
  type ColumnDef,
  flexRender,
  getCoreRowModel,
  getPaginationRowModel,
  useReactTable,
} from '@tanstack/react-table'

import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { Spinner } from '@/components/ui/spinner'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

import PageHeader from '@/components/layout/PageHeader'
import { useRegisteredCronJobs, useAllCronJobs } from '@/hooks/queries/base/useCronQueries'
import { useCronMutations } from '@/hooks/mutations/useCronMutations'
import { CreateCronJobModal, CronJobDetailModal } from '@/components/modals/cron'
import { CronJobStatusTag, NextRunTimeCell, CronExpressionDisplay, CronJobFilters } from '@/components/cron'
import { useConfirm } from '@/hooks/useConfirm'
import type { CronJob } from '@/hooks/api/cronApi'

const CronManagement: React.FC = () => {
  const { confirm, confirmDialog } = useConfirm()
  const [createModalOpen, setCreateModalOpen] = useState(false)
  const [editModalOpen, setEditModalOpen] = useState(false)
  const [detailModalOpen, setDetailModalOpen] = useState(false)
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null)
  const [filters, setFilters] = useState<{
    identifier?: string
    status: string[]
  }>({
    status: ['active', 'paused'],
  })

  const { data: registeredJobs, isLoading: jobsLoading, refetch: refetchJobs } = useRegisteredCronJobs()
  const { data: cronJobs = [], isLoading: cronJobsLoading, error: cronJobsError, refetch: refetchCronJobs } = useAllCronJobs(filters)
  const { usePauseCronJob, useResumeCronJob, useCancelCronJob } = useCronMutations()

  const pauseMutation = usePauseCronJob()
  const resumeMutation = useResumeCronJob()
  const cancelMutation = useCancelCronJob()

  const handleViewDetail = (cronjobId: string) => {
    setSelectedJobId(cronjobId)
    setDetailModalOpen(true)
  }

  const handleEditJob = (cronjobId: string) => {
    setSelectedJobId(cronjobId)
    setEditModalOpen(true)
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

  const { pageIndex, pageSize } = table.getState().pagination
  const totalRows = table.getCoreRowModel().rows.length
  const start = totalRows > 0 ? pageIndex * pageSize + 1 : 0
  const end = Math.min((pageIndex + 1) * pageSize, totalRows)

  return (
    <div className="space-y-4">
      <PageHeader
        title="定时任务管理"
        icon={<Clock className="h-5 w-5" />}
        actions={
          <>
            <Button
              variant="outline"
              onClick={() => {
                refetchJobs()
                refetchCronJobs()
              }}
              disabled={jobsLoading || cronJobsLoading}
            >
              {(jobsLoading || cronJobsLoading)
                ? <Spinner className="mr-2 size-4" />
                : <RotateCw className="mr-2 h-4 w-4" />
              }
              刷新
            </Button>
            <Button onClick={() => setCreateModalOpen(true)}>
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

          {cronJobsLoading ? (
            <div className="flex items-center justify-center py-16">
              <Spinner className="size-8" />
            </div>
          ) : (
            <>
              <div className="rounded-md border">
                <Table>
                  <TableHeader>
                    {table.getHeaderGroups().map(headerGroup => (
                      <TableRow key={headerGroup.id}>
                        {headerGroup.headers.map(header => (
                          <TableHead key={header.id}>
                            {header.isPlaceholder
                              ? null
                              : flexRender(header.column.columnDef.header, header.getContext())}
                          </TableHead>
                        ))}
                      </TableRow>
                    ))}
                  </TableHeader>
                  <TableBody>
                    {table.getRowModel().rows.length ? (
                      table.getRowModel().rows.map(row => (
                        <TableRow key={row.id}>
                          {row.getVisibleCells().map(cell => (
                            <TableCell key={cell.id}>
                              {flexRender(cell.column.columnDef.cell, cell.getContext())}
                            </TableCell>
                          ))}
                        </TableRow>
                      ))
                    ) : (
                      <TableRow>
                        <TableCell colSpan={columns.length} className="h-24 text-center text-muted-foreground">
                          <div className="space-y-2">
                            <div>暂无定时任务</div>
                            <div className="text-sm">
                              点击&ldquo;创建任务&rdquo;按钮开始创建定时任务
                            </div>
                          </div>
                        </TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </div>

              {totalRows > 0 && (
                <div className="flex items-center justify-between pt-3">
                  <span className="text-sm text-muted-foreground">
                    {start}-{end} 共 {totalRows} 个任务
                  </span>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => table.previousPage()}
                      disabled={!table.getCanPreviousPage()}
                    >
                      上一页
                    </Button>
                    <span className="text-sm text-muted-foreground">
                      {pageIndex + 1} / {table.getPageCount()}
                    </span>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => table.nextPage()}
                      disabled={!table.getCanNextPage()}
                    >
                      下一页
                    </Button>
                  </div>
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>

      <CreateCronJobModal
        open={createModalOpen}
        onCancel={() => setCreateModalOpen(false)}
        onSuccess={() => refetchCronJobs()}
      />

      <CreateCronJobModal
        open={editModalOpen}
        onCancel={() => {
          setEditModalOpen(false)
          setSelectedJobId(null)
        }}
        onSuccess={() => refetchCronJobs()}
        isEdit={true}
        cronjobId={selectedJobId || undefined}
      />

      <CronJobDetailModal
        open={detailModalOpen}
        cronjobId={selectedJobId}
        onCancel={() => {
          setDetailModalOpen(false)
          setSelectedJobId(null)
        }}
      />

      {confirmDialog}
    </div>
  )
}

export default CronManagement
