import L from 'leaflet'
import axios from 'axios'

import { api } from '@/utils/api'
import { BLOCKS_PER_REGION } from './coords'

export interface AuthedTileLayerOptions extends L.GridLayerOptions {
  tileSize?: number
}

export abstract class AuthedTileLayer extends L.GridLayer {
  private readonly aborts = new Map<string, AbortController>()

  constructor(opts: AuthedTileLayerOptions = {}) {
    super({ tileSize: BLOCKS_PER_REGION, ...opts })
  }

  protected abstract buildUrl(coords: L.Coords): string
  protected abstract shouldFetch(coords: L.Coords): boolean
  protected buildParams(coords: L.Coords): Record<string, unknown> | undefined {
    void coords
    return undefined
  }

  protected createTile(coords: L.Coords, done: L.DoneCallback): HTMLElement {
    const tile = document.createElement('img')
    tile.style.width = `${BLOCKS_PER_REGION}px`
    tile.style.height = `${BLOCKS_PER_REGION}px`
    tile.style.imageRendering = 'pixelated'
    tile.alt = ''

    if (!this.shouldFetch(coords)) {
      queueMicrotask(() => done(undefined, tile))
      return tile
    }

    const key = this._tileCoordsToKey(coords)
    const ctrl = new AbortController()
    this.aborts.set(key, ctrl)

    api
      .get(this.buildUrl(coords), {
        params: this.buildParams(coords),
        responseType: 'blob',
        signal: ctrl.signal,
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
