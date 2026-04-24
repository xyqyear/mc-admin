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

// One [x, z] pair per existing r.X.Z.mca file in a dimension's region folder.
export type RegionList = Array<[number, number]>

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
