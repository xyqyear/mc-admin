import L from 'leaflet'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { waitFor } from '@testing-library/react'
import { mockCanvas } from '@/test/canvas'
import { buildPlayerLocationsLayer, type BuildPlayerLocationsLayerOptions, type PlayerLocationsLayer } from './PlayerOverlayLayer'
import type { PlayerLocationEntry } from './contracts'

let map: L.Map
let container: HTMLDivElement
let contextFor: ReturnType<typeof mockCanvas>
beforeEach(() => { contextFor = mockCanvas() })
afterEach(() => { map?.remove(); container?.remove(); vi.restoreAllMocks(); vi.unstubAllGlobals() })
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
const draws = (layer: PlayerLocationsLayer) => contextFor(layer.getElement()!).draws

it('reuses player bitmaps after panning away and back and after position-only updates', async () => {
  setup()
  const options = settings([player(1)])
  const layer = buildPlayerLocationsLayer(options).addTo(map)
  const sprite = draws(layer)[0].source as HTMLCanvasElement

  map.setView([0, 5000], 0)
  await waitFor(() => expect(draws(layer)).toHaveLength(0))
  expect(sprite.width).toBeGreaterThan(0)

  map.setView([0, 0], 0)
  await waitFor(() => expect(draws(layer)[0]?.source).toBe(sprite))
  layer.update({ ...options, players: [player(1, -17, -33)] })
  await waitFor(() => expect(draws(layer)[0]).toMatchObject({ source: sprite, x: 449, y: 366 }))
})

it('refreshes changed offscreen profiles and releases buffers for filtered and removed players', async () => {
  setup()
  const players = [player(1), player(2)]
  const options = settings(players)
  const layer = buildPlayerLocationsLayer(options).addTo(map)
  const original = draws(layer).map(draw => draw.source as HTMLCanvasElement)

  map.setView([0, 5000], 0)
  await waitFor(() => expect(draws(layer)).toHaveLength(0))
  const profiles = new Map([[players[0].uuid!, {
    uuid: players[0].uuid!, player_db_id: 1, current_name: '新的名字',
    avatar_base64: null, resolved: true, last_skin_update: null,
  }]])
  const updated = { ...options, profilesByUuid: profiles }
  layer.update(updated)
  expect(original[0].width).toBe(0)
  expect(original[1].width).toBeGreaterThan(0)

  map.setView([0, 0], 0)
  await waitFor(() => expect(draws(layer)).toHaveLength(2))
  const renamed = draws(layer)[0].source as HTMLCanvasElement
  expect(contextFor(renamed).fillText).toHaveBeenCalledWith('新的名字', 60, 7)
  expect(draws(layer)[1].source).toBe(original[1])

  layer.update({ ...updated, onlineOnly: true, onlinePlayerUuids: new Set([players[0].uuid!]) })
  expect(original[1].width).toBe(0)
  expect(renamed.width).toBe(0)
  await waitFor(() => expect(draws(layer)).toHaveLength(1))
  const onlineSprite = draws(layer)[0].source as HTMLCanvasElement
  expect(draws(layer)[0].alpha).toBe(0.68)

  layer.update(settings([]))
  expect(onlineSprite.width).toBe(0)
  expect(layer.getElement()!.width).toBe(0)
})

it('keeps hidden buffers released during map interaction and rebuilds them when shown', async () => {
  setup()
  const options = settings([player(1)])
  const layer = buildPlayerLocationsLayer(options).addTo(map)
  const canvas = layer.getElement()!
  const sprite = draws(layer)[0].source as HTMLCanvasElement
  layer.update(settings([]))
  const clears = contextFor(canvas).clearRect.mock.calls.length

  map.panBy([200, 0], { animate: false })
  map.setZoom(-1)
  map.fire('resize')
  await new Promise(requestAnimationFrame)
  expect(canvas.hidden).toBe(true)
  expect(canvas.width).toBe(0)
  expect(canvas.height).toBe(0)
  expect(sprite.width).toBe(0)
  expect(contextFor(canvas).clearRect).toHaveBeenCalledTimes(clears)

  layer.update(options)
  expect(canvas.hidden).toBe(false)
  expect(canvas.width).toBeGreaterThan(0)
  expect(draws(layer)).toHaveLength(1)
  expect(draws(layer)[0].source).not.toBe(sprite)
})

it('invalidates cached offscreen bitmaps when the device pixel ratio changes', async () => {
  setup()
  const layer = buildPlayerLocationsLayer(settings([player(1)])).addTo(map)
  const original = draws(layer)[0].source as HTMLCanvasElement
  map.setView([0, 5000], 0)
  await waitFor(() => expect(draws(layer)).toHaveLength(0))

  vi.stubGlobal('devicePixelRatio', 2)
  map.fire('resize')
  await waitFor(() => expect(original.width).toBe(0))
  expect(layer.getElement()!.width).toBe(2112)
  map.setView([0, 0], 0)
  await waitFor(() => expect(draws(layer)).toHaveLength(1))
  const replacement = draws(layer)[0].source as HTMLCanvasElement
  expect(replacement.width).toBe(248)
  expect(replacement.height).toBe(90)
})

it('draws partially visible players, reveals distant positions on pan and zoom, and retains every overlapping player', async () => {
  setup()
  const layer = buildPlayerLocationsLayer(settings([player(1, -450), player(2, 4000, -4000), player(3, -4000, 4000)])).addTo(map)
  expect(draws(layer)).toHaveLength(1)
  expect(draws(layer)[0]).toMatchObject({ x: 16, y: 399 })
  map.setView([4000, 4000], 0)
  await waitFor(() => expect(draws(layer)[0]).toMatchObject({ x: 466, y: 399 }))
  map.setView([0, 0], -4)
  await waitFor(() => expect(draws(layer)).toHaveLength(3))
  layer.update(settings(Array.from({ length: 1080 }, (_, i) => player(i))))
  await waitFor(() => expect(draws(layer)).toHaveLength(1080))
  expect(container.querySelectorAll('.player-locations-canvas')).toHaveLength(1)
  expect(layer.getElement()!.getAttribute('aria-label')).toBe('玩家位置：1080 个')
})

it('draws signed coordinates and literal profile text while reusing unaffected sprites', async () => {
  setup()
  const players = [player(1, -17, -33), player(2)]
  const options = settings(players)
  const layer = buildPlayerLocationsLayer(options).addTo(map)
  const canvas = layer.getElement()
  const firstSprite = draws(layer)[0].source
  const secondSprite = draws(layer)[1].source
  expect(draws(layer)[0]).toMatchObject({ x: 449, y: 366, alpha: 0.46 })
  const profiles = new Map([[players[0].uuid!, { uuid: players[0].uuid!, player_db_id: 1, current_name: '<b>玩家</b>',
    avatar_base64: null, resolved: true, last_skin_update: null }]])
  layer.update({ ...options, profilesByUuid: profiles })
  await waitFor(() => expect(draws(layer)[0].source).not.toBe(firstSprite))
  expect(draws(layer)[1].source).toBe(secondSprite)
  expect(layer.getElement()).toBe(canvas)
  expect(contextFor(draws(layer)[0].source as HTMLCanvasElement).fillText).toHaveBeenCalledWith('<b>玩家</b>', 60, 7)
  expect(container.querySelector('b')).toBeNull()
})

it('preserves online filtering, unknown status, hidden layers and dimension isolation', async () => {
  setup()
  const players = [player(1), player(2), { ...player(3), region_dir_relpath: 'world/DIM-1/region' }]
  const options = { ...settings(players), onlinePlayerUuids: new Set([players[0].uuid!]) }
  const layer = buildPlayerLocationsLayer(options).addTo(map)
  expect(draws(layer).map(draw => draw.alpha)).toEqual([0.68, 0.46])
  layer.update({ ...options, onlineOnly: true })
  await waitFor(() => expect(draws(layer)).toHaveLength(1))
  expect(draws(layer)[0].alpha).toBe(0.68)
  layer.update({ ...options, onlineStatusAvailable: false })
  await waitFor(() => expect(draws(layer).map(draw => draw.alpha)).toEqual([0.58, 0.58]))
  layer.update({ ...options, currentDimRelpath: 'world/DIM-1/region' })
  await waitFor(() => expect(draws(layer)).toHaveLength(1))
  layer.update({ ...options, currentDimRelpath: null })
  expect(layer.getElement()!.hidden).toBe(true)
  expect(layer.getElement()!.width).toBe(0)
  layer.update(options)
  expect(layer.getElement()!.hidden).toBe(false)
  expect(draws(layer)).toHaveLength(2)
})

it('does not repaint within the pan gutter, cancels pending work and releases buffers on removal', async () => {
  setup()
  const layer = buildPlayerLocationsLayer(settings([player(1)])).addTo(map)
  const canvas = layer.getElement()!
  const context = contextFor(canvas)
  const clears = context.clearRect.mock.calls.length
  map.panBy([40, 0], { animate: false })
  await new Promise(requestAnimationFrame)
  expect(context.clearRect).toHaveBeenCalledTimes(clears)
  const cancel = vi.spyOn(window, 'cancelAnimationFrame')
  map.fire('resize')
  layer.remove()
  expect(cancel).toHaveBeenCalled()
  expect(canvas.width).toBe(0)
  expect(layer.getElement()).toBeNull()
  layer.addTo(map)
  expect(container.querySelectorAll('.player-locations-canvas')).toHaveLength(1)
  expect(draws(layer)).toHaveLength(1)
  layer.remove()
  map.fire('move')
  expect(container.querySelector('.player-locations-canvas')).toBeNull()
})

it('scales backing pixels for high DPI and refreshes saved positions and resized viewports', async () => {
  setup()
  vi.stubGlobal('devicePixelRatio', 1.5)
  const options = settings([player(1, 700)])
  const layer = buildPlayerLocationsLayer(options).addTo(map)
  expect(draws(layer)).toHaveLength(0)
  expect(layer.getElement()!.width).toBe(1584)
  expect(layer.getElement()!.height).toBe(1284)
  Object.defineProperty(container, 'clientWidth', { value: 1600 })
  map.invalidateSize()
  await waitFor(() => expect(draws(layer)).toHaveLength(1))
  expect(layer.getElement()!.width).toBe(2784)
  layer.update({ ...options, players: [player(1, -17, -33)] })
  await waitFor(() => expect(draws(layer)[0]).toMatchObject({ x: 849, y: 366 }))
  layer.update({ ...options, players: [player(1, 9000)] })
  await waitFor(() => expect(draws(layer)).toHaveLength(0))
})

it('shares decoded avatars, keeps placeholders on failure and ignores late image completion after removal', async () => {
  setup()
  const images: HTMLImageElement[] = []
  vi.stubGlobal('Image', vi.fn(function () {
    const image = document.createElement('img')
    images.push(image)
    return image
  }))
  const players = [player(1), player(2)]
  const profiles = new Map(players.map(p => [p.uuid!, { uuid: p.uuid!, player_db_id: null,
    current_name: '玩家', avatar_base64: 'same-avatar', resolved: true, last_skin_update: null }]))
  const layer = buildPlayerLocationsLayer({ ...settings(players), profilesByUuid: profiles }).addTo(map)
  expect(images).toHaveLength(1)
  const placeholder = draws(layer)[0].source as HTMLCanvasElement
  expect(contextFor(placeholder).fillText).toHaveBeenCalledWith('玩', 60, 27)
  Object.defineProperty(images[0], 'naturalWidth', { value: 8 })
  images[0].dispatchEvent(new Event('load'))
  await waitFor(() => expect(draws(layer)[0].source).not.toBe(placeholder))
  for (const draw of draws(layer)) expect(contextFor(draw.source as HTMLCanvasElement).drawImage).toHaveBeenCalledWith(images[0], 49, 16, 22, 22)
  const loadedSprites = draws(layer).map(draw => draw.source as HTMLCanvasElement)
  layer.remove()
  expect(images[0].onload).toBeNull()
  for (const sprite of loadedSprites) expect(sprite.width).toBe(0)
  const frame = vi.spyOn(window, 'requestAnimationFrame')
  images[0].dispatchEvent(new Event('load'))
  expect(frame).not.toHaveBeenCalled()
  layer.addTo(map)
  expect(images).toHaveLength(2)
  images[1].dispatchEvent(new Event('error'))
  expect(contextFor(draws(layer)[0].source as HTMLCanvasElement).fillText).toHaveBeenCalledWith('玩', 60, 27)
})

it('animates zoom around the requested center after a pan and keeps the canvas in the marker pane', () => {
  setup()
  const layer = buildPlayerLocationsLayer(settings([player(1)])).addTo(map)
  expect(layer.getElement()!.parentElement).toBe(map.getPane('markerPane'))
  map.panBy([40, 0], { animate: false })
  const transform = vi.spyOn(L.DomUtil, 'setTransform')
  map.fire('zoomanim', { zoom: 1, center: L.latLng(100, -200) })
  expect(transform).toHaveBeenCalledWith(layer.getElement(), L.point(-216, -356), 2)
})
