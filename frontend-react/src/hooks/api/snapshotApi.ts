import type { BackupRepositoryUsage } from "@/types/ServerRuntime";
import { api } from "@/utils/api";

interface SnapshotSummary {
  backup_start: string;
  backup_end: string;
  files_new: number;
  files_changed: number;
  files_unmodified: number;
  dirs_new: number;
  dirs_changed: number;
  dirs_unmodified: number;
  data_blobs: number;
  tree_blobs: number;
  data_added: number;
  data_added_packed: number;
  total_files_processed: number;
  total_bytes_processed: number;
}

interface Snapshot {
  time: string;
  tree: string;
  paths: string[];
  hostname: string;
  username: string;
  id: string;
  short_id: string;
  program_version?: string;
  summary?: SnapshotSummary;
}

interface CreateSnapshotResponse {
  message: string;
  snapshot: Snapshot;
}

interface ListSnapshotsResponse {
  snapshots: Snapshot[];
}

interface SnapshotRestoreRequest {
  snapshot_id: string;
  server_id?: string;
  paths?: string[];
}

// SSE event payload streamed by POST /snapshots/restore. Mirrors the world-
// restore RestoreEvent shape so the same progress reducer can drive it.
type SnapshotRestoreEventType =
  | 'start'
  | 'safety_snapshot'
  | 'restore'
  | 'invalidate_cache'
  | 'complete'
  | 'error'

interface SnapshotRestoreEvent {
  event_type: SnapshotRestoreEventType
  message?: string
  percent?: number
  safety_snapshot_id?: string
}

interface DeleteSnapshotResponse {
  message: string;
}

interface ListLocksResponse {
  locks: string;
}

interface UnlockResponse {
  message: string;
  output: string;
}

interface RestorePreviewRequest {
  snapshot_id: string;
  server_id?: string;
  paths?: string[];
}

interface RestorePreviewAction {
  message_type: string;
  action?: string;
  item?: string;
  size?: number;
}

interface RestorePreviewResponse {
  actions: RestorePreviewAction[];
  preview_summary: string;
}

export const snapshotApi = {
  getAllSnapshots: async (params?: {
    server_id?: string;
    path?: string;
  }): Promise<Snapshot[]> => {
    const queryParams = new URLSearchParams();
    if (params?.server_id) queryParams.set('server_id', params.server_id);
    if (params?.path) queryParams.set('path', params.path);

    const url = `/snapshots${queryParams.toString() ? `?${queryParams.toString()}` : ''}`;
    const res = await api.get<ListSnapshotsResponse>(url);
    return res.data.snapshots;
  },

  createSnapshot: async (params?: {
    server_id?: string;
    paths?: string[];
  }): Promise<CreateSnapshotResponse> => {
    const res = await api.post<CreateSnapshotResponse>("/snapshots", params || {});
    return res.data;
  },

  previewRestore: async (data: RestorePreviewRequest): Promise<RestorePreviewResponse> => {
    const res = await api.post<RestorePreviewResponse>("/snapshots/restore/preview", data);
    return res.data;
  },

  createGlobalSnapshot: async (): Promise<CreateSnapshotResponse> => {
    return snapshotApi.createSnapshot();
  },

  getBackupRepositoryUsage: async (): Promise<BackupRepositoryUsage> => {
    const res = await api.get<BackupRepositoryUsage>("/snapshots/repository-usage");
    return res.data;
  },

  deleteSnapshot: async (snapshotId: string): Promise<DeleteSnapshotResponse> => {
    const res = await api.delete<DeleteSnapshotResponse>(`/snapshots/${snapshotId}`);
    return res.data;
  },

  listLocks: async (): Promise<ListLocksResponse> => {
    const res = await api.get<ListLocksResponse>("/snapshots/locks");
    return res.data;
  },

  unlockRepository: async (): Promise<UnlockResponse> => {
    const res = await api.post<UnlockResponse>("/snapshots/unlock");
    return res.data;
  },
};

export type {
  Snapshot,
  CreateSnapshotResponse,
  ListSnapshotsResponse,
  SnapshotRestoreRequest,
  SnapshotRestoreEvent,
  SnapshotRestoreEventType,
  RestorePreviewRequest,
  RestorePreviewAction,
  RestorePreviewResponse,
  BackupRepositoryUsage,
  DeleteSnapshotResponse,
  ListLocksResponse,
  UnlockResponse
};