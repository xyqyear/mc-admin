import type L from 'leaflet'

import {
  AuthedTileLayer,
  type AuthedTileLayerOptions,
} from '@/components/map/AuthedTileLayer'

interface PreviewTileLayerOptions extends AuthedTileLayerOptions {
  serverId: string
  sessionId: string
  available: ReadonlySet<string>
}

export class PreviewTileLayer extends AuthedTileLayer {
  private readonly serverId: string
  private readonly sessionId: string
  private readonly available: ReadonlySet<string>

  constructor(opts: PreviewTileLayerOptions) {
    super(opts)
    this.serverId = opts.serverId
    this.sessionId = opts.sessionId
    this.available = opts.available
  }

  protected buildUrl(coords: L.Coords): string {
    return `/servers/${this.serverId}/world-restore/preview/${this.sessionId}/tile/${coords.x}/${coords.y}.png`
  }

  protected shouldFetch(coords: L.Coords): boolean {
    return this.available.has(`${coords.x},${coords.y}`)
  }
}
