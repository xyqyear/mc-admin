import React, { useState, useMemo } from 'react'
import { toast } from 'sonner'
import { useQueryClient } from '@tanstack/react-query'
import {
  Database,
  History,
  Eye,
  Loader2,
} from 'lucide-react'
import {
  type ColumnDef,
  type SortingState,
  getCoreRowModel,
  getSortedRowModel,
  getPaginationRowModel,
  useReactTable,
} from '@tanstack/react-table'

import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { Spinner } from '@/components/ui/spinner'
import {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
} from '@/components/ui/tooltip'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

import { DataTable } from '@/components/common/DataTable'
import { SortableHeader } from '@/components/common/SortableHeader'
import { StatusBadge, type BadgeTone } from '@/components/common/StatusBadge'
import { useConfirm } from '@/hooks/useConfirm'
import { useEventStream } from '@/hooks/useEventStream'
import { useSnapshotMutations } from '@/hooks/mutations/useSnapshotMutations'
import { useSnapshotQueries } from '@/hooks/queries/base/useSnapshotQueries'
import { queryKeys } from '@/utils/api'
import { formatDateTime } from '@/utils/formatUtils'
import { formatUtils } from '@/utils/serverUtils'
import type { FileItem } from '@/types/Server'
import type {
  Snapshot,
  RestorePreviewAction,
  SnapshotRestoreEvent,
} from '@/hooks/api/snapshotApi'

import { RestoreProgressCard } from '@/components/world-restore/RestoreProgressCard'
import {
  applyRestoreEvent,
  initialProgress,
  type RestoreProgressState,
} from '@/components/world-restore/restoreProgress'

interface SnapshotSelectionDialogProps {
  open: boolean
  onCancel: () => void
  snapshots: Snapshot[]
  loading: boolean
  onRestore: (snapshotId: string) => void
  restoreLoading: boolean
  filePath: string
  onPreview: (snapshotId: string) => void
  previewLoading: boolean
  isServerMode?: boolean
  // When set, the selection table is replaced with the live progress card.
  restoreState?: RestoreProgressState
  onCloseAfterRestore?: () => void
}

const snapshotColumns: ColumnDef<Snapshot, any>[] = [
  {
    accessorKey: 'short_id',
    header: '快照ID',
    size: 100,
    cell: ({ row }) => (
      <Tooltip>
        <TooltipTrigger>
          <StatusBadge tone="info" badgeStyle="soft" className="font-mono">
            {row.original.short_id}
          </StatusBadge>
        </TooltipTrigger>
        <TooltipContent>完整ID: {row.original.id}</TooltipContent>
      </Tooltip>
    ),
  },
  {
    accessorKey: 'time',
    header: ({ column }) => <SortableHeader column={column} title="创建时间" />,
    size: 180,
    cell: ({ row }) => (
      <span className="font-mono text-sm">{formatDateTime(row.original.time)}</span>
    ),
    sortingFn: (a, b) => new Date(a.original.time).getTime() - new Date(b.original.time).getTime(),
  },
  {
    accessorKey: 'username',
    header: '用户',
    size: 120,
    cell: ({ row }) => <span className="text-sm">{row.original.username}</span>,
  },
]

const SnapshotSelectionDialog: React.FC<SnapshotSelectionDialogProps> = ({
  open,
  onCancel,
  snapshots,
  loading,
  onRestore,
  restoreLoading,
  filePath,
  onPreview,
  previewLoading,
  isServerMode = false,
  restoreState,
  onCloseAfterRestore,
}) => {
  const [sorting, setSorting] = useState<SortingState>([{ id: 'time', desc: true }])

  const actionColumn: ColumnDef<Snapshot, any> = useMemo(() => ({
    id: 'actions',
    header: '操作',
    size: 180,
    cell: ({ row }) => (
      <div className="flex items-center gap-1">
        <Button
          variant="outline"
          size="sm"
          onClick={() => onPreview(row.original.id)}
          disabled={previewLoading}
        >
          <Eye className="mr-1 h-3.5 w-3.5" />
          预览
        </Button>
        <Button
          size="sm"
          onClick={() => onRestore(row.original.id)}
          disabled={restoreLoading}
        >
          {restoreLoading && <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />}
          回滚
        </Button>
      </div>
    ),
  }), [onPreview, onRestore, previewLoading, restoreLoading])

  const allColumns = useMemo(() => [...snapshotColumns, actionColumn], [actionColumn])

  const table = useReactTable({
    data: snapshots,
    columns: allColumns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    getRowId: (row) => row.id,
    autoResetPageIndex: false,
    initialState: { pagination: { pageSize: 10 } },
  })

  React.useEffect(() => {
    if (open) {
      table.setPageIndex(0)
    }
  }, [open, table])

  const showProgress =
    !!restoreState && (restoreState.active || restoreState.done || !!restoreState.error)

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) {
          // Block close while a restore is actively running.
          if (restoreState?.active) return
          onCancel()
        }
      }}
    >
      <DialogContent className="sm:max-w-200 max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            选择要回滚的快照 - {isServerMode ? '整个服务器' : filePath}
          </DialogTitle>
          <DialogDescription>
            以下是包含{isServerMode ? '整个服务器' : '该路径'}的所有快照，请选择要回滚的版本
          </DialogDescription>
        </DialogHeader>

        {showProgress && restoreState ? (
          <div className="space-y-3">
            <RestoreProgressCard state={restoreState} />
            {(restoreState.done || restoreState.error) && (
              <DialogFooter>
                <Button onClick={onCloseAfterRestore}>关闭</Button>
              </DialogFooter>
            )}
          </div>
        ) : (
          <DataTable
            table={table}
            isLoading={loading}
            rowLabel="个快照"
            pageSizeOptions={[5, 10, 20, 50]}
            emptyMessage={`没有找到包含${isServerMode ? '整个服务器' : '该路径'}的快照`}
          />
        )}
      </DialogContent>
    </Dialog>
  )
}

interface PreviewDialogProps {
  open: boolean
  onCancel: () => void
  previewData: RestorePreviewAction[] | null
  previewSummary: string | null
  loading: boolean
  snapshotId: string
  isServerMode?: boolean
}

const actionToneMap: Record<string, BadgeTone> = {
  updated: 'warning',
  deleted: 'danger',
  restored: 'success',
}

const actionLabelMap: Record<string, string> = {
  updated: '更新',
  deleted: '删除',
  restored: '恢复',
}

const PreviewDialog: React.FC<PreviewDialogProps> = ({
  open,
  onCancel,
  previewData,
  previewSummary,
  loading,
  snapshotId,
  isServerMode = false,
}) => (
  <Dialog open={open} onOpenChange={(o) => !o && onCancel()}>
    <DialogContent className="sm:max-w-200 max-h-[85vh] overflow-y-auto">
      <DialogHeader>
        <DialogTitle>
          预览{isServerMode ? '服务器' : ''}快照回滚 - {snapshotId}
        </DialogTitle>
      </DialogHeader>

      {loading ? (
        <div className="text-center py-8">
          <Spinner className="mx-auto size-6 mb-2" />
          <span className="text-sm text-muted-foreground">正在生成预览...</span>
        </div>
      ) : previewData ? (
        <div className="space-y-4">
          {previewSummary && (
            <div className="bg-blue-50 dark:bg-blue-950/40 p-3 rounded-md border border-blue-200 dark:border-blue-900">
              <span className="font-semibold text-sm">{previewSummary}</span>
            </div>
          )}

          <div className="flex items-center gap-2">
            <Separator className="flex-1" />
            <span className="text-xs text-muted-foreground">详细变更列表</span>
            <Separator className="flex-1" />
          </div>

          <div className="space-y-2 max-h-96 overflow-y-auto">
            {previewData.map((action, index) => (
              <div key={index} className="p-3 border rounded-md bg-muted/50">
                <div className="flex items-center gap-2">
                  {(() => {
                    const tone = actionToneMap[action.action || '']
                    const label = actionLabelMap[action.action || ''] || action.action || action.message_type
                    return tone ? (
                      <StatusBadge tone={tone} badgeStyle="soft">{label}</StatusBadge>
                    ) : (
                      <Badge variant="outline">{label}</Badge>
                    )
                  })()}
                  <span className="font-mono text-xs">{action.item}</span>
                  {action.action !== 'deleted' && action.size != null && (
                    <span className="text-xs text-muted-foreground">
                      ({formatUtils.formatBytes(action.size)})
                    </span>
                  )}
                </div>
              </div>
            ))}
            {previewData.length === 0 && (
              <div className="text-center py-8 text-muted-foreground">
                没有变更
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="text-center py-8 text-muted-foreground">
          无法生成预览
        </div>
      )}
    </DialogContent>
  </Dialog>
)

interface FileSnapshotActionsProps {
  file?: FileItem
  serverId: string
  path?: string
  isServerMode?: boolean
  onRefresh?: () => void
}

const FileSnapshotActions: React.FC<FileSnapshotActionsProps> = ({
  file,
  serverId,
  path,
  isServerMode = false,
  onRefresh,
}) => {
  const queryClient = useQueryClient()
  const [isSnapshotDialogOpen, setIsSnapshotDialogOpen] = useState(false)
  const [selectedSnapshotId, setSelectedSnapshotId] = useState<string>('')
  const [isPreviewVisible, setIsPreviewVisible] = useState(false)
  const [previewData, setPreviewData] = useState<RestorePreviewAction[] | null>(null)
  const [previewSummary, setPreviewSummary] = useState<string | null>(null)

  // `restoreFor` becomes non-null on rollback click; useEventStream activates
  // and feeds events into the reducer.
  const [restoreFor, setRestoreFor] = useState<string | null>(null)
  const [restoreState, setRestoreState] =
    useState<RestoreProgressState>(initialProgress)

  const { confirm, confirmDialog } = useConfirm()

  const { useCreateSnapshot, usePreviewRestore } = useSnapshotMutations()
  const { useSnapshotsForPath } = useSnapshotQueries()

  const createSnapshotMutation = useCreateSnapshot()
  const previewRestoreMutation = usePreviewRestore()

  const actualPath = path || file?.path || '/'
  const displayName = isServerMode ? '整个服务器' : (file?.name || '服务器')

  const {
    data: snapshots = [],
    isLoading: isLoadingSnapshots,
    refetch: refetchSnapshots,
  } = useSnapshotsForPath(serverId, actualPath, false)

  useEventStream<SnapshotRestoreEvent>({
    enabled: !!restoreFor && !restoreState.error && !restoreState.done,
    url: '/snapshots/restore',
    method: 'POST',
    body: restoreFor
      ? {
          snapshot_id: restoreFor,
          server_id: serverId,
          paths: [actualPath],
        }
      : undefined,
    onEvent: (ev) => setRestoreState((prev) => applyRestoreEvent(prev, ev)),
    onClose: () =>
      setRestoreState((prev) =>
        prev.done || prev.error
          ? prev
          : { ...prev, active: false, error: '连接中断' },
      ),
    onError: (msg) =>
      setRestoreState((prev) => ({ ...prev, active: false, error: msg })),
  })

  React.useEffect(() => {
    if (restoreState.done) {
      toast.success(`已成功回滚 ${displayName}`)
      queryClient.invalidateQueries({ queryKey: queryKeys.files.all })
      queryClient.invalidateQueries({ queryKey: queryKeys.snapshots.all })
    } else if (restoreState.error) {
      toast.error(`回滚失败: ${restoreState.error}`)
    }
  }, [restoreState.done, restoreState.error, displayName, queryClient])

  const handleBackup = () => {
    confirm({
      title: '确认创建快照',
      description: `确定要为 ${displayName} 创建快照吗？`,
      confirmText: '确定',
      cancelText: '取消',
      onConfirm: async () => {
        await createSnapshotMutation.mutateAsync({
          server_id: serverId,
          paths: [actualPath],
        })
        toast.success(`已为 ${displayName} 创建快照`)
      },
    })
  }

  const handleRollback = () => {
    refetchSnapshots()
    setIsSnapshotDialogOpen(true)
  }

  const handleSnapshotRestore = (snapshotId: string) => {
    setSelectedSnapshotId(snapshotId)
    setRestoreState({
      active: true,
      percent: 0,
      message: '准备开始',
      log: [],
      done: false,
      error: null,
    })
    setRestoreFor(snapshotId)
  }

  const handleCloseAfterRestore = () => {
    setRestoreFor(null)
    setRestoreState(initialProgress)
    setSelectedSnapshotId('')
    setIsSnapshotDialogOpen(false)
    onRefresh?.()
  }

  const handlePreviewRestore = async (snapshotId: string) => {
    try {
      setSelectedSnapshotId(snapshotId)
      setPreviewData(null)
      setPreviewSummary(null)
      setIsPreviewVisible(true)

      const previewResult = await previewRestoreMutation.mutateAsync({
        snapshot_id: snapshotId,
        server_id: serverId,
        paths: [actualPath],
      })

      setPreviewData(previewResult.actions)
      setPreviewSummary(previewResult.preview_summary)
    } catch (error: any) {
      toast.error(`预览失败: ${error?.message || '未知错误'}`)
      setIsPreviewVisible(false)
    }
  }

  return (
    <>
      <div className="flex items-center gap-1">
        <Tooltip>
          <TooltipTrigger
            className="inline-flex"
            render={
              <Button
                variant="outline"
                size={isServerMode ? 'default' : 'icon-sm'}
                onClick={handleBackup}
                disabled={createSnapshotMutation.isPending}
              />
            }
          >
            {createSnapshotMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Database className="h-4 w-4" />
            )}
            {isServerMode && <span className="ml-1">创建快照</span>}
          </TooltipTrigger>
          <TooltipContent>为 {displayName} 创建快照</TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger
            className="inline-flex"
            render={
              <Button
                variant={isServerMode ? 'default' : 'outline'}
                size={isServerMode ? 'default' : 'icon-sm'}
                onClick={handleRollback}
              />
            }
          >
            <History className="h-4 w-4" />
            {isServerMode && <span className="ml-1">快照回滚</span>}
          </TooltipTrigger>
          <TooltipContent>回滚 {displayName}</TooltipContent>
        </Tooltip>
      </div>

      <SnapshotSelectionDialog
        open={isSnapshotDialogOpen}
        onCancel={() => {
          setIsSnapshotDialogOpen(false)
          setRestoreFor(null)
          setRestoreState(initialProgress)
          setSelectedSnapshotId('')
        }}
        snapshots={snapshots}
        loading={isLoadingSnapshots}
        onRestore={handleSnapshotRestore}
        restoreLoading={restoreState.active}
        filePath={actualPath}
        onPreview={handlePreviewRestore}
        previewLoading={previewRestoreMutation.isPending}
        isServerMode={isServerMode}
        restoreState={restoreState}
        onCloseAfterRestore={handleCloseAfterRestore}
      />

      <PreviewDialog
        open={isPreviewVisible}
        onCancel={() => setIsPreviewVisible(false)}
        previewData={previewData}
        previewSummary={previewSummary}
        loading={previewRestoreMutation.isPending}
        snapshotId={selectedSnapshotId}
        isServerMode={isServerMode}
      />

      {confirmDialog}
    </>
  )
}

export default FileSnapshotActions
