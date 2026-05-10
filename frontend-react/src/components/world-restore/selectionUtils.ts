import type { ChunkKey } from '@/types/MapTypes'
import {
  chunkKeyToCoord,
  chunksToFullyCoveredRegions,
  computeRegionCoverage,
} from '@/components/map/coords'
import type { RestorationSelection } from '@/types/WorldRestore'

// `scope` lets callers pick a coarser grain than the current selection;
// world scope spans every valid world root and carries no relpath.
export function buildSelection(args: {
  scope: 'world' | 'dimension' | 'regions' | 'chunks'
  regionDirRelpath: string | null
  selection: Set<ChunkKey>
}): RestorationSelection {
  const { scope, regionDirRelpath, selection } = args
  if (scope === 'world') {
    return { type: 'world' }
  }
  if (scope === 'dimension') {
    return {
      type: 'dimension',
      region_dir_relpath: regionDirRelpath ?? undefined,
    }
  }
  if (scope === 'regions') {
    const regions = chunksToFullyCoveredRegions(selection).map(
      (r) => [r.rx, r.rz] as [number, number],
    )
    return {
      type: 'regions',
      region_dir_relpath: regionDirRelpath ?? undefined,
      regions,
    }
  }
  const chunks: Array<[number, number]> = []
  for (const k of selection) {
    const c = chunkKeyToCoord(k)
    chunks.push([c.cx, c.cz])
  }
  return {
    type: 'chunks',
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
  const { covered, fullyCovered } = computeRegionCoverage(selection)
  return {
    chunkCount: selection.size,
    regionCount: covered,
    fullRegionCount: fullyCovered,
  }
}
