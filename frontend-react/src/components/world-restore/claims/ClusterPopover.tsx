import React from 'react'
import { Popover as PopoverPrimitive } from '@base-ui/react/popover'

import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import type {
  FtbClusterEntry,
  FtbTeamEntry,
  FtbTeamType,
} from '@/types/FtbClaims'
import type { WorldRestoreSelectionMode } from '@/stores/useWorldRestoreSelectionStore'

import { teamColors } from './teamColors'

const TYPE_LABEL: Record<FtbTeamType, string> = {
  player: '玩家',
  party: '队伍',
  server: '服务器',
  unknown: '未知',
}

interface ClusterPopoverProps {
  team: FtbTeamEntry
  cluster: FtbClusterEntry
  anchorEl: HTMLElement
  mode: WorldRestoreSelectionMode
  teamChunksInDim: number
  clustersInDim: number
  onClose: () => void
  onSelectCluster: () => void
  onSelectTeamInDim: () => void
}

export const ClusterPopover: React.FC<ClusterPopoverProps> = ({
  team,
  cluster,
  anchorEl,
  mode,
  teamChunksInDim,
  clustersInDim,
  onClose,
  onSelectCluster,
  onSelectTeamInDim,
}) => {
  const color = teamColors(team.id, team.type)
  const forceCount = cluster.force_loaded.length
  return (
    <PopoverPrimitive.Root
      open
      onOpenChange={(open) => {
        if (!open) onClose()
      }}
    >
      <PopoverPrimitive.Portal>
        <PopoverPrimitive.Positioner
          anchor={anchorEl}
          side="top"
          sideOffset={8}
          className="isolate z-1100"
        >
          <PopoverPrimitive.Popup
            className="z-1100 flex w-72 flex-col gap-3 rounded-lg bg-popover p-3 text-sm text-popover-foreground shadow-lg ring-1 ring-foreground/10 outline-hidden"
          >
            <div className="flex items-start gap-2">
              <span
                aria-hidden
                className="mt-1 inline-block h-3 w-3 shrink-0 rounded-sm"
                style={{ background: color.stroke }}
              />
              <div className="min-w-0 flex-1">
                <div className="truncate font-medium" title={team.display_name}>
                  {team.display_name}
                </div>
                <div className="mt-0.5 flex items-center gap-1.5 text-xs text-muted-foreground">
                  <Badge variant="secondary" className="px-1.5 py-0">
                    {TYPE_LABEL[team.type]}
                  </Badge>
                  <span>·</span>
                  <span>{cluster.chunks.length} 区块</span>
                  {forceCount > 0 && (
                    <>
                      <span>·</span>
                      <span className="text-red-500">{forceCount} 强加载</span>
                    </>
                  )}
                </div>
              </div>
            </div>

            <div className="text-xs text-muted-foreground">
              <div>
                团队在该维度共 {teamChunksInDim} 区块 / {clustersInDim} 个簇
              </div>
              {team.members.length > 0 && (
                <div className="mt-1 truncate" title={team.members.map((m) => m.name ?? m.uuid ?? '?').join(', ')}>
                  成员：{team.members.map((m) => m.name ?? m.uuid ?? '?').join(', ')}
                </div>
              )}
            </div>

            <div className="flex flex-col gap-1.5">
              <Button size="sm" onClick={onSelectCluster}>
                选择此簇（{mode === 'region' ? '按区域' : '按区块'}）
              </Button>
              <Button size="sm" variant="outline" onClick={onSelectTeamInDim}>
                选择该团队在此维度的全部
              </Button>
            </div>
          </PopoverPrimitive.Popup>
        </PopoverPrimitive.Positioner>
      </PopoverPrimitive.Portal>
    </PopoverPrimitive.Root>
  )
}
