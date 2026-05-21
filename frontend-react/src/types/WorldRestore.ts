// World-restore types — mirror backend pydantic models in
// app/models.py (Restoration*) and app/world/restore.py (PreviewEvent,
// RestoreEvent), plus the response models in app/routers/servers/world_restore.py.

// Mirrors the backend ResticSnapshot model. Local copy because snapshotApi.ts
// keeps its own shape unexported.
export interface ResticSnapshotSummary {
  backup_start?: string
  backup_end?: string
  files_new?: number
  files_changed?: number
  files_unmodified?: number
  dirs_new?: number
  dirs_changed?: number
  dirs_unmodified?: number
  data_blobs?: number
  tree_blobs?: number
  data_added?: number
  data_added_packed?: number
  total_files_processed?: number
  total_bytes_processed?: number
}

export interface ResticSnapshot {
  time: string
  paths: string[]
  hostname: string
  username: string
  program_version?: string
  id: string
  short_id: string
}

export interface ResticSnapshotWithSummary extends ResticSnapshot {
  summary?: ResticSnapshotSummary
}

export type RestorationType = 'world' | 'dimension' | 'regions' | 'chunks'

export type RestorationStatus =
  | 'running'
  | 'succeeded'
  | 'failed'
  | 'interrupted'

// Selection sent to the backend. The backend resolves it against the world
// layout to produce the affected MCA paths. `chunks` carries absolute chunk
// coords; the orchestrator groups them by region at execution time.
//
// `region_dir_relpath` is required for DIMENSION / REGIONS / CHUNKS scopes.
// The relpath is under the server's data/ dir (e.g. "world/region",
// "world_creative/region/DIM-1") and uniquely identifies a dimension across
// all world roots because the world root dir name is its prefix.
// WORLD scope ignores it and snapshots/restores every valid world root.
export interface RestorationSelection {
  type: RestorationType
  region_dir_relpath?: string | null
  regions?: Array<[number, number]>
  chunks?: Array<[number, number]>
}

export interface DimensionInfoResponse {
  region_dir: string
  entities_dir: string | null
  poi_dir: string | null
}

export interface WorldRootResponse {
  name: string
  path: string
  dimensions: DimensionInfoResponse[]
}

export interface WorldLayoutResponse {
  world_roots: WorldRootResponse[]
}

export interface DimensionLabelsResponse {
  dimension_labels: Record<string, string>
}

export interface ListEligibleSnapshotsResponse {
  snapshots: ResticSnapshot[]
}

export interface CreateSnapshotResponse {
  message: string
  snapshot: ResticSnapshotWithSummary
}

export interface RestorationResponse {
  id: string
  server_id: string
  type: RestorationType
  source_snapshot_id: string
  safety_snapshot_id: string | null
  // Whether each referenced restic snapshot still exists. Backend fills
  // these by intersecting row IDs against a fresh `restic snapshots` listing.
  // When the safety snapshot is gone, the rollback button is hidden.
  source_snapshot_exists: boolean
  safety_snapshot_exists: boolean
  selection: RestorationSelection
  is_rollback: boolean
  initiated_by_user_id: number | null
  started_at: string
  finished_at: string | null
  status: RestorationStatus
  error_message: string | null
}

export interface ListRestorationsResponse {
  restorations: RestorationResponse[]
  total: number
}

// Server-Sent Event payloads. The backend emits exactly one JSON object per
// `data:` line; both event types share `event_type` so the frontend can
// dispatch on it without duplicating the union.
export type RestoreEventType =
  | 'start'
  | 'safety_snapshot'
  | 'stage'
  | 'merge_region'
  | 'restore'
  | 'invalidate_cache'
  | 'complete'
  | 'error'

export interface RestoreEvent {
  event_type: RestoreEventType
  message?: string
  percent?: number
  rx?: number
  rz?: number
  sub_dir?: string
  restoration_id?: string
  safety_snapshot_id?: string
}

export type PreviewEventType =
  | 'start'
  | 'stage'
  | 'merge_region'
  | 'render_progress'
  | 'ready'
  | 'error'

export interface PreviewEvent {
  event_type: PreviewEventType
  message?: string
  session_id?: string
  percent?: number
}

// Body for POST /preview, /restore.
export interface PreviewRequest {
  source_snapshot_id: string
  selection: RestorationSelection
}

export interface RestoreRequest {
  source_snapshot_id: string
  selection: RestorationSelection
}

// Detail shape of the 423 (locked) response. Surfaces who is currently
// holding the per-server operation lock.
export interface LockedDetail {
  reason: 'locked'
  holder: {
    kind: string
    server_id?: string | null
    extra?: Record<string, unknown>
  } | null
}
