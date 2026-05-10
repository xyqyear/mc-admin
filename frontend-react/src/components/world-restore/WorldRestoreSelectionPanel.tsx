import React, { useMemo, useState } from 'react'
import {
  Camera,
  ClipboardList,
  History as HistoryIcon,
  Loader2,
  RotateCcw,
} from 'lucide-react'
import { Tabs as TabsPrimitive } from '@base-ui/react/tabs'

import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
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
  regionDirRelpath: string | null
  selection: Set<ChunkKey>
  mode: WorldRestoreSelectionMode
  // Mode toggle is URL-driven; the panel only signals the change up.
  onModeChange: (mode: WorldRestoreSelectionMode) => void
  serverStopped: boolean
}

export const WorldRestoreSelectionPanel: React.FC<
  WorldRestoreSelectionPanelProps
> = ({
  serverId,
  regionDirRelpath,
  selection,
  mode,
  onModeChange,
  serverStopped,
}) => {
  const stats = useMemo(() => computeSelectionStats(selection), [selection])
  const { confirm, confirmDialog } = useConfirm()
  const setMode = useWorldRestoreSelectionStore((s) => s.setMode)
  const { useCreateWorldSnapshot } = useWorldRestoreMutations()
  const createSnapshot = useCreateWorldSnapshot(serverId)

  const [pickerOpen, setPickerOpen] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [pickerSelection, setPickerSelection] =
    useState<RestorationSelection | null>(null)

  // Chunk ↔ region isn't safely bidirectional, so `setMode` wipes the selection.
  const handleModeChange = (next: WorldRestoreSelectionMode) => {
    if (next === mode) return
    setMode(serverId, next)
    onModeChange(next)
  }

  // WORLD scope spans every valid root, so no per-root identifier is needed.
  const dimensionReady = !!regionDirRelpath
  const layoutReady = dimensionReady
  const hasSelection = stats.chunkCount > 0
  const isComplete = mode === 'region' ? stats.fullRegionCount > 0 : hasSelection

  // Manual snapshots cover only dimension/world; narrower scopes are taken
  // automatically as safety snapshots before a rollback.
  const startCreate = (
    scope: 'world' | 'dimension',
    description: string,
  ) => {
    const sel = buildSelection({
      scope,
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
    const sel = buildSelection({
      scope,
      regionDirRelpath,
      selection,
    })
    setPickerSelection(sel)
    setPickerOpen(true)
  }

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
            <TabsList className="w-full relative">
              <TabsPrimitive.Indicator
                className="absolute left-0 top-0 z-0 rounded-md bg-background shadow-sm pointer-events-none translate-x-(--active-tab-left) translate-y-(--active-tab-top) w-(--active-tab-width) h-(--active-tab-height) transition-[translate,width,height] duration-300 ease-out dark:bg-input/30 dark:border dark:border-input"
              />
              <TabsTrigger
                value="region"
                className="flex-1 relative z-10 data-active:bg-transparent data-active:shadow-none dark:data-active:bg-transparent dark:data-active:border-transparent"
              >
                区域选择
              </TabsTrigger>
              <TabsTrigger
                value="chunk"
                className="flex-1 relative z-10 data-active:bg-transparent data-active:shadow-none dark:data-active:bg-transparent dark:data-active:border-transparent"
              >
                区块选择
              </TabsTrigger>
            </TabsList>
            <TabsContent value="region" className="mt-2 text-xs text-muted-foreground">
              按住 Ctrl 选择，右键取消。拖动可框选
            </TabsContent>
            <TabsContent value="chunk" className="mt-2 text-xs text-muted-foreground">
              按住 Ctrl 框选，右键取消。拖动可框选
            </TabsContent>
          </Tabs>
        </div>

        <div className="space-y-2">
          <div className="font-medium">创建快照</div>
          <Button
            variant="outline"
            size="sm"
            className="w-full justify-start"
            disabled={!dimensionReady || createSnapshot.isPending}
            onClick={() =>
              startCreate(
                'dimension',
                `将为当前维度 ${regionDirRelpath ?? ''} 创建快照。`,
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
                '将为该服务器的所有世界创建快照。',
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
          <Separator />
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
