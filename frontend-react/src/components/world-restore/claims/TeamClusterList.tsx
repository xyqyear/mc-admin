import React, { useMemo, useState } from 'react'
import { ChevronDown, ChevronRight, RefreshCw, Search } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Spinner } from '@/components/ui/spinner'
import { Switch } from '@/components/ui/switch'
import { Badge } from '@/components/ui/badge'
import type {
  FtbClaimsResponse,
  FtbClusterEntry,
  FtbTeamEntry,
} from '@/types/FtbClaims'
import type { ChunkKey } from '@/types/MapTypes'
import type { WorldRestoreSelectionMode } from '@/stores/useWorldRestoreSelectionStore'

import { isClusterFullySelected } from './claimSelection'
import { teamColors } from './teamColors'

type SortKey = 'name' | 'chunks-desc' | 'clusters-desc'

interface TeamClusterListProps {
  data: FtbClaimsResponse | undefined
  isLoading: boolean
  isError: boolean
  currentDimRelpath: string | null
  mode: WorldRestoreSelectionMode
  selection: Set<ChunkKey>
  overlayVisible: boolean
  onOverlayVisibleChange: (visible: boolean) => void
  onRefresh: () => void
  onClusterHover: (clusterIds: Set<string> | null) => void
  onClusterClick: (cluster: FtbClusterEntry) => void
  onClusterSelect: (cluster: FtbClusterEntry) => void
  onTeamHover: (clusterIds: Set<string> | null) => void
  onTeamSelectInDim: (team: FtbTeamEntry) => void
}

const SORT_OPTIONS: ReadonlyArray<{ value: SortKey; label: string }> = [
  { value: 'name', label: '名称' },
  { value: 'chunks-desc', label: '区块数 ↓' },
  { value: 'clusters-desc', label: '簇数 ↓' },
]

function sortTeams(teams: FtbTeamEntry[], sort: SortKey): FtbTeamEntry[] {
  const copy = [...teams]
  if (sort === 'name') {
    copy.sort((a, b) =>
      a.display_name.localeCompare(b.display_name, undefined, { sensitivity: 'base' }),
    )
  } else if (sort === 'chunks-desc') {
    copy.sort((a, b) => b.total_chunks - a.total_chunks)
  } else if (sort === 'clusters-desc') {
    copy.sort((a, b) => b.clusters.length - a.clusters.length)
  }
  return copy
}

function matches(team: FtbTeamEntry, q: string): boolean {
  if (!q) return true
  const needle = q.trim().toLowerCase()
  if (team.display_name.toLowerCase().includes(needle)) return true
  if (team.id.toLowerCase().includes(needle)) return true
  for (const m of team.members) {
    if (m.name && m.name.toLowerCase().includes(needle)) return true
    if (m.uuid && m.uuid.toLowerCase().includes(needle)) return true
  }
  return false
}

export const TeamClusterList: React.FC<TeamClusterListProps> = ({
  data,
  isLoading,
  isError,
  currentDimRelpath,
  mode,
  selection,
  overlayVisible,
  onOverlayVisibleChange,
  onRefresh,
  onClusterHover,
  onClusterClick,
  onClusterSelect,
  onTeamHover,
  onTeamSelectInDim,
}) => {
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState<SortKey>('chunks-desc')
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  const filteredSorted = useMemo(() => {
    const teams = data?.teams ?? []
    return sortTeams(teams.filter((t) => matches(t, query)), sort)
  }, [data?.teams, query, sort])

  const toggleExpand = (teamId: string) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(teamId)) next.delete(teamId)
      else next.add(teamId)
      return next
    })
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-6">
        <Spinner />
      </div>
    )
  }
  if (isError) {
    return (
      <div className="text-xs text-destructive">
        加载领地数据失败
        <Button size="sm" variant="outline" className="ml-2 h-6 px-2" onClick={onRefresh}>
          <RefreshCw className="mr-1 h-3 w-3" /> 重试
        </Button>
      </div>
    )
  }
  if (!data) return null
  if (!data.available) {
    return (
      <div className="text-xs text-muted-foreground">
        该世界未检测到 FTB Utilities / FTB Chunks 数据。
      </div>
    )
  }

  return (
    <div className="flex flex-1 min-h-0 flex-col gap-2">
      <div className="flex items-center gap-2">
        <div className="text-sm font-medium">领地列表</div>
        <Badge variant="secondary" className="text-[10px] px-1.5">
          {data.detected_format ?? '?'}
        </Badge>
        <Switch
          size="sm"
          checked={overlayVisible}
          onCheckedChange={onOverlayVisibleChange}
          aria-label="切换领地图层显示"
          title={overlayVisible ? '隐藏地图上的领地图层' : '显示地图上的领地图层'}
        />
        <div className="flex-1" />
        <Button
          size="icon-sm"
          variant="ghost"
          title="重新解析"
          onClick={onRefresh}
        >
          <RefreshCw className="h-3.5 w-3.5" />
        </Button>
      </div>

      <div className="relative">
        <Search className="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="搜索团队 / 成员"
          className="h-7 pl-7 text-xs"
        />
      </div>

      <Select
        value={sort}
        onValueChange={(v) => setSort(v as SortKey)}
        itemToStringLabel={(v) =>
          SORT_OPTIONS.find((o) => o.value === v)?.label ?? String(v)
        }
      >
        <SelectTrigger className="h-7 text-xs">
          <SelectValue placeholder="排序" />
        </SelectTrigger>
        <SelectContent>
          {SORT_OPTIONS.map((o) => (
            <SelectItem key={o.value} value={o.value}>
              {o.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <div
        className="flex-1 min-h-0 overflow-y-auto rounded border bg-background"
        onMouseLeave={() => {
          onClusterHover(null)
          onTeamHover(null)
        }}
      >
        {filteredSorted.length === 0 && (
          <div className="py-4 text-center text-xs text-muted-foreground">
            没有匹配的团队
          </div>
        )}
        {filteredSorted.map((team) => (
          <TeamRow
            key={team.id}
            team={team}
            expanded={expanded.has(team.id)}
            onToggle={() => toggleExpand(team.id)}
            mode={mode}
            currentDimRelpath={currentDimRelpath}
            selection={selection}
            onTeamHover={onTeamHover}
            onTeamSelectInDim={onTeamSelectInDim}
            onClusterHover={onClusterHover}
            onClusterClick={onClusterClick}
            onClusterSelect={onClusterSelect}
          />
        ))}
      </div>
    </div>
  )
}

interface TeamRowProps {
  team: FtbTeamEntry
  expanded: boolean
  onToggle: () => void
  mode: WorldRestoreSelectionMode
  currentDimRelpath: string | null
  selection: Set<ChunkKey>
  onTeamHover: (clusterIds: Set<string> | null) => void
  onTeamSelectInDim: (team: FtbTeamEntry) => void
  onClusterHover: (clusterIds: Set<string> | null) => void
  onClusterClick: (cluster: FtbClusterEntry) => void
  onClusterSelect: (cluster: FtbClusterEntry) => void
}

const TeamRow: React.FC<TeamRowProps> = ({
  team,
  expanded,
  onToggle,
  mode,
  currentDimRelpath,
  selection,
  onTeamHover,
  onTeamSelectInDim,
  onClusterHover,
  onClusterClick,
  onClusterSelect,
}) => {
  const color = teamColors(team.id, team.type)
  const inDimClusters = team.clusters.filter(
    (c) => c.region_dir_relpath === currentDimRelpath,
  )
  const inDimClusterIds = useMemo(
    () => new Set(inDimClusters.map((c) => c.id)),
    [inDimClusters],
  )
  const chunksInDim = inDimClusters.reduce((s, c) => s + c.chunks.length, 0)
  const hasInDimClusters = inDimClusters.length > 0
  return (
    <div className="border-b last:border-b-0">
      <div
        className="flex items-center gap-1.5 px-2 py-1.5 cursor-pointer hover:bg-muted/40"
        onClick={onToggle}
        onMouseEnter={() => hasInDimClusters && onTeamHover(inDimClusterIds)}
      >
        <span className="text-muted-foreground">
          {expanded ? (
            <ChevronDown className="h-3.5 w-3.5" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5" />
          )}
        </span>
        <span
          aria-hidden
          className="inline-block h-3 w-3 shrink-0 rounded-sm"
          style={{ background: color.stroke }}
        />
        <span
          className="flex-1 truncate text-xs font-medium"
          title={team.display_name}
        >
          {team.display_name}
        </span>
        <span className="text-[10px] text-muted-foreground">
          {chunksInDim}/{team.total_chunks}
        </span>
      </div>
      {expanded && (
        <div className="bg-muted/20 pl-7 pr-2 py-1">
          {team.clusters.length === 0 && (
            <div className="py-1 text-[10px] text-muted-foreground">无领地</div>
          )}
          {team.clusters.map((c) => (
            <ClusterRow
              key={c.id}
              cluster={c}
              isCurrentDim={c.region_dir_relpath === currentDimRelpath}
              accent={color.stroke}
              mode={mode}
              selection={selection}
              onClusterHover={onClusterHover}
              onClusterClick={onClusterClick}
              onClusterSelect={onClusterSelect}
            />
          ))}
          {hasInDimClusters && (
            <Button
              size="sm"
              variant="ghost"
              className="mt-1 h-6 w-full justify-start px-2 text-[11px]"
              onClick={(e) => {
                e.stopPropagation()
                onTeamSelectInDim(team)
              }}
            >
              选择该团队在此维度的全部（{chunksInDim} 区块）
            </Button>
          )}
        </div>
      )}
    </div>
  )
}

interface ClusterRowProps {
  cluster: FtbClusterEntry
  isCurrentDim: boolean
  accent: string
  mode: WorldRestoreSelectionMode
  selection: Set<ChunkKey>
  onClusterHover: (clusterIds: Set<string> | null) => void
  onClusterClick: (cluster: FtbClusterEntry) => void
  onClusterSelect: (cluster: FtbClusterEntry) => void
}

const ClusterRow: React.FC<ClusterRowProps> = ({
  cluster,
  isCurrentDim,
  accent,
  mode,
  selection,
  onClusterHover,
  onClusterClick,
  onClusterSelect,
}) => {
  const fullySelected = isCurrentDim && isClusterFullySelected(cluster, selection, mode)
  const forceCount = cluster.force_loaded.length
  return (
    <div
      className={
        'flex items-center gap-1.5 py-1 cursor-pointer rounded-sm pr-1 ' +
        (isCurrentDim ? 'hover:bg-muted/60' : 'opacity-50 hover:opacity-80')
      }
      style={{
        borderLeft: `3px solid ${fullySelected ? accent : 'transparent'}`,
        paddingLeft: 6,
      }}
      onMouseEnter={() => isCurrentDim && onClusterHover(new Set([cluster.id]))}
      onClick={() => onClusterClick(cluster)}
    >
      <div className="flex-1 min-w-0 text-[11px]">
        <div className="truncate">
          {cluster.chunks.length} 区块
          {forceCount > 0 && (
            <span className="text-red-500 ml-1">·{forceCount} 强加载</span>
          )}
        </div>
        {!isCurrentDim && cluster.region_dir_relpath && (
          <div className="truncate text-[10px] text-muted-foreground">
            {cluster.region_dir_relpath}
          </div>
        )}
      </div>
      {fullySelected && (
        <Badge variant="secondary" className="text-[9px] px-1 py-0">
          已选
        </Badge>
      )}
      {isCurrentDim && !fullySelected && (
        <Button
          size="sm"
          variant="outline"
          className="h-5 px-1.5 text-[10px]"
          onClick={(e) => {
            e.stopPropagation()
            onClusterSelect(cluster)
          }}
        >
          选择
        </Button>
      )}
    </div>
  )
}
