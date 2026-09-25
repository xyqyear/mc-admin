import { useQuery } from '@tanstack/react-query'

import { worldRestoreApi } from '@/features/world/restore/api'
import type { RestorationSelection } from '@/features/world/restore/contracts'
import { queryKeys } from '@/shared/http/api'

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
