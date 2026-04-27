import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { CheckCircle2, XCircle } from 'lucide-react'

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Progress } from '@/components/ui/progress'
import { Spinner } from '@/components/ui/spinner'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { useEventStream } from '@/hooks/useEventStream'
import { useWorldRestoreMutations } from '@/hooks/mutations/useWorldRestoreMutations'
import {
  BLOCKS_PER_REGION,
  chunksToCoveredRegions,
  chunkKeyToCoord,
} from '@/components/map/coords'
import type {
  PreviewEvent,
  RestorationSelection,
} from '@/types/WorldRestore'

import { PreviewTileLayer } from './PreviewTileLayer'

interface RestorePreviewModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  serverId: string
  sourceSnapshotId: string | null
  selection: RestorationSelection | null
}

interface PreviewState {
  percent: number
  message: string
  sessionId: string | null
  ready: boolean
  error: string | null
}

const initialState: PreviewState = {
  percent: 0,
  message: '准备开始',
  sessionId: null,
  ready: false,
  error: null,
}

const STAGE_LABEL: Record<string, string> = {
  start: '准备',
  stage: '提取快照内容',
  merge_region: '合并区块',
  render_progress: '渲染',
  ready: '就绪',
  error: '错误',
}

// 30s heartbeat — well under the backend's 30-min TTL.
const HEARTBEAT_MS = 30_000

function blockToLatLng(bx: number, bz: number): [number, number] {
  return [-bz, bx]
}

// Compute the affected-region set + initial map view from the selection.
// For dimension/world scopes there are no affected regions yet — the modal
// shows a "no regions to render" message rather than a blank black canvas.
function computeAffected(selection: RestorationSelection | null): {
  regions: Array<{ rx: number; rz: number }>
  initialBlock: { bx: number; bz: number } | null
} {
  if (!selection)
    return { regions: [], initialBlock: null }
  if (selection.type === 'regions') {
    const regions = (selection.regions ?? []).map(([rx, rz]) => ({ rx, rz }))
    if (regions.length === 0) return { regions: [], initialBlock: null }
    const r0 = regions[0]
    return {
      regions,
      initialBlock: {
        bx: r0.rx * BLOCKS_PER_REGION + BLOCKS_PER_REGION / 2,
        bz: r0.rz * BLOCKS_PER_REGION + BLOCKS_PER_REGION / 2,
      },
    }
  }
  if (selection.type === 'chunks') {
    const set = new Set<`${number},${number}`>()
    for (const [cx, cz] of selection.chunks ?? []) set.add(`${cx},${cz}`)
    const regions = chunksToCoveredRegions(set)
    if (regions.length === 0) return { regions: [], initialBlock: null }
    const r0 = regions[0]
    return {
      regions,
      initialBlock: {
        bx: r0.rx * BLOCKS_PER_REGION + BLOCKS_PER_REGION / 2,
        bz: r0.rz * BLOCKS_PER_REGION + BLOCKS_PER_REGION / 2,
      },
    }
  }
  return { regions: [], initialBlock: null }
}

export const RestorePreviewModal: React.FC<RestorePreviewModalProps> = ({
  open,
  onOpenChange,
  serverId,
  sourceSnapshotId,
  selection,
}) => {
  const [state, setState] = useState<PreviewState>(initialState)
  // The map lives in both a ref (for synchronous teardown inside the
  // container callback ref) and state (so the layer-attach and overlay
  // effects re-run once the map is available).
  const mapRef = useRef<L.Map | null>(null)
  const [mapInstance, setMapInstance] = useState<L.Map | null>(null)
  const layerRef = useRef<PreviewTileLayer | null>(null)
  const overlayRef = useRef<L.LayerGroup | null>(null)
  const resizeObserverRef = useRef<ResizeObserver | null>(null)

  const { useEndPreview, useHeartbeatPreview } = useWorldRestoreMutations()
  const endPreview = useEndPreview(serverId)
  const heartbeat = useHeartbeatPreview(serverId)

  const affected = useMemo(() => computeAffected(selection), [selection])
  const availableSet = useMemo(
    () => new Set(affected.regions.map((r) => `${r.rx},${r.rz}`)),
    [affected.regions],
  )

  // Reset state whenever the modal opens with a new snapshot/selection pair.
  useEffect(() => {
    if (!open) return
    setState(initialState)
  }, [open, sourceSnapshotId])

  useEventStream<PreviewEvent>({
    enabled: open && !!sourceSnapshotId && !!selection && !state.error,
    url: `/servers/${serverId}/world-restore/preview`,
    method: 'POST',
    body:
      open && sourceSnapshotId && selection
        ? { source_snapshot_id: sourceSnapshotId, selection }
        : undefined,
    onEvent: (ev) => {
      const stageText = STAGE_LABEL[ev.event_type] ?? ev.event_type
      const text = ev.message ?? stageText
      if (ev.event_type === 'error') {
        setState((prev) => ({ ...prev, error: ev.message ?? '未知错误' }))
        return
      }
      if (ev.event_type === 'ready') {
        setState((prev) => ({
          ...prev,
          percent: 100,
          message: text,
          ready: true,
          sessionId: ev.session_id ?? prev.sessionId,
        }))
        return
      }
      setState((prev) => ({
        ...prev,
        percent: ev.percent ?? prev.percent,
        message: text,
        sessionId: ev.session_id ?? prev.sessionId,
      }))
    },
    onError: (msg) => setState((prev) => ({ ...prev, error: msg })),
  })

  // Callback ref on the map container: mounts Leaflet when the div attaches
  // and tears it down when it detaches. Reacting in the ref callback (rather
  // than a useRef + useEffect pair) keeps mount/unmount tied to the DOM node
  // lifecycle directly, which is what Leaflet needs.
  const initial = affected.initialBlock
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

      if (!node || !initial) return

      const map = L.map(node, {
        crs: L.CRS.Simple,
        minZoom: -4,
        maxZoom: 4,
        zoom: 0,
        center: blockToLatLng(initial.bx, initial.bz),
        attributionControl: false,
        preferCanvas: true,
      })
      mapRef.current = map
      overlayRef.current = L.layerGroup().addTo(map)
      setMapInstance(map)

      // Re-measure on container size changes (dialog open animation, browser
      // zoom, viewport resize) so Leaflet computes visible tiles against the
      // actual rendered size.
      const ro = new ResizeObserver(() => map.invalidateSize())
      ro.observe(node)
      resizeObserverRef.current = ro
    },
    [initial],
  )

  // Attach the preview tile layer once we know the session id and the map
  // is initialized. Aborting requests when the modal closes is handled
  // inside PreviewTileLayer.
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
      noWrap: true,
      keepBuffer: 2,
      minZoom: -4,
      maxZoom: 4,
      minNativeZoom: 0,
      maxNativeZoom: 0,
    })
    layer.addTo(mapInstance)
    layerRef.current = layer
  }, [serverId, state.sessionId, availableSet, mapInstance])

  // Selection overlay — paint the affected regions so the user can see the
  // boundary even before tiles finish loading.
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
      // Use the fine-grained chunk overlay only for smaller selections; past
      // the threshold the region rectangles above are sufficient.
      const renderer = L.canvas()
      for (const [cx, cz] of selection.chunks ?? []) {
        const c = chunkKeyToCoord(`${cx},${cz}`)
        const sw = blockToLatLng(c.cx * 16, (c.cz + 1) * 16)
        const ne = blockToLatLng((c.cx + 1) * 16, c.cz * 16)
        L.rectangle([sw, ne], {
          renderer,
          color: '#3b82f6',
          weight: 1,
          fillOpacity: 0.2,
        }).addTo(group)
      }
    }
  }, [affected.regions, selection, mapInstance])

  // Heartbeat while the preview is open. Silent on error — the page can
  // recover by re-opening the preview.
  useEffect(() => {
    if (!open) return
    if (!state.sessionId) return
    const sid = state.sessionId
    const id = window.setInterval(() => {
      heartbeat.mutate(sid)
    }, HEARTBEAT_MS)
    return () => window.clearInterval(id)
  }, [open, state.sessionId, heartbeat])

  // End the preview session when the dialog closes. Fire-and-forget; if the
  // request never lands, the janitor reaps the session by TTL.
  useEffect(() => {
    if (open) return
    const sid = state.sessionId
    if (!sid) return
    endPreview.mutate(sid)
    setState(initialState)
    // Intentionally limit deps — we only want to fire on close transitions.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
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

        {!affected.initialBlock && selection && (
          <Alert>
            <AlertTitle>无可预览的区域</AlertTitle>
            <AlertDescription>
              当前选择范围为整个维度或整个世界，预览仅支持区域/区块级别的恢复操作。请选中具体区域后再试。
            </AlertDescription>
          </Alert>
        )}

        {affected.initialBlock && (
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

            {/* Only mount Leaflet after the backend signals `ready`. Tiles are
                rendered lazily on first request, so mounting earlier would
                fire tile fetches before the per-session render queue is
                attached and 404 them. */}
            {/* `isolate` + `contain: paint` + `translate-z-0` keep the map's
                repaints from bubbling out to the dialog's compositing layer.
                Without this, the dialog overlay's `backdrop-blur` is
                re-evaluated by the GPU on every Leaflet pan frame, which
                makes panning visibly laggier than the live map. */}
            {state.ready && (
              <div
                ref={containerRefCallback}
                className="isolate mt-2 h-[480px] w-full translate-z-0 overflow-hidden rounded-md border [contain:paint]"
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
