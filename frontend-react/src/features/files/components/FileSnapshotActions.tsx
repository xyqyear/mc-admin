import { fileSnapshotScope, useSnapshotOperation } from '@/features/backups/commands'
import { SnapshotPreviewDialog } from '@/features/backups/ui/SnapshotPreviewDialog'
import { RestorationHistoryDialog } from '@/features/backups/ui/RestorationHistoryDialog'
import {
  getCoreRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from '@tanstack/react-table'
import {
  Database,
  Eye,
  History,
  Loader2,
} from 'lucide-react'
import React, { useMemo, useState } from 'react'
import { toast } from 'sonner'

import { Button } from '@/shared/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/shared/ui/dialog'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/shared/ui/tooltip'

import { DataTable } from '@/shared/components/DataTable'
import { SortableHeader } from '@/shared/components/SortableHeader'
import { StatusBadge } from '@/shared/components/StatusBadge'
import type { FileItem } from '@/features/files/contracts'
import type { Snapshot, SnapshotPreviewRequest } from '@/features/backups/contracts';
import { useSnapshotMutations } from '@/features/backups/commands'
import { useSnapshotQueries } from '@/features/backups/queries'
import { useConfirm } from '@/shared/hooks/useConfirm'
import { formatDateTime } from '@/shared/utils/formatUtils'

import {
  type RestoreProgressState
} from '@/features/backups/contracts'
import { RestoreProgressCard } from '@/features/backups/ui/RestoreProgressCard'

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
          恢复
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
            选择要恢复的快照 - {isServerMode ? '整个服务器' : filePath}
          </DialogTitle>
          <DialogDescription>
            以下是包含{isServerMode ? '整个服务器' : '该路径'}的所有快照，请选择要恢复的版本
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
}) => {
  const [isSnapshotDialogOpen, setIsSnapshotDialogOpen] = useState(false)
  const [selectedSnapshotId, setSelectedSnapshotId] = useState<string>('')
  const [previewRequest, setPreviewRequest] = useState<SnapshotPreviewRequest | null>(null)

  const actualPath = path || file?.path || '/'
  const scope = useMemo(() => fileSnapshotScope(serverId, [actualPath]), [serverId, actualPath])
  const { state: restoreState, start: startRestore, reset: resetRestore } = useSnapshotOperation(scope)
  const [historyOpen, setHistoryOpen] = useState(false)

  const { confirm, confirmDialog } = useConfirm()

  const { useCreateSnapshot } = useSnapshotMutations()
  const { useSnapshotsForPath } = useSnapshotQueries()

  const createSnapshotMutation = useCreateSnapshot()

  const displayName = isServerMode ? '整个服务器' : (file?.name || '服务器')

  const {
    data: snapshots = [],
    isLoading: isLoadingSnapshots,
    refetch: refetchSnapshots,
  } = useSnapshotsForPath(serverId, actualPath, false)

  React.useEffect(() => {
    if (restoreState.done) {
      toast.success(`已成功恢复 ${displayName}`)
    } else if (restoreState.error) {
      toast.error(`恢复失败: ${restoreState.error}`)
    }
  }, [restoreState.done, restoreState.error, displayName])

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
    void startRestore(snapshotId)
  }

  const handleCloseAfterRestore = () => {
    resetRestore()
    setSelectedSnapshotId('')
    setIsSnapshotDialogOpen(false)
  }

  const handlePreviewRestore = (snapshotId: string) => {
    setSelectedSnapshotId(snapshotId)
    setPreviewRequest({ scope, source_snapshot_id: snapshotId })
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
                disabled={createSnapshotMutation.isPending || restoreState.active}
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
                disabled={restoreState.active}
              />
            }
          >
            <History className="h-4 w-4" />
            {isServerMode && <span className="ml-1">快照恢复</span>}
          </TooltipTrigger>
          <TooltipContent>恢复 {displayName}</TooltipContent>
        </Tooltip>
      </div>

      <SnapshotSelectionDialog
        open={isSnapshotDialogOpen || restoreState.active}
        onCancel={() => {
          setIsSnapshotDialogOpen(false)
          resetRestore()
          setSelectedSnapshotId('')
        }}
        snapshots={snapshots}
        loading={isLoadingSnapshots}
        onRestore={handleSnapshotRestore}
        restoreLoading={restoreState.active}
        filePath={actualPath}
        onPreview={handlePreviewRestore}
        previewLoading={!!previewRequest}
        isServerMode={isServerMode}
        restoreState={restoreState}
        onCloseAfterRestore={handleCloseAfterRestore}
      />

      <SnapshotPreviewDialog
        request={previewRequest}
        onClose={() => setPreviewRequest(null)}
        onRestore={previewId => {
          void startRestore(selectedSnapshotId, previewId).then(() => setPreviewRequest(null))
        }}
      />

      {isServerMode && <Button variant="outline" onClick={() => setHistoryOpen(true)}>恢复历史</Button>}
      <RestorationHistoryDialog open={historyOpen} onClose={() => setHistoryOpen(false)} scope={scope} />
      {confirmDialog}
    </>
  )
}

export default FileSnapshotActions
