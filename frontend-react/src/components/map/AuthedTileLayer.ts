import L from 'leaflet'
import axios from 'axios'

import { api } from '@/utils/api'
import { BLOCKS_PER_REGION } from './coords'

export interface AuthedTileLayerOptions extends L.GridLayerOptions {
  tileSize?: number
}

interface TileLoadResource {
  ctrl: AbortController
  tile: HTMLImageElement
  url: string | null
  disposed: boolean
  doneCalled: boolean
}

const EMPTY_IMAGE_SRC =
  'data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs='

export abstract class AuthedTileLayer extends L.GridLayer {
  private readonly tileResources = new Map<string, TileLoadResource>()

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
    const resource: TileLoadResource = {
      ctrl: new AbortController(),
      tile,
      url: null,
      disposed: false,
      doneCalled: false,
    }
    this.tileResources.set(key, resource)

    api
      .get(this.buildUrl(coords), {
        params: this.buildParams(coords),
        responseType: 'blob',
        signal: resource.ctrl.signal,
        timeout: 0,
      })
      .then((res) => {
        if (resource.disposed) return
        const url = URL.createObjectURL(res.data)
        resource.url = url
        tile.onload = () => {
          this.completeTile(key, resource, done)
        }
        tile.onerror = (err) => {
          this.completeTile(key, resource, done, err as unknown as Error)
        }
        tile.src = url
      })
      .catch((err) => {
        if (resource.disposed) return
        if (axios.isCancel(err) || err?.code === 'ERR_CANCELED') return
        if (err?.status === 404) {
          this.completeTile(key, resource, done)
          return
        }
        this.completeTile(key, resource, done, err)
      })

    return tile
  }

  private completeTile(
    key: string,
    resource: TileLoadResource,
    done: L.DoneCallback,
    err?: Error,
  ): void {
    if (resource.disposed || resource.doneCalled) return
    resource.doneCalled = true
    this.releaseObjectUrl(resource)
    resource.tile.onload = null
    resource.tile.onerror = null
    this.tileResources.delete(key)
    done(err, resource.tile)
  }

  private releaseObjectUrl(resource: TileLoadResource): void {
    if (!resource.url) return
    URL.revokeObjectURL(resource.url)
    resource.url = null
  }

  private clearTileImage(tile: HTMLImageElement): void {
    tile.onload = null
    tile.onerror = null
    tile.src = EMPTY_IMAGE_SRC
  }

  private disposeTileResource(
    key: string,
    tile: HTMLElement | undefined,
  ): void {
    const resource = this.tileResources.get(key)
    if (resource) {
      resource.disposed = true
      resource.ctrl.abort()
      this.releaseObjectUrl(resource)
      this.clearTileImage(resource.tile)
      this.tileResources.delete(key)
      return
    }
    if (tile instanceof HTMLImageElement) {
      this.clearTileImage(tile)
    }
  }

  protected _removeTile(key: string): void {
    const tile = (
      this as unknown as {
        _tiles?: Record<string, { el: HTMLElement | undefined }>
      }
    )._tiles?.[key]?.el
    this.disposeTileResource(key, tile)
    // @ts-expect-error: super._removeTile is typed as private in @types/leaflet
    super._removeTile(key)
  }

  onRemove(map: L.Map): this {
    for (const key of [...this.tileResources.keys()]) {
      this.disposeTileResource(key, undefined)
    }
    return super.onRemove(map) as this
  }
}
