import { useQueryClient } from '@tanstack/react-query'
import {
  useCallback,
  useEffect,
  useMemo,
  useState
} from 'react'
import { toast } from 'sonner'
import { setWorldMapMode, useWorldMapController } from '@/features/world/useWorldMapController'

import { type ServerMapOverlay } from '@/features/world/map/ServerMap'
import { chunkPruneApi } from '@/features/world/prune/api'
import { buildPrunePreviewLayer } from '@/features/world/prune/components/PrunePreviewOverlayLayer'
import {
  secondsToThresholdInput,
  thresholdInputToSeconds,
} from '@/features/world/prune/components/thresholdUnits'
import type { ChunkPruneMode, ChunkPruneResultData } from '@/features/world/prune/contracts'
import {
  useChunkPrunePreviewGeometry,
  useChunkPruneSettings,
  useChunkPruneState,
} from '@/features/world/prune/queries'
import { useTaskMutations } from '@/features/tasks/commands'
import { taskQueryKeys } from '@/features/tasks/queries'
import { useConfirm } from '@/shared/hooks/useConfirm'
import type { BackgroundTaskStatus } from '@/features/tasks/contracts'
import { getErrorMessage, queryKeys, type ApiError } from '@/shared/http/api'

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

export function previewUnavailableMessage(availability: string | undefined): string | null {
  if (availability === 'expired') return '预览已过期，请重新生成预览后再删除。'
  if (availability === 'stale') return '世界文件或保护范围已变化，请重新生成预览。'
  if (availability === 'consumed') return '此预览已用于删除，请重新生成预览。'
  if (availability === 'unavailable') return '预览产物已不可用，请重新生成预览。'
  return null
}

export function useChunkPruneController(serverId: string) {
  const world = useWorldMapController(serverId)
  const { serverStopped, regionRelpath, claimsOverlays, playersOverlays } = world
  const urlMode: ChunkPruneMode = world.rawMode === 'chunks' ? 'chunks' : 'regions'
  const queryClient = useQueryClient()
  const settingsQ = useChunkPruneSettings(serverId)
  const { useCancelTask } = useTaskMutations()
  const cancelTask = useCancelTask()
  const { confirm, confirmDialog } = useConfirm()

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
  const [submissionError, setSubmissionError] = useState<string | null>(null)
  const [rejectedPreviewId, setRejectedPreviewId] = useState<string | null>(null)
  const preview = stateQ.data?.preview
  const previewAvailable = !(preview?.apply_task_id === applyTaskId && applyTask?.errorCode?.startsWith('prune_preview_')) && preview?.availability === 'ready' && preview.task_id === previewTaskId && rejectedPreviewId !== previewTaskId
  const previewRenderable = previewAvailable || preview?.availability === 'consumed'
  const availabilityError = previewUnavailableMessage(preview?.availability)
  const previewError =
    availabilityError ?? previewTask?.error ?? (stateQ.isError ? '无法读取区块清理任务状态' : null)
  const applyError =
    submissionError ?? applyTask?.error ?? (stateQ.isError ? '无法读取区块清理任务状态' : null)
  const previewActive = isTaskActive(previewStatus)
  const applyActive = isTaskActive(applyStatus)

  const applyModeChange = useCallback((mode: ChunkPruneMode) => {
    setWorldMapMode(mode)
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

  const previewMatchesCurrentControls =
    !!previewResult &&
    previewResult.threshold_seconds === thresholdSeconds &&
    previewResult.mode === urlMode
  const previewGeometryQ = useChunkPrunePreviewGeometry(
    serverId,
    previewTaskId ?? undefined,
    previewStatus === 'completed' && previewMatchesCurrentControls && previewRenderable,
  )
  const currentPreviewDimension = useMemo(
    () =>
      previewMatchesCurrentControls && regionRelpath
        ? previewGeometryQ.data?.dimensions.find(
          (dim) => dim.region_dir_relpath === regionRelpath,
        ) ?? null
        : null,
    [previewGeometryQ.data, previewMatchesCurrentControls, regionRelpath],
  )

  const pruneOverlay = useMemo<ServerMapOverlay[] | undefined>(() => {
    if (
      !previewTaskId ||
      previewStatus !== 'completed' ||
      !previewRenderable ||
      !currentPreviewDimension ||
      !previewMatchesCurrentControls
    ) {
      return undefined
    }
    if (currentPreviewDimension.shapes.length === 0) return undefined
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
    previewRenderable,
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
    previewAvailable &&
    !!previewResult &&
    previewMatchesCurrentControls &&
    serverStopped &&
    !applyActive

  const startPreview = useCallback(async () => {
    setPreviewStarting(true)
    setSubmissionError(null)
    try {
      await chunkPruneApi.startPreview(serverId, {
        threshold_seconds: thresholdSeconds,
        mode: urlMode,
      })
      queryClient.invalidateQueries({
        queryKey: queryKeys.chunkPrune.state(serverId),
      })
      queryClient.invalidateQueries({ queryKey: taskQueryKeys.all })
      queryClient.invalidateQueries({ queryKey: queryKeys.operations.all })
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
        queryClient.invalidateQueries({ queryKey: queryKeys.operations.all })
      },
    })
  }, [cancelTask, previewTaskId, queryClient, serverId])

  const startApply = useCallback(() => {
    if (!previewTaskId || !canApply) return
    confirm({
      title: '删除预览中的区块',
      description:
        '该操作会修改该服务器所有维度的世界区域文件，并清理对应地图瓦片缓存。请确认服务器已停止并且当前预览仍是你想执行的范围。',
      confirmText: '删除区块',
      cancelText: '取消',
      variant: 'destructive',
      onConfirm: async () => {
        setSubmissionError(null)
        try {
          await chunkPruneApi.startApply(serverId, {
            preview_task_id: previewTaskId,
          })
          queryClient.invalidateQueries({
            queryKey: queryKeys.chunkPrune.state(serverId),
          })
          queryClient.invalidateQueries({ queryKey: taskQueryKeys.all })
          queryClient.invalidateQueries({ queryKey: queryKeys.operations.all })
        } catch (e) {
          const message = getErrorMessage(e, '启动区块删除失败')
          setSubmissionError(message)
          const detail = (e as ApiError).detail
          if (detail && typeof detail === 'object' && 'code' in detail && String(detail.code).startsWith('prune_preview_')) setRejectedPreviewId(previewTaskId)
          void queryClient.invalidateQueries({ queryKey: queryKeys.chunkPrune.state(serverId) })
          toast.error('启动区块删除失败', { description: message })
        }
      },
    })
  }, [canApply, confirm, previewTaskId, queryClient, serverId])

  const cancelApply = useCallback(() => {
    if (!applyTaskId) return
    cancelTask.mutate(applyTaskId, {
      onSuccess: () => {
        queryClient.invalidateQueries({
          queryKey: queryKeys.chunkPrune.state(serverId),
        })
        queryClient.invalidateQueries({ queryKey: taskQueryKeys.all })
        queryClient.invalidateQueries({ queryKey: queryKeys.operations.all })
      },
    })
  }, [applyTaskId, cancelTask, queryClient, serverId])

  return {
    ...world,
    urlMode,
    settingsQ,
    thresholdValue,
    setThresholdValue,
    thresholdUnit,
    setThresholdUnit,
    thresholdSeconds,
    stateQ,
    previewAvailable,
    previewStarting,
    cancelTask,
    previewTask,
    applyTask,
    previewTaskId,
    applyTaskId,
    previewStatus,
    applyStatus,
    previewResult,
    applyResult,
    previewError,
    applyError,
    previewActive,
    applyActive,
    previewMatchesCurrentControls,
    previewGeometryQ,
    currentPreviewDimension,
    mapOverlays,
    canPreview,
    canApply,
    startPreview,
    cancelPreview,
    startApply,
    cancelApply,
    handleModeChange,
    confirmDialog
  }
}
