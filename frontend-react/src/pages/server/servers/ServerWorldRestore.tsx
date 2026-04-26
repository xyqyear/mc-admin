import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { History as HistoryIcon } from 'lucide-react'

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
import WorldRestoreSelectionPanel from '@/components/world-restore/WorldRestoreSelectionPanel'
import {
  ServerStopGuard,
  ServerStartHint,
} from '@/components/world-restore/ServerStopGuard'
import { useWorldLayout } from '@/hooks/queries/base/useWorldRestoreQueries'
import { useMapRegions } from '@/hooks/queries/base/useMapQueries'
import { useServerQueries } from '@/hooks/queries/base/useServerQueries'
import {
  useWorldRestoreSelectionStore,
  type WorldRestoreSelectionMode,
} from '@/stores/useWorldRestoreSelectionStore'
import type { ChunkKey, SelectionMode } from '@/types/MapTypes'

const STOPPED_STATUSES = new Set(['EXISTS', 'CREATED', 'REMOVED'])

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
  const worldRootName = searchParams.get('world') ?? null
  const urlMode = searchParams.get('mode') === 'chunk' ? 'chunk' : 'region'
  const [initialView] = useState(() => parseInitialView(searchParams))

  const layoutQ = useWorldLayout(serverId)
  const { useServerStatus } = useServerQueries()
  const statusQ = useServerStatus(serverId)
  const serverStopped = statusQ.data ? STOPPED_STATUSES.has(statusQ.data) : false

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
  const { rootList, currentDimension, currentRoot } = useMemo(() => {
    const roots = layoutQ.data?.world_roots ?? []
    if (roots.length === 0) {
      return { rootList: [], currentDimension: null, currentRoot: null }
    }
    const byName = new Map(roots.map((r) => [r.name, r]))
    const root =
      (worldRootName ? byName.get(worldRootName) : undefined) ?? roots[0]
    const dim =
      root.dimensions.find(
        (d) => relpathOf(d.region_dir, root.path) === dimensionRelpath,
      ) ??
      root.dimensions.find((d) => d.label === 'Overworld') ??
      root.dimensions[0]
    return { rootList: roots, currentDimension: dim ?? null, currentRoot: root }
  }, [layoutQ.data, worldRootName, dimensionRelpath])

  const regionRelpath = useMemo(() => {
    if (!currentDimension || !currentRoot) return null
    return relpathOf(currentDimension.region_dir, currentRoot.path)
  }, [currentDimension, currentRoot])

  // Seed URL with default world+dim once the layout loads. Replace, no
  // history entries.
  useEffect(() => {
    if (!currentRoot || !currentDimension) return
    const wantedRel = relpathOf(currentDimension.region_dir, currentRoot.path)
    if (worldRootName === currentRoot.name && dimensionRelpath === wantedRel) return
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        next.set('world', currentRoot.name)
        next.set('dim', wantedRel)
        return next
      },
      { replace: true },
    )
  }, [currentRoot, currentDimension, worldRootName, dimensionRelpath, setSearchParams])

  // Reflect URL → store. The store wipes the selection when world or dim
  // changes (chunks aren't comparable across dimensions).
  useEffect(() => {
    if (!serverId) return
    setStoreDimension(serverId, worldRootName, dimensionRelpath)
  }, [serverId, worldRootName, dimensionRelpath, setStoreDimension])

  useEffect(() => {
    if (!serverId) return
    setStoreMode(serverId, urlMode)
  }, [serverId, urlMode, setStoreMode])

  const {
    data: regionsList,
    isLoading: regionsLoading,
    isError: regionsError,
  } = useMapRegions(serverId, regionRelpath ?? undefined)

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
    (rootName: string, dimRelpath: string) => {
      setSearchParams(
        (prev) => {
          const params = new URLSearchParams(prev)
          params.set('world', rootName)
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
    const out: Array<{ value: string; label: string; rootName: string }> = []
    for (const r of layoutQ.data.world_roots) {
      for (const d of r.dimensions) {
        const rel = relpathOf(d.region_dir, r.path)
        const label =
          layoutQ.data.world_roots.length > 1
            ? `${r.name} / ${d.label}`
            : d.label
        out.push({
          value: `${r.name}::${rel}`,
          label,
          rootName: r.name,
        })
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
  const selection = selectionState?.selection ?? new Set<ChunkKey>()

  return (
    <div className="flex flex-col gap-4 h-full">
      <PageHeader
        title="世界恢复"
        icon={<HistoryIcon className="w-5 h-5" />}
        serverTag={serverId}
        actions={
          dimensionOptions.length > 0 ? (
            <div className="flex items-center gap-2">
              <div className="inline-flex rounded-md border border-input p-0.5 bg-background">
                <Button
                  variant={urlMode === 'region' ? 'secondary' : 'ghost'}
                  size="sm"
                  onClick={() => handleModeChange('region')}
                >
                  区域
                </Button>
                <Button
                  variant={urlMode === 'chunk' ? 'secondary' : 'ghost'}
                  size="sm"
                  onClick={() => handleModeChange('chunk')}
                >
                  区块
                </Button>
              </div>
              <Select
                value={
                  worldRootName && dimensionRelpath
                    ? `${worldRootName}::${dimensionRelpath}`
                    : undefined
                }
                onValueChange={(v) => {
                  if (typeof v !== 'string') return
                  const [rootName, rel] = v.split('::')
                  if (rootName && rel) handleDimensionChange(rootName, rel)
                }}
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
            </div>
          ) : null
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

      <ServerStopGuard serverId={serverId} status={statusQ.data} />

      <div className="flex-1 min-h-0 grid grid-cols-[1fr_360px] gap-4">
        <Card className="overflow-hidden">
          <CardContent className="p-0 h-full min-h-[60vh]">
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
              <div className="h-full min-h-[60vh] flex items-center justify-center">
                <Spinner />
              </div>
            ) : null}
          </CardContent>
        </Card>

        <div className="flex flex-col gap-3 min-w-0">
          <WorldRestoreSelectionPanel
            serverId={serverId}
            worldRootName={currentRoot?.name ?? null}
            dimensionLabel={currentDimension?.label ?? null}
            regionDirRelpath={regionRelpath}
            selection={selection}
            mode={urlMode}
            onModeChange={handleModeChange}
            onSelectionChange={handleSelectionChange}
            serverStopped={serverStopped}
          />
          <ServerStartHint serverId={serverId} status={statusQ.data} />
        </div>
      </div>
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
