import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { Map as MapIcon, RefreshCw } from 'lucide-react'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Spinner } from '@/components/ui/spinner'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import PageHeader from '@/components/layout/PageHeader'
import ServerMap, { type ServerMapView } from '@/components/map/ServerMap'
import MapHelpButton from '@/components/map/MapHelpButton'
import MapInitDialog from '@/components/dialogs/MapInitDialog'
import WorldRestoreSelectionPanel from '@/components/world-restore/WorldRestoreSelectionPanel'
import { ServerStopGuard } from '@/components/world-restore/ServerStopGuard'
import { useWorldLayout } from '@/hooks/queries/base/useWorldRestoreQueries'
import { useMapRegions, useMapStatus } from '@/hooks/queries/base/useMapQueries'
import ServerOperationButtons from '@/components/server/ServerOperationButtons'
import { useServerQueries } from '@/hooks/queries/base/useServerQueries'
import {
  useWorldRestoreSelectionStore,
  type WorldRestoreSelectionMode,
} from '@/stores/useWorldRestoreSelectionStore'
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

  // Re-fetch the world manifest (existing MCAs + their mtimes). Refetching
  // the regions query produces a new Map instance, which rebuilds the tile
  // layer; updated mtimes flow into the `?mt=` cache-buster so any tiles
  // whose source MCA changed are refetched (and re-rendered) end-to-end.
  const handleRefreshMap = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: queryKeys.map.all })
  }, [queryClient])

  const selectionState = useWorldRestoreSelectionStore((s) =>
    s.byServer[serverId],
  )
  const setSelection = useWorldRestoreSelectionStore((s) => s.setSelection)
  const setStoreDimension = useWorldRestoreSelectionStore((s) => s.setDimension)
  const setStoreMode = useWorldRestoreSelectionStore((s) => s.setMode)

  // Resolve the selected dimension's region_dir from the layout response. The
  // map tile layer needs the *region directory* path (e.g.
  // `world/region`), which is the `region_dir_relpath` the backend returns;
  // for the existing /map endpoint we send it as the `region` query param.
  // The relpath alone identifies a (root, dim) pair uniquely because every
  // root is named in the first path segment.
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
    // Fall back to the first root's Overworld (or first dimension).
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

  // Seed URL with default dim once the layout loads. Replace, no history
  // entries.
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

  // Reflect URL → store. The store wipes the selection when dim changes.
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
          // Drop view params — different dimensions have different extents.
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
          <div className="flex items-center gap-2">
            {dimensionOptions.length > 0 && (
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
                  <SelectTrigger className="w-[260px]">
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
            )}
            <ServerOperationButtons
              serverId={serverId}
              serverName={serverInfoQ.data?.name ?? serverId}
              status={statusQ.data}
              showReturnButton={false}
            />
          </div>
        }
      />

      {layoutQ.isLoading && (
        <Card>
          <CardContent className="py-8 flex justify-center">
            <Spinner />
          </CardContent>
        </Card>
      )}

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

      {mapInitialized && (
        <div className="flex-1 min-h-0 grid grid-cols-1 md:grid-cols-[1fr_180px] gap-4">
          <Card className="overflow-hidden">
            <CardContent className="p-0 h-[60vh] md:h-full md:min-h-[60vh]">
              {regionsMap && regionRelpath ? (
                <ServerMap
                  serverId={serverId}
                  regionPath={regionRelpath}
                  regions={regionsMap}
                  selectionMode={selectionMode}
                  selection={selection}
                  onSelectionChange={handleSelectionChange}
                  initialView={initialView}
                  onViewChange={handleViewChange}
                />
              ) : regionsLoading ? (
                <div className="h-[60vh] md:h-full flex items-center justify-center">
                  <Spinner />
                </div>
              ) : null}
            </CardContent>
          </Card>

          <div className="flex flex-col gap-3 min-w-0">
            <WorldRestoreSelectionPanel
              serverId={serverId}
              regionDirRelpath={regionRelpath}
              selection={selection}
              mode={urlMode}
              onModeChange={handleModeChange}
              serverStopped={serverStopped}
            />
          </div>
        </div>
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

// region_dir is returned as an absolute path; the existing /map/regions
// endpoint expects a relpath under data/. Strip the server's data path prefix
// using the world root path as the cut point: the layout response gives us
// `path = <data>/<world_root>` and `region_dir = <data>/<world_root>/<...>`,
// so the data-relative path is `<world_root>/<region_dir tail>`.
function relpathOf(regionDir: string, worldRootPath: string): string {
  const sep = '/'
  const rootBase = worldRootPath.split(sep).pop() ?? ''
  if (!rootBase) return regionDir
  const idx = regionDir.lastIndexOf(`${sep}${rootBase}${sep}`)
  if (idx < 0) {
    // Region dir lives directly inside data/, no nesting.
    return `${rootBase}/${regionDir.split(sep).pop() ?? ''}`
  }
  return regionDir.slice(idx + 1)
}

export default ServerWorldRestore
