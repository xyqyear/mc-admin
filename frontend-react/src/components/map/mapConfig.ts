import { BLOCKS_PER_REGION, type RegionCoord } from './coords'

export type LatLngPair = [number, number]

export const SERVER_MAP_MIN_ZOOM = -4
export const SERVER_MAP_MAX_ZOOM = 2
export const SERVER_MAP_NATIVE_ZOOM = 0

export function clampServerMapZoom(zoom: number): number {
  return Math.min(SERVER_MAP_MAX_ZOOM, Math.max(SERVER_MAP_MIN_ZOOM, zoom))
}

export function blockToLatLng(bx: number, bz: number): LatLngPair {
  return [-bz, bx]
}

export function regionCoordsToLatLngBounds(
  regions: Iterable<RegionCoord>,
): [LatLngPair, LatLngPair] | undefined {
  let minRx = Infinity
  let minRz = Infinity
  let maxRx = -Infinity
  let maxRz = -Infinity

  for (const { rx, rz } of regions) {
    minRx = Math.min(minRx, rx)
    minRz = Math.min(minRz, rz)
    maxRx = Math.max(maxRx, rx)
    maxRz = Math.max(maxRz, rz)
  }

  if (!Number.isFinite(minRx)) return undefined

  return [
    blockToLatLng(minRx * BLOCKS_PER_REGION, (maxRz + 1) * BLOCKS_PER_REGION),
    blockToLatLng((maxRx + 1) * BLOCKS_PER_REGION, minRz * BLOCKS_PER_REGION),
  ]
}

export function regionKeysToLatLngBounds(
  regionKeys: Iterable<string>,
): [LatLngPair, LatLngPair] | undefined {
  function* coords(): IterableIterator<RegionCoord> {
    for (const key of regionKeys) {
      const [rx, rz] = key.split(',').map(Number)
      if (Number.isFinite(rx) && Number.isFinite(rz)) {
        yield { rx, rz }
      }
    }
  }

  return regionCoordsToLatLngBounds(coords())
}
