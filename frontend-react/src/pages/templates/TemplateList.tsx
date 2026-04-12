import React, { useState } from "react"
import { useNavigate } from "react-router-dom"
import {
  FileText,
  Plus,
  RefreshCw,
  Pencil,
  Trash2,
  Copy,
  Settings,
  ChevronLeft,
  ChevronRight,
  ArrowUpDown,
} from "lucide-react"
import {
  type ColumnDef,
  type SortingState,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  getPaginationRowModel,
  useReactTable,
} from "@tanstack/react-table"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Spinner } from "@/components/ui/spinner"
import {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
} from "@/components/ui/tooltip"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

import PageHeader from "@/components/layout/PageHeader"
import { useConfirm } from "@/hooks/useConfirm"
import { useTemplates } from "@/hooks/queries/base/useTemplateQueries"
import { useTemplateMutations } from "@/hooks/mutations/useTemplateMutations"
import type { TemplateListItem } from "@/hooks/api/templateApi"

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

const TemplateList: React.FC = () => {
  const navigate = useNavigate()
  const { confirm, confirmDialog } = useConfirm()

  const {
    data: templates = [],
    isLoading,
    error,
    refetch,
  } = useTemplates()

  const { useDeleteTemplate } = useTemplateMutations()
  const deleteMutation = useDeleteTemplate()

  const [sorting, setSorting] = useState<SortingState>([])
  const [pagination, setPagination] = useState({ pageIndex: 0, pageSize: 10 })

  const handleCreate = () => navigate("/templates/new")
  const handleCopyCreate = (templateId: number) => navigate(`/templates/new?copyFrom=${templateId}`)
  const handleEdit = (templateId: number) => navigate(`/templates/${templateId}/edit`)

  const handleDelete = (template: TemplateListItem) => {
    confirm({
      title: '删除模板',
      description: `确定要删除模板 "${template.name}" 吗？此操作不可恢复。`,
      confirmText: '确认删除',
      cancelText: '取消',
      variant: 'destructive',
      onConfirm: async () => {
        await deleteMutation.mutateAsync(template.id)
      },
    })
  }

  const columns: ColumnDef<TemplateListItem, any>[] = [
    {
      accessorKey: 'name',
      header: ({ column }) => <SortableHeader column={column} title="模板名称" />,
      cell: ({ row }) => <span className="font-semibold">{row.original.name}</span>,
    },
    {
      accessorKey: 'description',
      header: '描述',
      cell: ({ row }) => (
        <span className="text-muted-foreground">{row.original.description || "-"}</span>
      ),
    },
    {
      accessorKey: 'variable_count',
      header: '变量数量',
      size: 120,
      cell: ({ row }) => <span>{row.original.variable_count}</span>,
    },
    {
      accessorKey: 'created_at',
      header: ({ column }) => <SortableHeader column={column} title="创建时间" />,
      size: 180,
      cell: ({ row }) => (
        <span className="text-muted-foreground">
          {new Date(row.original.created_at).toLocaleString("zh-CN")}
        </span>
      ),
    },
    {
      id: 'actions',
      header: '操作',
      size: 150,
      cell: ({ row }) => (
        <div className="flex items-center gap-1">
          <Tooltip>
            <TooltipTrigger
              className="inline-flex"
              render={
                <Button
                  variant="ghost"
                  size="icon-sm"
                  onClick={() => handleEdit(row.original.id)}
                />
              }
            >
              <Pencil className="h-4 w-4" />
            </TooltipTrigger>
            <TooltipContent>编辑</TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger
              className="inline-flex"
              render={
                <Button
                  variant="ghost"
                  size="icon-sm"
                  onClick={() => handleCopyCreate(row.original.id)}
                />
              }
            >
              <Copy className="h-4 w-4" />
            </TooltipTrigger>
            <TooltipContent>复制创建</TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger
              className="inline-flex"
              render={
                <Button
                  variant="ghost"
                  size="icon-sm"
                  className="text-destructive hover:text-destructive"
                  onClick={() => handleDelete(row.original)}
                />
              }
            >
              <Trash2 className="h-4 w-4" />
            </TooltipTrigger>
            <TooltipContent>删除</TooltipContent>
          </Tooltip>
        </div>
      ),
    },
  ]

  const table = useReactTable({
    data: templates,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    onSortingChange: setSorting,
    onPaginationChange: setPagination,
    state: { sorting, pagination },
    getRowId: (row) => String(row.id),
  })

  const { pageIndex, pageSize } = table.getState().pagination
  const totalRows = table.getCoreRowModel().rows.length
  const start = totalRows > 0 ? pageIndex * pageSize + 1 : 0
  const end = Math.min((pageIndex + 1) * pageSize, totalRows)

  return (
    <div className="space-y-4">
      <PageHeader title="服务器模板" icon={<FileText className="h-5 w-5" />} />

      <Card>
        <CardContent>
          <div className="flex items-center gap-2 mb-4">
            <Button onClick={handleCreate}>
              <Plus className="mr-1 h-4 w-4" />
              新建模板
            </Button>
            <Button variant="outline" onClick={() => navigate("/templates/default-variables")}>
              <Settings className="mr-1 h-4 w-4" />
              默认变量配置
            </Button>
            <Button variant="outline" onClick={() => refetch()}>
              <RefreshCw className="mr-1 h-4 w-4" />
              刷新
            </Button>
          </div>

          {error ? (
            <div className="text-center py-8 text-muted-foreground">
              加载失败: {error.message}
            </div>
          ) : isLoading ? (
            <div className="flex justify-center py-8">
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
                        <TableCell colSpan={columns.length} className="h-24 text-center text-muted-foreground">
                          <div className="space-y-2">
                            <p>暂无模板</p>
                            <Button onClick={handleCreate}>创建第一个模板</Button>
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
                    {start}-{end} 共 {totalRows} 个模板
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
            </>
          )}
        </CardContent>
      </Card>

      {confirmDialog}
    </div>
  )
}

export default TemplateList
