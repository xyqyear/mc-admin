import React, { useMemo, useState } from 'react'
import {
  Camera,
  ClipboardList,
  History as HistoryIcon,
  Loader2,
  RotateCcw,
} from 'lucide-react'

import { Button } from '@/shared/ui/button'
import { Separator } from '@/shared/ui/separator'
import { useCreateSnapshot } from '@/features/backups/commands'
import { useSnapshotTarget } from '@/features/backups/queries'
import { SnapshotCreateDialog } from '@/features/backups/ui/SnapshotCreateDialog'
import type { WorldRestoreSelectionMode } from '@/features/world/restore/selectionStore'
import type { ChunkKey } from '@/features/world/map/contracts'
import type { RestorationSelection, SnapshotScope } from '@/features/backups/contracts'

import { buildSelection, computeSelectionStats } from '@/features/world/restore/components/selectionUtils'
import { SnapshotPicker } from '@/features/world/restore/components/SnapshotPicker'
import { RestorationHistoryDrawer } from '@/features/world/restore/components/RestorationHistoryDrawer'

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
  const [createRequest, setCreateRequest] = useState<{ scope: SnapshotScope; label: string } | null>(null)
  const createSnapshot = useCreateSnapshot()

  const [pickerOpen, setPickerOpen] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [pickerSelection, setPickerSelection] =
    useState<RestorationSelection | null>(null)

  const dimensionReady = !!regionDirRelpath
  const layoutReady = dimensionReady
  const hasSelection = stats.chunkCount > 0
  const isComplete = mode === 'region' ? stats.fullRegionCount > 0 : hasSelection

  const worldTarget = useSnapshotTarget({ kind: 'world', server_id: serverId, selection: { type: 'world' } })
  const dimensionTarget = useSnapshotTarget(regionDirRelpath ? { kind: 'world', server_id: serverId, selection: { type: 'dimension', region_dir_relpath: regionDirRelpath } } : null)
  const selectionTarget = useSnapshotTarget(isComplete && regionDirRelpath ? { kind: 'world', server_id: serverId,
    selection: buildSelection({ scope: mode === 'region' ? 'regions' : 'chunks', regionDirRelpath, selection }) } : null)
  const canWorld = worldTarget.data?.allowed === true && !worldTarget.isError
  const canDimension = dimensionTarget.data?.allowed === true && !dimensionTarget.isError
  const canSelection = selectionTarget.data?.allowed === true && !selectionTarget.isError

  const startCreate = (
    scope: 'world' | 'dimension',
    description: string,
  ) => {
    const sel = buildSelection({
      scope,
      regionDirRelpath,
      selection,
    })
    setCreateRequest({ scope: { kind: 'world', server_id: serverId, selection: sel }, label: description })
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
            disabled={!dimensionReady || !canDimension || createSnapshot.isPending}
            onClick={() =>
              startCreate(
                'dimension',
                `当前维度 ${regionDirRelpath ?? ''}`,
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
            disabled={!layoutReady || !canWorld || createSnapshot.isPending}
            onClick={() =>
              startCreate(
                'world',
                '该服务器的所有世界',
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
            disabled={!serverStopped || !isComplete || !canSelection}
            onClick={() => openPicker(mode === 'region' ? 'regions' : 'chunks')}
          >
            <RotateCcw className="mr-2 h-4 w-4" />
            恢复选中范围…
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="w-full justify-start"
            disabled={!serverStopped || !dimensionReady || !canDimension}
            onClick={() => openPicker('dimension')}
          >
            <RotateCcw className="mr-2 h-4 w-4" />
            恢复整个维度…
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="w-full justify-start"
            disabled={!serverStopped || !layoutReady || !canWorld}
            onClick={() => openPicker('world')}
          >
            <RotateCcw className="mr-2 h-4 w-4" />
            恢复整个世界…
          </Button>
        </div>

        {[...new Set([worldTarget, dimensionTarget, selectionTarget].flatMap(query =>
          query.isError ? ['暂时无法检查忽略规则，请稍后重试'] : query.data?.reason ? [query.data.reason]
            : query.data?.skipped_count ? ['所选范围包含忽略目录，创建与恢复会跳过这些内容。'] : []))].map(message =>
          <p key={message} className="text-xs text-muted-foreground">{message}</p>)}
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
      <SnapshotCreateDialog request={createRequest} creation={createSnapshot} onClose={() => setCreateRequest(null)} />
      <SnapshotPicker
        open={pickerOpen}
        hidden={historyOpen}
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
