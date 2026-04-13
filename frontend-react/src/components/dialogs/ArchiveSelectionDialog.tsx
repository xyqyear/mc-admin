import React, { useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  FileArchive,
  File,
  Folder,
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
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'

import { DataTable } from '@/components/common/DataTable'
import { SortableHeader } from '@/components/common/SortableHeader'
import { useArchiveQueries } from '@/hooks/queries/base/useArchiveQueries'
import { formatFileSize, formatDate } from '@/utils/formatUtils'
import type { ArchiveFileItem } from '@/hooks/api/archiveApi'

interface ArchiveSelectionDialogProps {
  open: boolean
  onCancel: () => void
  onSelect: (filename: string) => void
  title?: string
  description?: string
  selectButtonText?: string
  selectButtonType?: 'primary' | 'danger'
}

const ArchiveSelectionDialog: React.FC<ArchiveSelectionDialogProps> = ({
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

          <RadioGroup
            value={selectedFile ?? ''}
            onValueChange={setSelectedFile}
          >
            <DataTable
              table={table}
              isLoading={isLoading}
              rowLabel="个文件"
              pageSizeOptions={[10, 20, 50]}
              emptyMessage="暂无压缩包文件"
              onRowClick={(row) => setSelectedFile(row.original.path)}
            />
          </RadioGroup>

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

export default ArchiveSelectionDialog
