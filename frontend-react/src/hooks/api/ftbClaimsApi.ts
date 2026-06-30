import { api } from '@/utils/api'
import type { FtbClaimsResponse } from '@/types/FtbClaims'

export const ftbClaimsApi = {
  getClaims: (serverId: string) =>
    api
      .get<FtbClaimsResponse>(`/servers/${serverId}/claims`)
      .then((r) => r.data),
}
