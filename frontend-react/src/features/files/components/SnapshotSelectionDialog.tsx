import { getCoreRowModel, getPaginationRowModel, getSortedRowModel, useReactTable, type ColumnDef, type SortingState } from '@tanstack/react-table'
import { Eye, Loader2 } from 'lucide-react'
import React, { useMemo, useState } from 'react'
import { Button } from '@/shared/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/shared/ui/dialog'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/shared/ui/tooltip'
import { DataTable } from '@/shared/components/DataTable'
import { SortableHeader } from '@/shared/components/SortableHeader'
import { StatusBadge } from '@/shared/components/StatusBadge'
import { formatDateTime } from '@/shared/utils/formatUtils'
import type { SnapshotRestoreSource, RestoreProgressState } from '@/features/backups/contracts'
import { SnapshotSkipNotice } from '@/features/backups/ui/SnapshotSkipNotice'
import { RestoreProgressCard } from '@/features/backups/ui/RestoreProgressCard'

interface SnapshotSelectionDialogProps {
  open: boolean
  onCancel: () => void
  snapshots: SnapshotRestoreSource[]
  loading: boolean
  onRestore: (snapshotId: string) => void
  restoreLoading: boolean
  filePath: string
  onPreview: (snapshotId: string) => void
  previewLoading: boolean
  isServerMode?: boolean
  restoreState?: RestoreProgressState
  onCloseAfterRestore?: () => void
  notice?: string | null
}

const snapshotColumns: ColumnDef<SnapshotRestoreSource, any>[] = [
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
    accessorKey: 'note',
    header: '备注',
    cell: ({ row }) => <span className="whitespace-pre-wrap break-words text-sm">{row.original.note || '无备注'}</span>,
  },
  {
    accessorKey: 'username',
    header: '用户',
    size: 120,
    cell: ({ row }) => <span className="text-sm">{row.original.username}</span>,
  },
  {
    id: 'skipped',
    header: '跳过内容',
    cell: ({ row }) => row.original.skipped_count
      ? <SnapshotSkipNotice paths={row.original.skipped_paths} count={row.original.skipped_count} />
      : <span className="text-sm text-muted-foreground">无</span>,
  },
]

export const SnapshotSelectionDialog: React.FC<SnapshotSelectionDialogProps> = ({
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
  notice,
}) => {
  const [sorting, setSorting] = useState<SortingState>([{ id: 'time', desc: true }])

  const actionColumn: ColumnDef<SnapshotRestoreSource, any> = useMemo(() => ({
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
          if (restoreState?.active) return
          onCancel()
        }
      }}
    >
      <DialogContent className="sm:max-w-200 max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            选择要恢复的快照 - {isServerMode ? '服务器数据目录' : filePath}
          </DialogTitle>
          <DialogDescription>
            请选择恢复版本。被忽略的路径会跳过，其余所选内容将恢复；各版本的跳过内容见下表。
          </DialogDescription>
        </DialogHeader>
        {notice && <p className="text-sm text-muted-foreground">{notice}</p>}

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
            emptyMessage={`没有找到包含${isServerMode ? '服务器数据目录' : '该路径'}的快照`}
          />
        )}
      </DialogContent>
    </Dialog>
  )
}
