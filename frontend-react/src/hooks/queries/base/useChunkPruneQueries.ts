import { useQuery } from '@tanstack/react-query'

import { chunkPruneApi } from '@/hooks/api/chunkPruneApi'
import { queryKeys } from '@/utils/api'

export const useChunkPruneSettings = (serverId: string | undefined) =>
  useQuery({
    queryKey: queryKeys.chunkPrune.settings(serverId ?? ''),
    queryFn: () => chunkPruneApi.getSettings(serverId!),
    enabled: !!serverId,
    staleTime: 60_000,
  })

export const useChunkPruneState = (serverId: string | undefined) =>
  useQuery({
    queryKey: queryKeys.chunkPrune.state(serverId ?? ''),
    queryFn: () => chunkPruneApi.getState(serverId!),
    enabled: !!serverId,
    refetchInterval: (query) => {
      const state = query.state.data
      const tasks = [state?.previewTask, state?.applyTask]
      const hasActiveTask = tasks.some(
        (task) => task?.status === 'pending' || task?.status === 'running',
      )
      return hasActiveTask ? 1000 : 10000
    },
    staleTime: 1000,
    refetchOnMount: 'always',
  })
