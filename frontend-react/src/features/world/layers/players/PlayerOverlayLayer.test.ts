import L from 'leaflet'
import { afterEach, expect, it, vi } from 'vitest'
import { waitFor } from '@testing-library/react'
import { buildPlayerLocationsLayer, type BuildPlayerLocationsLayerOptions } from './PlayerOverlayLayer'
import type { PlayerLocationEntry } from './contracts'

let map: L.Map
let container: HTMLDivElement
afterEach(() => { map?.remove(); container?.remove(); vi.restoreAllMocks() })
function setup() {
  container = document.createElement('div')
  Object.defineProperties(container, { clientWidth: { value: 800, configurable: true }, clientHeight: { value: 600 } })
  document.body.appendChild(container)
  map = L.map(container, { crs: L.CRS.Simple, center: [0, 0], zoom: 0, minZoom: -4, zoomAnimation: false })
}
function player(id: number, x = 0, z = 0): PlayerLocationEntry {
  const uuid = id.toString(16).padStart(32, '0')
  return { id: uuid, uuid, id_kind: 'uuid', source: `${id}.dat`, storage: 'playerdata', data_version: 1,
    dimension_id: 'minecraft:overworld', region_dir_relpath: 'world/region', pos: { x, y: 64, z } }
}
function settings(players: PlayerLocationEntry[]): BuildPlayerLocationsLayerOptions {
  return { players, currentDimRelpath: 'world/region', profilesByUuid: new Map(), onlinePlayerUuids: new Set(), onlineOnly: false, onlineStatusAvailable: true }
}
const titles = () => Array.from(container.querySelectorAll<HTMLElement>('.player-location-icon')).map(e => e.title)

it('keeps partially visible markers, reveals distant players on pan and zoom, and releases offscreen DOM', async () => {
  setup()
  const layer = buildPlayerLocationsLayer(settings([player(1, -450), player(2, 4000, -4000), player(3, -4000, 4000)])).addTo(map)
  expect(titles()).toHaveLength(1)
  expect((layer.getLayers()[0] as L.Marker).getLatLng()).toEqual(L.latLng(-0, -450))
  map.setView([4000, 4000], 0)
  await waitFor(() => expect(titles()).toHaveLength(1))
  await waitFor(() => expect((layer.getLayers()[0] as L.Marker).getLatLng()).toEqual(L.latLng(4000, 4000)))
  map.setView([0, 0], -4)
  await waitFor(() => expect(titles()).toHaveLength(3))
  map.setView([-4000, -4000], 0)
  await waitFor(() => expect(titles()).toHaveLength(1))
  expect((layer.getLayers()[0] as L.Marker).getLatLng()).toEqual(L.latLng(-4000, -4000))
})

it('updates one profile in place while retaining another avatar and escaped names and coordinates', () => {
  setup()
  const players = [player(1, -17, -33), player(2)]
  const options = settings(players)
  const layer = buildPlayerLocationsLayer(options).addTo(map)
  const [first, second] = layer.getLayers() as L.Marker[]
  const secondElement = second.getElement()
  const secondAvatar = secondElement!.querySelector('.player-location-avatar-placeholder')
  const profiles = new Map([[players[0].uuid!, { uuid: players[0].uuid!, player_db_id: 1, current_name: '<b>玩家</b>',
    avatar_base64: null, resolved: true, last_skin_update: null }]])
  layer.update({ ...options, profilesByUuid: profiles })
  expect(layer.getLayers()).toEqual([first, second])
  expect(second.getElement()).toBe(secondElement)
  expect(second.getElement()!.querySelector('.player-location-avatar-placeholder')).toBe(secondAvatar)
  expect(first.getElement()!.title).toBe('<b>玩家</b>')
  expect(first.getElement()!.querySelector('b')).toBeNull()
  expect(first.getTooltip()!.getContent()).toContain('X -17 / Y 64 / Z -33')
  expect(first.getLatLng()).toEqual(L.latLng(33, -17))
  expect(first.options.interactive).toBe(false)
})

it('preserves online filtering, unknown status, hidden layers and dimension isolation', () => {
  setup()
  const players = [player(1), player(2), { ...player(3), region_dir_relpath: 'world/DIM-1/region' }]
  const options = { ...settings(players), onlinePlayerUuids: new Set([players[0].uuid!]) }
  const layer = buildPlayerLocationsLayer(options).addTo(map)
  expect(titles()).toHaveLength(2)
  expect(container.querySelectorAll('.player-location-marker--offline')).toHaveLength(1)
  layer.update({ ...options, onlineOnly: true })
  expect(titles()).toHaveLength(1)
  expect(container.querySelectorAll('.player-location-marker--online')).toHaveLength(1)
  layer.update({ ...options, onlineStatusAvailable: false })
  expect(container.querySelectorAll('.player-location-marker--unknown')).toHaveLength(2)
  layer.update({ ...options, currentDimRelpath: 'world/DIM-1/region' })
  expect(titles()).toHaveLength(1)
  layer.update({ ...options, currentDimRelpath: null })
  expect(titles()).toHaveLength(0)
  layer.update({ ...options, players: [] })
  expect(titles()).toHaveLength(0)
  layer.update(options)
  expect(titles()).toHaveLength(2)
})

it('cancels scheduled work on removal and can reattach without duplicate markers', async () => {
  setup()
  const layer = buildPlayerLocationsLayer(settings([player(1)])).addTo(map)
  const cancel = vi.spyOn(window, 'cancelAnimationFrame')
  map.fire('move')
  layer.remove()
  expect(cancel).toHaveBeenCalled()
  expect(titles()).toHaveLength(0)
  layer.addTo(map)
  map.fire('move')
  await waitFor(() => expect(titles()).toHaveLength(1))
  layer.remove()
  map.fire('move')
  expect(titles()).toHaveLength(0)
})

it('reveals players after a resize and refreshes saved positions without leaving stale markers', async () => {
  setup()
  const options = settings([player(1, 700)])
  const layer = buildPlayerLocationsLayer(options).addTo(map)
  expect(titles()).toHaveLength(0)
  Object.defineProperty(container, 'clientWidth', { value: 1600 })
  map.invalidateSize({ pan: false })
  await waitFor(() => expect(titles()).toHaveLength(1))
  layer.update({ ...options, players: [player(1, -17, -33)] })
  expect((layer.getLayers()[0] as L.Marker).getLatLng()).toEqual(L.latLng(33, -17))
  layer.update({ ...options, players: [player(1, 9000)] })
  expect(titles()).toHaveLength(0)
})
