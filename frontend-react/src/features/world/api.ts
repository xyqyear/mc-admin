import { api } from '@/shared/http/api'
import type { MapStatus, RegionList } from '@/features/world/map/contracts'
import type { FtbClaimsResponse } from '@/features/world/layers/claims/contracts'
import type { PlayerLocationsResponse } from '@/features/world/layers/players/contracts'
import type { WorldLayoutResponse, DimensionLabelsResponse } from '@/features/world/contracts'

export const worldApi = {
  getLayout: (serverId: string) =>
    api
      .get<WorldLayoutResponse>(`/servers/${serverId}/world-restore/layout`)
      .then((r) => r.data),

  getDimensionLabels: (serverId: string) =>
    api
      .get<DimensionLabelsResponse>(
        `/servers/${serverId}/world-restore/dimension-labels`,
      )
      .then((r) => r.data),

  getPlayerLocations: (serverId: string) =>
    api
      .get<PlayerLocationsResponse>(
        `/servers/${serverId}/player-locations`,
      )
      .then((r) => r.data),


  getStatus: (serverId: string) =>
    api.get<MapStatus>(`/servers/${serverId}/map/status`).then((r) => r.data),

  getRegions: (serverId: string, region: string) =>
    api
      .get<RegionList>(`/servers/${serverId}/map/regions`, {
        params: { region },
      })
      .then((r) => r.data),


  getClaims: (serverId: string) =>
    api
      .get<FtbClaimsResponse>(`/servers/${serverId}/claims`)
      .then((r) => r.data),

}
