import L from 'leaflet'
import { expect, it } from 'vitest'

import { ServerMapTileLayer } from './ServerMapTileLayer'

const coords = Object.assign(L.point(-1, 0), { z: 0 })
const options = { serverId: 'alpha', regionPath: 'world/region' }

it('uses a stable timestamp-only URL across layer creation and zoom levels', () => {
  const first = new ServerMapTileLayer({ ...options, regions: new Map([['-1,0', 100]]) })
  const second = new ServerMapTileLayer({ ...options, regions: new Map([['-1,0', 100], ['2,3', 200]]) })
  const url = new URL(first.getTileUrl(coords))

  expect(url.pathname).toBe('/api/servers/alpha/map/tiles/-1/0.png')
  expect(Object.fromEntries(url.searchParams)).toEqual({ region: 'world/region', mt: '100' })
  expect(second.getTileUrl(Object.assign(L.point(-1, 0), { z: -4 }))).toBe(url.toString())
})

it.each([101, 99, 0])('changes the tile URL when its timestamp becomes %s', mtime => {
  const before = new ServerMapTileLayer({ ...options, regions: new Map([['-1,0', 100]]) })
  const after = new ServerMapTileLayer({ ...options, regions: new Map([['-1,0', mtime]]) })

  expect(after.getTileUrl(coords)).not.toBe(before.getTileUrl(coords))
  expect(new URL(after.getTileUrl(coords)).searchParams.get('mt')).toBe(String(mtime))
})

it('keeps server and dimension caches separate and avoids requests for absent regions', () => {
  const regions = new Map([['-1,0', 100]])
  const first = new ServerMapTileLayer({ ...options, regions })
  const otherServer = new ServerMapTileLayer({ ...options, serverId: 'beta', regions })
  const otherDimension = new ServerMapTileLayer({ ...options, regionPath: 'world/DIM-1/region', regions })

  expect(new Set([first, otherServer, otherDimension].map(layer => layer.getTileUrl(coords))).size).toBe(3)
  expect(first.getTileUrl(Object.assign(L.point(0, 0), { z: 0 }))).toMatch(/^data:image\/gif;/)
})
