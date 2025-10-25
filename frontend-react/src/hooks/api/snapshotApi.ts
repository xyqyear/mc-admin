import type { BackupRepositoryUsage } from "@/types/ServerRuntime";
import { api } from "@/utils/api";

// Snapshot management types
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

interface RestoreSnapshotRequest {
  snapshot_id: string;
  server_id?: string;
  path?: string;
  skip_safety_check?: boolean;  // 新增：控制是否跳过安全检查
}

interface RestoreSnapshotResponse {
  message: string;
  safety_snapshot_id?: string;
}

interface DeleteSnapshotResponse {
  message: string;
}

interface RestorePreviewRequest {
  snapshot_id: string;
  server_id?: string;
  path?: string;
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
  // 列出所有快照（可按路径过滤）
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

  // 创建快照（全局或特定路径）
  createSnapshot: async (params?: {
    server_id?: string;
    path?: string;
  }): Promise<CreateSnapshotResponse> => {
    const res = await api.post<CreateSnapshotResponse>("/snapshots", params || {});
    return res.data;
  },

  // 恢复快照（包含安全检查）
  restoreSnapshot: async (data: RestoreSnapshotRequest): Promise<RestoreSnapshotResponse> => {
    const res = await api.post<RestoreSnapshotResponse>("/snapshots/restore", data);
    return res.data;
  },

  // 预览快照恢复操作
  previewRestore: async (data: RestorePreviewRequest): Promise<RestorePreviewResponse> => {
    const res = await api.post<RestorePreviewResponse>("/snapshots/restore/preview", data);
    return res.data;
  },

  // 创建全局快照（向后兼容）
  createGlobalSnapshot: async (): Promise<CreateSnapshotResponse> => {
    return snapshotApi.createSnapshot();
  },

  // 获取备份仓库使用情况
  getBackupRepositoryUsage: async (): Promise<BackupRepositoryUsage> => {
    const res = await api.get<BackupRepositoryUsage>("/snapshots/repository-usage");
    return res.data;
  },

  // 删除快照
  deleteSnapshot: async (snapshotId: string): Promise<DeleteSnapshotResponse> => {
    const res = await api.delete<DeleteSnapshotResponse>(`/snapshots/${snapshotId}`);
    return res.data;
  },
};

// Export types for use in other modules
export type {
  Snapshot,
  CreateSnapshotResponse,
  ListSnapshotsResponse,
  RestoreSnapshotRequest,
  RestoreSnapshotResponse,
  RestorePreviewRequest,
  RestorePreviewAction,
  RestorePreviewResponse,
  BackupRepositoryUsage,
  DeleteSnapshotResponse
};