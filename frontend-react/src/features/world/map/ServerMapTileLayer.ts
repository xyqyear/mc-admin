import type L from 'leaflet'

import { ServerTileLayer, type ServerTileLayerOptions } from '@/features/world/map/ServerTileLayer'

interface ServerMapTileLayerOptions extends ServerTileLayerOptions {
  serverId: string
  regionPath: string
  regions: ReadonlyMap<string, number>
  revision?: string
}

export class ServerMapTileLayer extends ServerTileLayer {
  private readonly serverId: string
  private readonly regionPath: string
  private readonly regions: ReadonlyMap<string, number>
  private readonly revision?: string

  constructor(opts: ServerMapTileLayerOptions) {
    super(opts)
    this.serverId = opts.serverId
    this.regionPath = opts.regionPath
    this.regions = opts.regions
    this.revision = opts.revision
  }

  protected buildPath(coords: L.Coords): string {
    return `/servers/${this.serverId}/map/tiles/${coords.x}/${coords.y}.png`
  }

  protected shouldFetch(coords: L.Coords): boolean {
    return this.regions.has(`${coords.x},${coords.y}`)
  }

  protected buildParams(coords: L.Coords): Record<string, unknown> | undefined {
    const mt = this.regions.get(`${coords.x},${coords.y}`)
    return { region: this.regionPath, mt, revision: this.revision }
  }
}
