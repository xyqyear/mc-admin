import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import type L from 'leaflet'
import { useParams } from 'react-router'
import { useQueryClient } from '@tanstack/react-query'
import { Eraser, RefreshCw } from 'lucide-react'
import { toast } from 'sonner'

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
import MapHelpButton from '@/components/map/MapHelpButton'
import MapInitDialog from '@/components/dialogs/MapInitDialog'
import ServerOperationButtons from '@/components/server/ServerOperationButtons'
import ServerMap, { type ServerMapOverlay, type ServerMapView } from '@/components/map/ServerMap'
import ChunkPrunePanel from '@/components/chunk-prune/ChunkPrunePanel'
import {
  secondsToThresholdInput,
  thresholdInputToSeconds,
} from '@/components/chunk-prune/thresholdUnits'
import { buildPrunePreviewLayer } from '@/components/chunk-prune/PrunePreviewOverlayLayer'
import {
  buildDimensionOptions,
  relpathOf,
  selectWorldDimension,
} from '@/components/map/worldDimensions'
import { ClusterPopover } from '@/components/map/layers/claims/ClusterPopover'
import { TeamClusterList } from '@/components/map/layers/claims/TeamClusterList'
import { useClaimsOverlay } from '@/components/map/layers/claims/useClaimsOverlay'
import { PlayerLocationList } from '@/components/map/layers/players/PlayerLocationList'
import { usePlayersOverlay } from '@/components/map/layers/players/usePlayersOverlay'
import { normalizePlayerUuid } from '@/components/map/layers/players/playerLocationDisplay'
import { chunkPruneApi } from '@/hooks/api/chunkPruneApi'
import { useTaskMutations } from '@/hooks/mutations/useTaskMutations'
import {
  useChunkPruneSettings,
  useChunkPruneState,
} from '@/hooks/queries/base/useChunkPruneQueries'
import { useFtbClaims } from '@/hooks/queries/base/useFtbClaimsQueries'
import { useMapRegions, useMapStatus } from '@/hooks/queries/base/useMapQueries'
import {
  usePlayerMapProfiles,
  useServerOnlinePlayers,
} from '@/hooks/queries/base/usePlayerQueries'
import { useServerQueries } from '@/hooks/queries/base/useServerQueries'
import {
  useWorldDimensionLabels,
  useWorldLayout,
  useWorldRestorePlayerLocations,
} from '@/hooks/queries/base/useWorldRestoreQueries'
import { useConfirm } from '@/hooks/useConfirm'
import {
  readHashUrlParams,
  replaceHashUrlParams,
  useHashUrlParams,
  type HashUrlParamsUpdater,
} from '@/hooks/useHashUrlParams'
import { taskQueryKeys } from '@/hooks/queries/base/useTaskQueries'
import type { FtbClusterEntry, FtbTeamEntry } from '@/types/FtbClaims'
import type { ChunkPruneMode, ChunkPruneResultData } from '@/types/ChunkPrune'
import type { ChunkKey } from '@/types/MapTypes'
import type { PlayerLocationEntry } from '@/types/PlayerLocations'
import type { BackgroundTaskStatus } from '@/stores/useBackgroundTaskStore'
import { queryKeys } from '@/utils/api'

const STOPPED_STATUSES = new Set(['EXISTS', 'CREATED', 'REMOVED'])
const CHUNK_PRUNE_REACTIVE_URL_KEYS = ['dim', 'mode'] as const
const CHUNK_PRUNE_URL_KEYS = [
  ...CHUNK_PRUNE_REACTIVE_URL_KEYS,
  'z',
  'cx',
  'cz',
] as const

function replaceChunkPruneUrlParams(update: HashUrlParamsUpdater): void {
  replaceHashUrlParams(CHUNK_PRUNE_URL_KEYS, update)
}

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

function isChunkPruneResultData(
  value: unknown,
): value is ChunkPruneResultData {
  if (!value || typeof value !== 'object') return false
  const data = value as { mode?: unknown; dry_run?: unknown }
  return (
    (data.mode === 'chunks' || data.mode === 'regions') &&
    typeof data.dry_run === 'boolean'
  )
}

const isTaskActive = (status: string): boolean =>
  status === 'pending' || status === 'running'

const ServerChunkPrune: React.FC = () => {
  const { id } = useParams<{ id: string }>()
  const serverId = id ?? ''
  const [urlParams] = useHashUrlParams(CHUNK_PRUNE_REACTIVE_URL_KEYS)
  const dimensionRelpath = urlParams.get('dim') ?? null
  const urlMode: ChunkPruneMode =
    urlParams.get('mode') === 'chunks' ? 'chunks' : 'regions'
  const [initialView] = useState(() =>
    parseInitialView(readHashUrlParams(CHUNK_PRUNE_URL_KEYS)),
  )

  const queryClient = useQueryClient()
  const settingsQ = useChunkPruneSettings(serverId)
  const layoutQ = useWorldLayout(serverId)
  const labelsQ = useWorldDimensionLabels(serverId)
  const { useServerStatus, useServerInfo } = useServerQueries()
  const statusQ = useServerStatus(serverId)
  const serverInfoQ = useServerInfo(serverId)
  const serverStopped = statusQ.data ? STOPPED_STATUSES.has(statusQ.data) : false
  const { useCancelTask } = useTaskMutations()
  const cancelTask = useCancelTask()
  const { confirm, confirmDialog } = useConfirm()

  const [initOpen, setInitOpen] = useState(false)
  const [initForce, setInitForce] = useState(false)
  const mapStatusQ = useMapStatus(serverId)
  const mapInitialized =
    !!mapStatusQ.data?.client_jar_present &&
    !!mapStatusQ.data?.palette_present &&
    !!mapStatusQ.data?.palette_current

  const [thresholdValue, setThresholdValue] = useState('30')
  const [thresholdUnit, setThresholdUnit] =
    useState<ReturnType<typeof secondsToThresholdInput>['unit']>('seconds')
  const [settingsApplied, setSettingsApplied] = useState(false)

  useEffect(() => {
    if (settingsApplied || !settingsQ.data) return
    const next = secondsToThresholdInput(settingsQ.data.default_threshold_seconds)
    setThresholdValue(next.value)
    setThresholdUnit(next.unit)
    setSettingsApplied(true)
  }, [settingsApplied, settingsQ.data])

  const thresholdSeconds = useMemo(
    () => thresholdInputToSeconds(thresholdValue, thresholdUnit),
    [thresholdUnit, thresholdValue],
  )

  const [previewStarting, setPreviewStarting] = useState(false)
  const stateQ = useChunkPruneState(serverId)
  const previewTask = stateQ.data?.previewTask ?? null
  const applyTask = stateQ.data?.applyTask ?? null
  const previewTaskId = previewTask?.taskId ?? null
  const applyTaskId = applyTask?.taskId ?? null
  const previewStatus: BackgroundTaskStatus | 'idle' =
    previewTask?.status ?? (stateQ.isError ? 'failed' : 'idle')
  const applyStatus: BackgroundTaskStatus | 'idle' =
    applyTask?.status ?? (stateQ.isError ? 'failed' : 'idle')
  const previewResult =
    previewTask?.taskType === 'chunk_prune_preview' &&
    isChunkPruneResultData(previewTask.result) &&
    previewTask.result.dry_run
    ? previewTask.result
    : null
  const applyResult =
    applyTask?.taskType === 'chunk_prune_apply' &&
    isChunkPruneResultData(applyTask.result)
    ? applyTask.result
    : null
  const previewError =
    previewTask?.error ?? (stateQ.isError ? '无法读取区块清理任务状态' : null)
  const applyError =
    applyTask?.error ?? (stateQ.isError ? '无法读取区块清理任务状态' : null)
  const previewActive = isTaskActive(previewStatus)
  const applyActive = isTaskActive(applyStatus)

  const { rootList, currentDimension, currentRoot } = useMemo(
    () => selectWorldDimension(layoutQ.data, dimensionRelpath),
    [dimensionRelpath, layoutQ.data],
  )

  const regionRelpath = useMemo(() => {
    if (!currentDimension || !currentRoot) return null
    return relpathOf(currentDimension.region_dir, currentRoot.path)
  }, [currentDimension, currentRoot])

  useEffect(() => {
    if (!currentRoot || !currentDimension) return
    const wantedRel = relpathOf(currentDimension.region_dir, currentRoot.path)
    if (dimensionRelpath === wantedRel) return
    replaceChunkPruneUrlParams((params) => {
      params.set('dim', wantedRel)
    })
  }, [currentDimension, currentRoot, dimensionRelpath])

  useEffect(() => {
    if (applyStatus !== 'completed') return
    queryClient.invalidateQueries({ queryKey: queryKeys.map.all })
  }, [applyStatus, queryClient])

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

  const handleViewChange = useCallback((view: ServerMapView) => {
    replaceChunkPruneUrlParams((params) => {
      params.set('z', String(view.zoom))
      params.set('cx', String(view.cx))
      params.set('cz', String(view.cz))
    })
  }, [])

  const handleDimensionChange = useCallback((dimRelpath: string) => {
    replaceChunkPruneUrlParams((params) => {
      params.set('dim', dimRelpath)
      params.delete('z')
      params.delete('cx')
      params.delete('cz')
    })
  }, [])

  const applyModeChange = useCallback((mode: ChunkPruneMode) => {
    replaceChunkPruneUrlParams((params) => {
      params.set('mode', mode)
    })
  }, [])

  const handleModeChange = useCallback(
    (mode: ChunkPruneMode) => {
      if (mode === urlMode) return
      if (urlMode === 'regions' && mode === 'chunks') {
        confirm({
          title: '区块清理仍处于实验性',
          description:
            '区块模式会直接修改单个区块，可能导致清理范围不符合预期，甚至造成区域、实体或 POI 数据不一致。除非确实需要精细清理，请优先使用区域模式。',
          cancelText: '留在区域模式',
          confirmText: '我了解风险，切换到区块模式',
          variant: 'destructive',
          onConfirm: () => applyModeChange(mode),
        })
        return
      }
      applyModeChange(mode)
    },
    [applyModeChange, confirm, urlMode],
  )

  const dimensionOptions = useMemo(
    () =>
      buildDimensionOptions(
        layoutQ.data,
        labelsQ.data?.dimension_labels,
      ),
    [labelsQ.data?.dimension_labels, layoutQ.data],
  )
  const dimensionLabelByRelpath = useMemo(
    () => new Map(dimensionOptions.map((o) => [o.value, o.label])),
    [dimensionOptions],
  )

  const claimsQ = useFtbClaims(serverId, mapInitialized)
  const claimsAvailable = !!claimsQ.data?.available
  const [claimsOverlayVisible, setClaimsOverlayVisible] = useState(true)
  const teams = useMemo<FtbTeamEntry[]>(
    () => claimsQ.data?.teams ?? [],
    [claimsQ.data],
  )
  const pendingPanRef = useRef<{
    dimRelpath: string
    bx: number
    bz: number
  } | null>(null)
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
    enabled: claimsAvailable && claimsOverlayVisible,
    onRender: handleOverlayRender,
  })

  const playerLocationsQ = useWorldRestorePlayerLocations(
    serverId,
    mapInitialized,
  )
  const [playersOverlayVisible, setPlayersOverlayVisible] = useState(true)
  const [onlinePlayersOnly, setOnlinePlayersOnly] = useState(false)
  const playerLocations = useMemo<PlayerLocationEntry[]>(
    () => playerLocationsQ.data?.players ?? [],
    [playerLocationsQ.data],
  )
  const onlinePlayersQ = useServerOnlinePlayers(serverId)
  const onlinePlayerUuids = useMemo(
    () =>
      new Set(
        (onlinePlayersQ.data ?? [])
          .map((player) => normalizePlayerUuid(player.uuid))
          .filter((uuid): uuid is string => !!uuid),
      ),
    [onlinePlayersQ.data],
  )
  const onlineStatusAvailable = !!onlinePlayersQ.data && !onlinePlayersQ.isError
  const playerUuids = useMemo(
    () =>
      playerLocations
        .map((player) => player.uuid)
        .filter((uuid): uuid is string => !!uuid),
    [playerLocations],
  )
  const playerProfiles = usePlayerMapProfiles(
    playerUuids,
    mapInitialized && !!playerLocationsQ.data,
  )
  const { overlays: playersOverlays, panToBlock: panToPlayerBlock } =
    usePlayersOverlay({
      players: playerLocations,
      currentDimRelpath: regionRelpath,
      profilesByUuid: playerProfiles.profilesByUuid,
      onlinePlayerUuids,
      onlineOnly: onlinePlayersOnly && onlineStatusAvailable,
      onlineStatusAvailable,
      enabled: mapInitialized,
      visible: playersOverlayVisible,
      onRender: handleOverlayRender,
    })

  const previewMatchesCurrentControls =
    !!previewResult &&
    previewResult.threshold_seconds === thresholdSeconds &&
    previewResult.mode === urlMode
  const currentPreviewDimension = useMemo(
    () =>
      previewMatchesCurrentControls && regionRelpath
        ? previewResult?.dimensions?.find(
            (dim) => dim.region_dir_relpath === regionRelpath,
          ) ?? null
        : null,
    [previewMatchesCurrentControls, previewResult, regionRelpath],
  )

  const pruneOverlay = useMemo<ServerMapOverlay[] | undefined>(() => {
    if (
      !previewTaskId ||
      previewStatus !== 'completed' ||
      !currentPreviewDimension ||
      !previewMatchesCurrentControls
    ) {
      return undefined
    }
    const hasCells =
      urlMode === 'regions'
        ? currentPreviewDimension.selected_regions.length > 0
        : currentPreviewDimension.selected_chunks.length > 0
    if (!hasCells) return undefined
    return [
      {
        id: `chunk-prune-preview-${previewTaskId}-${regionRelpath ?? 'none'}`,
        render: () =>
          buildPrunePreviewLayer({
            mode: urlMode,
            dimension: currentPreviewDimension,
          }),
      },
    ]
  }, [
    currentPreviewDimension,
    previewMatchesCurrentControls,
    previewStatus,
    previewTaskId,
    regionRelpath,
    urlMode,
  ])

  const mapOverlays = useMemo(() => {
    const out = [
      ...(claimsOverlays ?? []),
      ...(playersOverlays ?? []),
      ...(pruneOverlay ?? []),
    ]
    return out.length > 0 ? out : undefined
  }, [claimsOverlays, playersOverlays, pruneOverlay])

  const handleRefreshMap = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: queryKeys.map.all })
  }, [queryClient])
  const handleRefreshClaims = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: queryKeys.ftbClaims.all })
  }, [queryClient])
  const handleRefreshPlayers = useCallback(() => {
    queryClient.invalidateQueries({
      queryKey: queryKeys.worldRestore.playerLocations(serverId),
    })
  }, [queryClient, serverId])
  const handleInitComplete = useCallback(() => {
    setInitOpen(false)
    setInitForce(false)
    queryClient.invalidateQueries({ queryKey: queryKeys.map.all })
  }, [queryClient])

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
    [handleDimensionChange, panToBlock, regionRelpath],
  )
  const handlePlayerClick = useCallback(
    (player: PlayerLocationEntry) => {
      if (player.region_dir_relpath === regionRelpath) {
        panToPlayerBlock(player.pos.x, player.pos.z)
        return
      }
      if (player.region_dir_relpath) {
        pendingPanRef.current = {
          dimRelpath: player.region_dir_relpath,
          bx: player.pos.x,
          bz: player.pos.z,
        }
        handleDimensionChange(player.region_dir_relpath)
      }
    },
    [handleDimensionChange, panToPlayerBlock, regionRelpath],
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

  const canPreview =
    !!serverId &&
    thresholdSeconds >= 0 &&
    !previewStarting &&
    !previewActive &&
    !applyActive
  const canApply =
    !!serverId &&
    !!previewTaskId &&
    previewStatus === 'completed' &&
    !!previewResult &&
    previewMatchesCurrentControls &&
    serverStopped &&
    !applyActive &&
    applyStatus !== 'completed'

  const startPreview = useCallback(async () => {
    setPreviewStarting(true)
    try {
      await chunkPruneApi.startPreview(serverId, {
        threshold_seconds: thresholdSeconds,
        mode: urlMode,
      })
      queryClient.invalidateQueries({
        queryKey: queryKeys.chunkPrune.state(serverId),
      })
      queryClient.invalidateQueries({ queryKey: taskQueryKeys.all })
    } catch (e) {
      const message = (e as Error).message || '启动区块清理预览失败'
      toast.error('启动区块清理预览失败', { description: message })
    } finally {
      setPreviewStarting(false)
    }
  }, [queryClient, serverId, thresholdSeconds, urlMode])

  const cancelPreview = useCallback(() => {
    if (!previewTaskId) return
    cancelTask.mutate(previewTaskId, {
      onSuccess: () => {
        queryClient.invalidateQueries({
          queryKey: queryKeys.chunkPrune.state(serverId),
        })
        queryClient.invalidateQueries({ queryKey: taskQueryKeys.all })
      },
    })
  }, [cancelTask, previewTaskId, queryClient, serverId])

  const startApply = useCallback(() => {
    if (!previewTaskId) return
    confirm({
      title: '删除预览中的区块',
      description:
        '该操作会修改该服务器所有维度的世界区域文件，并清理对应地图瓦片缓存。请确认服务器已停止并且当前预览仍是你想执行的范围。',
      confirmText: '删除区块',
      cancelText: '取消',
      variant: 'destructive',
      onConfirm: async () => {
        try {
          await chunkPruneApi.startApply(serverId, {
            preview_task_id: previewTaskId,
          })
          queryClient.invalidateQueries({
            queryKey: queryKeys.chunkPrune.state(serverId),
          })
          queryClient.invalidateQueries({ queryKey: taskQueryKeys.all })
        } catch (e) {
          const message = (e as Error).message || '启动区块删除失败'
          toast.error('启动区块删除失败', { description: message })
        }
      },
    })
  }, [confirm, previewTaskId, queryClient, serverId])

  const cancelApply = useCallback(() => {
    if (!applyTaskId) return
    cancelTask.mutate(applyTaskId, {
      onSuccess: () => {
        queryClient.invalidateQueries({
          queryKey: queryKeys.chunkPrune.state(serverId),
        })
        queryClient.invalidateQueries({ queryKey: taskQueryKeys.all })
      },
    })
  }, [applyTaskId, cancelTask, queryClient, serverId])

  if (!serverId) {
    return (
      <Alert variant="destructive">
        <AlertTitle>错误</AlertTitle>
        <AlertDescription>缺少服务器ID</AlertDescription>
      </Alert>
    )
  }

  return (
    <div className="flex h-full flex-col gap-4">
      <PageHeader
        title="区块清理"
        icon={<Eraser className="h-5 w-5" />}
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
                    <Button
                      variant="destructive"
                      onClick={() => {
                        setInitForce(true)
                        setInitOpen(true)
                      }}
                      title="删除客户端 JAR 和调色板缓存后重新下载并生成"
                    >
                      重载渲染前置
                    </Button>
                  </>
                )}
                <Select
                  items={dimensionOptions}
                  value={dimensionRelpath ?? null}
                  onValueChange={(v) => {
                    if (typeof v === 'string') handleDimensionChange(v)
                  }}
                  itemToStringLabel={(v) =>
                    dimensionOptions.find((o) => o.value === v)?.label ??
                    String(v)
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
                <MapHelpButton
                  title="区块清理说明"
                  description="预览会扫描服务器所有维度；当前选择的维度只影响地图上显示哪一部分结果。"
                >
                  <div className="space-y-3 text-sm">
                    <section>
                      <div className="mb-1 font-medium">清理机制</div>
                      <ul className="list-inside list-disc space-y-1 text-muted-foreground">
                        <li>区块清理会删除 InhabitedTime 低于阈值的区块；这个值越低，通常说明区块被玩家长期使用或人工改动的可能性越低。</li>
                      </ul>
                    </section>
                    <section>
                      <div className="mb-1 font-medium">查看地图</div>
                      <ul className="list-inside list-disc space-y-1 text-muted-foreground">
                        <li>按住鼠标左键/中键拖动：平移视角</li>
                        <li>滚轮：缩放</li>
                        <li>顶部维度选择：切换当前显示的维度</li>
                      </ul>
                    </section>
                    <section>
                      <div className="mb-1 font-medium">预览清理范围</div>
                      <ul className="list-inside list-disc space-y-1 text-muted-foreground">
                        <li>设置清理阈值后点击“预览”</li>
                        <li>预览运行时只更新进度，不会实时绘制地图</li>
                        <li>预览完成后，地图会用红色覆盖层显示将被删除的区块或区域</li>
                        <li>切换维度只切换预览显示，不会重新扫描</li>
                      </ul>
                    </section>
                    <section>
                      <div className="mb-1 font-medium">清理模式</div>
                      <ul className="list-inside list-disc space-y-1 text-muted-foreground">
                        <li>区块模式：逐个删除低于阈值的区块，同一区域内的高活跃区块会保留</li>
                        <li>区域模式：只有整个区域都符合条件时才删除该区域</li>
                      </ul>
                    </section>
                    <section>
                      <div className="mb-1 font-medium">FTB 领地保护</div>
                      <ul className="list-inside list-disc space-y-1 text-muted-foreground">
                        <li>清理前会读取 FTB Claims / FTB Utilities 的领地数据</li>
                        <li>区块模式下，被领地声明的区块会跳过</li>
                        <li>区域模式下，只要区域内存在领地区块，整个区域都会保留</li>
                      </ul>
                    </section>
                    <section>
                      <div className="mb-1 font-medium">执行删除</div>
                      <ul className="list-inside list-disc space-y-1 text-muted-foreground">
                        <li>只有当前阈值和模式仍匹配已完成预览时，才能执行删除</li>
                        <li>删除前需要先停止服务器</li>
                        <li>删除会作用于服务器所有维度，而不是当前显示的维度</li>
                        <li>删除会同时处理对应的 region、entities、poi 数据</li>
                        <li>删除完成后会刷新受影响的地图缓存</li>
                      </ul>
                    </section>
                    <section>
                      <div className="mb-1 font-medium">图层</div>
                      <ul className="list-inside list-disc space-y-1 text-muted-foreground">
                        <li>领地图层用于确认受保护区域</li>
                        <li>玩家位置图层用于辅助判断哪些区域可能仍然重要</li>
                        <li>图层显示/隐藏只影响地图展示，不影响预览或删除范围</li>
                      </ul>
                    </section>
                    <section>
                      <div className="mb-1 font-medium">风险提示</div>
                      <ul className="list-inside list-disc space-y-1 text-muted-foreground">
                        <li>InhabitedTime 是活跃度指标，不是“是否被人工修改”的绝对证明</li>
                        <li>执行删除前建议确认预览覆盖层，并确保最近有可用备份</li>
                      </ul>
                    </section>
                  </div>
                </MapHelpButton>
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

      {!mapStatusQ.isLoading && mapStatusQ.data && !mapInitialized && (
        <Card>
          <CardContent className="flex flex-col items-center gap-4 py-8">
            <div className="text-center text-muted-foreground">
              {!mapStatusQ.data.client_jar_present
                ? '尚未下载客户端 JAR。'
                : !mapStatusQ.data.palette_present
                  ? '尚未生成调色板。'
                  : '调色板已过期（版本或mods变更）。'}
            </div>
            <Button
              onClick={() => {
                setInitForce(false)
                setInitOpen(true)
              }}
            >
              初始化地图
            </Button>
          </CardContent>
        </Card>
      )}

      {(mapInitialized || layoutQ.isLoading) && (
        <div className="flex flex-col gap-4 md:grid md:min-h-0 md:flex-1 md:grid-cols-[1fr_270px] md:grid-rows-1">
          <Card className="overflow-hidden py-0">
            <CardContent className="h-[60vh] p-0 md:h-full md:min-h-[60vh]">
              {regionsMap && regionRelpath ? (
                <ServerMap
                  serverId={serverId}
                  regionPath={regionRelpath}
                  regions={regionsMap}
                  selectionMode="none"
                  overlays={mapOverlays}
                  initialView={initialView}
                  onViewChange={handleViewChange}
                />
              ) : layoutQ.isLoading || regionsLoading ? (
                <div className="flex h-[60vh] items-center justify-center md:h-full">
                  <Spinner />
                </div>
              ) : null}
            </CardContent>
          </Card>

          <div className="flex min-w-0 flex-col md:min-h-0 md:overflow-y-auto md:*:shrink-0">
            <Card>
              <CardContent>
                <Tabs defaultValue="prune" className="gap-4">
                  <TabsList
                    className={
                      claimsAvailable
                        ? 'grid w-full grid-cols-3'
                        : 'grid w-full grid-cols-2'
                    }
                  >
                    <TabsTrigger value="prune">清理</TabsTrigger>
                    {claimsAvailable && (
                      <TabsTrigger value="claims">领地列表</TabsTrigger>
                    )}
                    <TabsTrigger value="players">玩家位置</TabsTrigger>
                  </TabsList>
                  <TabsContent value="prune">
                    <ChunkPrunePanel
                      thresholdValue={thresholdValue}
                      thresholdUnit={thresholdUnit}
                      thresholdSeconds={thresholdSeconds}
                      mode={urlMode}
                      previewStatus={previewStatus}
                      previewStarting={previewStarting}
                      previewProgress={previewTask?.progress ?? null}
                      previewMessage={previewTask?.message ?? null}
                      previewResult={previewResult}
                      previewError={previewError}
                      applyStatus={applyStatus}
                      applyProgress={applyTask?.progress ?? null}
                      applyMessage={applyTask?.message ?? null}
                      applyResult={applyResult}
                      applyError={applyError}
                      serverStopped={serverStopped}
                      canPreview={canPreview}
                      canApply={canApply}
                      cancellingPreview={cancelTask.isPending}
                      cancellingApply={cancelTask.isPending}
                      onThresholdValueChange={setThresholdValue}
                      onThresholdUnitChange={setThresholdUnit}
                      onModeChange={handleModeChange}
                      onPreview={startPreview}
                      onCancelPreview={cancelPreview}
                      onApply={startApply}
                      onCancelApply={cancelApply}
                    />
                  </TabsContent>
                  <TabsContent value="claims">
                    {claimsAvailable && (
                      <TeamClusterList
                        data={claimsQ.data}
                        isLoading={claimsQ.isLoading}
                        isError={claimsQ.isError}
                        currentDimRelpath={regionRelpath}
                        dimensionLabelByRelpath={dimensionLabelByRelpath}
                        mode={urlMode === 'regions' ? 'region' : 'chunk'}
                        selection={new Set<ChunkKey>()}
                        overlayVisible={claimsOverlayVisible}
                        selectable={false}
                        onOverlayVisibleChange={setClaimsOverlayVisible}
                        onRefresh={handleRefreshClaims}
                        onClusterHover={highlightClusters}
                        onClusterClick={handleClusterClick}
                        onClusterSelect={() => undefined}
                        onTeamHover={highlightClusters}
                        onTeamSelectInDim={() => undefined}
                      />
                    )}
                  </TabsContent>
                  <TabsContent value="players">
                    <PlayerLocationList
                      data={playerLocationsQ.data}
                      isLoading={playerLocationsQ.isLoading}
                      isError={playerLocationsQ.isError}
                      currentDimRelpath={regionRelpath}
                      dimensionLabelByRelpath={dimensionLabelByRelpath}
                      profilesByUuid={playerProfiles.profilesByUuid}
                      pendingProfileUuids={playerProfiles.pendingUuids}
                      onlinePlayerUuids={onlinePlayerUuids}
                      onlineOnly={onlinePlayersOnly}
                      onlineStatusLoading={onlinePlayersQ.isLoading}
                      onlineStatusAvailable={onlineStatusAvailable}
                      overlayVisible={playersOverlayVisible}
                      onOverlayVisibleChange={setPlayersOverlayVisible}
                      onOnlineOnlyChange={setOnlinePlayersOnly}
                      onRefresh={handleRefreshPlayers}
                      onPlayerClick={handlePlayerClick}
                    />
                  </TabsContent>
                </Tabs>
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
          mode={urlMode === 'regions' ? 'region' : 'chunk'}
          teamChunksInDim={popoverContext.teamChunksInDim}
          clustersInDim={popoverContext.clustersInDim}
          onClose={closeClaimsPopover}
          onSelectCluster={() => closeClaimsPopover()}
          onSelectTeamInDim={() => closeClaimsPopover()}
        />
      )}

      <MapInitDialog
        open={initOpen}
        serverId={serverId}
        force={initForce}
        onClose={() => {
          setInitOpen(false)
          setInitForce(false)
        }}
        onComplete={handleInitComplete}
      />
      {confirmDialog}
    </div>
  )
}

export default ServerChunkPrune
