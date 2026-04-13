import React, { useState, useMemo } from 'react'
import {
  Copy,
  Eye,
  Settings,
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
import { Spinner } from '@/components/ui/spinner'
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
import { useServerQueries } from '@/hooks/queries/base/useServerQueries'
import type { ServerListItem } from '@/hooks/api/serverApi'

interface ServerTemplateDialogProps {
  open: boolean
  onCancel: () => void
  onSelect: (composeContent: string) => void
  title?: string
  description?: string
  selectButtonText?: string
}

const ServerTemplateDialog: React.FC<ServerTemplateDialogProps> = ({
  open,
  onCancel,
  onSelect,
  title = "选择服务器模板",
  description = "选择现有服务器作为模板，使用其 Docker Compose 配置创建新服务器",
  selectButtonText = "使用模板"
}) => {
  const { useServers, useComposeFile } = useServerQueries()
  const { data: servers, isLoading: serversLoading } = useServers({
    enabled: open
  })

  const [selectedServer, setSelectedServer] = useState<ServerListItem | null>(null)
  const [previewDialogOpen, setPreviewDialogOpen] = useState(false)
  const [sorting, setSorting] = useState<SortingState>([])
  const [pagination, setPagination] = useState({ pageIndex: 0, pageSize: 10 })

  const { data: composeContent, isLoading: composeLoading } = useComposeFile(
    selectedServer?.id || '',
    { enabled: !!selectedServer }
  )

  const handleSelect = () => {
    if (selectedServer && composeContent) {
      onSelect(composeContent)
    }
  }

  const handleCancel = () => {
    setSelectedServer(null)
    setPreviewDialogOpen(false)
    onCancel()
  }

  const handlePreview = (server: ServerListItem) => {
    setSelectedServer(server)
    setPreviewDialogOpen(true)
  }

  const serverList = useMemo(() => servers || [], [servers])

  const columns: ColumnDef<ServerListItem, any>[] = useMemo(() => [
    {
      id: 'radio',
      header: '',
      size: 40,
      cell: ({ row }) => (
        <RadioGroupItem value={row.original.id} />
      ),
      enableSorting: false,
    },
    {
      accessorKey: 'name',
      header: ({ column }) => <SortableHeader column={column} title="服务器名称" />,
      cell: ({ row }) => (
        <div className="flex items-center gap-2">
          <Settings className="h-4 w-4 text-blue-600 shrink-0" />
          <span className="font-medium">{row.original.name}</span>
        </div>
      ),
    },
    {
      accessorKey: 'serverType',
      header: '服务器类型',
      size: 120,
      cell: ({ row }) => (
        <span className="uppercase text-sm">{row.original.serverType}</span>
      ),
    },
    {
      accessorKey: 'javaVersion',
      header: 'Java版本',
      size: 100,
      cell: ({ row }) => (
        <span className="text-sm">Java {row.original.javaVersion}</span>
      ),
    },
    {
      accessorKey: 'gameVersion',
      header: '游戏版本',
      size: 120,
      cell: ({ row }) => (
        <span className="text-sm">{row.original.gameVersion}</span>
      ),
    },
    {
      id: 'actions',
      header: '操作',
      size: 80,
      cell: ({ row }) => (
        <Button
          variant="outline"
          size="sm"
          onClick={(e) => {
            e.stopPropagation()
            handlePreview(row.original)
          }}
        >
          <Eye className="mr-1 h-3.5 w-3.5" />
          预览
        </Button>
      ),
    },
  ], [])

  const table = useReactTable({
    data: serverList,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    onSortingChange: setSorting,
    onPaginationChange: setPagination,
    state: { sorting, pagination },
    getRowId: (row) => row.id,
  })

  return (
    <>
      <Dialog open={open} onOpenChange={(o) => !o && handleCancel()}>
        <DialogContent className="sm:max-w-225 max-h-[85vh] overflow-y-auto" showCloseButton={false}>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Copy className="h-5 w-5" />
              {title}
            </DialogTitle>
          </DialogHeader>

          <div className="space-y-4">
            <Alert>
              <AlertTitle>{description}</AlertTitle>
            </Alert>

            {serverList.length === 0 && !serversLoading && (
              <Alert variant="destructive">
                <AlertTitle>暂无可用服务器</AlertTitle>
                <AlertDescription>没有找到可以作为模板的服务器。请先创建一个服务器后再使用模板功能。</AlertDescription>
              </Alert>
            )}

            <RadioGroup
              value={selectedServer?.id ?? ''}
              onValueChange={(v) => {
                const server = serverList.find(s => s.id === v)
                setSelectedServer(server || null)
              }}
            >
              <DataTable
                table={table}
                isLoading={serversLoading}
                rowLabel="个服务器"
                pageSizeOptions={[10, 20, 50]}
                emptyMessage="暂无服务器"
                onRowClick={(row) => setSelectedServer(row.original)}
              />
            </RadioGroup>

            {selectedServer && (
              <Alert>
                <AlertTitle className="text-green-600">已选择服务器: {selectedServer.name}</AlertTitle>
                <AlertDescription>将使用该服务器的 Docker Compose 配置作为模板创建新服务器</AlertDescription>
              </Alert>
            )}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={handleCancel}>取消</Button>
            <Button
              disabled={!selectedServer || composeLoading}
              onClick={handleSelect}
            >
              {composeLoading && <Spinner className="mr-2 size-4" />}
              {selectButtonText}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={previewDialogOpen} onOpenChange={(o) => !o && setPreviewDialogOpen(false)}>
        <DialogContent className="sm:max-w-200">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Eye className="h-5 w-5" />
              预览 Docker Compose 配置
              {selectedServer && <span className="text-muted-foreground font-normal">- {selectedServer.name}</span>}
            </DialogTitle>
          </DialogHeader>

          <div className="space-y-4">
            {selectedServer && (
              <Alert>
                <AlertTitle>服务器信息: {selectedServer.name}</AlertTitle>
                <AlertDescription>类型: {selectedServer.serverType} | 游戏版本: {selectedServer.gameVersion} | 端口: {selectedServer.gamePort}</AlertDescription>
              </Alert>
            )}

            {composeLoading ? (
              <div className="flex justify-center py-8">
                <Spinner className="size-8" />
              </div>
            ) : composeContent ? (
              <div className="bg-muted p-4 rounded border">
                <pre className="text-sm overflow-auto max-h-96 whitespace-pre-wrap">
                  {composeContent}
                </pre>
              </div>
            ) : (
              <Alert variant="destructive">
                <AlertTitle>无法加载配置文件</AlertTitle>
                <AlertDescription>该服务器的 Docker Compose 配置文件不存在或无法访问。</AlertDescription>
              </Alert>
            )}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setPreviewDialogOpen(false)}>关闭</Button>
            <Button
              disabled={!composeContent || composeLoading}
              onClick={() => {
                setPreviewDialogOpen(false)
                handleSelect()
              }}
            >
              {composeLoading && <Spinner className="mr-2 size-4" />}
              使用此模板
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}

export default ServerTemplateDialog
