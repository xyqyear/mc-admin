import React, { useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  FileArchive,
  File,
  Folder,
  ChevronLeft,
  ChevronRight,
  ArrowUpDown,
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
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { Spinner } from '@/components/ui/spinner'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
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
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'

import { useArchiveQueries } from '@/hooks/queries/base/useArchiveQueries'
import { formatFileSize, formatDate } from '@/utils/formatUtils'
import type { ArchiveFileItem } from '@/hooks/api/archiveApi'

interface ArchiveSelectionModalProps {
  open: boolean
  onCancel: () => void
  onSelect: (filename: string) => void
  title?: string
  description?: string
  selectButtonText?: string
  selectButtonType?: 'primary' | 'danger'
}

// --- Sortable header helper ---

function SortableHeader<TData>({
  column,
  title,
}: {
  column: import('@tanstack/react-table').Column<TData>
  title: string
}) {
  return (
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
}

const ArchiveSelectionModal: React.FC<ArchiveSelectionModalProps> = ({
  open,
  onCancel,
  onSelect,
  title = '选择压缩包文件',
  description = '请选择要使用的压缩包文件来创建服务器',
  selectButtonText = '选择文件',
  selectButtonType = 'primary',
}) => {
  const navigate = useNavigate()
  const { useArchiveFileList } = useArchiveQueries()
  const { data: fileData, isLoading } = useArchiveFileList('/', open)

  const [selectedFile, setSelectedFile] = useState<string | null>(null)
  const [sorting, setSorting] = useState<SortingState>([
    { id: 'modified_at', desc: true },
  ])
  const [pagination, setPagination] = useState({ pageIndex: 0, pageSize: 20 })

  const archiveFiles = useMemo(() =>
    (fileData?.items || []).filter(file => {
      const isArchive = file.name.toLowerCase().endsWith('.zip') ||
        file.name.toLowerCase().endsWith('.7z')
      return file.type === 'file' && isArchive
    }),
    [fileData?.items]
  )

  const handleSelect = () => {
    if (selectedFile) {
      onSelect(selectedFile)
    }
  }

  const handleCancel = () => {
    setSelectedFile(null)
    onCancel()
  }

  const handleGoToArchives = () => {
    navigate('/archives')
    handleCancel()
  }

  const columns: ColumnDef<ArchiveFileItem, any>[] = [
    {
      id: 'radio',
      header: '',
      size: 40,
      cell: ({ row }) => (
        <RadioGroupItem value={row.original.path} />
      ),
      enableSorting: false,
    },
    {
      accessorKey: 'name',
      header: ({ column }) => <SortableHeader column={column} title="文件名" />,
      cell: ({ row }) => {
        const name = row.original.name
        const isZip = name.toLowerCase().endsWith('.zip')
        const is7z = name.toLowerCase().endsWith('.7z')
        return (
          <div className="flex items-center gap-2">
            {isZip || is7z ? (
              <FileArchive className="h-4 w-4 text-yellow-500 shrink-0" />
            ) : (
              <File className="h-4 w-4 text-green-500 shrink-0" />
            )}
            <span className="font-medium">{name}</span>
          </div>
        )
      },
      sortingFn: (a, b) =>
        a.original.name.localeCompare(b.original.name, 'zh-CN', { sensitivity: 'base' }),
    },
    {
      accessorKey: 'size',
      header: ({ column }) => <SortableHeader column={column} title="大小" />,
      size: 120,
      cell: ({ row }) => formatFileSize(row.original.size),
    },
    {
      accessorKey: 'modified_at',
      header: ({ column }) => <SortableHeader column={column} title="修改时间" />,
      size: 180,
      cell: ({ row }) => formatDate(row.original.modified_at),
    },
  ]

  const table = useReactTable({
    data: archiveFiles,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    onSortingChange: setSorting,
    onPaginationChange: setPagination,
    state: { sorting, pagination },
    autoResetPageIndex: false,
    getRowId: (row) => row.path,
  })

  const { pageIndex, pageSize } = table.getState().pagination
  const totalRows = table.getCoreRowModel().rows.length
  const start = totalRows > 0 ? pageIndex * pageSize + 1 : 0
  const end = Math.min((pageIndex + 1) * pageSize, totalRows)

  return (
    <Dialog open={open} onOpenChange={(o) => !o && handleCancel()}>
      <DialogContent className="sm:max-w-200 max-h-[85vh] overflow-y-auto" showCloseButton={false}>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileArchive className="h-5 w-5" />
            {title}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <Alert>
            <AlertTitle>{description}</AlertTitle>
          </Alert>

          {archiveFiles.length === 0 && !isLoading && (
            <Alert>
              <AlertTitle>未找到压缩包文件</AlertTitle>
              <AlertDescription>
                没有找到可用的 .zip 或 .7z 压缩包文件。请先上传压缩包文件到归档管理。
              </AlertDescription>
            </Alert>
          )}

          {isLoading ? (
            <div className="flex justify-center py-8">
              <Spinner className="size-8" />
            </div>
          ) : (
            <RadioGroup
              value={selectedFile ?? ''}
              onValueChange={setSelectedFile}
            >
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
                        <TableRow
                          key={row.id}
                          className="cursor-pointer"
                          onClick={() => setSelectedFile(row.original.path)}
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
                          暂无压缩包文件
                        </TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </div>
            </RadioGroup>
          )}

          {totalRows > 0 && (
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">
                {start}-{end} 共 {totalRows} 个文件
              </span>
              <div className="flex items-center gap-2">
                <Select
                  value={String(pageSize)}
                  onValueChange={(v) => table.setPageSize(Number(v))}
                >
                  <SelectTrigger className="w-22.5">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {[10, 20, 50].map(size => (
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

          {selectedFile && (
            <Alert>
              <AlertTitle className="text-green-600">已选择文件: {selectedFile}</AlertTitle>
            </Alert>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={handleGoToArchives}>
            <Folder className="mr-2 h-4 w-4" />
            压缩包管理
          </Button>
          <Button variant="outline" onClick={handleCancel}>
            取消
          </Button>
          <Button
            variant={selectButtonType === 'danger' ? 'destructive' : 'default'}
            disabled={!selectedFile}
            onClick={handleSelect}
          >
            {selectButtonText}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default ArchiveSelectionModal
