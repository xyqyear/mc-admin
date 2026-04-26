import L from 'leaflet'
import axios from 'axios'

import { api } from '@/utils/api'
import { BLOCKS_PER_REGION } from '@/components/map/coords'

interface PreviewTileLayerOptions extends L.GridLayerOptions {
  serverId: string
  sessionId: string
  // Set of `${rx},${rz}` keys that the backend has rendered for this preview
  // session. Tiles outside this set are short-circuited to a blank image so
  // we don't pile up 404s while the user pans the empty grid around the
  // affected regions.
  available: ReadonlySet<string>
}

// Leaflet GridLayer for the preview map. Mirrors ServerMapTileLayer but hits
// the preview endpoint instead of /map/tiles.
export class PreviewTileLayer extends L.GridLayer {
  private readonly serverId: string
  private readonly sessionId: string
  private readonly available: ReadonlySet<string>
  private readonly aborts = new Map<string, AbortController>()

  constructor(opts: PreviewTileLayerOptions) {
    super({ tileSize: BLOCKS_PER_REGION, ...opts })
    this.serverId = opts.serverId
    this.sessionId = opts.sessionId
    this.available = opts.available
  }

  protected createTile(coords: L.Coords, done: L.DoneCallback): HTMLElement {
    const tile = document.createElement('img')
    tile.style.width = `${BLOCKS_PER_REGION}px`
    tile.style.height = `${BLOCKS_PER_REGION}px`
    tile.style.imageRendering = 'pixelated'
    tile.alt = ''

    if (!this.available.has(`${coords.x},${coords.y}`)) {
      queueMicrotask(() => done(undefined, tile))
      return tile
    }

    const key = this._tileCoordsToKey(coords)
    const ctrl = new AbortController()
    this.aborts.set(key, ctrl)

    api
      .get(
        `/servers/${this.serverId}/world-restore/preview/${this.sessionId}/tile/${coords.x}/${coords.y}.png`,
        {
          responseType: 'blob',
          signal: ctrl.signal,
          timeout: 0,
        },
      )
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
