// Mirrors backend `app/player_locations/models.py`.

export type PlayerIdKind = 'uuid' | 'name'
export type PlayerStorageKind = 'playerdata' | 'players_data' | 'legacy_players'
export type PlayerSkipReason =
  | 'parse_error'
  | 'missing_pos'
  | 'invalid_pos'
  | 'missing_dimension'
  | 'invalid_dimension'

export interface PlayerLocationDimensionEntry {
  dimension_id: string
  folder: string
  region_dir_relpath: string | null
  exists_on_disk: boolean
}

export interface PlayerLocationPosition {
  x: number
  y: number
  z: number
}

export interface PlayerLocationEntry {
  id: string
  id_kind: PlayerIdKind
  uuid: string | null
  source: string
  storage: PlayerStorageKind
  data_version: number | null
  dimension_id: string
  region_dir_relpath: string | null
  pos: PlayerLocationPosition
}

export interface PlayerLocationSkippedFile {
  source: string
  storage: PlayerStorageKind
  reason: PlayerSkipReason
  message: string | null
}

export interface PlayerLocationsResponse {
  dimensions: PlayerLocationDimensionEntry[]
  players: PlayerLocationEntry[]
  skipped: PlayerLocationSkippedFile[]
}
