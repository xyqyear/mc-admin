
export interface SnapshotSummary {
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

export interface Snapshot {
  time: string;
  paths: string[];
  excludes: string[];
  hostname: string;
  username: string;
  id: string;
  short_id: string;
  program_version?: string;
  summary?: SnapshotSummary;
}

export interface CreateSnapshotResponse {
  message: string;
  snapshot: Snapshot;
}

export interface ListSnapshotsResponse {
  snapshots: Snapshot[];
}

export interface SnapshotRestoreRequest {
  snapshot_id: string;
  server_id?: string;
  paths?: string[];
}

export type SnapshotRestoreEventType =
  | 'start'
  | 'safety_snapshot'
  | 'restore'
  | 'invalidate_cache'
  | 'complete'
  | 'error'

export interface SnapshotRestoreEvent {
  event_type: SnapshotRestoreEventType
  message?: string
  percent?: number
  safety_snapshot_id?: string
}

export interface DeleteSnapshotResponse {
  message: string;
}

export interface ListLocksResponse {
  locks: string;
}

export interface UnlockResponse {
  message: string;
  output: string;
}

export interface RestorePreviewRequest {
  snapshot_id: string;
  server_id?: string;
  paths?: string[];
}

export interface RestorePreviewAction {
  action: string;
  item?: string;
  size?: number;
}

export interface RestorePreviewResponse {
  actions: RestorePreviewAction[];
  preview_summary: string;
}

export interface BackupRepositoryUsage {
  backupUsedGB: number;
  backupTotalGB: number;
  backupAvailableGB: number;
}
