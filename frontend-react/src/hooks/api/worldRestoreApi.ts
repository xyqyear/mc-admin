import { api } from '@/utils/api'
import type {
  CreateSnapshotResponse,
  ListEligibleSnapshotsResponse,
  ListRestorationsResponse,
  RestorationResponse,
  RestorationSelection,
  WorldLayoutResponse,
} from '@/types/WorldRestore'

// REST surface for the world-restore feature. Streaming endpoints (POST
// /preview, POST /restore, POST /restorations/{id}/rollback) are consumed via
// useEventStream — see hooks/useEventStream.ts.
export const worldRestoreApi = {
  getLayout: (serverId: string) =>
    api
      .get<WorldLayoutResponse>(`/servers/${serverId}/world-restore/layout`)
      .then((r) => r.data),

  eligibleSnapshots: (serverId: string, selection: RestorationSelection) =>
    api
      .post<ListEligibleSnapshotsResponse>(
        `/servers/${serverId}/world-restore/eligible-snapshots`,
        selection,
      )
      .then((r) => r.data),

  createSnapshot: (serverId: string, selection: RestorationSelection) =>
    api
      .post<CreateSnapshotResponse>(
        `/servers/${serverId}/world-restore/snapshots`,
        selection,
      )
      .then((r) => r.data),

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

  listRestorations: (serverId: string, limit = 50, offset = 0) =>
    api
      .get<ListRestorationsResponse>(
        `/servers/${serverId}/world-restore/restorations`,
        { params: { limit, offset } },
      )
      .then((r) => r.data),

  getRestoration: (serverId: string, restorationId: string) =>
    api
      .get<RestorationResponse>(
        `/servers/${serverId}/world-restore/restorations/${restorationId}`,
      )
      .then((r) => r.data),
}
