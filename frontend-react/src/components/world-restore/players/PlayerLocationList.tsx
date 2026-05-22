import React, { useMemo } from 'react'
import { RefreshCw } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Spinner } from '@/components/ui/spinner'
import { Switch } from '@/components/ui/switch'
import { MCAvatar } from '@/components/players/MCAvatar'
import type { PlayerMapProfileResponse } from '@/hooks/api/playerApi'
import type {
  PlayerLocationEntry,
  PlayerLocationsResponse,
} from '@/types/PlayerLocations'
import { cn } from '@/lib/utils'

import {
  formatCoordinate,
  isPlayerOnline,
  normalizedUuidOf,
  playerDisplayName,
  playerLocationKey,
} from './playerLocationDisplay'

interface PlayerLocationListProps {
  data: PlayerLocationsResponse | undefined
  isLoading: boolean
  isError: boolean
  currentDimRelpath: string | null
  dimensionLabelByRelpath: Map<string, string>
  profilesByUuid: ReadonlyMap<string, PlayerMapProfileResponse>
  pendingProfileUuids: ReadonlySet<string>
  onlinePlayerUuids: ReadonlySet<string>
  onlineOnly: boolean
  onlineStatusLoading: boolean
  onlineStatusAvailable: boolean
  overlayVisible: boolean
  onOverlayVisibleChange: (visible: boolean) => void
  onOnlineOnlyChange: (onlineOnly: boolean) => void
  onRefresh: () => void
  onPlayerClick: (player: PlayerLocationEntry) => void
}

export const PlayerLocationList: React.FC<PlayerLocationListProps> = ({
  data,
  isLoading,
  isError,
  currentDimRelpath,
  dimensionLabelByRelpath,
  profilesByUuid,
  pendingProfileUuids,
  onlinePlayerUuids,
  onlineOnly,
  onlineStatusLoading,
  onlineStatusAvailable,
  overlayVisible,
  onOverlayVisibleChange,
  onOnlineOnlyChange,
  onRefresh,
  onPlayerClick,
}) => {
  const onlineFilterActive = onlineOnly && onlineStatusAvailable
  const players = useMemo(() => {
    const list = [...(data?.players ?? [])]
    const visiblePlayers = onlineFilterActive
      ? list.filter((player) => isPlayerOnline(player, onlinePlayerUuids))
      : list
    visiblePlayers.sort((a, b) => {
      const aOnline = isPlayerOnline(a, onlinePlayerUuids) ? 0 : 1
      const bOnline = isPlayerOnline(b, onlinePlayerUuids) ? 0 : 1
      if (aOnline !== bOnline) return aOnline - bOnline
      const aCurrent = a.region_dir_relpath === currentDimRelpath ? 0 : 1
      const bCurrent = b.region_dir_relpath === currentDimRelpath ? 0 : 1
      if (aCurrent !== bCurrent) return aCurrent - bCurrent
      const aProfile = a.uuid ? profilesByUuid.get(a.uuid) : undefined
      const bProfile = b.uuid ? profilesByUuid.get(b.uuid) : undefined
      const aName = playerDisplayName(a, aProfile)
      const bName = playerDisplayName(b, bProfile)
      return aName.localeCompare(bName, undefined, { sensitivity: 'base' })
    })
    return visiblePlayers
  }, [
    data?.players,
    onlineFilterActive,
    onlinePlayerUuids,
    currentDimRelpath,
    profilesByUuid,
  ])

  const allPlayers = data?.players ?? []
  const currentCount = allPlayers.filter(
    (player) => player.region_dir_relpath === currentDimRelpath,
  ).length
  const onlineLocationCount = allPlayers.filter((player) =>
    isPlayerOnline(player, onlinePlayerUuids),
  ).length

  if (isLoading) {
    return (
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-center py-2">
          <Spinner />
        </div>
        {[0, 1, 2].map((n) => (
          <div key={n} className="flex items-center gap-2 rounded border px-2 py-2">
            <Skeleton className="size-8 rounded-sm" />
            <div className="flex flex-1 flex-col gap-1">
              <Skeleton className="h-3 w-24" />
              <Skeleton className="h-3 w-32" />
            </div>
          </div>
        ))}
      </div>
    )
  }

  if (isError) {
    return (
      <div className="text-xs text-destructive">
        加载玩家位置失败
        <Button size="sm" variant="outline" className="ml-2 h-6 px-2" onClick={onRefresh}>
          <RefreshCw className="mr-1 h-3 w-3" /> 重试
        </Button>
      </div>
    )
  }

  if (!data) return null

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-1.5">
          <Switch
            size="sm"
            checked={overlayVisible}
            onCheckedChange={onOverlayVisibleChange}
            aria-label="切换玩家位置图层显示"
            title={overlayVisible ? '隐藏地图上的玩家位置' : '显示地图上的玩家位置'}
          />
          <span className="text-xs text-muted-foreground">在地图上显示</span>
        </div>
        <div className="flex items-center gap-1.5">
          <Switch
            size="sm"
            checked={onlineOnly}
            disabled={!onlineStatusAvailable && !onlineOnly}
            onCheckedChange={onOnlineOnlyChange}
            aria-label="仅显示在线玩家"
            title="仅显示在线玩家"
          />
          <span className="text-xs text-muted-foreground">仅在线玩家</span>
        </div>
        <div className="flex-1" />
        <Badge variant="secondary" className="h-5 px-1.5 text-[10px]">
          {currentCount}/{data.players.length}
        </Badge>
        <Badge variant="outline" className="h-5 px-1.5 text-[10px]">
          在线 {onlineLocationCount}/{data.players.length}
        </Badge>
        {onlineStatusLoading && (
          <Skeleton className="h-5 w-12 rounded-full" />
        )}
        {!onlineStatusLoading && !onlineStatusAvailable && (
          <Badge variant="outline" className="h-5 px-1.5 text-[10px]">
            在线状态不可用
          </Badge>
        )}
        {data.skipped.length > 0 && (
          <Badge variant="outline" className="h-5 px-1.5 text-[10px]">
            跳过 {data.skipped.length}
          </Badge>
        )}
        <Button
          size="icon-sm"
          variant="ghost"
          title="重新解析"
          onClick={onRefresh}
        >
          <RefreshCw className="h-3.5 w-3.5" />
        </Button>
      </div>

      <div className="rounded border bg-background">
        {players.length === 0 ? (
          <div className="py-4 text-center text-xs text-muted-foreground">
            {onlineFilterActive ? '未发现在线玩家位置' : '未发现玩家位置'}
          </div>
        ) : (
          players.map((player) => {
            const online = isPlayerOnline(player, onlinePlayerUuids)
            return (
              <PlayerRow
                key={playerLocationKey(player)}
                player={player}
                isCurrentDim={player.region_dir_relpath === currentDimRelpath}
                isOnline={online}
                onlineStatusAvailable={onlineStatusAvailable}
                dimensionLabelByRelpath={dimensionLabelByRelpath}
                profile={
                  player.uuid ? profilesByUuid.get(player.uuid) : undefined
                }
                profilePending={
                  !!player.uuid && pendingProfileUuids.has(player.uuid)
                }
                onClick={onPlayerClick}
              />
            )
          })
        )}
      </div>
    </div>
  )
}

interface PlayerRowProps {
  player: PlayerLocationEntry
  isCurrentDim: boolean
  isOnline: boolean
  onlineStatusAvailable: boolean
  dimensionLabelByRelpath: Map<string, string>
  profile: PlayerMapProfileResponse | undefined
  profilePending: boolean
  onClick: (player: PlayerLocationEntry) => void
}

const PlayerRow: React.FC<PlayerRowProps> = ({
  player,
  isCurrentDim,
  isOnline,
  onlineStatusAvailable,
  dimensionLabelByRelpath,
  profile,
  profilePending,
  onClick,
}) => {
  const name = playerDisplayName(player, profile)
  const uuid = normalizedUuidOf(player)
  const canNavigate = !!player.region_dir_relpath
  const dimLabel =
    (player.region_dir_relpath &&
      dimensionLabelByRelpath.get(player.region_dir_relpath)) ||
    player.dimension_id

  return (
    <button
      type="button"
      disabled={!canNavigate}
      className={cn(
        'flex w-full items-center gap-2 border-b px-2 py-2 text-left last:border-b-0',
        canNavigate && 'cursor-pointer hover:bg-muted/45',
        !canNavigate && 'cursor-default opacity-45',
        canNavigate && !isCurrentDim && 'opacity-55 hover:opacity-85',
        canNavigate && onlineStatusAvailable && !isOnline && 'opacity-70 hover:opacity-90',
      )}
      title={canNavigate ? '点击定位玩家' : '该维度未匹配到地图目录'}
      onClick={() => canNavigate && onClick(player)}
    >
      <div className="relative shrink-0">
        <MCAvatar avatarBase64={profile?.avatar_base64} size={32} playerName={name} />
        {onlineStatusAvailable && (
          <span
            className={cn(
              'absolute -bottom-0.5 -right-0.5 size-2.5 rounded-full border border-background',
              isOnline ? 'bg-green-500' : 'bg-muted-foreground/45',
            )}
            aria-hidden="true"
          />
        )}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1">
          <span className="truncate text-xs font-medium" title={name}>
            {name}
          </span>
          {profilePending && !profile?.current_name && (
            <Skeleton className="h-3 w-10 shrink-0" />
          )}
        </div>
        <div className="mt-0.5 flex items-center gap-1 text-[10px] text-muted-foreground">
          <span className="truncate" title={dimLabel}>
            {dimLabel}
          </span>
          {!isCurrentDim && canNavigate && (
            <Badge variant="outline" className="h-4 px-1 text-[9px]">
              切换
            </Badge>
          )}
          {!canNavigate && (
            <Badge variant="outline" className="h-4 px-1 text-[9px]">
              未匹配
            </Badge>
          )}
        </div>
        {uuid && (
          <div className="mt-0.5 truncate text-[10px] text-muted-foreground/75">
            {uuid}
          </div>
        )}
      </div>
      <div className="shrink-0 text-right font-mono text-[10px] leading-4 text-muted-foreground">
        <div>X {formatCoordinate(player.pos.x)}</div>
        <div>Y {formatCoordinate(player.pos.y)}</div>
        <div>Z {formatCoordinate(player.pos.z)}</div>
      </div>
    </button>
  )
}
