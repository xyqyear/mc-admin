import React, { useMemo } from 'react'
import {
  type ColumnDef,
  type SortingState,
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
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Spinner } from '@/components/ui/spinner'
import {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
} from '@/components/ui/tooltip'

import { DataTable } from '@/components/common/DataTable'
import { SortableHeader } from '@/components/common/SortableHeader'
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

  return (
    <>
      <DataTable
        table={table}
        isLoading={isLoadingFiles}
        rowLabel="个文件"
        emptyMessage="暂无文件"
        useColumnSizing
        onRowDoubleClick={(row) => {
          if (row.original.type === 'directory') {
            onFolderOpen(row.original)
          }
        }}
      />
      {confirmDialog}
    </>
  )
}

export default FileTable
