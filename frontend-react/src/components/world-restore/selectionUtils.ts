import type { ChunkKey } from '@/types/MapTypes'
import {
  chunkKeyToCoord,
  chunksToCoveredRegions,
  chunksToFullyCoveredRegions,
} from '@/components/map/coords'
import type { RestorationSelection } from '@/types/WorldRestore'

// Build the backend RestorationSelection payload from the page's selection
// state. The `scope` argument lets the caller pick a coarser grain than the
// current selection — e.g. "create snapshot of the whole dimension" reuses
// the current dimension/world but discards the chunks/regions arrays.
export function buildSelection(args: {
  scope: 'world' | 'dimension' | 'regions' | 'chunks'
  worldRootName: string
  dimensionLabel: string | null
  regionDirRelpath: string | null
  selection: Set<ChunkKey>
}): RestorationSelection {
  const { scope, worldRootName, dimensionLabel, regionDirRelpath, selection } =
    args
  if (scope === 'world') {
    return { type: 'world', world_root_name: worldRootName }
  }
  if (scope === 'dimension') {
    return {
      type: 'dimension',
      world_root_name: worldRootName,
      dimension_label: dimensionLabel ?? undefined,
      region_dir_relpath: regionDirRelpath ?? undefined,
    }
  }
  if (scope === 'regions') {
    const regions = chunksToFullyCoveredRegions(selection).map(
      (r) => [r.rx, r.rz] as [number, number],
    )
    return {
      type: 'regions',
      world_root_name: worldRootName,
      dimension_label: dimensionLabel ?? undefined,
      region_dir_relpath: regionDirRelpath ?? undefined,
      regions,
    }
  }
  // chunks
  const chunks: Array<[number, number]> = []
  for (const k of selection) {
    const c = chunkKeyToCoord(k)
    chunks.push([c.cx, c.cz])
  }
  return {
    type: 'chunks',
    world_root_name: worldRootName,
    dimension_label: dimensionLabel ?? undefined,
    region_dir_relpath: regionDirRelpath ?? undefined,
    chunks,
  }
}

export interface SelectionStats {
  chunkCount: number
  regionCount: number
  fullRegionCount: number
}

export function computeSelectionStats(
  selection: Set<ChunkKey>,
): SelectionStats {
  return {
    chunkCount: selection.size,
    regionCount: chunksToCoveredRegions(selection).length,
    fullRegionCount: chunksToFullyCoveredRegions(selection).length,
  }
}
