import { api } from '@/shared/http/api'
import { transformTask } from '@/features/tasks/api';
import type { BackgroundTaskResponse } from '@/features/tasks/contracts';
import type { BackgroundTask } from '@/features/tasks/contracts'
import type {
  ChunkPruneApplyRequest,
  ChunkPrunePreview,
  ChunkPrunePreviewGeometryResponse,
  ChunkPrunePreviewRequest,
  ChunkPruneSettingsResponse,
  ChunkPruneStartResponse,
} from '@/features/world/prune/contracts'

export interface ChunkPruneState {
  preview: ChunkPrunePreview | null
  previewTask: BackgroundTask | null
  applyTask: BackgroundTask | null
}

interface ChunkPruneStateResponse {
  preview?: ChunkPrunePreview | null
  preview_task: BackgroundTaskResponse | null
  apply_task: BackgroundTaskResponse | null
}

export const chunkPruneApi = {
  getSettings: (serverId: string) =>
    api
      .get<ChunkPruneSettingsResponse>(
        `/servers/${serverId}/chunk-prune/settings`,
      )
      .then((r) => r.data),

  getState: (serverId: string): Promise<ChunkPruneState> =>
    api
      .get<ChunkPruneStateResponse>(`/servers/${serverId}/chunk-prune/state`)
      .then((r) => ({
        preview: r.data.preview ?? null,
        previewTask: r.data.preview_task
          ? transformTask(r.data.preview_task)
          : null,
        applyTask: r.data.apply_task
          ? transformTask(r.data.apply_task)
          : null,
      })),

  getPreviewGeometry: (
    serverId: string,
    previewTaskId: string,
  ): Promise<ChunkPrunePreviewGeometryResponse> =>
    api
      .get<ChunkPrunePreviewGeometryResponse>(
        `/servers/${serverId}/chunk-prune/previews/${previewTaskId}/geometry`,
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
