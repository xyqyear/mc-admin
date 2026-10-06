import L from 'leaflet'
import { expect, it } from 'vitest'
import { buildClaimsLayer, type ClaimsLayerRefs } from '@/features/world/layers/claims/ClaimOverlayLayer'
import { buildPlayerLocationsLayer } from '@/features/world/layers/players/PlayerOverlayLayer'
import type { PlayerLocationEntry } from '@/features/world/layers/players/contracts'
import { buildPrunePreviewLayer } from '@/features/world/prune/components/PrunePreviewOverlayLayer'

it.each([
  ['regions', [
    [[512, -1024], [512, 512], [-1024, 512], [-1024, -1024]],
    [[-0, -512], [-0, 0], [-512, 0], [-512, -512]],
  ]],
  ['chunks', [
    [[16, -32], [16, 16], [-32, 16], [-32, -32]],
    [[-0, -16], [-0, 0], [-16, 0], [-16, -16]],
  ]],
] as const)('renders %s geometry with negative coordinates and a separate hole', (mode, expected) => {
  const group = buildPrunePreviewLayer({
    mode,
    dimension: {
      region_dir_relpath: 'world/region', unit: mode === 'chunks' ? 'chunk' : 'region', cell_count: 8,
      shapes: [{ id: 'negative-ring', cell_count: 8, bbox: [-2, -1, 1, 2], rings: [
        [[-2, -1], [1, -1], [1, 2], [-2, 2]],
        [[-1, 0], [0, 0], [0, 1], [-1, 1]],
      ] }],
    },
  })
  const polygon = group.getLayers()[0]
  expect(polygon).toBeInstanceOf(L.Polygon)
  const rings = (polygon as L.Polygon).getLatLngs() as L.LatLng[][]
  expect(rings.map(ring => ring.map(point => [point.lat, point.lng]))).toEqual(expected)
})

it('renders a negative claimed chunk at its block boundaries', () => {
  const refs: ClaimsLayerRefs = { polygonsByClusterId: new Map(), labelsByClusterId: new Map(), teamIdByClusterId: new Map() }
  buildClaimsLayer({
    currentDimRelpath: 'world/region', refs, onLabelClick: () => undefined,
    teams: [{ id: 'team', display_name: '测试领地', type: 'party', members: [], owner: null, total_chunks: 1,
      clusters: [{ id: 'negative', region_dir_relpath: 'world/region', chunks: [[-2, -3]], force_loaded: [],
        centroid_block: [-24, -40], bbox_chunk: [-2, -3, -2, -3], regions: [[-1, -1]] }],
    }],
  })
  const polygon = refs.polygonsByClusterId.get('negative')!
  const ring = polygon.getLatLngs()[0] as L.LatLng[]
  expect(ring.map(point => [point.lat, point.lng]).sort()).toEqual([[48, -32], [48, -16], [32, -16], [32, -32]].sort())
})

it('uses the same normalized online identity and cached label for UUID and id fallback markers', () => {
  const uuid = '0123456789abcdef0123456789abcdef'
  const raw = '01234567-89AB-CDEF-0123-456789ABCDEF'
  const base: PlayerLocationEntry = { id: raw, id_kind: 'uuid', uuid: raw, source: 'first.dat', storage: 'playerdata',
    data_version: 1, dimension_id: 'minecraft:overworld', region_dir_relpath: 'world/region', pos: { x: -17, y: 64, z: -33 } }
  const group = buildPlayerLocationsLayer({
    players: [base, { ...base, uuid: null, source: 'fallback.dat', pos: { x: -18, y: 64, z: 34 } },
      { ...base, id: 'LegacyName', uuid: null, id_kind: 'name', source: 'legacy.dat' }],
    currentDimRelpath: 'world/region', profilesByUuid: new Map([[uuid, { uuid, player_db_id: 1,
      current_name: '同一玩家', avatar_base64: null, resolved: true, last_skin_update: null }]]),
    onlinePlayerUuids: new Set([uuid]), onlineOnly: true, onlineStatusAvailable: true,
  })
  const markers = group.getLayers() as L.Marker[]
  expect(markers).toHaveLength(2)
  expect(markers.map(marker => [marker.getLatLng().lat, marker.getLatLng().lng])).toEqual([[33, -17], [-34, -18]])
  for (const marker of markers) {
    const icon = marker.options.icon as L.DivIcon
    expect(icon.options.html).toContain('同一玩家')
    expect(icon.options.html).toContain('player-location-marker--online')
  }
})
