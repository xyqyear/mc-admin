import { api } from '@/utils/api'
import {
  transformTask,
  type BackgroundTaskResponse,
} from '@/hooks/api/taskApi'
import type { BackgroundTask } from '@/stores/useBackgroundTaskStore'
import type {
  ChunkPruneApplyRequest,
  ChunkPrunePreviewGeometryResponse,
  ChunkPrunePreviewRequest,
  ChunkPruneSettingsResponse,
  ChunkPruneStartResponse,
} from '@/types/ChunkPrune'

export interface ChunkPruneState {
  previewTask: BackgroundTask | null
  applyTask: BackgroundTask | null
}

interface ChunkPruneStateResponse {
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
