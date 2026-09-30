import { api } from '@/shared/http/api'

export const worldRestoreApi = {
  heartbeatPreview: (serverId: string, sessionId: string) =>
    api
      .post<void>(
        `/servers/${serverId}/world-restore/preview/${sessionId}/heartbeat`,
      )
      .then((r) => r.data),

  endPreview: (serverId: string, sessionId: string) =>
    api
      .delete<void>(
        `/servers/${serverId}/world-restore/preview/${sessionId}`,
      )
      .then((r) => r.data),

  // Tile URL is exposed (not a fetch helper) — Leaflet's GridLayer needs the
  // URL string itself; the dedicated tile layer handles the authed fetch.
  previewTileUrl: (serverId: string, sessionId: string, rx: number, rz: number) =>
    `/servers/${serverId}/world-restore/preview/${sessionId}/tile/${rx}/${rz}.png`,

}
