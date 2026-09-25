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
