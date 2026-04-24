import L from 'leaflet'
import axios from 'axios'

import { api } from '@/utils/api'

import { BLOCKS_PER_REGION } from './coords'

interface ServerMapTileLayerOptions extends L.GridLayerOptions {
  serverId: string
  regionPath: string
  // Manifest of existing regions for this dimension, keyed as `${x},${z}`.
  // Tiles whose key is not in the set are skipped without an HTTP request —
  // critical for sparse worlds (islands, lines) where most viewport tiles miss.
  regions: ReadonlySet<string>
}

// Custom GridLayer that fetches PNGs through the project's authed axios so the
// JWT interceptor applies. Aborts in-flight requests on tile unload, which
// cascades all the way to backend queue cancellation.
export class ServerMapTileLayer extends L.GridLayer {
  private readonly serverId: string
  private readonly regionPath: string
  private readonly regions: ReadonlySet<string>
  private readonly aborts = new Map<string, AbortController>()

  constructor(opts: ServerMapTileLayerOptions) {
    super({ tileSize: BLOCKS_PER_REGION, ...opts })
    this.serverId = opts.serverId
    this.regionPath = opts.regionPath
    this.regions = opts.regions
  }

  protected createTile(coords: L.Coords, done: L.DoneCallback): HTMLElement {
    const tile = document.createElement('img')
    tile.style.width = `${BLOCKS_PER_REGION}px`
    tile.style.height = `${BLOCKS_PER_REGION}px`
    tile.style.imageRendering = 'pixelated'
    tile.alt = ''

    // Manifest short-circuit: if the region isn't on disk, deliver a blank
    // tile synchronously and skip the network round-trip entirely. The 404
    // path below stays as a safety net for regions generated after the
    // manifest was fetched.
    if (!this.regions.has(`${coords.x},${coords.y}`)) {
      queueMicrotask(() => done(undefined, tile))
      return tile
    }

    const key = this._tileCoordsToKey(coords)
    const ctrl = new AbortController()
    this.aborts.set(key, ctrl)

    api
      .get(`/servers/${this.serverId}/map/tiles/${coords.x}/${coords.y}.png`, {
        params: { region: this.regionPath },
        responseType: 'blob',
        signal: ctrl.signal,
        // No timeout for tile fetches; backend has its own request_timeout
        // and we want browser-driven cancellation to be the only signal.
        timeout: 0,
      })
      .then((res) => {
        const url = URL.createObjectURL(res.data)
        tile.onload = () => {
          URL.revokeObjectURL(url)
          done(undefined, tile)
        }
        tile.onerror = (err) => {
          URL.revokeObjectURL(url)
          done(err as unknown as Error, tile)
        }
        tile.src = url
      })
      .catch((err) => {
        if (axios.isCancel(err) || err?.code === 'ERR_CANCELED') return
        if (err?.status === 404) {
          // Empty region: deliver a blank tile so leaflet stops trying.
          done(undefined, tile)
          return
        }
        done(err, tile)
      })
      .finally(() => {
        this.aborts.delete(key)
      })

    return tile
  }

  // Override Leaflet's internal _removeTile to abort in-flight requests when
  // a tile leaves the viewport. The underscore-prefix method is internal but
  // stable across Leaflet 1.x.
  protected _removeTile(key: string): void {
    this.aborts.get(key)?.abort()
    this.aborts.delete(key)
    // @ts-expect-error: super._removeTile is typed as private in @types/leaflet
    super._removeTile(key)
  }

  onRemove(map: L.Map): this {
    for (const ctrl of this.aborts.values()) ctrl.abort()
    this.aborts.clear()
    return super.onRemove(map) as this
  }
}
