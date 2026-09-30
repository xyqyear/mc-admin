import type L from 'leaflet'

import {
  ServerTileLayer,
  type ServerTileLayerOptions,
} from '@/features/world/map/ServerTileLayer'

interface PreviewTileLayerOptions extends ServerTileLayerOptions {
  sessionId: string
  available: ReadonlySet<string>
}

export class PreviewTileLayer extends ServerTileLayer {
  private readonly sessionId: string
  private readonly available: ReadonlySet<string>

  constructor(opts: PreviewTileLayerOptions) {
    super(opts)
    this.sessionId = opts.sessionId
    this.available = opts.available
  }

  protected buildPath(coords: L.Coords): string {
    return `/snapshots/previews/${this.sessionId}/tiles/${coords.x}/${coords.y}.png`
  }

  protected shouldFetch(coords: L.Coords): boolean {
    return this.available.has(`${coords.x},${coords.y}`)
  }
}
