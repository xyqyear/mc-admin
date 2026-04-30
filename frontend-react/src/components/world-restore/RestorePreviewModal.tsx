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

} from '@/components/map/coords'
import type {
  PreviewEvent,
  RestorationSelection,
} from '@/types/WorldRestore'

import { PreviewTileLayer } from './PreviewTileLayer'

// A non-null `request` means "preview this snapshot+selection pair". Nulling
// it triggers the dialog's close transition; callers don't manage `open`
// separately. Both call sites (snapshot picker, history drawer) hold one of
// these in state and clear it on close.
export interface RestorePreviewRequest {
  sourceSnapshotId: string
  selection: RestorationSelection
}

interface RestorePreviewModalProps {
  serverId: string
  request: RestorePreviewRequest | null
  onClose: () => void
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

interface BlockBounds {
  bxMin: number
  bzMin: number
  bxMax: number
  bzMax: number
}

// Compute the affected-region set + selection bounding box from the selection.
// For dimension/world scopes there are no affected regions yet — the modal
// shows a "no regions to render" message rather than a blank black canvas.
// `bounds` is the tightest block-aligned box around the selection (chunk-precise
// for chunk selections, region-precise for region selections); the map uses it
// to fitBounds so the rollback area is centered and zoomed to fit.
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
  // close transition. The parent nulls `request` on close, which would
  // otherwise blank the title/progress/map mid-animation.
  const [latched, setLatched] = useState<RestorePreviewRequest | null>(request)
  useEffect(() => {
    if (request) setLatched(request)
  }, [request])
  const selection = latched?.selection ?? null

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

  // Reset state whenever a fresh request comes in (new snapshot/selection or
  // a re-open after close). Object identity is the trigger — callers create a
  // new request object on each open click.
  useEffect(() => {
    if (!request) return
    setState(initialState)
  }, [request])

  useEventStream<PreviewEvent>({
    enabled: !!request && !state.error,
    url: `/servers/${serverId}/world-restore/preview`,
    method: 'POST',
    body: request
      ? {
          source_snapshot_id: request.sourceSnapshotId,
          selection: request.selection,
        }
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
        minZoom: -4,
        maxZoom: 4,
        attributionControl: false,
        zoomControl: false,
        preferCanvas: true,
      })
      const sw = blockToLatLng(bounds.bxMin, bounds.bzMax)
      const ne = blockToLatLng(bounds.bxMax, bounds.bzMin)
      // maxZoom: 2 keeps a single-chunk selection from zooming all the way to
      // the map's max (4×) and losing the surrounding context.
      map.fitBounds([sw, ne], { padding: [20, 20], maxZoom: 2 })
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
    [bounds],
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
