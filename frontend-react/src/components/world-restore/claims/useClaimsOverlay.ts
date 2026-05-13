import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
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
  onRender?: (map: L.Map, dim: string | null) => void
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
  onRender,
}: UseClaimsOverlayOptions): UseClaimsOverlayResult {
  const refsRef = useRef<ClaimsLayerRefs>({
    polygonsByClusterId: new Map(),
    labelsByClusterId: new Map(),
    teamIdByClusterId: new Map(),
  })
  const mapRef = useRef<L.Map | null>(null)
  const [popover, setPopover] = useState<PopoverState | null>(null)
  const popoverElRef = useRef<HTMLElement | null>(null)

  // Mirror onRender into a ref so a non-stable caller identity doesn't rebuild the overlay.
  const onRenderRef = useRef(onRender)
  useEffect(() => {
    onRenderRef.current = onRender
  }, [onRender])

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
          // Pan before layers attach: see docs/ftb-claims-overlay.md.
          onRenderRef.current?.(map, currentDimRelpath)
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
