import L from 'leaflet'

import {
  BLOCKS_PER_CHUNK,
  BLOCKS_PER_REGION,
} from '@/components/map/coords'
import type {
  ChunkPruneDimensionResult,
  ChunkPruneMode,
} from '@/types/ChunkPrune'
import { computeBoundaryRings, type Ring } from '@/components/world-restore/claims/computeBoundary'

type Cell = [number, number]

const blockToLatLng = (bx: number, bz: number): L.LatLngExpression => [-bz, bx]

function ringToLatLngs(ring: Ring, cellSize: number): L.LatLngExpression[] {
  return ring.map(([x, z]) => blockToLatLng(x * cellSize, z * cellSize))
}

function connectedComponents(cells: Cell[]): Cell[][] {
  const remaining = new Set(cells.map(([x, z]) => `${x},${z}`))
  const components: Cell[][] = []
  for (const [sx, sz] of cells) {
    const startKey = `${sx},${sz}`
    if (!remaining.has(startKey)) continue
    const component: Cell[] = []
    const stack: Cell[] = [[sx, sz]]
    remaining.delete(startKey)
    while (stack.length > 0) {
      const [x, z] = stack.pop()!
      component.push([x, z])
      const neighbors: Cell[] = [
        [x + 1, z],
        [x - 1, z],
        [x, z + 1],
        [x, z - 1],
      ]
      for (const [nx, nz] of neighbors) {
        const key = `${nx},${nz}`
        if (!remaining.delete(key)) continue
        stack.push([nx, nz])
      }
    }
    components.push(component)
  }
  return components
}

export interface BuildPrunePreviewLayerOptions {
  mode: ChunkPruneMode
  dimension: ChunkPruneDimensionResult
}

export function buildPrunePreviewLayer({
  mode,
  dimension,
}: BuildPrunePreviewLayerOptions): L.LayerGroup {
  const group = L.layerGroup()
  const renderer = L.canvas({ padding: 0.2 })
  const cells =
    mode === 'regions'
      ? dimension.selected_regions.map<Cell>((region) => [
          region.region_x,
          region.region_z,
        ])
      : dimension.selected_chunks.map<Cell>((chunk) => [
          chunk.chunk_x,
          chunk.chunk_z,
        ])
  const cellSize = mode === 'regions' ? BLOCKS_PER_REGION : BLOCKS_PER_CHUNK
  const components = connectedComponents(cells)

  for (const component of components) {
    const rings = computeBoundaryRings(component)
    rings.sort((a, b) => b.length - a.length)
    const polygon = L.polygon(
      rings.map((ring) => ringToLatLngs(ring, cellSize)) as L.LatLngExpression[][],
      {
        renderer,
        color: '#ef4444',
        weight: mode === 'regions' ? 1.5 : 1,
        opacity: 0.9,
        fillColor: '#ef4444',
        fillOpacity: mode === 'regions' ? 0.18 : 0.22,
        interactive: false,
      },
    )
    group.addLayer(polygon)
  }

  return group
}
