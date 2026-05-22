import type { PlayerMapProfileResponse } from '@/hooks/api/playerApi'
import type { PlayerLocationEntry } from '@/types/PlayerLocations'

export function normalizedUuidOf(
  player: Pick<PlayerLocationEntry, 'uuid' | 'id'>,
): string | null {
  const raw = player.uuid ?? player.id
  return normalizePlayerUuid(raw)
}

export function normalizePlayerUuid(value: string | null | undefined): string | null {
  if (!value) return null
  const normalized = value.replaceAll('-', '').toLowerCase()
  return /^[0-9a-f]{32}$/.test(normalized) ? normalized : null
}

export function isPlayerOnline(
  player: Pick<PlayerLocationEntry, 'uuid' | 'id'>,
  onlinePlayerUuids: ReadonlySet<string>,
): boolean {
  const uuid = normalizedUuidOf(player)
  return !!uuid && onlinePlayerUuids.has(uuid)
}

export function shortPlayerId(value: string | null | undefined): string {
  if (!value) return 'unknown'
  const compact = value.replaceAll('-', '')
  return compact.length > 12 ? compact.slice(0, 8) : value
}

export function playerFallbackLabel(player: PlayerLocationEntry): string {
  if (player.id_kind === 'name') return player.id
  return shortPlayerId(player.uuid ?? player.id)
}

export function playerDisplayName(
  player: PlayerLocationEntry,
  profile: PlayerMapProfileResponse | undefined,
): string {
  return profile?.current_name?.trim() || playerFallbackLabel(player)
}

export function playerLocationKey(player: PlayerLocationEntry): string {
  return `${player.storage}:${player.source}:${player.id}`
}

export function formatCoordinate(value: number): string {
  if (Number.isInteger(value)) return String(value)
  return value.toFixed(1)
}
