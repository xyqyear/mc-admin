// React glue for the FTB claims overlay.
//
// Owns the popover state, imperative refs to the per-cluster polygons (so
// hover highlights from the side panel don't trigger a Leaflet rebuild), and
// the map reference captured the first time the overlay renders.

import { useCallback, useMemo, useRef, useState } from 'react'
import type L from 'leaflet'

import type { ServerMapOverlay } from '@/components/map/ServerMap'
import type { FtbTeamEntry } from '@/types/FtbClaims'

import {
  buildClaimsLayer,
  type ClaimsLayerRefs,
} from './ClaimOverlayLayer'

import './claims.css'

export interface PopoverState {
  clusterId: string
  anchorEl: HTMLElement
}

export interface UseClaimsOverlayOptions {
  teams: FtbTeamEntry[]
  currentDimRelpath: string | null
  enabled: boolean
}

export interface UseClaimsOverlayResult {
  overlays: ServerMapOverlay[] | undefined
  popover: PopoverState | null
  closePopover: () => void
  highlightClusters: (clusterIds: Set<string> | null) => void
  panToBlock: (bx: number, bz: number) => void
}

export function useClaimsOverlay({
  teams,
  currentDimRelpath,
  enabled,
}: UseClaimsOverlayOptions): UseClaimsOverlayResult {
  const refsRef = useRef<ClaimsLayerRefs>({
    polygonsByClusterId: new Map(),
    labelsByClusterId: new Map(),
    teamIdByClusterId: new Map(),
  })
  const mapRef = useRef<L.Map | null>(null)
  const [popover, setPopover] = useState<PopoverState | null>(null)
  const popoverElRef = useRef<HTMLElement | null>(null)

  const handleLabelClick = useCallback((clusterId: string, anchorEl: HTMLElement) => {
    popoverElRef.current = anchorEl
    setPopover({ clusterId, anchorEl })
  }, [])

  const overlays = useMemo<ServerMapOverlay[] | undefined>(() => {
    if (!enabled) return undefined
    return [
      {
        id: 'ftb-claims',
        render: (map) => {
          mapRef.current = map
          return buildClaimsLayer({
            teams,
            currentDimRelpath,
            onLabelClick: handleLabelClick,
            refs: refsRef.current,
          })
        },
      },
    ]
  }, [enabled, teams, currentDimRelpath, handleLabelClick])

  const closePopover = useCallback(() => {
    setPopover(null)
    popoverElRef.current = null
  }, [])

  const highlightClusters = useCallback((clusterIds: Set<string> | null) => {
    const polygons = refsRef.current.polygonsByClusterId
    for (const [id, poly] of polygons) {
      const on = clusterIds === null ? false : clusterIds.has(id)
      poly.setStyle({
        weight: on ? 3.5 : 1.5,
        fillOpacity: on ? 0.45 : 0.22,
      })
    }
  }, [])

  const panToBlock = useCallback((bx: number, bz: number) => {
    mapRef.current?.panTo([-bz, bx])
  }, [])

  return {
    overlays,
    popover,
    closePopover,
    highlightClusters,
    panToBlock,
  }
}
