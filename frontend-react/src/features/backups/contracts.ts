
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
  | { kind: 'world'; server_id: string; selection: RestorationSelection }

export interface RestorationSelection {
  type: 'world' | 'dimension' | 'regions' | 'chunks'
  region_dir_relpath?: string | null
  regions?: Array<[number, number]>
  chunks?: Array<[number, number]>
}

export interface SnapshotTaskAccepted {
  task_id: string
  restoration_id?: string | null
  skipped_paths: string[]
}

export interface RestoreProgressState {
  active: boolean
  percent: number | null
  taskId?: string
  message: string
  log: string[]
  done: boolean
  error: string | null
}

export interface Restoration {
  id: string
  operation_id: string | null
  server_id: string | null
  server_generation: number | null
  targets: Array<{ server_id: string; generation: number | null }>
  binding_issue: string | null
  entry_point: string | null
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

export interface RestorationFilters {
  kind?: SnapshotScope['kind']
  status?: Restoration['status']
  entry_point?: 'files' | 'world' | 'snapshots' | 'history'
}

export interface ActiveRestorations {
  restorations: Array<Pick<Restoration, 'id' | 'operation_id' | 'scope' | 'status'>>
  total: number
}

export interface SnapshotTargetCheck {
  allowed: boolean
  reason: string | null
  skipped_paths: string[]
  skipped_count: number
}

export interface ListSnapshotsResponse {
  snapshots: Snapshot[];
}

export interface SnapshotRestoreRequest {
  source_snapshot_id: string
  scope: SnapshotScope
  entry_point?: 'files' | 'world' | 'snapshots'
  preview_id?: string
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

export interface SnapshotPreviewRequest {
  scope: SnapshotScope
  source_snapshot_id: string
}

export interface RestorePreviewAction {
  action: 'updated' | 'deleted' | 'restored'
  item: string
  size: number | null
}

export interface SnapshotPreviewResult {
  preview_id: string
  kind: 'files' | 'map'
  preview_summary: string
  updated: number
  deleted: number
  restored: number
  skipped_paths: string[]
  skipped_count: number
  notice: string
}

export interface SnapshotPreviewActions {
  actions: RestorePreviewAction[]
  next_cursor: number | null
}

export interface BackupRepositoryUsage {
  backupUsedGB: number;
  backupTotalGB: number;
  backupAvailableGB: number;
}
