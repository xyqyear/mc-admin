import React, { useMemo } from 'react'
import {
  type ColumnDef,
  type SortingState,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  getPaginationRowModel,
  useReactTable,
} from '@tanstack/react-table'
import {
  Trash2,
  Download,
  Pencil,
  Archive,
  ArrowUpDown,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Spinner } from '@/components/ui/spinner'
import {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
} from '@/components/ui/tooltip'
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

import { isFileEditable } from '@/config/fileEditingConfig'
import { formatFileSize, formatDate, naturalCompare } from '@/utils/formatUtils'
import FileIcon from '@/components/files/FileIcon'
import FileSnapshotActions from '@/components/files/FileSnapshotActions'
import HighlightedFileName from '@/components/server/HighlightedFileName'
import { useConfirm } from '@/hooks/useConfirm'
import type { FileItem } from '@/types/Server'
import type { MatchResult } from '@/utils/fileSearchUtils'

type FileItemWithMatch = FileItem & { matchResult?: MatchResult }

interface FileTableProps {
  fileData?: { items: FileItemWithMatch[] }
  isLoadingFiles: boolean
  selectedFiles: string[]
  setSelectedFiles: (files: string[]) => void
  currentPage: number
  pageSize: number
  setCurrentPage: (page: number) => void
  setPageSize: (size: number) => void
  serverId: string
  onFileEdit: (file: FileItem) => void
  onFileDelete: (file: FileItem) => void
  onFileDownload: (file: FileItem) => void
  onFileRename: (file: FileItem) => void
  onFolderOpen: (file: FileItem) => void
  onFileCompress: (file: FileItem) => void
  createArchiveMutation: { isPending: boolean }
}

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

const FileTable: React.FC<FileTableProps> = ({
  fileData,
  isLoadingFiles,
  selectedFiles,
  setSelectedFiles,
  currentPage,
  pageSize,
  setCurrentPage,
  setPageSize,
  serverId,
  onFileEdit,
  onFileDelete,
  onFileDownload,
  onFileRename,
  onFolderOpen,
  onFileCompress,
  createArchiveMutation
}) => {
  const { confirm, confirmDialog } = useConfirm()
  const [sorting, setSorting] = React.useState<SortingState>([
    { id: 'name', desc: false }
  ])

  const columns: ColumnDef<FileItemWithMatch, any>[] = useMemo(() => [
    {
      id: 'select',
      header: ({ table }) => (
        <Checkbox
          checked={table.getIsAllPageRowsSelected()}
          indeterminate={table.getIsSomePageRowsSelected() && !table.getIsAllPageRowsSelected()}
          onCheckedChange={(checked) => table.toggleAllPageRowsSelected(checked === true)}
        />
      ),
      cell: ({ row }) => (
        <Checkbox
          checked={row.getIsSelected()}
          onCheckedChange={(checked) => row.toggleSelected(checked === true)}
        />
      ),
      size: 40,
      enableSorting: false,
    },
    {
      accessorKey: 'name',
      header: ({ column }) => <SortableHeader column={column} title="文件名" />,
      sortingFn: (a, b) => {
        if (a.original.type !== b.original.type) {
          return a.original.type === 'directory' ? -1 : 1
        }
        return naturalCompare(a.original.name, b.original.name)
      },
      cell: ({ row }) => {
        const file = row.original
        const isEditable = isFileEditable(file.name)
        const isDirectory = file.type === 'directory'

        return (
          <div className="flex items-center gap-2">
            <FileIcon file={file} />
            <Tooltip>
              <TooltipTrigger
                className="text-left"
                render={
                  <span
                    onClick={() => {
                      if (isDirectory) onFolderOpen(file)
                      else if (isEditable) onFileEdit(file)
                    }}
                  />
                }
              >
                <HighlightedFileName
                  name={file.name}
                  matchResult={file.matchResult}
                  className={
                    isDirectory ? 'font-medium cursor-pointer hover:text-blue-600' :
                      isEditable ? 'font-medium cursor-pointer text-blue-600 hover:text-blue-800' :
                        'font-medium'
                  }
                />
              </TooltipTrigger>
              {(isDirectory || isEditable) && (
                <TooltipContent>
                  {isDirectory ? '点击打开文件夹' : '点击编辑文件'}
                </TooltipContent>
              )}
            </Tooltip>
          </div>
        )
      },
    },
    {
      accessorKey: 'size',
      header: '大小',
      size: 90,
      cell: ({ row }) => formatFileSize(row.original.size),
      sortingFn: (a, b) => a.original.size - b.original.size,
    },
    {
      accessorKey: 'modified_at',
      header: '修改时间',
      size: 150,
      cell: ({ row }) => formatDate(row.original.modified_at),
      sortingFn: (a, b) => a.original.modified_at - b.original.modified_at,
    },
    {
      id: 'actions',
      header: '操作',
      size: 200,
      cell: ({ row }) => {
        const file = row.original
        return (
          <div className="flex items-center gap-1">
            <FileSnapshotActions file={file} serverId={serverId} />
            <Tooltip>
              <TooltipTrigger
                className="inline-flex"
                render={
                  <Button
                    variant="outline"
                    size="icon-sm"
                    onClick={() => onFileDownload(file)}
                  />
                }
              >
                <Download className="h-4 w-4" />
              </TooltipTrigger>
              <TooltipContent>下载</TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger
                className="inline-flex"
                render={
                  <Button
                    variant="outline"
                    size="icon-sm"
                    onClick={() => onFileCompress(file)}
                    disabled={createArchiveMutation.isPending}
                  />
                }
              >
                {createArchiveMutation.isPending
                  ? <Spinner className="size-4" />
                  : <Archive className="h-4 w-4" />
                }
              </TooltipTrigger>
              <TooltipContent>压缩</TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger
                className="inline-flex"
                render={
                  <Button
                    variant="outline"
                    size="icon-sm"
                    onClick={() => onFileRename(file)}
                  />
                }
              >
                <Pencil className="h-4 w-4" />
              </TooltipTrigger>
              <TooltipContent>重命名</TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger
                className="inline-flex"
                render={
                  <Button
                    variant="outline"
                    size="icon-sm"
                    className="text-destructive hover:text-destructive"
                    onClick={() =>
                      confirm({
                        title: '确认删除',
                        description: `确定要删除 "${file.name}" 吗？`,
                        confirmText: '确定',
                        cancelText: '取消',
                        variant: 'destructive',
                        onConfirm: async () => onFileDelete(file),
                      })
                    }
                  />
                }
              >
                <Trash2 className="h-4 w-4" />
              </TooltipTrigger>
              <TooltipContent>删除</TooltipContent>
            </Tooltip>
          </div>
        )
      },
    },
  ], [serverId, onFolderOpen, onFileEdit, onFileDownload, onFileCompress, onFileRename, onFileDelete, createArchiveMutation, confirm])

  const data = fileData?.items || []

  const table = useReactTable({
    data,
    columns,
    state: {
      sorting,
      rowSelection: Object.fromEntries(selectedFiles.map(f => [f, true])),
      pagination: { pageIndex: currentPage - 1, pageSize },
    },
    onSortingChange: setSorting,
    onRowSelectionChange: (updater) => {
      const newSelection = typeof updater === 'function'
        ? updater(Object.fromEntries(selectedFiles.map(f => [f, true])))
        : updater
      setSelectedFiles(Object.keys(newSelection).filter(k => newSelection[k]))
    },
    onPaginationChange: (updater) => {
      const newPagination = typeof updater === 'function'
        ? updater({ pageIndex: currentPage - 1, pageSize })
        : updater
      if (newPagination.pageSize !== pageSize) {
        setPageSize(newPagination.pageSize)
        setCurrentPage(1)
      } else {
        setCurrentPage(newPagination.pageIndex + 1)
      }
    },
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    getRowId: (row) => row.path,
    manualPagination: false,
    autoResetPageIndex: false,
  })

  const totalRows = table.getCoreRowModel().rows.length
  const pageIndex = table.getState().pagination.pageIndex
  const start = totalRows === 0 ? 0 : pageIndex * pageSize + 1
  const end = Math.min((pageIndex + 1) * pageSize, totalRows)

  return (
    <>
      {isLoadingFiles ? (
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
                      <TableHead key={header.id} style={header.column.getSize() ? { width: header.column.getSize() } : undefined}>
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
                    <TableRow
                      key={row.id}
                      data-state={row.getIsSelected() && "selected"}
                      onDoubleClick={() => {
                        if (row.original.type === 'directory') {
                          onFolderOpen(row.original)
                        }
                      }}
                    >
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
                      暂无文件
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </div>

          {totalRows > 0 && (
            <div className="flex items-center justify-between pt-3">
              <span className="text-sm text-muted-foreground">
                {start}-{end} 共 {totalRows} 个文件
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
      {confirmDialog}
    </>
  )
}

export default FileTable
