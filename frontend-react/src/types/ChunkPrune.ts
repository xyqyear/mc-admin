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

export interface ChunkPruneSelectedChunk {
  chunk_x: number
  chunk_z: number
  region_x: number
  region_z: number
}

export interface ChunkPruneSelectedRegion {
  region_x: number
  region_z: number
}

export interface ChunkPruneDimensionResult {
  region_dir_relpath: string
  selected_chunks: ChunkPruneSelectedChunk[]
  selected_regions: ChunkPruneSelectedRegion[]
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
  affected_regions_by_dimension?: Record<string, Array<[number, number]>>
  dimensions?: ChunkPruneDimensionResult[]
  claims_loaded?: number
  claimed_chunks_protected?: number
  chunks_skipped_by_claims?: number
  regions_skipped_by_claims?: number
}
