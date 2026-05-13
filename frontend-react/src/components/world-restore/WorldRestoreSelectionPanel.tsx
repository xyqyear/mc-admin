import React, { useMemo, useState } from 'react'
import {
  Camera,
  ClipboardList,
  History as HistoryIcon,
  Loader2,
  RotateCcw,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { useConfirm } from '@/hooks/useConfirm'
import { useWorldRestoreMutations } from '@/hooks/mutations/useWorldRestoreMutations'
import type { WorldRestoreSelectionMode } from '@/stores/useWorldRestoreSelectionStore'
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
  serverStopped: boolean
}

export const WorldRestoreSelectionPanel: React.FC<
  WorldRestoreSelectionPanelProps
> = ({
  serverId,
  regionDirRelpath,
  selection,
  mode,
  serverStopped,
}) => {
  const stats = useMemo(() => computeSelectionStats(selection), [selection])
  const { confirm, confirmDialog } = useConfirm()
  const { useCreateWorldSnapshot } = useWorldRestoreMutations()
  const createSnapshot = useCreateWorldSnapshot(serverId)

  const [pickerOpen, setPickerOpen] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [pickerSelection, setPickerSelection] =
    useState<RestorationSelection | null>(null)

  const dimensionReady = !!regionDirRelpath
  const layoutReady = dimensionReady
  const hasSelection = stats.chunkCount > 0
  const isComplete = mode === 'region' ? stats.fullRegionCount > 0 : hasSelection

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
    <>
      <div className="flex flex-col gap-4">
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
      </div>
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
    </>
  )
}

export default WorldRestoreSelectionPanel
