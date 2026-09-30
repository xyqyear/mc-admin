
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
  snapshot: Snapshot;
  skipped_paths: string[];
}

export type SnapshotScope =
  | { kind: 'global' }
  | { kind: 'server'; server_id: string }
  | { kind: 'paths'; server_id: string; paths: string[] }

export interface SnapshotTaskAccepted {
  task_id: string
  restoration_id?: string | null
  skipped_paths: string[]
}

export interface RestoreProgressState {
  active: boolean
  percent: number
  message: string
  log: string[]
  done: boolean
  error: string | null
}

export interface Restoration {
  id: string
  operation_id: string | null
  server_id: string | null
  scope: SnapshotScope | null
  source_snapshot_id: string
  safety_snapshot_id: string | null
  source_snapshot_exists: boolean
  safety_snapshot_exists: boolean
  rollback_available: boolean
  rollback_unavailable_reason: string | null
  rollback_of_id: string | null
  is_rollback: boolean
  started_at: string
  finished_at: string | null
  status: 'pending' | 'running' | 'succeeded' | 'failed' | 'cancelled' | 'interrupted'
  error_message: string | null
}

export interface RestorationHistory {
  restorations: Restoration[]
  total: number
}

export interface ListSnapshotsResponse {
  snapshots: Snapshot[];
}

export interface SnapshotRestoreRequest {
  source_snapshot_id: string
  scope: SnapshotScope
  entry_point?: 'files' | 'world' | 'snapshots'
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
