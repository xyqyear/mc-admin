import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { CheckCircle2, XCircle } from 'lucide-react'
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { RestorePreviewRequest } from '@/features/world/restore/contracts'
import { useRestorePreview } from '@/features/world/restore/useRestorePreview'

import { Alert, AlertDescription, AlertTitle } from '@/shared/ui/alert'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/shared/ui/dialog'
import { Progress } from '@/shared/ui/progress'
import { Spinner } from '@/shared/ui/spinner'
import {
  BLOCKS_PER_REGION,
  chunksToCoveredRegions,
} from '@/features/world/map/coords'
import {
  blockToLatLng,
  regionCoordsToLatLngBounds,
  SERVER_MAP_MAX_ZOOM,
  SERVER_MAP_MIN_ZOOM,
  SERVER_MAP_NATIVE_ZOOM,
} from '@/features/world/map/mapConfig'
import type {
  RestorationSelection
} from '@/features/world/restore/contracts'

import { PreviewTileLayer } from '@/features/world/restore/components/PreviewTileLayer'

// A non-null `request` means "preview this snapshot+selection pair"; nulling
// it triggers the dialog's close transition.
export type { RestorePreviewRequest } from '@/features/world/restore/contracts'
interface RestorePreviewModalProps {
  serverId: string
  request: RestorePreviewRequest | null
  onClose: () => void
}

interface BlockBounds {
  bxMin: number
  bzMin: number
  bxMax: number
  bzMax: number
}

// Dimension/world scopes have no affected regions; modal shows a "no regions"
// message instead of a blank canvas. `bounds` drives map fitBounds.
function computeAffected(selection: RestorationSelection | null): {
  regions: Array<{ rx: number; rz: number }>
  bounds: BlockBounds | null
} {
  if (!selection) return { regions: [], bounds: null }
  if (selection.type === 'regions') {
    const regions = (selection.regions ?? []).map(([rx, rz]) => ({ rx, rz }))
    if (regions.length === 0) return { regions: [], bounds: null }
    let bxMin = Infinity, bzMin = Infinity, bxMax = -Infinity, bzMax = -Infinity
    for (const { rx, rz } of regions) {
      bxMin = Math.min(bxMin, rx * BLOCKS_PER_REGION)
      bzMin = Math.min(bzMin, rz * BLOCKS_PER_REGION)
      bxMax = Math.max(bxMax, (rx + 1) * BLOCKS_PER_REGION)
      bzMax = Math.max(bzMax, (rz + 1) * BLOCKS_PER_REGION)
    }
    return { regions, bounds: { bxMin, bzMin, bxMax, bzMax } }
  }
  if (selection.type === 'chunks') {
    const chunks = selection.chunks ?? []
    if (chunks.length === 0) return { regions: [], bounds: null }
    const set = new Set<`${number},${number}`>()
    for (const [cx, cz] of chunks) set.add(`${cx},${cz}`)
    const regions = chunksToCoveredRegions(set)
    let bxMin = Infinity, bzMin = Infinity, bxMax = -Infinity, bzMax = -Infinity
    for (const [cx, cz] of chunks) {
      bxMin = Math.min(bxMin, cx * 16)
      bzMin = Math.min(bzMin, cz * 16)
      bxMax = Math.max(bxMax, (cx + 1) * 16)
      bzMax = Math.max(bzMax, (cz + 1) * 16)
    }
    return { regions, bounds: { bxMin, bzMin, bxMax, bzMax } }
  }
  return { regions: [], bounds: null }
}

export const RestorePreviewModal: React.FC<RestorePreviewModalProps> = ({
  serverId,
  request,
  onClose,
}) => {
  const open = !!request
  // Latch the active request so the dialog body keeps rendering through the
  // close transition; nulling `request` would otherwise blank mid-animation.
  const [latched, setLatched] = useState<RestorePreviewRequest | null>(request)
  useEffect(() => {
    if (request) setLatched(request)
  }, [request])
  const selection = latched?.selection ?? null

  const state = useRestorePreview(serverId, request)
  // Map lives in both a ref (for synchronous teardown in the container ref
  // callback) and state (so layer/overlay effects re-run once it's available).
  const mapRef = useRef<L.Map | null>(null)
  const [mapInstance, setMapInstance] = useState<L.Map | null>(null)
  const layerRef = useRef<PreviewTileLayer | null>(null)
  const overlayRef = useRef<L.LayerGroup | null>(null)
  const resizeObserverRef = useRef<ResizeObserver | null>(null)

  const affected = useMemo(() => computeAffected(selection), [selection])
  const availableSet = useMemo(
    () => new Set(affected.regions.map((r) => `${r.rx},${r.rz}`)),
    [affected.regions],
  )
  const tileBounds = useMemo(
    () => regionCoordsToLatLngBounds(affected.regions),
    [affected.regions],
  )

  // Mount/unmount in the ref callback (not useEffect) keeps Leaflet's
  // lifecycle tied directly to the DOM node attaching/detaching.
  const bounds = affected.bounds
  const containerRefCallback = useCallback(
    (node: HTMLDivElement | null) => {
      resizeObserverRef.current?.disconnect()
      resizeObserverRef.current = null
      if (mapRef.current) {
        mapRef.current.remove()
        mapRef.current = null
      }
      overlayRef.current = null
      layerRef.current = null
      setMapInstance(null)

      if (!node || !bounds) return

      const map = L.map(node, {
        crs: L.CRS.Simple,
        minZoom: SERVER_MAP_MIN_ZOOM,
        maxZoom: SERVER_MAP_MAX_ZOOM,
        attributionControl: false,
        zoomControl: false,
        fadeAnimation: false,
        preferCanvas: true,
      })
      const sw = blockToLatLng(bounds.bxMin, bounds.bzMax)
      const ne = blockToLatLng(bounds.bxMax, bounds.bzMin)
      map.fitBounds([sw, ne], {
        padding: [20, 20],
        maxZoom: SERVER_MAP_MAX_ZOOM,
      })
      mapRef.current = map
      overlayRef.current = L.layerGroup().addTo(map)
      setMapInstance(map)

      // Re-measure on container resizes so Leaflet's tile math matches actual size.
      const ro = new ResizeObserver(() => map.invalidateSize())
      ro.observe(node)
      resizeObserverRef.current = ro
    },
    [bounds],
  )

  useEffect(() => {
    if (!mapInstance) return
    if (!state.sessionId) return
    if (layerRef.current) {
      mapInstance.removeLayer(layerRef.current)
    }
    const layer = new PreviewTileLayer({
      serverId,
      sessionId: state.sessionId,
      available: availableSet,
      bounds: tileBounds,
      noWrap: true,
      keepBuffer: 2,
      minZoom: SERVER_MAP_MIN_ZOOM,
      maxZoom: SERVER_MAP_MAX_ZOOM,
      minNativeZoom: SERVER_MAP_NATIVE_ZOOM,
      maxNativeZoom: SERVER_MAP_NATIVE_ZOOM,
    })
    layer.addTo(mapInstance)
    layerRef.current = layer
  }, [serverId, state.sessionId, availableSet, tileBounds, mapInstance])

  // Paint affected regions so the boundary is visible before tiles load.
  useEffect(() => {
    if (!mapInstance) return
    const group = overlayRef.current
    if (!group) return
    group.clearLayers()
    if (!selection) return
    if (selection.type === 'regions' || selection.type === 'chunks') {
      for (const r of affected.regions) {
        const sw = blockToLatLng(
          r.rx * BLOCKS_PER_REGION,
          (r.rz + 1) * BLOCKS_PER_REGION,
        )
        const ne = blockToLatLng(
          (r.rx + 1) * BLOCKS_PER_REGION,
          r.rz * BLOCKS_PER_REGION,
        )
        L.rectangle([sw, ne], {
          color: '#3b82f6',
          weight: 2,
          fill: false,
        }).addTo(group)
      }
    }
    if (selection.type === 'chunks' && (selection.chunks?.length ?? 0) <= 5_000) {
      // Past 5k chunks the region rectangles above are sufficient.
      const renderer = L.canvas()
      for (const [cx, cz] of selection.chunks ?? []) {
        const sw = blockToLatLng(cx * 16, (cz + 1) * 16)
        const ne = blockToLatLng((cx + 1) * 16, cz * 16)
        L.rectangle([sw, ne], {
          renderer,
          color: '#3b82f6',
          weight: 1,
          fillOpacity: 0.2,
        }).addTo(group)
      }
    }
  }, [affected.regions, selection, mapInstance])

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) onClose()
      }}
    >
      <DialogContent
        className="w-full max-w-4xl"
        showCloseButton={!!state.error || state.ready || !state.sessionId}
      >
        <DialogHeader>
          <DialogTitle>恢复预览</DialogTitle>
          <DialogDescription>
            预览不会修改实时世界。关闭对话框后会清理临时渲染数据。
          </DialogDescription>
        </DialogHeader>

        {!affected.bounds && selection && (
          <Alert>
            <AlertTitle>无可预览的区域</AlertTitle>
            <AlertDescription>
              当前选择范围为整个维度或整个世界，预览仅支持区域/区块级别的恢复操作。请选中具体区域后再试。
            </AlertDescription>
          </Alert>
        )}

        {affected.bounds && (
          <>
            <div className="flex items-center gap-2 text-sm">
              {state.error ? (
                <XCircle className="h-4 w-4 text-destructive" />
              ) : state.ready ? (
                <CheckCircle2 className="h-4 w-4 text-emerald-500" />
              ) : (
                <Spinner className="h-4 w-4" />
              )}
              <span className="text-muted-foreground">
                {state.error ?? state.message}
              </span>
              <span className="ml-auto tabular-nums text-muted-foreground">
                {Math.round(state.percent)}%
              </span>
            </div>
            <Progress value={state.percent} />

            {/* Mount only after `ready`; earlier tile fetches 404 because the
                per-session render queue isn't attached yet. `isolate` +
                `contain: paint` + `translate-z-0` stop pan repaints from
                re-evaluating the dialog overlay's `backdrop-blur` per frame. */}
            {state.ready && (
              <div
                ref={containerRefCallback}
                className="isolate mt-2 h-120 w-full translate-z-0 overflow-hidden rounded-md border contain-[paint]"
                style={{ background: 'var(--card)' }}
              />
            )}
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}

export default RestorePreviewModal
