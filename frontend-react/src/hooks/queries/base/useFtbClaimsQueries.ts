import { useQuery } from '@tanstack/react-query'

import { ftbClaimsApi } from '@/hooks/api/ftbClaimsApi'
import { queryKeys } from '@/utils/api'

export const useFtbClaims = (serverId: string | undefined, enabled = true) =>
  useQuery({
    queryKey: queryKeys.ftbClaims.claims(serverId ?? ''),
    queryFn: () => ftbClaimsApi.getClaims(serverId!),
    enabled: !!serverId && enabled,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  })
