import L from 'leaflet'

import {
  BLOCKS_PER_CHUNK,
  BLOCKS_PER_REGION,
} from '@/components/map/coords'
import type {
  ChunkPruneGeometryDimension,
  ChunkPruneMode,
  GridRing,
} from '@/types/ChunkPrune'

const blockToLatLng = (bx: number, bz: number): L.LatLngExpression => [-bz, bx]

function ringToLatLngs(ring: GridRing, cellSize: number): L.LatLngExpression[] {
  return ring.map(([x, z]) => blockToLatLng(x * cellSize, z * cellSize))
}

export interface BuildPrunePreviewLayerOptions {
  mode: ChunkPruneMode
  dimension: ChunkPruneGeometryDimension
}

export function buildPrunePreviewLayer({
  mode,
  dimension,
}: BuildPrunePreviewLayerOptions): L.LayerGroup {
  const group = L.layerGroup()
  const renderer = L.canvas({ padding: 0.2 })
  const cellSize = mode === 'regions' ? BLOCKS_PER_REGION : BLOCKS_PER_CHUNK

  for (const shape of dimension.shapes) {
    if (shape.rings.length === 0) continue
    const polygon = L.polygon(
      shape.rings.map((ring) => ringToLatLngs(ring, cellSize)) as L.LatLngExpression[][],
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
