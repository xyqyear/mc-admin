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

export const snapshotApi = {
  // 列出所有快照 (不传入server_id和path)
  getAllSnapshots: async (): Promise<Snapshot[]> => {
    const res = await api.get<ListSnapshotsResponse>("/snapshots");
    return res.data.snapshots;
  },

  // 创建全局快照 (不传入server_id和path)
  createGlobalSnapshot: async (): Promise<CreateSnapshotResponse> => {
    const res = await api.post<CreateSnapshotResponse>("/snapshots", {});
    return res.data;
  },

  // 获取备份仓库使用情况
  getBackupRepositoryUsage: async (): Promise<BackupRepositoryUsage> => {
    const res = await api.get<BackupRepositoryUsage>("/snapshots/repository-usage");
    return res.data;
  },
};

// Export types for use in other modules
export type { Snapshot, CreateSnapshotResponse, ListSnapshotsResponse, BackupRepositoryUsage };