import { api } from '@/utils/api'
import type { DimensionInfo, MapStatus, RegionList } from '@/types/MapTypes'

export const mapApi = {
  getStatus: (serverId: string) =>
    api.get<MapStatus>(`/servers/${serverId}/map/status`).then((r) => r.data),

  getDimensions: (serverId: string) =>
    api
      .get<DimensionInfo[]>(`/servers/${serverId}/map/dimensions`)
      .then((r) => r.data),

  getRegions: (serverId: string, region: string) =>
    api
      .get<RegionList>(`/servers/${serverId}/map/regions`, {
        params: { region },
      })
      .then((r) => r.data),

  clearDimensionCache: (serverId: string, region: string) =>
    api
      .delete<{ cleared: string }>(`/servers/${serverId}/map/cache`, {
        params: { region },
      })
      .then((r) => r.data),
}
