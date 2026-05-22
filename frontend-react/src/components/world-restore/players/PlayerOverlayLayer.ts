import L from 'leaflet'

import type { PlayerMapProfileResponse } from '@/hooks/api/playerApi'
import type { PlayerLocationEntry } from '@/types/PlayerLocations'

import {
  isPlayerOnline,
  playerDisplayName,
  playerLocationKey,
} from './playerLocationDisplay'

// CRS.Simple: lat = -z, lng = x.
const blockToLatLng = (bx: number, bz: number): L.LatLngExpression => [-bz, bx]
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

export function buildPlayerLocationsLayer({
  players,
  currentDimRelpath,
  profilesByUuid,
  onlinePlayerUuids,
  onlineOnly,
  onlineStatusAvailable,
}: BuildPlayerLocationsLayerOptions): L.LayerGroup {
  const group = L.layerGroup()
  if (!currentDimRelpath) return group

  for (const player of players) {
    if (player.region_dir_relpath !== currentDimRelpath) continue
    const online = isPlayerOnline(player, onlinePlayerUuids)
    if (onlineOnly && !online) continue
    const profile = player.uuid ? profilesByUuid.get(player.uuid) : undefined
    const label = playerDisplayName(player, profile)
    const status: PlayerOnlineStatus = onlineStatusAvailable
      ? online
        ? 'online'
        : 'offline'
      : 'unknown'
    const icon = L.divIcon({
      html: markerHtml(label, profile?.avatar_base64, status),
      className: 'player-location-icon',
      iconSize: [MARKER_WIDTH, NAME_HEIGHT + MARKER_GAP + AVATAR_SIZE],
      iconAnchor: [
        MARKER_WIDTH / 2,
        NAME_HEIGHT + MARKER_GAP + AVATAR_SIZE / 2,
      ],
    })
    group.addLayer(
      L.marker(blockToLatLng(player.pos.x, player.pos.z), {
        icon,
        interactive: false,
        keyboard: false,
        title: label,
      }).bindTooltip(tooltipHtml(player, label, status), {
        direction: 'top',
        opacity: 0.92,
      }),
    )
  }
  return group
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
