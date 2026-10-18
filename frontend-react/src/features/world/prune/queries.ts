import { useQuery } from '@tanstack/react-query'
import { useTask, useTaskFeed } from '@/features/tasks/queries'

import { chunkPruneApi } from '@/features/world/prune/api'
import { queryKeys } from '@/shared/http/api'
import { pruneStateIndex } from './observation'

export const useChunkPruneSettings = (serverId: string | undefined) =>
  useQuery({
    queryKey: queryKeys.chunkPrune.settings(serverId ?? ''),
    queryFn: () => chunkPruneApi.getSettings(serverId!),
    enabled: !!serverId,
    staleTime: 60_000,
  })

export function useChunkPruneState(serverId: string | undefined, accepted: { preview?: string; apply?: string } = {}) {
  const feed = useTaskFeed(!!serverId)
  const state = pruneStateIndex(feed.pruneStates, serverId)
  const previewId = accepted.preview ?? state?.previewTaskId
  const applyId = accepted.apply ?? state?.applyTaskId
  const preview = useTask(previewId ?? '')
  const apply = useTask(applyId ?? '')
  return {
    data: state ? { preview: state.preview, previewTask: preview.data ?? null, applyTask: apply.data ?? null } : undefined,
    observedPreviewId: state?.previewTaskId,
    observedApplyId: state?.applyTaskId,
    checking: !feed.connected || !state || !!(previewId && !preview.data) || !!(applyId && !apply.data)
      || preview.isAwaitingResult || apply.isAwaitingResult,
    isError: (!feed.connected && feed.pruneStates !== undefined) || preview.isError || apply.isError,
  }
}

export const useChunkPrunePreviewGeometry = (
  serverId: string | undefined,
  previewTaskId: string | undefined,
  enabled: boolean,
) =>
  useQuery({
    queryKey: queryKeys.chunkPrune.previewGeometry(
      serverId ?? '',
      previewTaskId ?? '',
    ),
    queryFn: () => chunkPruneApi.getPreviewGeometry(serverId!, previewTaskId!),
    enabled: !!serverId && !!previewTaskId && enabled,
    staleTime: Infinity,
  })
