import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import { worldRestoreApi } from '@/hooks/api/worldRestoreApi'
import type { ApiError } from '@/utils/api'
import type { RestorationSelection } from '@/types/WorldRestore'
import { queryKeys } from '@/utils/api'

// Restoration and rollback flows are SSE — those are driven by `useEventStream`
// from the page directly, not as TanStack mutations. Only the plain JSON
// endpoints live here.

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
      // Silent on error — the page already polls and will recover by
      // restarting the preview if the session expires.
    })

  return {
    useCreateWorldSnapshot,
    useEndPreview,
    useHeartbeatPreview,
  }
}
