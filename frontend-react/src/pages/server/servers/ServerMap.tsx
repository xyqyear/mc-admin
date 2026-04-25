import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { Map as MapIcon } from 'lucide-react'

import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
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
import MapInitDialog from '@/components/dialogs/MapInitDialog'
import ServerMap, { type ServerMapView } from '@/components/map/ServerMap'
import {
  useMapDimensions,
  useMapRegions,
  useMapStatus,
} from '@/hooks/queries/base/useMapQueries'
import { queryKeys } from '@/utils/api'

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

const ServerMapPage: React.FC = () => {
  const { id } = useParams<{ id: string }>()
  const serverId = id || ''
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()

  const {
    data: status,
    isLoading: statusLoading,
    isError: statusError,
  } = useMapStatus(serverId)
  const {
    data: dimensions,
    isLoading: dimensionsLoading,
    isError: dimensionsError,
  } = useMapDimensions(serverId)

  // URL is the single source of truth for the dimension; the dropdown reads
  // and writes ?dim=. Zoom/center are seeded from the URL once, after which
  // the map drives the URL one-way (replace, no history entries).
  const selectedRegion = searchParams.get('dim')
  const [initialView] = useState(() => parseInitialView(searchParams))
  const [initOpen, setInitOpen] = useState(false)

  const {
    data: regionsList,
    isLoading: regionsLoading,
    isError: regionsError,
  } = useMapRegions(serverId, selectedRegion ?? undefined)

  // Stable Map reference per regionsList payload (key `${x},${z}` → mtime).
  // The map effect depends on referential identity to know when to swap
  // layers. The tile layer uses the mtime to cache-bust per region.
  const regionsMap = useMemo(() => {
    if (!regionsList) return undefined
    return new Map(regionsList.map(([x, z, mt]) => [`${x},${z}`, mt]))
  }, [regionsList])

  useEffect(() => {
    if (selectedRegion) return
    if (dimensions && dimensions.length > 0) {
      const overworld = dimensions.find((d) => d.label === 'Overworld')
      const dim = (overworld ?? dimensions[0]).region_path
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev)
          next.set('dim', dim)
          return next
        },
        { replace: true },
      )
    }
  }, [dimensions, selectedRegion, setSearchParams])

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

  if (!serverId) {
    return (
      <Alert variant="destructive">
        <AlertTitle>错误</AlertTitle>
        <AlertDescription>缺少服务器ID</AlertDescription>
      </Alert>
    )
  }

  const initialized =
    status?.client_jar_present &&
    status?.palette_present &&
    status?.palette_current

  const handleInitComplete = () => {
    setInitOpen(false)
    queryClient.invalidateQueries({ queryKey: queryKeys.map.all })
  }

  return (
    <div className="flex flex-col gap-4 h-full">
      <PageHeader
        title="地图"
        icon={<MapIcon className="w-5 h-5" />}
        serverTag={serverId}
        actions={
          dimensions && dimensions.length > 0 && initialized ? (
            <div className="flex items-center gap-2">
              <Select
                value={selectedRegion ?? undefined}
                onValueChange={(v) => {
                  if (!v) return
                  setSearchParams(
                    (prev) => {
                      const next = new URLSearchParams(prev)
                      next.set('dim', v)
                      return next
                    },
                    { replace: true },
                  )
                }}
              >
                <SelectTrigger className="w-[260px]">
                  <SelectValue placeholder="选择维度">
                    {(value: string) => {
                      const d = dimensions.find((x) => x.region_path === value)
                      return d ? `${d.label} (${d.mca_count})` : '选择维度'
                    }}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {dimensions.map((d) => (
                    <SelectItem key={d.region_path} value={d.region_path}>
                      {d.label} ({d.mca_count})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button variant="outline" onClick={() => setInitOpen(true)}>
                重新初始化
              </Button>
            </div>
          ) : null
        }
      />

      {(statusLoading || dimensionsLoading) && (
        <Card>
          <CardContent className="py-8 flex justify-center">
            <Spinner />
          </CardContent>
        </Card>
      )}

      {(statusError || dimensionsError) && (
        <Alert variant="destructive">
          <AlertTitle>加载失败</AlertTitle>
          <AlertDescription>无法获取地图状态或维度列表</AlertDescription>
        </Alert>
      )}

      {!statusLoading && status && !initialized && (
        <Card>
          <CardContent className="py-8 flex flex-col items-center gap-4">
            <div className="text-center text-muted-foreground">
              {!status.client_jar_present
                ? '尚未下载客户端 JAR。'
                : !status.palette_present
                ? '尚未生成调色板。'
                : '调色板已过期（版本或mods变更）。'}
            </div>
            <Button onClick={() => setInitOpen(true)}>初始化地图</Button>
          </CardContent>
        </Card>
      )}

      {!dimensionsLoading &&
        initialized &&
        dimensions &&
        dimensions.length === 0 && (
          <Alert>
            <AlertTitle>未发现维度</AlertTitle>
            <AlertDescription>
              当前服务器的 data/ 目录下没有包含 r.X.Z.mca 的区域文件夹。
            </AlertDescription>
          </Alert>
        )}

      {initialized && selectedRegion && regionsError && (
        <Alert variant="destructive">
          <AlertTitle>加载失败</AlertTitle>
          <AlertDescription>无法获取该维度的区域清单</AlertDescription>
        </Alert>
      )}

      {initialized && selectedRegion && !regionsError && (
        <Card className="flex-1 overflow-hidden">
          <CardContent className="p-0 h-full min-h-[60vh]">
            {regionsMap ? (
              <ServerMap
                serverId={serverId}
                regionPath={selectedRegion}
                regions={regionsMap}
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

export default ServerMapPage
