import type { ReactNode } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { flexRender, type Row, type Table as TanstackTable } from '@tanstack/react-table'

import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
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
import { cn } from '@/lib/utils'

interface DataTableProps<TData> {
  table: TanstackTable<TData>
  isLoading?: boolean
  emptyMessage?: ReactNode
  /**
   * Number of columns used for the empty-row colSpan.
   * Defaults to the table's visible leaf column count.
   */
  columnCount?: number
  /** Applied to each body row (ignored for the empty row). */
  rowClassName?: string | ((row: Row<TData>) => string)
  onRowClick?: (row: Row<TData>) => void
  onRowDoubleClick?: (row: Row<TData>) => void
  /** Adds `style={{ width }}` to headers based on `column.getSize()`. */
  useColumnSizing?: boolean
  /** Render pagination footer. Default: true. */
  enablePagination?: boolean
  pageSizeOptions?: number[]
  /** Suffix for the "start-end 共 total X" label. Default: "条". */
  rowLabel?: string
  /** Footer style: "full" (icon buttons + page-size select) or "compact" (text buttons only, no select). */
  paginationVariant?: 'full' | 'compact'
  className?: string
}

export function DataTable<TData>({
  table,
  isLoading,
  emptyMessage = '暂无数据',
  columnCount,
  rowClassName,
  onRowClick,
  onRowDoubleClick,
  useColumnSizing,
  enablePagination = true,
  pageSizeOptions = [10, 20, 50, 100],
  rowLabel = '条',
  paginationVariant = 'full',
  className,
}: DataTableProps<TData>) {
  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Spinner className="size-8" />
      </div>
    )
  }

  const colSpan = columnCount ?? table.getVisibleLeafColumns().length
  const rows = table.getRowModel().rows

  return (
    <div className={className}>
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <TableHead
                    key={header.id}
                    style={
                      useColumnSizing && header.column.getSize()
                        ? { width: header.column.getSize() }
                        : undefined
                    }
                  >
                    {header.isPlaceholder
                      ? null
                      : flexRender(header.column.columnDef.header, header.getContext())}
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {rows.length ? (
              rows.map((row) => {
                const cls =
                  typeof rowClassName === 'function' ? rowClassName(row) : rowClassName
                return (
                  <TableRow
                    key={row.id}
                    data-state={row.getIsSelected() ? 'selected' : undefined}
                    className={cn(
                      (onRowClick || onRowDoubleClick) && 'cursor-pointer',
                      cls
                    )}
                    onClick={onRowClick ? () => onRowClick(row) : undefined}
                    onDoubleClick={onRowDoubleClick ? () => onRowDoubleClick(row) : undefined}
                  >
                    {row.getVisibleCells().map((cell) => (
                      <TableCell key={cell.id}>
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </TableCell>
                    ))}
                  </TableRow>
                )
              })
            ) : (
              <TableRow>
                <TableCell colSpan={colSpan} className="h-24 text-center text-muted-foreground">
                  {emptyMessage}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      {enablePagination && (
        <DataTablePagination
          table={table}
          pageSizeOptions={pageSizeOptions}
          rowLabel={rowLabel}
          variant={paginationVariant}
        />
      )}
    </div>
  )
}

interface DataTablePaginationProps<TData> {
  table: TanstackTable<TData>
  pageSizeOptions?: number[]
  rowLabel?: string
  variant?: 'full' | 'compact'
}

export function DataTablePagination<TData>({
  table,
  pageSizeOptions = [10, 20, 50, 100],
  rowLabel = '条',
  variant = 'full',
}: DataTablePaginationProps<TData>) {
  const { pageIndex, pageSize } = table.getState().pagination
  const totalRows = table.getCoreRowModel().rows.length
  if (totalRows === 0) return null

  const start = pageIndex * pageSize + 1
  const end = Math.min((pageIndex + 1) * pageSize, totalRows)

  if (variant === 'compact') {
    if (table.getPageCount() <= 1) return null
    return (
      <div className="flex items-center justify-between pt-3">
        <span className="text-sm text-muted-foreground">
          共 {totalRows} {rowLabel}
        </span>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => table.previousPage()}
            disabled={!table.getCanPreviousPage()}
          >
            上一页
          </Button>
          <span className="text-sm text-muted-foreground">
            {pageIndex + 1} / {table.getPageCount()}
          </span>
          <Button
            variant="outline"
            size="sm"
            onClick={() => table.nextPage()}
            disabled={!table.getCanNextPage()}
          >
            下一页
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="flex items-center justify-between pt-3">
      <span className="text-sm text-muted-foreground">
        {start}-{end} 共 {totalRows} {rowLabel}
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
            {pageSizeOptions.map((size) => (
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
  )
}

export default DataTable
