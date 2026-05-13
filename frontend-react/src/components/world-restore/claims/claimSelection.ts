// Per-mode mapping from cluster → set of chunk keys consumed by
// useWorldRestoreSelectionStore.
//
// Chunk mode: select the cluster's chunks directly.
// Region mode: expand each touched region to its full 1024 chunks, which is
// what the selection store uses to express "this region is fully covered".

import {
  CHUNKS_PER_REGION,
  chunkKey,
  regionToChunkKeys,
} from '@/components/map/coords'
import type { ChunkKey } from '@/types/MapTypes'
import type { FtbClusterEntry, FtbTeamEntry } from '@/types/FtbClaims'
import type { WorldRestoreSelectionMode } from '@/stores/useWorldRestoreSelectionStore'

export function clusterToChunkKeys(
  cluster: FtbClusterEntry,
  mode: WorldRestoreSelectionMode,
): Set<ChunkKey> {
  const out = new Set<ChunkKey>()
  if (mode === 'chunk') {
    for (const [cx, cz] of cluster.chunks) {
      out.add(chunkKey({ cx, cz }))
    }
    return out
  }
  // Region mode: every region touched by any of the cluster's chunks expands
  // to all 1024 chunks so chunksToFullyCoveredRegions sees it as covered.
  for (const [rx, rz] of cluster.regions) {
    for (const k of regionToChunkKeys({ rx, rz })) out.add(k)
  }
  return out
}

export function teamDimChunkKeys(
  team: FtbTeamEntry,
  regionDirRelpath: string,
  mode: WorldRestoreSelectionMode,
): Set<ChunkKey> {
  const out = new Set<ChunkKey>()
  for (const cluster of team.clusters) {
    if (cluster.region_dir_relpath !== regionDirRelpath) continue
    for (const k of clusterToChunkKeys(cluster, mode)) out.add(k)
  }
  return out
}

// "Fully selected" detector for a cluster — used by the side panel to show
// the cluster's row as already covered. In chunk mode, all the cluster's
// chunks must be present; in region mode, all the cluster's regions must be
// fully covered in the current selection.
export function isClusterFullySelected(
  cluster: FtbClusterEntry,
  selection: Set<ChunkKey>,
  mode: WorldRestoreSelectionMode,
): boolean {
  if (selection.size === 0) return false
  if (mode === 'chunk') {
    for (const [cx, cz] of cluster.chunks) {
      if (!selection.has(chunkKey({ cx, cz }))) return false
    }
    return true
  }
  for (const [rx, rz] of cluster.regions) {
    const cxBase = rx * CHUNKS_PER_REGION
    const czBase = rz * CHUNKS_PER_REGION
    for (let cz = czBase; cz < czBase + CHUNKS_PER_REGION; cz++) {
      for (let cx = cxBase; cx < cxBase + CHUNKS_PER_REGION; cx++) {
        if (!selection.has(chunkKey({ cx, cz }))) return false
      }
    }
  }
  return true
}
