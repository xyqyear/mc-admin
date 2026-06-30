export type ChunkPruneMode = 'chunks' | 'regions'

export interface ChunkPruneSettingsResponse {
  default_threshold_seconds: number
}

export interface ChunkPrunePreviewRequest {
  threshold_seconds: number
  mode: ChunkPruneMode
}

export interface ChunkPruneStartResponse {
  task_id: string
}

export interface ChunkPruneApplyRequest {
  preview_task_id: string
}

export type ChunkPruneGeometryUnit = 'chunk' | 'region'

export type GridVertex = [number, number]
export type GridRing = GridVertex[]

export interface GridShape {
  id: string
  cell_count: number
  bbox: [number, number, number, number]
  rings: GridRing[]
}

export interface ChunkPruneGeometryDimension {
  region_dir_relpath: string
  unit: ChunkPruneGeometryUnit
  cell_count: number
  shapes: GridShape[]
}

export interface ChunkPrunePreviewGeometryResponse {
  task_id: string
  server_id: string
  mode: ChunkPruneMode
  threshold_seconds: number
  threshold_ticks: number
  dimensions: ChunkPruneGeometryDimension[]
}

export interface ChunkPruneResultData {
  mode: ChunkPruneMode
  dry_run: boolean
  threshold_seconds?: number
  threshold_ticks?: number
  region_dirs: number
  regions_scanned: number
  chunks_scanned: number
  chunks_selected: number
  regions_selected: number
  affected_region_counts_by_dimension?: Record<string, number>
  claims_loaded?: number
  claimed_chunks_protected?: number
  chunks_skipped_by_claims?: number
  regions_skipped_by_claims?: number
}
