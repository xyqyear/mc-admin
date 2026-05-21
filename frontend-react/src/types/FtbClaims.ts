// Mirrors backend `app/ftb_claims/models.py`.

export type FtbTeamType = 'player' | 'party' | 'server' | 'unknown'

export interface FtbClaimMember {
  uuid?: string | null
  name?: string | null
  rank?: string | null
}

export interface FtbDimensionEntry {
  ftb_id: string
  region_dir_relpath: string | null
  exists_on_disk: boolean
}

export interface FtbClusterEntry {
  id: string
  region_dir_relpath: string | null
  chunks: Array<[number, number]>
  force_loaded: Array<[number, number]>
  centroid_block: [number, number]
  bbox_chunk: [number, number, number, number]
  regions: Array<[number, number]>
}

export interface FtbTeamEntry {
  id: string
  display_name: string
  type: FtbTeamType
  members: FtbClaimMember[]
  owner: FtbClaimMember | null
  total_chunks: number
  clusters: FtbClusterEntry[]
}

export interface FtbClaimsResponse {
  available: boolean
  dimensions: FtbDimensionEntry[]
  teams: FtbTeamEntry[]
}
