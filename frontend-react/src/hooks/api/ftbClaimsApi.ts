import { api } from '@/utils/api'
import type { FtbClaimsResponse } from '@/types/FtbClaims'

// REST surface for the FTB claims feature. The backend runs `mcmap
// extract-ftb-claims` fresh on every call — there is no caching layer.
export const ftbClaimsApi = {
  getClaims: (serverId: string) =>
    api
      .get<FtbClaimsResponse>(`/servers/${serverId}/world-restore/claims`)
      .then((r) => r.data),
}
