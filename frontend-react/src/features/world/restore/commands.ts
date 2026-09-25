import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import { worldRestoreApi } from '@/features/world/restore/api'
import type { ApiError } from '@/shared/http/api'
import type { RestorationSelection } from '@/features/world/restore/contracts'
import { queryKeys } from '@/shared/http/api'

// Request-owned restore controllers handle finite SSE; these commands return JSON.

export const useWorldRestoreMutations = () => {
  const queryClient = useQueryClient()

  const useCreateWorldSnapshot = (serverId: string) =>
    useMutation({
      mutationFn: (selection: RestorationSelection) =>
        worldRestoreApi.createSnapshot(serverId, selection),
      onSuccess: (data) => {
        toast.success(`快照创建成功: ${data.snapshot.short_id}`)
        queryClient.invalidateQueries({ queryKey: queryKeys.worldRestore.all })
        queryClient.invalidateQueries({ queryKey: queryKeys.snapshots.all })
      },
      onError: (error: ApiError) => {
        const detail = error?.message ?? '未知错误'
        toast.error(`快照创建失败: ${detail}`)
      },
    })

  const useEndPreview = (serverId: string) =>
    useMutation({
      mutationFn: (sessionId: string) =>
        worldRestoreApi.endPreview(serverId, sessionId),
      onError: (error: ApiError) => {
        // Tear-down failures are non-blocking (the janitor will reap stale
        // sessions) — surface as a low-priority info toast rather than error.
        const detail = error?.message ?? '未知错误'
        toast.message(`预览会话结束失败: ${detail}`)
      },
    })

  const useHeartbeatPreview = (serverId: string) =>
    useMutation({
      mutationFn: (sessionId: string) =>
        worldRestoreApi.heartbeatPreview(serverId, sessionId),

    })

  return {
    useCreateWorldSnapshot,
    useEndPreview,
    useHeartbeatPreview,
  }
}
