import L from 'leaflet'

import { buildApiUrl } from '@/utils/api'
import { BLOCKS_PER_REGION } from './coords'

export interface ServerTileLayerOptions extends L.TileLayerOptions {
  tileSize?: number
}

const EMPTY_IMAGE_SRC =
  'data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs='

export abstract class ServerTileLayer extends L.TileLayer {
  constructor(opts: ServerTileLayerOptions = {}) {
    super('', { tileSize: BLOCKS_PER_REGION, ...opts })
  }

  protected abstract buildPath(coords: L.Coords): string
  protected abstract shouldFetch(coords: L.Coords): boolean
  protected buildParams(coords: L.Coords): Record<string, unknown> | undefined {
    void coords
    return undefined
  }

  getTileUrl(coords: L.Coords): string {
    if (!this.shouldFetch(coords)) return EMPTY_IMAGE_SRC

    const url = new URL(buildApiUrl(this.buildPath(coords)))
    const params = this.buildParams(coords)
    if (params) {
      for (const [key, value] of Object.entries(params)) {
        if (value !== undefined && value !== null) {
          url.searchParams.set(key, String(value))
        }
      }
    }
    return url.toString()
  }

  createTile(coords: L.Coords, done: L.DoneCallback): HTMLElement {
    const tile = super.createTile(coords, done) as HTMLImageElement
    tile.style.imageRendering = 'pixelated'
    tile.alt = ''
    return tile
  }
}
