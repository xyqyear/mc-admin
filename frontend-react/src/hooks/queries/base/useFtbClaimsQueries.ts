import { useQuery } from '@tanstack/react-query'

import { ftbClaimsApi } from '@/hooks/api/ftbClaimsApi'
import { queryKeys } from '@/utils/api'

// Extraction takes a few hundred ms and produces a deterministic result for
// a given world snapshot — long stale time, no auto refetch. Users hit the
// page-level refresh action when they want to re-extract.
export const useFtbClaims = (serverId: string | undefined, enabled = true) =>
  useQuery({
    queryKey: queryKeys.ftbClaims.claims(serverId ?? ''),
    queryFn: () => ftbClaimsApi.getClaims(serverId!),
    enabled: !!serverId && enabled,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  })
