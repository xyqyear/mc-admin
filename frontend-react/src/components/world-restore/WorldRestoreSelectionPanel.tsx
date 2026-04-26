import React, { useMemo, useState } from 'react'
import {
  Camera,
  ClipboardList,
  History as HistoryIcon,
  Loader2,
  RotateCcw,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/ui/tabs'
import { useConfirm } from '@/hooks/useConfirm'
import { useWorldRestoreMutations } from '@/hooks/mutations/useWorldRestoreMutations'
import {
  type WorldRestoreSelectionMode,
  useWorldRestoreSelectionStore,
} from '@/stores/useWorldRestoreSelectionStore'
import type { ChunkKey } from '@/types/MapTypes'
import type { RestorationSelection } from '@/types/WorldRestore'

import { buildSelection, computeSelectionStats } from './selectionUtils'
import { SnapshotPicker } from './SnapshotPicker'
import { RestorationHistoryDrawer } from './RestorationHistoryDrawer'

interface WorldRestoreSelectionPanelProps {
  serverId: string
  worldRootName: string | null
  dimensionLabel: string | null
  regionDirRelpath: string | null
  selection: Set<ChunkKey>
  mode: WorldRestoreSelectionMode
  // Mode toggle is URL-driven on the page; the panel only signals the change
  // up. The page persists URL + store.
  onModeChange: (mode: WorldRestoreSelectionMode) => void
  // Mirrors what ServerWorldRestore wires from useWorldRestoreSelectionStore.
  onSelectionChange: (next: Set<ChunkKey>) => void
  serverStopped: boolean
}

// Switching modes can lose data — chunk → region keeps only fully-covered
// regions. We confirm before discarding chunks. Going region → chunk is safe;
// the underlying ChunkKey set is unchanged.
const REGION_FANOUT_WARN_THRESHOLD = 256

export const WorldRestoreSelectionPanel: React.FC<
  WorldRestoreSelectionPanelProps
> = ({
  serverId,
  worldRootName,
  dimensionLabel,
  regionDirRelpath,
  selection,
  mode,
  onModeChange,
  onSelectionChange,
  serverStopped,
}) => {
  const stats = useMemo(() => computeSelectionStats(selection), [selection])
  const { confirm, confirmDialog } = useConfirm()
  const setMode = useWorldRestoreSelectionStore((s) => s.setMode)
  const setSelection = useWorldRestoreSelectionStore((s) => s.setSelection)
  const { useCreateWorldSnapshot } = useWorldRestoreMutations()
  const createSnapshot = useCreateWorldSnapshot(serverId)

  // Snapshot picker / history drawer open state. Keeping the handles here
  // means the side panel can show its own buttons without leaking dialog
  // state to the page.
  const [pickerOpen, setPickerOpen] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [pickerSelection, setPickerSelection] =
    useState<RestorationSelection | null>(null)

  const handleModeChange = (next: WorldRestoreSelectionMode) => {
    if (next === mode) return
    if (next === 'region' && stats.chunkCount > 0) {
      const fullCount = stats.fullRegionCount
      const dropped = stats.regionCount - fullCount
      if (dropped > 0) {
        confirm({
          title: '切换到区域模式',
          description: `当前选中 ${stats.chunkCount} 个区块，覆盖 ${stats.regionCount} 个区域，但只有 ${fullCount} 个区域被完整覆盖。切换后将丢弃未完整覆盖的 ${dropped} 个区域的部分选择。`,
          confirmText: '继续切换',
          variant: 'default',
          onConfirm: () => {
            setMode(serverId, next)
            onModeChange(next)
          },
        })
        return
      }
    }
    if (next === 'chunk' && stats.fullRegionCount > REGION_FANOUT_WARN_THRESHOLD) {
      confirm({
        title: '切换到区块模式',
        description: `当前选中 ${stats.fullRegionCount} 个区域（约 ${stats.fullRegionCount * 1024} 个区块），切换后大量区块将参与渲染，可能影响性能。`,
        confirmText: '继续切换',
        variant: 'default',
        onConfirm: () => {
          setMode(serverId, next)
          onModeChange(next)
        },
      })
      return
    }
    setMode(serverId, next)
    onModeChange(next)
  }

  const layoutReady = !!worldRootName
  const dimensionReady = !!regionDirRelpath
  const hasSelection = stats.chunkCount > 0
  const isComplete = mode === 'region' ? stats.fullRegionCount > 0 : hasSelection

  // Snapshot creation — three scopes. Each one builds a different selection
  // payload and confirms before firing.
  const startCreate = (
    scope: 'world' | 'dimension' | 'regions' | 'chunks',
    description: string,
  ) => {
    if (!worldRootName) return
    const sel = buildSelection({
      scope,
      worldRootName,
      dimensionLabel,
      regionDirRelpath,
      selection,
    })
    confirm({
      title: '创建快照',
      description,
      confirmText: '创建快照',
      variant: 'default',
      onConfirm: async () => {
        await createSnapshot.mutateAsync(sel)
      },
    })
  }

  const openPicker = (scope: 'world' | 'dimension' | 'regions' | 'chunks') => {
    if (!worldRootName) return
    const sel = buildSelection({
      scope,
      worldRootName,
      dimensionLabel,
      regionDirRelpath,
      selection,
    })
    setPickerSelection(sel)
    setPickerOpen(true)
  }

  const clearSelection = () => onSelectionChange(new Set<ChunkKey>())
  void setSelection

  return (
    <Card className="flex flex-col">
      <CardContent className="flex flex-col gap-4 p-4">
        <div>
          <div className="font-medium mb-2">选择模式</div>
          <Tabs
            value={mode}
            onValueChange={(v) => {
              if (v === 'chunk' || v === 'region') handleModeChange(v)
            }}
          >
            <TabsList className="w-full">
              <TabsTrigger value="region" className="flex-1">
                区域选择
              </TabsTrigger>
              <TabsTrigger value="chunk" className="flex-1">
                区块选择
              </TabsTrigger>
            </TabsList>
            <TabsContent value="region" className="mt-2 text-xs text-muted-foreground">
              单击切换整个区域；按住 Shift 拖动框选；右键拖动取消。
            </TabsContent>
            <TabsContent value="chunk" className="mt-2 text-xs text-muted-foreground">
              单击切换单个区块；按住 Shift 拖动框选；右键拖动取消。
            </TabsContent>
          </Tabs>
        </div>

        <div className="rounded-md border bg-muted/30 p-3 text-sm">
          <div className="font-medium mb-1">当前选区</div>
          {hasSelection ? (
            <div className="text-muted-foreground space-y-0.5 tabular-nums">
              <div>
                区块 <span className="text-foreground">{stats.chunkCount}</span> 个
              </div>
              <div>
                覆盖区域 <span className="text-foreground">{stats.regionCount}</span> 个
                （完整 <span className="text-foreground">{stats.fullRegionCount}</span> 个）
              </div>
            </div>
          ) : (
            <div className="text-muted-foreground">未选择任何区块</div>
          )}
          {hasSelection && (
            <Button
              variant="ghost"
              size="sm"
              className="mt-2 h-7 px-2"
              onClick={clearSelection}
            >
              清空选择
            </Button>
          )}
        </div>

        <div className="space-y-2">
          <div className="font-medium">创建快照</div>
          <Button
            variant="outline"
            size="sm"
            className="w-full justify-start"
            disabled={!layoutReady || !isComplete || createSnapshot.isPending}
            onClick={() =>
              startCreate(
                mode === 'region' ? 'regions' : 'chunks',
                mode === 'region'
                  ? `将为选中的 ${stats.fullRegionCount} 个区域创建快照。`
                  : `将为选中的 ${stats.chunkCount} 个区块创建快照。`,
              )
            }
          >
            {createSnapshot.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Camera className="mr-2 h-4 w-4" />
            )}
            选中范围
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="w-full justify-start"
            disabled={!dimensionReady || createSnapshot.isPending}
            onClick={() =>
              startCreate(
                'dimension',
                `将为当前维度 ${dimensionLabel ?? regionDirRelpath ?? ''} 创建快照。`,
              )
            }
          >
            {createSnapshot.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Camera className="mr-2 h-4 w-4" />
            )}
            整个维度
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="w-full justify-start"
            disabled={!layoutReady || createSnapshot.isPending}
            onClick={() =>
              startCreate(
                'world',
                `将为整个世界 ${worldRootName ?? ''} 创建快照。`,
              )
            }
          >
            {createSnapshot.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Camera className="mr-2 h-4 w-4" />
            )}
            整个世界
          </Button>
        </div>

        <div className="space-y-2">
          <div className="font-medium">恢复</div>
          {!serverStopped && (
            <div className="text-xs text-destructive">
              服务器运行中时无法恢复。请先停止服务器。
            </div>
          )}
          <Button
            size="sm"
            className="w-full justify-start"
            disabled={!serverStopped || !isComplete}
            onClick={() => openPicker(mode === 'region' ? 'regions' : 'chunks')}
          >
            <RotateCcw className="mr-2 h-4 w-4" />
            恢复选中范围…
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="w-full justify-start"
            disabled={!serverStopped || !dimensionReady}
            onClick={() => openPicker('dimension')}
          >
            <RotateCcw className="mr-2 h-4 w-4" />
            恢复整个维度…
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="w-full justify-start"
            disabled={!serverStopped || !layoutReady}
            onClick={() => openPicker('world')}
          >
            <RotateCcw className="mr-2 h-4 w-4" />
            恢复整个世界…
          </Button>
        </div>

        <div className="border-t pt-3 space-y-2">
          <Button
            variant="ghost"
            size="sm"
            className="w-full justify-start"
            onClick={() => setHistoryOpen(true)}
          >
            <HistoryIcon className="mr-2 h-4 w-4" />
            查看恢复历史
          </Button>
          <div className="flex items-start gap-2 text-xs text-muted-foreground">
            <ClipboardList className="h-3.5 w-3.5 mt-0.5 shrink-0" />
            <span>
              快照创建会写入服务器 Restic 仓库；恢复前会自动创建一个安全快照以便后续回滚。
            </span>
          </div>
        </div>
      </CardContent>
      {confirmDialog}
      <SnapshotPicker
        open={pickerOpen}
        onOpenChange={setPickerOpen}
        serverId={serverId}
        selection={pickerSelection}
      />
      <RestorationHistoryDrawer
        open={historyOpen}
        onOpenChange={setHistoryOpen}
        serverId={serverId}
        serverStopped={serverStopped}
      />
    </Card>
  )
}

export default WorldRestoreSelectionPanel
