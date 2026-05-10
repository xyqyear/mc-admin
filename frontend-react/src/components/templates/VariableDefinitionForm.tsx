import React, { useState, useCallback, useRef, useMemo } from "react"
import { Search, Plus, Pencil, Trash2, GripVertical } from "lucide-react"
import {
  DndContext,
  closestCenter,
  PointerSensor,
  KeyboardSensor,
  useSensor,
  useSensors,
} from "@dnd-kit/core"
import type { DragEndEvent } from "@dnd-kit/core"
import {
  SortableContext,
  verticalListSortingStrategy,
  arrayMove,
} from "@dnd-kit/sortable"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

import SortableVariableRow from "./SortableVariableRow"
import VariableEditDialog from "./VariableEditDialog"
import { useConfirm } from "@/hooks/useConfirm"
import type { VariableFormData } from "./variableSchemas"

export type { VariableFormData } from "./variableSchemas"

interface VariableDefinitionFormProps {
  value: VariableFormData[]
  onChange: (variables: VariableFormData[]) => void
  disabled?: boolean
  title?: string
}

const TYPE_LABELS: Record<VariableFormData["type"], { label: string; className: string }> = {
  string: { label: "字符串", className: "text-blue-600 border-blue-300" },
  int: { label: "整数", className: "text-green-600 border-green-300" },
  float: { label: "浮点数", className: "text-cyan-600 border-cyan-300" },
  enum: { label: "枚举", className: "text-orange-600 border-orange-300" },
  bool: { label: "布尔值", className: "text-purple-600 border-purple-300" },
}

interface KeyedVariable extends VariableFormData {
  _key: string
}

const VariableDefinitionForm: React.FC<VariableDefinitionFormProps> = ({
  value,
  onChange,
  disabled = false,
  title,
}) => {
  const { confirm, confirmDialog } = useConfirm()
  const [searchText, setSearchText] = useState("")
  const [dialogOpen, setDialogOpen] = useState(false)
  const [dialogMode, setDialogMode] = useState<"add" | "edit">("add")
  const [editingIndex, setEditingIndex] = useState<number>(-1)
  const [editingData, setEditingData] = useState<Partial<VariableFormData> | undefined>()

  const keyCounter = useRef(0)
  const keyMapRef = useRef(new WeakMap<VariableFormData, string>())

  const getKey = useCallback((item: VariableFormData): string => {
    let key = keyMapRef.current.get(item)
    if (!key) {
      key = `var-${keyCounter.current++}`
      keyMapRef.current.set(item, key)
    }
    return key
  }, [])

  const keyedItems: KeyedVariable[] = useMemo(
    () => value.map((v) => ({ ...v, _key: getKey(v) })),
    [value, getKey]
  )

  const isSearching = searchText.trim().length > 0

  const filteredItems = useMemo(() => {
    if (!isSearching) return keyedItems
    const lower = searchText.toLowerCase()
    return keyedItems.filter(
      (v) =>
        v.name.toLowerCase().includes(lower) ||
        (v.display_name ?? "").toLowerCase().includes(lower)
    )
  }, [keyedItems, searchText, isSearching])

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor)
  )

  const handleDragEnd = useCallback(
    (event: DragEndEvent) => {
      const { active, over } = event
      if (!over || active.id === over.id) return
      const oldIndex = keyedItems.findIndex((v) => v._key === active.id)
      const newIndex = keyedItems.findIndex((v) => v._key === over.id)
      if (oldIndex === -1 || newIndex === -1) return
      const reordered = arrayMove([...value], oldIndex, newIndex)
      onChange(reordered)
    },
    [keyedItems, value, onChange]
  )

  const openAddDialog = useCallback(() => {
    setDialogMode("add")
    setEditingIndex(-1)
    setEditingData(undefined)
    setDialogOpen(true)
  }, [])

  const openEditDialog = useCallback(
    (record: KeyedVariable) => {
      const idx = keyedItems.findIndex((v) => v._key === record._key)
      if (idx === -1) return
      const { _key: _unused, ...data } = record
      void _unused
      setDialogMode("edit")
      setEditingIndex(idx)
      setEditingData(structuredClone(data))
      setDialogOpen(true)
    },
    [keyedItems]
  )

  const handleDialogOk = useCallback(
    (data: VariableFormData) => {
      const next = [...value]
      if (dialogMode === "add") {
        next.push(data)
      } else if (editingIndex >= 0) {
        next[editingIndex] = data
      }
      onChange(next)
      setDialogOpen(false)
    },
    [value, onChange, dialogMode, editingIndex]
  )

  const handleDelete = useCallback(
    (record: KeyedVariable) => {
      confirm({
        title: '确认删除',
        description: '确定删除该变量？',
        confirmText: '确定',
        cancelText: '取消',
        variant: 'destructive',
        onConfirm: async () => {
          const idx = keyedItems.findIndex((v) => v._key === record._key)
          if (idx === -1) return
          const next = [...value]
          next.splice(idx, 1)
          onChange(next)
        },
      })
    },
    [keyedItems, value, onChange, confirm]
  )

  const formatDefault = (val: unknown): string => {
    if (val === undefined || val === null) return "-"
    if (typeof val === "boolean") return val ? "true" : "false"
    return String(val)
  }

  const showDragHandle = !disabled && !isSearching
  const showActions = !disabled
  const sortableIds = keyedItems.map((v) => v._key)

  const renderRow = (item: KeyedVariable) => {
    const typeInfo = TYPE_LABELS[item.type]
    const cells = (
      <>
        {showDragHandle && (
          <TableCell className="w-10">
            <GripVertical className="h-4 w-4 text-muted-foreground cursor-grab" />
          </TableCell>
        )}
        <TableCell>
          <code className="text-[13px]">{item.name || <span className="text-muted-foreground">-</span>}</code>
        </TableCell>
        <TableCell>{item.display_name || "-"}</TableCell>
        <TableCell className="w-[90px]">
          {typeInfo ? (
            <Badge variant="outline" className={typeInfo.className}>{typeInfo.label}</Badge>
          ) : item.type}
        </TableCell>
        <TableCell className="max-w-[200px] truncate">{formatDefault(item.default)}</TableCell>
        {showActions && (
          <TableCell className="w-20">
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={() => openEditDialog(item)}
              >
                <Pencil className="h-3.5 w-3.5" />
              </Button>
              <Button
                variant="ghost"
                size="icon-sm"
                className="text-destructive hover:text-destructive"
                onClick={() => handleDelete(item)}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            </div>
          </TableCell>
        )}
      </>
    )

    if (showDragHandle) {
      return (
        <SortableVariableRow
          key={item._key}
          data-row-key={item._key}
          className="border-b transition-colors hover:bg-muted/50"
        >
          {cells}
        </SortableVariableRow>
      )
    }
    return <TableRow key={item._key}>{cells}</TableRow>
  }

  return (
    <div>
      {title && (
        <div className="font-semibold text-[15px] mb-3">{title}</div>
      )}

      <div className="flex justify-between items-center mb-3 gap-3">
        <div className="relative max-w-[300px] flex-1">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="搜索变量名或显示名称"
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            className="pl-8"
          />
        </div>
        {!disabled && (
          <Button onClick={openAddDialog}>
            <Plus className="mr-1 h-4 w-4" />
            添加变量
          </Button>
        )}
      </div>

      {value.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
          <p className="mb-3">暂无变量</p>
          {!disabled && (
            <Button onClick={openAddDialog}>
              <Plus className="mr-1 h-4 w-4" />
              添加变量
            </Button>
          )}
        </div>
      ) : (
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          onDragEnd={handleDragEnd}
        >
          <SortableContext
            items={sortableIds}
            strategy={verticalListSortingStrategy}
          >
            <div className="rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    {showDragHandle && <TableHead className="w-10" />}
                    <TableHead>变量名</TableHead>
                    <TableHead>显示名称</TableHead>
                    <TableHead className="w-[90px]">类型</TableHead>
                    <TableHead>默认值</TableHead>
                    {showActions && <TableHead className="w-20">操作</TableHead>}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredItems.length > 0 ? (
                    filteredItems.map(renderRow)
                  ) : (
                    <TableRow>
                      <TableCell colSpan={showDragHandle ? 6 : 5} className="h-24 text-center text-muted-foreground">
                        无匹配变量
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </div>
          </SortableContext>
        </DndContext>
      )}

      <VariableEditDialog
        open={dialogOpen}
        mode={dialogMode}
        initialData={editingData}
        onOk={handleDialogOk}
        onCancel={() => setDialogOpen(false)}
      />

      {confirmDialog}
    </div>
  )
}

export default VariableDefinitionForm
