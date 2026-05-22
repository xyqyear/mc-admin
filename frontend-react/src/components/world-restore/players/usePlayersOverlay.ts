import { useCallback, useEffect, useMemo, useRef } from 'react'
import L from 'leaflet'

import type { ServerMapOverlay } from '@/components/map/ServerMap'
import type { PlayerMapProfileResponse } from '@/hooks/api/playerApi'
import type { PlayerLocationEntry } from '@/types/PlayerLocations'

import { buildPlayerLocationsLayer } from './PlayerOverlayLayer'

import './players.css'

export interface UsePlayersOverlayOptions {
  players: PlayerLocationEntry[]
  currentDimRelpath: string | null
  profilesByUuid: ReadonlyMap<string, PlayerMapProfileResponse>
  onlinePlayerUuids: ReadonlySet<string>
  onlineOnly: boolean
  onlineStatusAvailable: boolean
  enabled: boolean
  visible: boolean
  onRender?: (map: L.Map, dim: string | null) => void
}

export interface UsePlayersOverlayResult {
  overlays: ServerMapOverlay[] | undefined
  panToBlock: (bx: number, bz: number) => void
}

export function usePlayersOverlay({
  players,
  currentDimRelpath,
  profilesByUuid,
  onlinePlayerUuids,
  onlineOnly,
  onlineStatusAvailable,
  enabled,
  visible,
  onRender,
}: UsePlayersOverlayOptions): UsePlayersOverlayResult {
  const mapRef = useRef<L.Map | null>(null)
  const onRenderRef = useRef(onRender)
  useEffect(() => {
    onRenderRef.current = onRender
  }, [onRender])

  const overlays = useMemo<ServerMapOverlay[] | undefined>(() => {
    if (!enabled) return undefined
    return [
      {
        id: 'player-locations',
        render: (map) => {
          mapRef.current = map
          onRenderRef.current?.(map, currentDimRelpath)
          if (!visible) return L.layerGroup()
          return buildPlayerLocationsLayer({
            players,
            currentDimRelpath,
            profilesByUuid,
            onlinePlayerUuids,
            onlineOnly,
            onlineStatusAvailable,
          })
        },
      },
    ]
  }, [
    enabled,
    visible,
    players,
    currentDimRelpath,
    profilesByUuid,
    onlinePlayerUuids,
    onlineOnly,
    onlineStatusAvailable,
  ])

  const panToBlock = useCallback((bx: number, bz: number) => {
    mapRef.current?.panTo([-bz, bx])
  }, [])

  return { overlays, panToBlock }
}
