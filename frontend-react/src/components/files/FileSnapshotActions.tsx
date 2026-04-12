import React, { useState, useMemo } from 'react'
import { toast } from 'sonner'
import {
  Database,
  History,
  Eye,
  ChevronLeft,
  ChevronRight,
  ArrowUpDown,
  Loader2,
} from 'lucide-react'
import {
  type ColumnDef,
  type SortingState,
  flexRender,
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

import { useConfirm } from '@/hooks/useConfirm'
import { useSnapshotMutations } from '@/hooks/mutations/useSnapshotMutations'
import { useSnapshotQueries } from '@/hooks/queries/base/useSnapshotQueries'
import { formatDateTime } from '@/utils/formatUtils'
import { formatUtils } from '@/utils/serverUtils'
import type { FileItem } from '@/types/Server'
import type { Snapshot, RestorePreviewAction } from '@/hooks/api/snapshotApi'

// --- Safety Check Dialog ---

interface SafetyCheckDialogProps {
  open: boolean
  onCancel: () => void
  onCreateAndRestore: () => void
  onContinueWithoutCreate: () => void
  loading?: boolean
  isServerMode?: boolean
}

const SafetyCheckDialog: React.FC<SafetyCheckDialogProps> = ({
  open,
  onCancel,
  onCreateAndRestore,
  onContinueWithoutCreate,
  loading = false,
  isServerMode = false,
}) => (
  <Dialog open={open} onOpenChange={(o) => !o && !loading && onCancel()}>
    <DialogContent showCloseButton={false}>
      <DialogHeader>
        <DialogTitle>安全检查</DialogTitle>
      </DialogHeader>
      <div className="space-y-4">
        <p className="text-orange-600">
          ⚠️ 检测到{isServerMode ? '整个服务器' : '该路径'}在过去1分钟内没有创建快照。
        </p>
        <p className="text-sm">
          为了安全起见，建议您在回滚前先创建一个当前状态的快照。
        </p>
        <div className="bg-muted p-3 rounded-md text-sm">
          <span className="text-muted-foreground">您可以选择：</span>
          <ul className="mt-2 ml-4 list-disc space-y-1">
            <li>创建快照并回滚：安全选项，创建备份后再执行回滚</li>
            <li>继续回滚：直接执行回滚，不创建备份</li>
          </ul>
        </div>
      </div>
      <DialogFooter>
        <Button variant="outline" onClick={onCancel} disabled={loading}>
          取消
        </Button>
        <Button
          variant="destructive"
          onClick={onContinueWithoutCreate}
          disabled={loading}
        >
          {loading && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
          继续回滚
        </Button>
        <Button onClick={onCreateAndRestore} disabled={loading}>
          {loading && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
          创建快照并回滚
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
)

// --- Snapshot Selection Dialog ---

const SortableHeader = ({ column, title }: { column: any; title: string }) => (
  <Button
    variant="ghost"
    size="sm"
    className="-ml-3"
    onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
  >
    {title}
    <ArrowUpDown className="ml-1 h-3.5 w-3.5" />
  </Button>
)

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
}

const snapshotColumns: ColumnDef<Snapshot, any>[] = [
  {
    accessorKey: 'short_id',
    header: '快照ID',
    size: 100,
    cell: ({ row }) => (
      <Tooltip>
        <TooltipTrigger>
          <Badge variant="outline" className="font-mono bg-blue-50 text-blue-700 border-blue-200">
            {row.original.short_id}
          </Badge>
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

  const pageIndex = table.getState().pagination.pageIndex
  const pageSize = table.getState().pagination.pageSize
  const totalRows = table.getFilteredRowModel().rows.length
  const start = totalRows === 0 ? 0 : pageIndex * pageSize + 1
  const end = Math.min((pageIndex + 1) * pageSize, totalRows)

  // Reset pagination when dialog opens
  React.useEffect(() => {
    if (open) {
      table.setPageIndex(0)
    }
  }, [open, table])

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onCancel()}>
      <DialogContent className="sm:max-w-200 max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            选择要回滚的快照 - {isServerMode ? '整个服务器' : filePath}
          </DialogTitle>
          <DialogDescription>
            以下是包含{isServerMode ? '整个服务器' : '该路径'}的所有快照，请选择要回滚的版本
          </DialogDescription>
        </DialogHeader>

        {loading ? (
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
                      <TableCell colSpan={allColumns.length} className="h-24 text-center text-muted-foreground">
                        没有找到包含{isServerMode ? '整个服务器' : '该路径'}的快照
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </div>

            {totalRows > 0 && (
              <div className="flex items-center justify-between pt-1">
                <span className="text-sm text-muted-foreground">
                  {start}-{end} 共 {totalRows} 个快照
                </span>
                <div className="flex items-center gap-2">
                  <Select
                    value={String(pageSize)}
                    onValueChange={(v) => v && table.setPageSize(Number(v))}
                    itemToStringLabel={(v) => `${v}条/页`}
                  >
                    <SelectTrigger className="w-22.5">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {[5, 10, 20, 50].map(size => (
                        <SelectItem key={size} value={String(size)}>
                          {size}条/页
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Button
                    variant="outline"
                    size="icon-sm"
                    onClick={() => table.previousPage()}
                    disabled={!table.getCanPreviousPage()}
                  >
                    <ChevronLeft className="h-4 w-4" />
                  </Button>
                  <span className="text-sm text-muted-foreground">
                    {pageIndex + 1} / {table.getPageCount()}
                  </span>
                  <Button
                    variant="outline"
                    size="icon-sm"
                    onClick={() => table.nextPage()}
                    disabled={!table.getCanNextPage()}
                  >
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            )}
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}

// --- Preview Dialog ---

interface PreviewDialogProps {
  open: boolean
  onCancel: () => void
  previewData: RestorePreviewAction[] | null
  previewSummary: string | null
  loading: boolean
  snapshotId: string
  isServerMode?: boolean
}

const actionColorMap: Record<string, string> = {
  updated: 'bg-orange-100 text-orange-700 border-orange-200',
  deleted: 'bg-red-100 text-red-700 border-red-200',
  restored: 'bg-green-100 text-green-700 border-green-200',
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
            <div className="bg-blue-50 p-3 rounded-md border border-blue-200">
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
                  <Badge
                    variant="outline"
                    className={actionColorMap[action.action || ''] || ''}
                  >
                    {actionLabelMap[action.action || ''] || action.action || action.message_type}
                  </Badge>
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

// --- Main Component ---

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
  const [isSnapshotModalVisible, setIsSnapshotModalVisible] = useState(false)
  const [isSafetyCheckVisible, setIsSafetyCheckVisible] = useState(false)
  const [selectedSnapshotId, setSelectedSnapshotId] = useState<string>('')
  const [isPreviewVisible, setIsPreviewVisible] = useState(false)
  const [previewData, setPreviewData] = useState<RestorePreviewAction[] | null>(null)
  const [previewSummary, setPreviewSummary] = useState<string | null>(null)

  const { confirm, ConfirmDialog } = useConfirm()

  const { useCreateSnapshot, useRestoreSnapshot, usePreviewRestore } = useSnapshotMutations()
  const { useSnapshotsForPath } = useSnapshotQueries()

  const createSnapshotMutation = useCreateSnapshot()
  const restoreSnapshotMutation = useRestoreSnapshot()
  const previewRestoreMutation = usePreviewRestore()

  const actualPath = path || file?.path || '/'
  const displayName = isServerMode ? '整个服务器' : (file?.name || '服务器')

  const {
    data: snapshots = [],
    isLoading: isLoadingSnapshots,
    refetch: refetchSnapshots,
  } = useSnapshotsForPath(serverId, actualPath, false)

  const handleBackup = () => {
    confirm({
      title: '确认创建快照',
      description: `确定要为 ${displayName} 创建快照吗？`,
      confirmText: '确定',
      cancelText: '取消',
      onConfirm: async () => {
        await createSnapshotMutation.mutateAsync({
          server_id: serverId,
          path: actualPath,
        })
        toast.success(`已为 ${displayName} 创建快照`)
      },
    })
  }

  const handleRollback = () => {
    refetchSnapshots()
    setIsSnapshotModalVisible(true)
  }

  const handleSnapshotRestore = async (snapshotId: string) => {
    setSelectedSnapshotId(snapshotId)

    try {
      await restoreSnapshotMutation.mutateAsync({
        snapshot_id: snapshotId,
        server_id: serverId,
        path: actualPath,
      })

      toast.success(`已成功回滚 ${displayName}`)
      setIsSnapshotModalVisible(false)
      onRefresh?.()
    } catch (error: any) {
      if (error?.message?.includes('no recent snapshot') || error?.message?.includes('1 minute')) {
        setIsSnapshotModalVisible(false)
        setIsSafetyCheckVisible(true)
      } else {
        toast.error(`回滚失败: ${error?.message || '未知错误'}`)
      }
    }
  }

  const handleCreateAndRestore = async () => {
    try {
      await createSnapshotMutation.mutateAsync({
        server_id: serverId,
        path: actualPath,
      })

      await restoreSnapshotMutation.mutateAsync({
        snapshot_id: selectedSnapshotId,
        server_id: serverId,
        path: actualPath,
      })

      toast.success(`已创建安全快照并成功回滚 ${displayName}`)
      setIsSafetyCheckVisible(false)
      setSelectedSnapshotId('')
      onRefresh?.()
    } catch (error: any) {
      toast.error(`操作失败: ${error?.message || '未知错误'}`)
    }
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
        path: actualPath,
      })

      setPreviewData(previewResult.actions)
      setPreviewSummary(previewResult.preview_summary)
    } catch (error: any) {
      toast.error(`预览失败: ${error?.message || '未知错误'}`)
      setIsPreviewVisible(false)
    }
  }

  const handleContinueWithoutCreate = async () => {
    try {
      await restoreSnapshotMutation.mutateAsync({
        snapshot_id: selectedSnapshotId,
        server_id: serverId,
        path: actualPath,
        skip_safety_check: true,
      })

      toast.success(`已成功回滚 ${displayName}`)
      setIsSafetyCheckVisible(false)
      setSelectedSnapshotId('')
      onRefresh?.()
    } catch (error: any) {
      toast.error(`回滚失败: ${error?.message || '未知错误'}`)
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
        open={isSnapshotModalVisible}
        onCancel={() => setIsSnapshotModalVisible(false)}
        snapshots={snapshots}
        loading={isLoadingSnapshots}
        onRestore={handleSnapshotRestore}
        restoreLoading={restoreSnapshotMutation.isPending}
        filePath={actualPath}
        onPreview={handlePreviewRestore}
        previewLoading={previewRestoreMutation.isPending}
        isServerMode={isServerMode}
      />

      <SafetyCheckDialog
        open={isSafetyCheckVisible}
        onCancel={() => {
          setIsSafetyCheckVisible(false)
          setSelectedSnapshotId('')
        }}
        onCreateAndRestore={handleCreateAndRestore}
        onContinueWithoutCreate={handleContinueWithoutCreate}
        loading={createSnapshotMutation.isPending || restoreSnapshotMutation.isPending}
        isServerMode={isServerMode}
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

      <ConfirmDialog />
    </>
  )
}

export default FileSnapshotActions
