// Server map (mcmap) types — mirror backend pydantic models in app/mcmap/types.py.

export interface MapStatus {
  client_jar_present: boolean
  palette_present: boolean
  palette_current: boolean
  version: string | null
}

export interface DimensionInfo {
  region_path: string
  label: string
  mca_count: number
}

// One [x, z, mtime] triple per existing r.X.Z.mca in the dimension's region
// folder. `mtime` is the MCA file's modification time in whole epoch seconds;
// the tile layer appends it as a `?mt=` query param so the browser HTTP cache
// busts automatically when the source MCA is regenerated.
export type RegionList = Array<[number, number, number]>

export type ChunkKey = `${number},${number}`

export type SelectionMode = 'none' | 'chunk' | 'region'

export type InitStage = 'client' | 'palette' | 'complete'

export type InitPhase =
  | 'starting'
  | 'downloading'
  | 'verifying'
  | 'pack_loaded'
  | 'resolving'
  | 'done'
  | 'error'

export interface InitEvent {
  stage: InitStage
  phase?: InitPhase
  percent?: number
  message?: string
  cached?: boolean
}
