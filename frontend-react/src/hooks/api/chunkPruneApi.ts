import { api } from '@/utils/api'
import type {
  ChunkPruneApplyRequest,
  ChunkPrunePreviewRequest,
  ChunkPruneSettingsResponse,
  ChunkPruneStartResponse,
} from '@/types/ChunkPrune'

export const chunkPruneApi = {
  getSettings: (serverId: string) =>
    api
      .get<ChunkPruneSettingsResponse>(
        `/servers/${serverId}/chunk-prune/settings`,
      )
      .then((r) => r.data),

  startPreview: (serverId: string, request: ChunkPrunePreviewRequest) =>
    api
      .post<ChunkPruneStartResponse>(
        `/servers/${serverId}/chunk-prune/preview`,
        request,
      )
      .then((r) => r.data),

  startApply: (serverId: string, request: ChunkPruneApplyRequest) =>
    api
      .post<ChunkPruneStartResponse>(
        `/servers/${serverId}/chunk-prune/apply`,
        request,
      )
      .then((r) => r.data),
}
