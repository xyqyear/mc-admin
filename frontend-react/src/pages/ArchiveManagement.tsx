import React, { useState, useMemo } from 'react'
import { toast } from 'sonner'
import {
  Trash2,
  Download,
  Upload,
  File,
  Folder,
  FileArchive,
  Pencil,
} from 'lucide-react'
import {
  type ColumnDef,
  type SortingState,
  type RowSelectionState,
  getCoreRowModel,
  getSortedRowModel,
  getPaginationRowModel,
  useReactTable,
} from '@tanstack/react-table'

import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { Checkbox } from '@/components/ui/checkbox'

import PageHeader from '@/components/layout/PageHeader'
import { DataTable } from '@/components/common/DataTable'
import { SortableHeader } from '@/components/common/SortableHeader'
import { RefreshButton } from '@/components/common/RefreshButton'
import DragDropOverlay from '@/components/server/DragDropOverlay'
import ArchiveUploadDialog from '@/components/dialogs/ArchiveUploadDialog'
import ArchiveRenameDialog from '@/components/dialogs/ArchiveRenameDialog'
import { useConfirm } from '@/hooks/useConfirm'
import { useArchiveQueries } from '@/hooks/queries/base/useArchiveQueries'
import { useArchiveMutations } from '@/hooks/mutations/useArchiveMutations'
import { formatFileSize, formatDate, naturalCompare } from '@/utils/formatUtils'
import { usePageDragUpload } from '@/hooks/usePageDragUpload'
import type { ArchiveFileItem } from '@/hooks/api/archiveApi'

const ArchiveManagement: React.FC = () => {
  const { confirm, confirmDialog } = useConfirm()

  const { useArchiveFileList } = useArchiveQueries()
  const { useDeleteItem, downloadFile } = useArchiveMutations()

  const { data: fileData, isLoading, isFetching, refetch } = useArchiveFileList()
  const archiveFiles = useMemo(() => fileData?.items || [], [fileData?.items])

  const deleteItemMutation = useDeleteItem()

  const [rowSelection, setRowSelection] = useState<RowSelectionState>({})
  const [isUploadDialogOpen, setIsUploadDialogOpen] = useState(false)
  const [dragDropFiles, setDragDropFiles] = useState<File[] | undefined>(undefined)
  const [renamingFile, setRenamingFile] = useState<ArchiveFileItem | null>(null)

  const [sorting, setSorting] = useState<SortingState>([
    { id: 'modified_at', desc: true },
  ])
  const [pagination, setPagination] = useState({ pageIndex: 0, pageSize: 20 })

  const { isDragging, isScanning } = usePageDragUpload({
    accept: '.zip,.7z',
    onFileDrop: (files) => {
      setDragDropFiles(files)
      setIsUploadDialogOpen(true)
      toast.info(`已选择 ${files.length} 个压缩包文件，请确认上传`)
    },
    onError: (errorMessage) => {
      toast.error(errorMessage)
    },
  })

  const handleDownload = async (file: ArchiveFileItem) => {
    await downloadFile(file.path, file.name)
  }

  const handleDelete = (file: ArchiveFileItem) => {
    confirm({
      title: '确认删除',
      description: `确定要删除 ${file.name} 吗？`,
      confirmText: '确定',
      cancelText: '取消',
      variant: 'destructive',
      onConfirm: async () => {
        await deleteItemMutation.mutateAsync(file.path)
      },
    })
  }

  const selectedPaths = useMemo(() => {
    return Object.keys(rowSelection)
      .filter(key => rowSelection[key])
      .map(idx => archiveFiles[Number(idx)]?.path)
      .filter(Boolean) as string[]
  }, [rowSelection, archiveFiles])

  const handleBulkDelete = () => {
    if (selectedPaths.length === 0) {
      toast.warning('请选择要删除的文件')
      return
    }
    confirm({
      title: '确认删除',
      description: `确定要删除选中的 ${selectedPaths.length} 个文件吗？`,
      confirmText: '确定',
      cancelText: '取消',
      variant: 'destructive',
      onConfirm: async () => {
        for (const filePath of selectedPaths) {
          await deleteItemMutation.mutateAsync(filePath)
        }
        setRowSelection({})
      },
    })
  }

  const handleRefresh = async () => {
    try {
      await refetch()
      toast.success('刷新成功')
    } catch {
      toast.error('刷新失败')
    }
  }

  const columns: ColumnDef<ArchiveFileItem, any>[] = [
    {
      id: 'select',
      header: ({ table }) => (
        <Checkbox
          checked={table.getIsAllPageRowsSelected()}
          onCheckedChange={(value) => table.toggleAllPageRowsSelected(!!value)}
        />
      ),
      cell: ({ row }) => (
        <Checkbox
          checked={row.getIsSelected()}
          onCheckedChange={(value) => row.toggleSelected(!!value)}
        />
      ),
      enableSorting: false,
      size: 40,
    },
    {
      accessorKey: 'name',
      header: ({ column }) => <SortableHeader column={column} title="文件名" />,
      cell: ({ row }) => {
        const file = row.original
        const isDirectory = file.type === 'directory'
        return (
          <div className="flex items-center gap-2">
            {isDirectory ? (
              <Folder className="h-4 w-4 text-blue-500 shrink-0" />
            ) : (
              <File className="h-4 w-4 text-green-500 shrink-0" />
            )}
            <span className="font-medium">{file.name}</span>
          </div>
        )
      },
      sortingFn: (a, b) => {
        if (a.original.type !== b.original.type) {
          return a.original.type === 'directory' ? -1 : 1
        }
        return naturalCompare(a.original.name, b.original.name)
      },
    },
    {
      accessorKey: 'size',
      header: ({ column }) => <SortableHeader column={column} title="大小" />,
      size: 90,
      cell: ({ row }) =>
        row.original.type === 'file' ? formatFileSize(row.original.size) : '-',
    },
    {
      accessorKey: 'modified_at',
      header: ({ column }) => <SortableHeader column={column} title="修改时间" />,
      size: 150,
      cell: ({ row }) => formatDate(row.original.modified_at),
    },
    {
      id: 'actions',
      header: '操作',
      size: 200,
      cell: ({ row }) => {
        const file = row.original
        return (
          <div className="flex items-center gap-1">
            {file.type === 'file' && (
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={() => handleDownload(file)}
                title="下载"
              >
                <Download className="h-4 w-4" />
              </Button>
            )}
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={() => setRenamingFile(file)}
              title="重命名"
            >
              <Pencil className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon-sm"
              className="text-destructive hover:text-destructive"
              onClick={() => handleDelete(file)}
              title="删除"
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
        )
      },
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
    onRowSelectionChange: setRowSelection,
    state: { sorting, pagination, rowSelection },
    autoResetPageIndex: false,
    getRowId: (row) => row.path,
  })

  return (
    <div className="space-y-4">
      <DragDropOverlay
        isDragging={isDragging}
        isScanning={isScanning}
        pageType="archive"
      />

      <PageHeader
        title="压缩包管理"
        icon={<FileArchive className="h-5 w-5" />}
        actions={
          <>
            <Button
              variant="outline"
              onClick={() => { setDragDropFiles(undefined); setIsUploadDialogOpen(true) }}
            >
              <Upload className="mr-2 h-4 w-4" />
              上传文件
            </Button>
            <RefreshButton onClick={handleRefresh} isRefreshing={isFetching} />
            {selectedPaths.length > 0 && (
              <Button
                variant="destructive"
                onClick={handleBulkDelete}
                disabled={deleteItemMutation.isPending}
              >
                <Trash2 className="mr-2 h-4 w-4" />
                批量删除 ({selectedPaths.length})
              </Button>
            )}
          </>
        }
      />

      <Card>
        <CardContent className="pt-6">
          <DataTable
            table={table}
            isLoading={isLoading}
            rowLabel="个文件"
            emptyMessage="暂无文件"
          />
        </CardContent>
      </Card>

      <Alert>
        <AlertTitle>压缩包管理说明</AlertTitle>
        <AlertDescription>
          您可以上传、下载、重命名和删除压缩包。上传完成后会自动进行 SHA256 完整性校验。
        </AlertDescription>
      </Alert>

      <ArchiveUploadDialog
        open={isUploadDialogOpen}
        onClose={() => { setIsUploadDialogOpen(false); setDragDropFiles(undefined) }}
        initialFiles={dragDropFiles}
      />

      <ArchiveRenameDialog
        open={!!renamingFile}
        file={renamingFile}
        onClose={() => setRenamingFile(null)}
      />

      {confirmDialog}
    </div>
  )
}

export default ArchiveManagement
