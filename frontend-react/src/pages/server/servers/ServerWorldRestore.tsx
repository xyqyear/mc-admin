import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { Map as MapIcon, RefreshCw } from 'lucide-react'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Spinner } from '@/components/ui/spinner'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import PageHeader from '@/components/layout/PageHeader'
import ServerMap, { type ServerMapView } from '@/components/map/ServerMap'
import MapHelpButton from '@/components/map/MapHelpButton'
import MapInitDialog from '@/components/dialogs/MapInitDialog'
import WorldRestoreSelectionPanel from '@/components/world-restore/WorldRestoreSelectionPanel'
import { ServerStopGuard } from '@/components/world-restore/ServerStopGuard'
import {
  clusterToChunkKeys,
  teamDimChunkKeys,
} from '@/components/world-restore/claims/claimSelection'
import { ClusterPopover } from '@/components/world-restore/claims/ClusterPopover'
import { TeamClusterList } from '@/components/world-restore/claims/TeamClusterList'
import { useClaimsOverlay } from '@/components/world-restore/claims/useClaimsOverlay'
import { useFtbClaims } from '@/hooks/queries/base/useFtbClaimsQueries'
import { useWorldLayout } from '@/hooks/queries/base/useWorldRestoreQueries'
import { useMapRegions, useMapStatus } from '@/hooks/queries/base/useMapQueries'
import ServerOperationButtons from '@/components/server/ServerOperationButtons'
import { useServerQueries } from '@/hooks/queries/base/useServerQueries'
import {
  useWorldRestoreSelectionStore,
  type WorldRestoreSelectionMode,
} from '@/stores/useWorldRestoreSelectionStore'
import type { FtbClusterEntry, FtbTeamEntry } from '@/types/FtbClaims'
import type { ChunkKey, SelectionMode } from '@/types/MapTypes'
import { queryKeys } from '@/utils/api'

const STOPPED_STATUSES = new Set(['EXISTS', 'CREATED', 'REMOVED'])
const EMPTY_SELECTION = new Set<ChunkKey>()

function parseInitialView(params: URLSearchParams): ServerMapView | undefined {
  if (!params.has('z') && !params.has('cx') && !params.has('cz')) return undefined
  const z = Number(params.get('z') ?? 0)
  const cx = Number(params.get('cx') ?? 0)
  const cz = Number(params.get('cz') ?? 0)
  return {
    zoom: Number.isFinite(z) ? z : 0,
    cx: Number.isFinite(cx) ? cx : 0,
    cz: Number.isFinite(cz) ? cz : 0,
  }
}

const ServerWorldRestore: React.FC = () => {
  const { id } = useParams<{ id: string }>()
  const serverId = id ?? ''
  const [searchParams, setSearchParams] = useSearchParams()

  const dimensionRelpath = searchParams.get('dim') ?? null
  const urlMode = searchParams.get('mode') === 'chunk' ? 'chunk' : 'region'
  const [initialView] = useState(() => parseInitialView(searchParams))

  const layoutQ = useWorldLayout(serverId)
  const { useServerStatus, useServerInfo } = useServerQueries()
  const statusQ = useServerStatus(serverId)
  const serverInfoQ = useServerInfo(serverId)
  const serverStopped = statusQ.data ? STOPPED_STATUSES.has(statusQ.data) : false

  const queryClient = useQueryClient()
  const mapStatusQ = useMapStatus(serverId)
  const mapInitialized =
    !!mapStatusQ.data?.client_jar_present &&
    !!mapStatusQ.data?.palette_present &&
    !!mapStatusQ.data?.palette_current
  const [initOpen, setInitOpen] = useState(false)
  const handleInitComplete = useCallback(() => {
    setInitOpen(false)
    queryClient.invalidateQueries({ queryKey: queryKeys.map.all })
  }, [queryClient])

  const handleRefreshMap = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: queryKeys.map.all })
  }, [queryClient])

  const selectionState = useWorldRestoreSelectionStore((s) =>
    s.byServer[serverId],
  )
  const setSelection = useWorldRestoreSelectionStore((s) => s.setSelection)
  const addToSelection = useWorldRestoreSelectionStore((s) => s.addToSelection)
  const setStoreDimension = useWorldRestoreSelectionStore((s) => s.setDimension)
  const setStoreMode = useWorldRestoreSelectionStore((s) => s.setMode)

  // Relpath uniquely identifies (root, dim) because the root name is the first segment.
  const { rootList, currentDimension, currentRoot } = useMemo(() => {
    const roots = layoutQ.data?.world_roots ?? []
    if (roots.length === 0) {
      return { rootList: [], currentDimension: null, currentRoot: null }
    }
    if (dimensionRelpath) {
      for (const root of roots) {
        const match = root.dimensions.find(
          (d) => relpathOf(d.region_dir, root.path) === dimensionRelpath,
        )
        if (match) {
          return {
            rootList: roots,
            currentDimension: match,
            currentRoot: root,
          }
        }
      }
    }
    const root = roots[0]
    const dim =
      root.dimensions.find((d) => d.label === 'Overworld') ??
      root.dimensions[0] ??
      null
    return { rootList: roots, currentDimension: dim, currentRoot: root }
  }, [layoutQ.data, dimensionRelpath])

  const regionRelpath = useMemo(() => {
    if (!currentDimension || !currentRoot) return null
    return relpathOf(currentDimension.region_dir, currentRoot.path)
  }, [currentDimension, currentRoot])

  // Seed default dim into URL once layout loads. Replace, no history entries.
  useEffect(() => {
    if (!currentRoot || !currentDimension) return
    const wantedRel = relpathOf(currentDimension.region_dir, currentRoot.path)
    if (dimensionRelpath === wantedRel) return
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        next.set('dim', wantedRel)
        return next
      },
      { replace: true },
    )
  }, [currentRoot, currentDimension, dimensionRelpath, setSearchParams])

  // The store wipes the selection when dim changes.
  useEffect(() => {
    if (!serverId) return
    setStoreDimension(serverId, dimensionRelpath)
  }, [serverId, dimensionRelpath, setStoreDimension])

  useEffect(() => {
    if (!serverId) return
    setStoreMode(serverId, urlMode)
  }, [serverId, urlMode, setStoreMode])

  const {
    data: regionsList,
    isLoading: regionsLoading,
    isError: regionsError,
  } = useMapRegions(
    serverId,
    mapInitialized ? regionRelpath ?? undefined : undefined,
  )

  const regionsMap = useMemo(() => {
    if (!regionsList) return undefined
    return new Map(regionsList.map(([x, z, mt]) => [`${x},${z}`, mt]))
  }, [regionsList])

  const handleViewChange = useCallback(
    (view: ServerMapView) => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev)
          next.set('z', String(view.zoom))
          next.set('cx', String(view.cx))
          next.set('cz', String(view.cz))
          return next
        },
        { replace: true },
      )
    },
    [setSearchParams],
  )

  const handleSelectionChange = useCallback(
    (next: Set<ChunkKey>) => {
      if (!serverId) return
      setSelection(serverId, next)
    },
    [serverId, setSelection],
  )

  const handleModeChange = useCallback(
    (next: WorldRestoreSelectionMode) => {
      setSearchParams(
        (prev) => {
          const params = new URLSearchParams(prev)
          params.set('mode', next)
          return params
        },
        { replace: true },
      )
    },
    [setSearchParams],
  )

  const handleDimensionChange = useCallback(
    (dimRelpath: string) => {
      setSearchParams(
        (prev) => {
          const params = new URLSearchParams(prev)
          params.set('dim', dimRelpath)
          // Different dimensions have different extents.
          params.delete('z')
          params.delete('cx')
          params.delete('cz')
          return params
        },
        { replace: true },
      )
    },
    [setSearchParams],
  )

  // --- FTB claims overlay ---

  const claimsQ = useFtbClaims(serverId, mapInitialized)
  const claimsAvailable = !!claimsQ.data?.available
  const [overlayVisible, setOverlayVisible] = useState(true)
  const teams = useMemo<FtbTeamEntry[]>(
    () => claimsQ.data?.teams ?? [],
    [claimsQ.data],
  )
  const pendingPanRef = useRef<{
    dimRelpath: string
    bx: number
    bz: number
  } | null>(null)

  // Cross-dim pan via overlay render; see docs/ftb-claims-overlay.md.
  const handleOverlayRender = useCallback(
    (map: L.Map, dim: string | null) => {
      const pending = pendingPanRef.current
      if (!pending || pending.dimRelpath !== dim) return
      queueMicrotask(() => {
        pendingPanRef.current = null
      })
      map.setView([-pending.bz, pending.bx], map.getZoom(), { animate: false })
    },
    [],
  )

  const {
    overlays: claimsOverlays,
    popover: claimsPopover,
    closePopover: closeClaimsPopover,
    highlightClusters,
    panToBlock,
  } = useClaimsOverlay({
    teams,
    currentDimRelpath: regionRelpath,
    enabled: claimsAvailable && overlayVisible,
    onRender: handleOverlayRender,
  })

  const handleRefreshClaims = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: queryKeys.ftbClaims.all })
  }, [queryClient])

  const handleClusterSelect = useCallback(
    (cluster: FtbClusterEntry) => {
      if (!serverId) return
      // Cluster's dim must match the current dim — selection lives per dim.
      if (cluster.region_dir_relpath !== regionRelpath) return
      const keys = clusterToChunkKeys(cluster, urlMode)
      addToSelection(serverId, keys)
    },
    [serverId, regionRelpath, urlMode, addToSelection],
  )

  const handleTeamSelectInDim = useCallback(
    (team: FtbTeamEntry) => {
      if (!serverId || !regionRelpath) return
      const keys = teamDimChunkKeys(team, regionRelpath, urlMode)
      addToSelection(serverId, keys)
    },
    [serverId, regionRelpath, urlMode, addToSelection],
  )

  const handleClusterClick = useCallback(
    (cluster: FtbClusterEntry) => {
      if (cluster.region_dir_relpath === regionRelpath) {
        const [bx, bz] = cluster.centroid_block
        panToBlock(bx, bz)
        return
      }
      if (cluster.region_dir_relpath) {
        const [bx, bz] = cluster.centroid_block
        pendingPanRef.current = {
          dimRelpath: cluster.region_dir_relpath,
          bx,
          bz,
        }
        handleDimensionChange(cluster.region_dir_relpath)
      }
    },
    [regionRelpath, panToBlock, handleDimensionChange],
  )

  const popoverContext = useMemo(() => {
    if (!claimsPopover) return null
    for (const team of teams) {
      for (const cluster of team.clusters) {
        if (cluster.id !== claimsPopover.clusterId) continue
        const teamClustersInDim = team.clusters.filter(
          (c) => c.region_dir_relpath === cluster.region_dir_relpath,
        )
        const teamChunksInDim = teamClustersInDim.reduce(
          (s, c) => s + c.chunks.length,
          0,
        )
        return {
          team,
          cluster,
          teamChunksInDim,
          clustersInDim: teamClustersInDim.length,
        }
      }
    }
    return null
  }, [claimsPopover, teams])

  const dimensionOptions = useMemo(() => {
    if (!layoutQ.data) return []
    const multipleRoots = layoutQ.data.world_roots.length > 1
    const out: Array<{ value: string; label: string }> = []
    for (const r of layoutQ.data.world_roots) {
      for (const d of r.dimensions) {
        const rel = relpathOf(d.region_dir, r.path)
        const label = multipleRoots ? `${r.name} / ${d.label}` : d.label
        out.push({ value: rel, label })
      }
    }
    return out
  }, [layoutQ.data])

  if (!serverId) {
    return (
      <Alert variant="destructive">
        <AlertTitle>错误</AlertTitle>
        <AlertDescription>缺少服务器ID</AlertDescription>
      </Alert>
    )
  }

  const selectionMode: SelectionMode = urlMode
  const selection = selectionState?.selection ?? EMPTY_SELECTION

  return (
    <div className="flex flex-col gap-4 h-full">
      <PageHeader
        title="地图回档"
        icon={<MapIcon className="w-5 h-5" />}
        serverTag={serverId}
        actions={
          <>
            {layoutQ.isLoading ? (
              <>
                <Skeleton className="h-9 w-30" />
                <Skeleton className="h-9 w-65" />
              </>
            ) : dimensionOptions.length > 0 ? (
              <>
                {mapInitialized && (
                  <>
                    <Button
                      variant="outline"
                      onClick={handleRefreshMap}
                      title="重新读取世界元数据并刷新瓦片"
                    >
                      <RefreshCw className="mr-1 h-4 w-4" />
                      刷新地图
                    </Button>
                    <Button variant="outline" onClick={() => setInitOpen(true)}>
                      重载渲染前置
                    </Button>
                    <Tabs
                      value={urlMode}
                      onValueChange={(v) => {
                        if (v === 'chunk' || v === 'region')
                          handleModeChange(v)
                      }}
                    >
                      <TabsList>
                        <TabsTrigger value="region" className="px-3">
                          区域选择
                        </TabsTrigger>
                        <TabsTrigger value="chunk" className="px-3">
                          区块选择
                        </TabsTrigger>
                      </TabsList>
                    </Tabs>
                  </>
                )}
                <Select
                  value={dimensionRelpath ?? undefined}
                  onValueChange={(v) => {
                    if (typeof v === 'string') handleDimensionChange(v)
                  }}
                  itemToStringLabel={(v) =>
                    dimensionOptions.find((o) => o.value === v)?.label ?? String(v)
                  }
                >
                  <SelectTrigger className="w-65">
                    <SelectValue placeholder="选择维度" />
                  </SelectTrigger>
                  <SelectContent>
                    {dimensionOptions.map((o) => (
                      <SelectItem key={o.value} value={o.value}>
                        {o.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <MapHelpButton />
              </>
            ) : null}
            <ServerOperationButtons
              serverId={serverId}
              serverName={serverInfoQ.data?.name ?? serverId}
              status={statusQ.data}
              showReturnButton={false}
            />
          </>
        }
      />

      {layoutQ.isError && (
        <Alert variant="destructive">
          <AlertTitle>加载失败</AlertTitle>
          <AlertDescription>无法获取世界布局</AlertDescription>
        </Alert>
      )}

      {!layoutQ.isLoading && layoutQ.data && rootList.length === 0 && (
        <Alert>
          <AlertTitle>未发现世界</AlertTitle>
          <AlertDescription>
            该服务器的 data/ 目录下没有可识别的世界根（缺少 level.dat）。
          </AlertDescription>
        </Alert>
      )}

      {regionsError && (
        <Alert variant="destructive">
          <AlertTitle>加载失败</AlertTitle>
          <AlertDescription>无法获取该维度的区域清单</AlertDescription>
        </Alert>
      )}

      {mapStatusQ.isError && (
        <Alert variant="destructive">
          <AlertTitle>加载失败</AlertTitle>
          <AlertDescription>无法获取地图初始化状态</AlertDescription>
        </Alert>
      )}

      {!mapStatusQ.isLoading && mapStatusQ.data && !mapInitialized && (
        <Card>
          <CardContent className="py-8 flex flex-col items-center gap-4">
            <div className="text-center text-muted-foreground">
              {!mapStatusQ.data.client_jar_present
                ? '尚未下载客户端 JAR。'
                : !mapStatusQ.data.palette_present
                ? '尚未生成调色板。'
                : '调色板已过期（版本或mods变更）。'}
            </div>
            <Button onClick={() => setInitOpen(true)}>初始化地图</Button>
          </CardContent>
        </Card>
      )}

      <ServerStopGuard status={statusQ.data} />

      {(mapInitialized || layoutQ.isLoading) && (
        <div className="flex flex-col gap-4 md:flex-1 md:min-h-0 md:grid md:grid-cols-[1fr_270px] md:grid-rows-1">
          <Card className="overflow-hidden py-0">
            <CardContent className="p-0 h-[60vh] md:h-full md:min-h-[60vh]">
              {regionsMap && regionRelpath ? (
                <ServerMap
                  serverId={serverId}
                  regionPath={regionRelpath}
                  regions={regionsMap}
                  selectionMode={selectionMode}
                  selection={selection}
                  onSelectionChange={handleSelectionChange}
                  overlays={claimsOverlays}
                  initialView={initialView}
                  onViewChange={handleViewChange}
                />
              ) : layoutQ.isLoading || regionsLoading ? (
                <div className="h-[60vh] md:h-full flex items-center justify-center">
                  <Spinner />
                </div>
              ) : null}
            </CardContent>
          </Card>

          <div className="flex flex-col min-w-0 md:min-h-0 md:overflow-y-auto md:*:shrink-0">
            <Card>
              <CardContent>
                {claimsAvailable ? (
                  <Tabs defaultValue="backup" className="gap-4">
                    <TabsList className="w-full">
                      <TabsTrigger value="backup">备份与恢复</TabsTrigger>
                      <TabsTrigger value="claims">领地列表</TabsTrigger>
                    </TabsList>
                    <TabsContent value="backup">
                      <WorldRestoreSelectionPanel
                        serverId={serverId}
                        regionDirRelpath={regionRelpath}
                        selection={selection}
                        mode={urlMode}
                        serverStopped={serverStopped}
                      />
                    </TabsContent>
                    <TabsContent value="claims">
                      <TeamClusterList
                        data={claimsQ.data}
                        isLoading={claimsQ.isLoading}
                        isError={claimsQ.isError}
                        currentDimRelpath={regionRelpath}
                        mode={urlMode}
                        selection={selection}
                        overlayVisible={overlayVisible}
                        onOverlayVisibleChange={setOverlayVisible}
                        onRefresh={handleRefreshClaims}
                        onClusterHover={highlightClusters}
                        onClusterClick={handleClusterClick}
                        onClusterSelect={handleClusterSelect}
                        onTeamHover={highlightClusters}
                        onTeamSelectInDim={handleTeamSelectInDim}
                      />
                    </TabsContent>
                  </Tabs>
                ) : (
                  <WorldRestoreSelectionPanel
                    serverId={serverId}
                    regionDirRelpath={regionRelpath}
                    selection={selection}
                    mode={urlMode}
                    serverStopped={serverStopped}
                  />
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      )}

      {claimsPopover && popoverContext && (
        <ClusterPopover
          team={popoverContext.team}
          cluster={popoverContext.cluster}
          anchorEl={claimsPopover.anchorEl}
          mode={urlMode}
          teamChunksInDim={popoverContext.teamChunksInDim}
          clustersInDim={popoverContext.clustersInDim}
          onClose={closeClaimsPopover}
          onSelectCluster={() => {
            handleClusterSelect(popoverContext.cluster)
            closeClaimsPopover()
          }}
          onSelectTeamInDim={() => {
            handleTeamSelectInDim(popoverContext.team)
            closeClaimsPopover()
          }}
        />
      )}

      <MapInitDialog
        open={initOpen}
        serverId={serverId}
        onClose={() => setInitOpen(false)}
        onComplete={handleInitComplete}
      />
    </div>
  )
}

function relpathOf(regionDir: string, worldRootPath: string): string {
  const sep = '/'
  const rootBase = worldRootPath.split(sep).pop() ?? ''
  if (!rootBase) return regionDir
  const idx = regionDir.lastIndexOf(`${sep}${rootBase}${sep}`)
  if (idx < 0) {
    return `${rootBase}/${regionDir.split(sep).pop() ?? ''}`
  }
  return regionDir.slice(idx + 1)
}

export default ServerWorldRestore
