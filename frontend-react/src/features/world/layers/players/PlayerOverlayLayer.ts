import L from 'leaflet'

import type { PlayerMapProfileResponse } from '@/features/players/contracts';
import type { PlayerLocationEntry } from '@/features/world/layers/players/contracts'
import { blockToLatLng } from '@/features/world/map/mapConfig'

import {
  isPlayerOnline,
  normalizedUuidOf,
  playerDisplayName,
  playerLocationKey,
} from '@/features/world/layers/players/playerLocationDisplay'

const MARKER_WIDTH = 120
const NAME_HEIGHT = 14
const MARKER_GAP = 1
const AVATAR_SIZE = 24
type PlayerOnlineStatus = 'online' | 'offline' | 'unknown'

export interface BuildPlayerLocationsLayerOptions {
  players: PlayerLocationEntry[]
  currentDimRelpath: string | null
  profilesByUuid: ReadonlyMap<string, PlayerMapProfileResponse>
  onlinePlayerUuids: ReadonlySet<string>
  onlineOnly: boolean
  onlineStatusAvailable: boolean
}

interface PlayerMarker {
  player: PlayerLocationEntry
  profile: PlayerMapProfileResponse | undefined
  status: PlayerOnlineStatus
  marker: L.Marker
}

export class PlayerLocationsLayer extends L.LayerGroup {
  private settings: BuildPlayerLocationsLayerOptions
  private markers = new Map<string, PlayerMarker>()
  private attachedMap: L.Map | null = null
  private frame: number | null = null

  constructor(settings: BuildPlayerLocationsLayerOptions) {
    super()
    this.settings = settings
  }

  update(settings: BuildPlayerLocationsLayerOptions): void {
    this.settings = settings
    this.refresh()
  }

  override onAdd(map: L.Map): this {
    this.attachedMap = map
    this.refresh()
    return super.onAdd(map)
  }

  override onRemove(map: L.Map): this {
    if (this.frame !== null) cancelAnimationFrame(this.frame)
    this.frame = null
    this.attachedMap = null
    return super.onRemove(map)
  }

  getEvents(): Record<string, L.LeafletEventHandlerFn> {
    return { move: this.scheduleRefresh, zoomend: this.scheduleRefresh, resize: this.scheduleRefresh }
  }

  private scheduleRefresh = (): void => {
    if (this.frame !== null) return
    this.frame = requestAnimationFrame(() => {
      this.frame = null
      this.refresh()
    })
  }

  private refresh(): void {
    const map = this.attachedMap
    if (!map) return
    const { players, currentDimRelpath, profilesByUuid, onlinePlayerUuids, onlineOnly, onlineStatusAvailable } = this.settings
    const bounds = map.getPixelBounds()
    // Include the whole icon and a pan gutter, even when its anchor is offscreen.
    const padding = L.point(MARKER_WIDTH / 2 + 128, NAME_HEIGHT + AVATAR_SIZE + 128)
    const visibleBounds = L.bounds(bounds.min!.subtract(padding), bounds.max!.add(padding))
    const retained = new Set<string>()

    for (const player of players) {
      if (!currentDimRelpath || player.region_dir_relpath !== currentDimRelpath) continue
      const online = isPlayerOnline(player, onlinePlayerUuids)
      if (onlineOnly && !online) continue
      const position = blockToLatLng(player.pos.x, player.pos.z)
      if (!visibleBounds.contains(map.project(position))) continue
      const key = playerLocationKey(player)
      retained.add(key)
      const uuid = normalizedUuidOf(player)
      const profile = uuid ? profilesByUuid.get(uuid) : undefined
      const status: PlayerOnlineStatus = onlineStatusAvailable
        ? online
          ? 'online'
          : 'offline'
        : 'unknown'
      const previous = this.markers.get(key)
      if (previous?.player === player && previous.profile === profile && previous.status === status) continue
      const label = playerDisplayName(player, profile)
      const icon = L.divIcon({
        html: markerHtml(label, profile?.avatar_base64, status),
        className: 'player-location-icon',
        iconSize: [MARKER_WIDTH, NAME_HEIGHT + MARKER_GAP + AVATAR_SIZE],
        iconAnchor: [
          MARKER_WIDTH / 2,
          NAME_HEIGHT + MARKER_GAP + AVATAR_SIZE / 2,
        ],
      })
      if (previous) {
        previous.marker.setIcon(icon).setLatLng(position)
        previous.marker.options.title = label
        const element = previous.marker.getElement()
        if (element) element.title = label
        previous.marker.setTooltipContent(tooltipHtml(player, label, status))
        this.markers.set(key, { player, profile, status, marker: previous.marker })
      } else {
        const marker = L.marker(position, {
          icon,
          interactive: false,
          keyboard: false,
          title: label,
        }).bindTooltip(tooltipHtml(player, label, status), {
          direction: 'top',
          opacity: 0.92,
        })
        this.addLayer(marker)
        this.markers.set(key, { player, profile, status, marker })
      }
    }
    for (const [key, entry] of this.markers) {
      if (retained.has(key)) continue
      this.removeLayer(entry.marker)
      this.markers.delete(key)
    }
  }
}

export function buildPlayerLocationsLayer(settings: BuildPlayerLocationsLayerOptions): PlayerLocationsLayer {
  return new PlayerLocationsLayer(settings)
}

function markerHtml(
  label: string,
  avatarBase64: string | null | undefined,
  status: PlayerOnlineStatus,
): string {
  const avatar = avatarBase64
    ? `<img class="player-location-avatar" src="data:image/png;base64,${escapeAttr(
        avatarBase64,
      )}" alt="">`
    : `<span class="player-location-avatar-placeholder">${escapeHtml(
        label.slice(0, 1).toUpperCase() || '?',
      )}</span>`
  const statusDot =
    status === 'unknown'
      ? ''
      : `<span class="player-location-status-dot player-location-status-dot-${status}" aria-hidden="true"></span>`
  return `<div class="player-location-marker player-location-marker--${status}"><span class="player-location-name">${escapeHtml(
    label,
  )}</span><span class="player-location-avatar-frame">${avatar}${statusDot}</span></div>`
}

function tooltipHtml(
  player: PlayerLocationEntry,
  label: string,
  status: PlayerOnlineStatus,
): string {
  const statusLine =
    status === 'unknown'
      ? ''
      : `<div style="opacity:0.8">${status === 'online' ? '在线' : '离线'}</div>`
  return `<div style="font-size:12px;line-height:1.35;max-width:220px">
  <div style="font-weight:600">${escapeHtml(label)}</div>
  ${statusLine}
  <div style="opacity:0.8">${escapeHtml(player.dimension_id)}</div>
  <div style="opacity:0.75">X ${Math.round(player.pos.x)} / Y ${Math.round(
    player.pos.y,
  )} / Z ${Math.round(player.pos.z)}</div>
  <div style="opacity:0.55">${escapeHtml(playerLocationKey(player))}</div>
</div>`
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function escapeAttr(s: string): string {
  return escapeHtml(s).replace(/'/g, '&#39;')
}
