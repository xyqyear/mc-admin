import React, { useState, useMemo } from 'react'
import {
  Copy,
  Eye,
  Settings,
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
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

import { useServerQueries } from '@/hooks/queries/base/useServerQueries'
import type { ServerListItem } from '@/hooks/api/serverApi'

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

interface ServerTemplateModalProps {
  open: boolean
  onCancel: () => void
  onSelect: (composeContent: string) => void
  title?: string
  description?: string
  selectButtonText?: string
}

const ServerTemplateModal: React.FC<ServerTemplateModalProps> = ({
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
  const [previewModalVisible, setPreviewModalVisible] = useState(false)
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
    setPreviewModalVisible(false)
    onCancel()
  }

  const handlePreview = (server: ServerListItem) => {
    setSelectedServer(server)
    setPreviewModalVisible(true)
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

  const { pageIndex, pageSize } = table.getState().pagination
  const totalRows = table.getCoreRowModel().rows.length
  const start = totalRows > 0 ? pageIndex * pageSize + 1 : 0
  const end = Math.min((pageIndex + 1) * pageSize, totalRows)

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

            {serversLoading ? (
              <div className="flex justify-center py-8">
                <Spinner className="size-8" />
              </div>
            ) : (
              <RadioGroup
                value={selectedServer?.id ?? ''}
                onValueChange={(v) => {
                  const server = serverList.find(s => s.id === v)
                  setSelectedServer(server || null)
                }}
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
                            onClick={() => setSelectedServer(row.original)}
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
                            {serversLoading ? '加载中...' : '暂无服务器'}
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
                  {start}-{end} 共 {totalRows} 个服务器
                </span>
                <div className="flex items-center gap-2">
                  <Select
                    value={String(pageSize)}
                    onValueChange={(v) => table.setPageSize(Number(v))}
                    itemToStringLabel={(v) => `${v}条/页`}
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

      <Dialog open={previewModalVisible} onOpenChange={(o) => !o && setPreviewModalVisible(false)}>
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
            <Button variant="outline" onClick={() => setPreviewModalVisible(false)}>关闭</Button>
            <Button
              disabled={!composeContent || composeLoading}
              onClick={() => {
                setPreviewModalVisible(false)
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

export default ServerTemplateModal
