import { useQuery } from '@tanstack/react-query'

import { worldRestoreApi } from '@/hooks/api/worldRestoreApi'
import type { RestorationSelection } from '@/types/WorldRestore'
import { queryKeys } from '@/utils/api'

export const useWorldLayout = (serverId: string | undefined) =>
  useQuery({
    queryKey: queryKeys.worldRestore.layout(serverId ?? ''),
    queryFn: () => worldRestoreApi.getLayout(serverId!),
    enabled: !!serverId,
    staleTime: 30_000,
  })

// Selection is part of the cache key by value (the queryKey factory
// stringifies it via React Query's key serializer), so different selections
// produce distinct cache entries.
export const useEligibleSnapshots = (
  serverId: string | undefined,
  selection: RestorationSelection | null,
) =>
  useQuery({
    queryKey: queryKeys.worldRestore.eligible(serverId ?? '', selection),
    queryFn: () => worldRestoreApi.eligibleSnapshots(serverId!, selection!),
    enabled: !!serverId && !!selection,
    staleTime: 5_000,
  })

// Lightly polls so an in-progress restoration appears in the history table
// without manual refresh. The orchestrator finishes in seconds, so 5s is
// short enough to feel live but cheap enough to leave running on the page.
export const useRestorations = (serverId: string | undefined) =>
  useQuery({
    queryKey: queryKeys.worldRestore.history(serverId ?? ''),
    queryFn: () => worldRestoreApi.listRestorations(serverId!),
    enabled: !!serverId,
    refetchInterval: 5_000,
  })

export const useRestoration = (
  serverId: string | undefined,
  restorationId: string | undefined,
) =>
  useQuery({
    queryKey: queryKeys.worldRestore.restoration(
      serverId ?? '',
      restorationId ?? '',
    ),
    queryFn: () => worldRestoreApi.getRestoration(serverId!, restorationId!),
    enabled: !!serverId && !!restorationId,
  })
