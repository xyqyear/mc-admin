import React, { useState, useMemo } from 'react'
import { toast } from 'sonner'
import {
  History,
  Server,
  Trash2,
  Plus,
  RotateCw,
  Unlock,
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

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
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

import PageHeader from '@/components/layout/PageHeader'
import { useConfirm } from '@/hooks/useConfirm'
import type { Snapshot } from '@/hooks/api/snapshotApi'
import { useSnapshotQueries } from '@/hooks/queries/base/useSnapshotQueries'
import { useSnapshotMutations } from '@/hooks/mutations/useSnapshotMutations'
import { formatDateTime } from '@/utils/formatUtils'

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

const columns: ColumnDef<Snapshot, any>[] = [
  {
    accessorKey: 'short_id',
    header: '快照ID',
    size: 100,
    cell: ({ row }) => {
      const snapshot = row.original
      return (
        <Tooltip>
          <TooltipTrigger>
            <Badge variant="outline" className="font-mono bg-blue-50 text-blue-700 border-blue-200">
              {snapshot.short_id}
            </Badge>
          </TooltipTrigger>
          <TooltipContent>完整ID: {snapshot.id}</TooltipContent>
        </Tooltip>
      )
    },
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
    accessorKey: 'paths',
    header: '备份路径',
    cell: ({ row }) => (
      <div className="space-y-1">
        {row.original.paths.map((path, index) => (
          <Badge key={index} variant="outline" className="font-mono text-xs">
            {path}
          </Badge>
        ))}
      </div>
    ),
  },
  {
    accessorKey: 'program_version',
    header: '版本信息',
    size: 120,
    cell: ({ row }) => {
      const version = row.original.program_version
      return version ? (
        <Badge variant="outline" className="text-xs bg-green-50 text-green-700 border-green-200">
          {version}
        </Badge>
      ) : (
        <span className="text-xs text-muted-foreground">-</span>
      )
    },
  },
]

const Snapshots: React.FC = () => {
  const { useGlobalSnapshots, useSnapshotLocks } = useSnapshotQueries()
  const { useCreateGlobalSnapshot, useDeleteSnapshot, useUnlockRepository } = useSnapshotMutations()

  const [sorting, setSorting] = useState<SortingState>([{ id: 'time', desc: true }])

  // Unlock dialog state
  const [unlockModalVisible, setUnlockModalVisible] = useState(false)
  const [locksInfo, setLocksInfo] = useState<string>('')
  const [unlockOutput, setUnlockOutput] = useState<string>('')
  const [isLoadingLocks, setIsLoadingLocks] = useState(false)

  const { confirm, ConfirmDialog } = useConfirm()

  const {
    data: snapshots = [],
    isLoading,
    isError,
    error,
    refetch,
  } = useGlobalSnapshots()
  const { refetch: refetchSnapshotLocks } = useSnapshotLocks(false)

  const createSnapshotMutation = useCreateGlobalSnapshot()
  const deleteSnapshotMutation = useDeleteSnapshot()
  const unlockMutation = useUnlockRepository()

  const actionColumn: ColumnDef<Snapshot, any> = useMemo(() => ({
    id: 'actions',
    header: '操作',
    size: 100,
    cell: ({ row }) => (
      <Button
        variant="destructive"
        size="sm"
        onClick={() =>
          confirm({
            title: '删除快照',
            description: `确定要删除此快照吗？快照ID: ${row.original.short_id}`,
            confirmText: '确认删除',
            cancelText: '取消',
            variant: 'destructive',
            onConfirm: async () => { await deleteSnapshotMutation.mutateAsync(row.original.id) },
          })
        }
      >
        <Trash2 className="mr-1 h-3.5 w-3.5" />
        删除
      </Button>
    ),
  }), [confirm, deleteSnapshotMutation])

  const allColumns = useMemo(() => [...columns, actionColumn], [actionColumn])

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
    initialState: { pagination: { pageSize: 20 } },
  })

  const pageIndex = table.getState().pagination.pageIndex
  const pageSize = table.getState().pagination.pageSize
  const totalRows = table.getFilteredRowModel().rows.length
  const start = totalRows === 0 ? 0 : pageIndex * pageSize + 1
  const end = Math.min((pageIndex + 1) * pageSize, totalRows)

  const handleCreateSnapshot = () => {
    createSnapshotMutation.mutate()
  }

  const handleUnlockClick = async () => {
    setIsLoadingLocks(true)
    setUnlockOutput('')

    try {
      const { data } = await refetchSnapshotLocks()
      if (!data) {
        throw new Error('未获取到锁信息')
      }
      setLocksInfo(data.locks)
      setUnlockModalVisible(true)
    } catch (err: any) {
      toast.error('获取锁信息失败', { description: err?.message || '未知错误' })
    } finally {
      setIsLoadingLocks(false)
    }
  }

  const handleUnlock = () => {
    confirm({
      title: '确认解锁',
      description: '确定要解锁 Restic 仓库吗？这将移除所有陈旧的锁。',
      confirmText: '确认解锁',
      cancelText: '取消',
      variant: 'destructive',
      onConfirm: async () => {
        const data = await unlockMutation.mutateAsync(undefined)
        setUnlockOutput(data.output)
        toast.success('解锁成功', { description: data.message })
      },
    })
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="快照管理"
        icon={<History />}
        actions={
          <>
            <Button
              variant="destructive"
              onClick={handleUnlockClick}
              disabled={isLoadingLocks}
            >
              {isLoadingLocks ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Unlock className="mr-1 h-4 w-4" />}
              解锁仓库
            </Button>
            <Button
              variant="outline"
              onClick={() => refetch()}
              disabled={isLoading}
            >
              <RotateCw className="mr-1 h-4 w-4" />
              刷新
            </Button>
            <Button
              onClick={handleCreateSnapshot}
              disabled={createSnapshotMutation.isPending}
            >
              {createSnapshotMutation.isPending ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Plus className="mr-1 h-4 w-4" />}
              创建全局快照
            </Button>
          </>
        }
      />

      {isError && (
        <Alert variant="destructive">
          <AlertTitle>加载快照列表失败</AlertTitle>
          <AlertDescription className="flex items-center justify-between">
            <span>{(error as any)?.message || '发生未知错误'}</span>
            <Button size="sm" variant="outline" onClick={() => refetch()}>
              重试
            </Button>
          </AlertDescription>
        </Alert>
      )}

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Server className="h-5 w-5" />
              <CardTitle className="text-base">快照列表</CardTitle>
              <span className="text-sm text-muted-foreground font-normal">
                ({snapshots.length} 个快照)
              </span>
            </div>
            <CardDescription>
              显示所有服务器的快照记录
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent>
          {isLoading ? (
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
                        <TableCell colSpan={allColumns.length} className="h-24 text-center">
                          <div className="py-8">
                            <Server className="mx-auto h-10 w-10 text-muted-foreground/30 mb-2" />
                            <div className="text-muted-foreground">暂无快照数据</div>
                            <div className="text-muted-foreground/70 text-sm mt-1">
                              点击&ldquo;创建全局快照&rdquo;开始备份服务器数据
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
                        {[10, 20, 50, 100].map(size => (
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
        </CardContent>
      </Card>

      {/* Unlock repository dialog */}
      <Dialog open={unlockModalVisible} onOpenChange={setUnlockModalVisible}>
        <DialogContent className="sm:max-w-175">
          <DialogHeader>
            <DialogTitle>解锁 Restic 仓库</DialogTitle>
            <DialogDescription>查看并管理 Restic 仓库锁</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <span className="font-semibold text-sm">当前锁信息：</span>
              <pre className="mt-2 p-3 bg-muted rounded-md border overflow-auto max-h-60 text-sm">
                {locksInfo || '无锁信息'}
              </pre>
            </div>

            {unlockOutput && (
              <div>
                <span className="font-semibold text-sm text-green-600">解锁输出：</span>
                <pre className="mt-2 p-3 bg-green-50 rounded-md border border-green-200 overflow-auto max-h-60 text-sm">
                  {unlockOutput}
                </pre>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setUnlockModalVisible(false)}>
              取消
            </Button>
            <Button
              variant="destructive"
              onClick={handleUnlock}
              disabled={unlockMutation.isPending || unlockOutput !== ''}
            >
              {unlockMutation.isPending && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
              解锁
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog />
    </div>
  )
}

export default Snapshots
