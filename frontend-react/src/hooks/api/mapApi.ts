import { api } from '@/utils/api'
import type { MapStatus, RegionList } from '@/types/MapTypes'

export const mapApi = {
  getStatus: (serverId: string) =>
    api.get<MapStatus>(`/servers/${serverId}/map/status`).then((r) => r.data),

  getRegions: (serverId: string, region: string) =>
    api
      .get<RegionList>(`/servers/${serverId}/map/regions`, {
        params: { region },
      })
      .then((r) => r.data),
}
