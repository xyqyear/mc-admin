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
