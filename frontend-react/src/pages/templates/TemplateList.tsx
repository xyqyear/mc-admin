import React, { useState } from "react"
import { useNavigate } from "react-router-dom"
import { toast } from "sonner"
import {
  FileText,
  Plus,
  Pencil,
  Trash2,
  Copy,
  Settings,
} from "lucide-react"
import {
  type ColumnDef,
  type SortingState,
  getCoreRowModel,
  getSortedRowModel,
  getPaginationRowModel,
  useReactTable,
} from "@tanstack/react-table"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
} from "@/components/ui/tooltip"

import PageHeader from "@/components/layout/PageHeader"
import { DataTable } from "@/components/common/DataTable"
import { SortableHeader } from "@/components/common/SortableHeader"
import { EmptyState } from "@/components/common/EmptyState"
import { RefreshButton } from "@/components/common/RefreshButton"
import { useConfirm } from "@/hooks/useConfirm"
import { useTemplates } from "@/hooks/queries/base/useTemplateQueries"
import { useTemplateMutations } from "@/hooks/mutations/useTemplateMutations"
import type { TemplateListItem } from "@/hooks/api/templateApi"

const TemplateList: React.FC = () => {
  const navigate = useNavigate()
  const { confirm, confirmDialog } = useConfirm()

  const {
    data: templates = [],
    isLoading,
    isFetching,
    error,
    refetch,
  } = useTemplates()

  const handleRefresh = async () => {
    try {
      await refetch()
      toast.success("刷新成功")
    } catch {
      toast.error("刷新失败")
    }
  }

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
            <RefreshButton onClick={handleRefresh} isRefreshing={isFetching} />
          </div>

          {error ? (
            <div className="text-center py-8 text-muted-foreground">
              加载失败: {error.message}
            </div>
          ) : (
            <DataTable
              table={table}
              isLoading={isLoading}
              rowLabel="个模板"
              pageSizeOptions={[10, 20, 50]}
              emptyMessage={
                <EmptyState
                  title="暂无模板"
                  action={<Button onClick={handleCreate}>创建第一个模板</Button>}
                />
              }
            />
          )}
        </CardContent>
      </Card>

      {confirmDialog}
    </div>
  )
}

export default TemplateList
