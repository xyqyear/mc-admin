import L from 'leaflet'

import type { PlayerMapProfileResponse } from '@/features/players/contracts'
import { blockToLatLng } from '@/features/world/map/mapConfig'
import type { PlayerLocationEntry } from './contracts'
import { isPlayerOnline, normalizedUuidOf, playerDisplayName, playerLocationKey } from './playerLocationDisplay'
import { createPlayerMarkerSprite, MARKER_ANCHOR, MARKER_SIZE, type PlayerOnlineStatus } from './playerMarkerSprite'

const PAN_PADDING = 128

export interface BuildPlayerLocationsLayerOptions {
  players: PlayerLocationEntry[]
  currentDimRelpath: string | null
  profilesByUuid: ReadonlyMap<string, PlayerMapProfileResponse>
  onlinePlayerUuids: ReadonlySet<string>
  onlineOnly: boolean
  onlineStatusAvailable: boolean
}

interface AvatarImage {
  image: HTMLImageElement
  ready: boolean
}

interface PlayerMarker {
  position: L.LatLng
  label: string
  status: PlayerOnlineStatus
  avatar: AvatarImage | undefined
  sprite: HTMLCanvasElement | undefined
  avatarReady: boolean
}

function releaseSprite(marker: PlayerMarker): void {
  if (!marker.sprite) return
  marker.sprite.width = marker.sprite.height = 0
  marker.sprite = undefined
}

export class PlayerLocationsLayer extends L.Layer {
  private settings: BuildPlayerLocationsLayerOptions
  private markers = new Map<string, PlayerMarker>()
  private images = new Map<string, AvatarImage>()
  private attachedMap: L.Map | null = null
  private canvas: HTMLCanvasElement | null = null
  private bounds: L.Bounds | null = null
  private northWest: L.LatLng | null = null
  private zoom = 0
  private ratio = 1
  private fontFamily = 'sans-serif'
  private frame: number | null = null

  constructor(settings: BuildPlayerLocationsLayerOptions) {
    super()
    L.setOptions(this, { pane: 'markerPane' })
    this.settings = settings
  }

  update(settings: BuildPlayerLocationsLayerOptions): void {
    this.settings = settings
    if (!this.attachedMap) return
    const next = new Map<string, PlayerMarker>()
    const usedImages = new Set<string>()
    for (const player of settings.players) {
      if (!settings.currentDimRelpath || player.region_dir_relpath !== settings.currentDimRelpath) continue
      const online = isPlayerOnline(player, settings.onlinePlayerUuids)
      if (settings.onlineOnly && !online) continue
      const uuid = normalizedUuidOf(player)
      const profile = uuid ? settings.profilesByUuid.get(uuid) : undefined
      const label = playerDisplayName(player, profile)
      const status = settings.onlineStatusAvailable
        ? online ? 'online' : 'offline'
        : 'unknown'
      const avatar = profile?.avatar_base64 ? this.avatarImage(profile.avatar_base64) : undefined
      if (profile?.avatar_base64) usedImages.add(profile.avatar_base64)
      const key = playerLocationKey(player)
      const previous = this.markers.get(key)
      const unchanged = previous?.label === label && previous.status === status && previous.avatar === avatar
      next.set(key, {
        position: L.latLng(blockToLatLng(player.pos.x, player.pos.z)),
        label,
        status,
        avatar,
        sprite: unchanged ? previous.sprite : undefined,
        avatarReady: previous?.avatarReady ?? false,
      })
    }
    for (const [key, marker] of this.markers) {
      if (marker.sprite !== next.get(key)?.sprite) releaseSprite(marker)
    }
    this.markers = next
    for (const [source, avatar] of this.images) {
      if (usedImages.has(source)) continue
      avatar.image.onload = avatar.image.onerror = null
      this.images.delete(source)
    }
    this.canvas?.setAttribute('aria-label', `玩家位置：${next.size} 个`)
    if (this.canvas) this.canvas.hidden = next.size === 0
    if (next.size === 0) {
      if (this.frame !== null) cancelAnimationFrame(this.frame)
      this.frame = null
      if (this.canvas) this.canvas.width = this.canvas.height = 0
      this.bounds = null
      this.northWest = null
      return
    }
    if (!this.bounds) this.reset()
    else this.scheduleDraw()
  }

  override onAdd(map: L.Map): this {
    this.attachedMap = map
    this.fontFamily = getComputedStyle(map.getContainer()).fontFamily || 'sans-serif'
    this.canvas = L.DomUtil.create('canvas', 'player-locations-canvas leaflet-zoom-animated')
    this.canvas.setAttribute('role', 'img')
    this.getPane()!.appendChild(this.canvas)
    this.update(this.settings)
    return this
  }

  override onRemove(): this {
    if (this.frame !== null) cancelAnimationFrame(this.frame)
    this.frame = null
    this.attachedMap = null
    if (this.canvas) {
      this.canvas.remove()
      this.canvas.width = this.canvas.height = 0
    }
    this.canvas = null
    this.bounds = null
    this.northWest = null
    for (const marker of this.markers.values()) releaseSprite(marker)
    this.markers.clear()
    for (const avatar of this.images.values()) avatar.image.onload = avatar.image.onerror = null
    this.images.clear()
    return this
  }

  getElement(): HTMLCanvasElement | null {
    return this.canvas
  }

  getEvents(): Record<string, L.LeafletEventHandlerFn> {
    return {
      move: this.onMove,
      moveend: this.onMove,
      zoom: this.scheduleReset,
      viewreset: this.scheduleReset,
      resize: this.scheduleReset,
      zoomanim: this.animateZoom as L.LeafletEventHandlerFn,
    }
  }

  private avatarImage(source: string): AvatarImage {
    const cached = this.images.get(source)
    if (cached) return cached
    const image = new Image()
    const avatar = { image, ready: false }
    this.images.set(source, avatar)
    image.onload = () => {
      avatar.ready = image.naturalWidth > 0
      if (this.attachedMap && this.images.get(source) === avatar) this.scheduleDraw()
    }
    image.onerror = () => { image.onload = image.onerror = null }
    image.src = `data:image/png;base64,${source}`
    return avatar
  }

  private onMove = (): void => {
    const map = this.attachedMap
    if (!map || this.markers.size === 0) return
    const topLeft = map.containerPointToLayerPoint([0, 0])
    const view = L.bounds(topLeft, topLeft.add(map.getSize()))
    if (!this.bounds?.contains(view) || this.zoom !== map.getZoom()) this.scheduleReset()
  }

  private scheduleReset = (): void => {
    this.bounds = null
    this.scheduleDraw()
  }

  private scheduleDraw = (): void => {
    if (this.frame !== null || !this.attachedMap || this.markers.size === 0) return
    this.frame = requestAnimationFrame(() => {
      this.frame = null
      if (!this.bounds) this.reset()
      else this.draw()
    })
  }

  private reset(): void {
    const map = this.attachedMap
    const canvas = this.canvas
    if (!map || !canvas) return
    const ratio = window.devicePixelRatio || 1
    if (this.ratio !== ratio) {
      for (const marker of this.markers.values()) releaseSprite(marker)
      this.ratio = ratio
    }
    const topLeft = map.containerPointToLayerPoint([-PAN_PADDING, -PAN_PADDING]).round()
    const size = map.getSize().add([PAN_PADDING * 2, PAN_PADDING * 2])
    this.bounds = L.bounds(topLeft, topLeft.add(size))
    this.northWest = map.layerPointToLatLng(topLeft)
    this.zoom = map.getZoom()
    const width = Math.ceil(size.x * ratio)
    const height = Math.ceil(size.y * ratio)
    if (canvas.width !== width) canvas.width = width
    if (canvas.height !== height) canvas.height = height
    canvas.style.width = `${size.x}px`
    canvas.style.height = `${size.y}px`
    L.DomUtil.setPosition(canvas, topLeft)
    this.draw()
  }

  private draw(): void {
    const map = this.attachedMap
    const canvas = this.canvas
    const bounds = this.bounds
    if (!map || !canvas || !bounds) return
    const context = canvas.getContext('2d')!
    context.setTransform(this.ratio, 0, 0, this.ratio, 0, 0)
    const size = bounds.getSize()
    context.clearRect(0, 0, size.x, size.y)
    const visible = [...this.markers.values()].flatMap(marker => {
      const point = map.latLngToLayerPoint(marker.position)
      const topLeft = point.subtract(MARKER_ANCHOR)
      // Keep offscreen sprites so returning pans do not rasterize names and shadows again.
      if (!bounds.intersects(L.bounds(topLeft, topLeft.add(MARKER_SIZE)))) return []
      return [{ marker, point, topLeft }]
    }).sort((a, b) => a.point.y - b.point.y)
    for (const { marker, topLeft } of visible) {
      const ready = marker.avatar?.ready ?? false
      if (!marker.sprite || marker.avatarReady !== ready) {
        releaseSprite(marker)
        marker.sprite = createPlayerMarkerSprite(
          marker.label, marker.status, ready ? marker.avatar!.image : null, this.ratio, this.fontFamily,
        )
        marker.avatarReady = ready
      }
      const offset = topLeft.subtract(bounds.min!)
      context.globalAlpha = marker.status === 'online' ? 0.68 : marker.status === 'offline' ? 0.46 : 0.58
      context.drawImage(marker.sprite, offset.x, offset.y, MARKER_SIZE.x, MARKER_SIZE.y)
    }
    context.globalAlpha = 1
  }

  private animateZoom = (event: L.ZoomAnimEvent): void => {
    const map = this.attachedMap
    if (!map || !this.canvas || !this.northWest) return
    const origin = map.project(event.center, event.zoom).subtract(map.getSize().divideBy(2))
      .subtract(map.containerPointToLayerPoint([0, 0])).round()
    const offset = map.project(this.northWest, event.zoom).subtract(origin)
    L.DomUtil.setTransform(this.canvas, offset, map.getZoomScale(event.zoom, this.zoom))
  }
}

export function buildPlayerLocationsLayer(settings: BuildPlayerLocationsLayerOptions): PlayerLocationsLayer {
  return new PlayerLocationsLayer(settings)
}
