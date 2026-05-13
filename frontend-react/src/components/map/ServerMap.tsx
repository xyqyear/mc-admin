import React, { useEffect, useMemo, useRef, useState } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { Eraser, Hand, LocateFixed, Plus, Trash2, X } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'
import type { ChunkKey, SelectionMode } from '@/types/MapTypes'

import {
  BLOCKS_PER_CHUNK,
  BLOCKS_PER_REGION,
  chunkKey,
  chunkKeyToCoord,
  chunksInBlockBox,
  chunksToCoveredRegions,
  chunksToFullyCoveredRegions,
  regionToChunkKeys,
} from './coords'
import { ServerMapTileLayer } from './ServerMapTileLayer'

const REGION_OVERLAY_THRESHOLD = 5_000

// Selection tool — the canonical input on every device. Desktop Ctrl-drag and
// right-click still work on top; on touch the tool is the only intent signal.
export type SelectionTool = 'pan' | 'add' | 'erase'

export interface ServerMapOverlay {
  id: string
  render: (map: L.Map) => L.Layer
}

export interface ServerMapView {
  zoom: number
  cx: number
  cz: number
}

export interface ServerMapProps {
  serverId: string
  regionPath: string
  // Manifest keyed by `${x},${z}` mapped to MCA mtime (epoch seconds). The
  // tile layer skips HTTP for absent regions and uses mtime as cache-buster.
  regions: ReadonlyMap<string, number>
  selectionMode?: SelectionMode
  selection?: Set<ChunkKey>
  onSelectionChange?: (next: Set<ChunkKey>) => void
  overlays?: ServerMapOverlay[]
  className?: string
  initialView?: ServerMapView
  onViewChange?: (view: ServerMapView) => void
}

// CRS.Simple convention: lat = -z, lng = x, 1 block = 1 unit.
type LatLngPair = [number, number]

function blockToLatLng(bx: number, bz: number): LatLngPair {
  return [-bz, bx]
}

function chunkBounds(cx: number, cz: number): [LatLngPair, LatLngPair] {
  const sw = blockToLatLng(cx * BLOCKS_PER_CHUNK, (cz + 1) * BLOCKS_PER_CHUNK)
  const ne = blockToLatLng((cx + 1) * BLOCKS_PER_CHUNK, cz * BLOCKS_PER_CHUNK)
  return [sw, ne]
}

function regionBounds(rx: number, rz: number): [LatLngPair, LatLngPair] {
  const sw = blockToLatLng(rx * BLOCKS_PER_REGION, (rz + 1) * BLOCKS_PER_REGION)
  const ne = blockToLatLng(
    (rx + 1) * BLOCKS_PER_REGION,
    rz * BLOCKS_PER_REGION,
  )
  return [sw, ne]
}

export const ServerMap: React.FC<ServerMapProps> = ({
  serverId,
  regionPath,
  regions,
  selectionMode = 'none',
  selection,
  onSelectionChange,
  overlays,
  className,
  initialView,
  onViewChange,
}) => {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<L.Map | null>(null)
  const tileLayerRef = useRef<ServerMapTileLayer | null>(null)
  const overlayLayerRef = useRef<L.LayerGroup | null>(null)
  const selectionLayerRef = useRef<L.LayerGroup | null>(null)
  // Drag-rect selection state in refs so mousemove can update the ghost
  // without re-rendering; hover handler reads `active` to skip during drags.
  const dragGhostRef = useRef<L.Rectangle | null>(null)
  const dragStateRef = useRef<{
    active: boolean
    start: L.LatLng | null
    last: L.LatLng | null
    mode: 'add' | 'remove'
    rafScheduled: boolean
  }>({
    active: false,
    start: null,
    last: null,
    mode: 'add',
    rafScheduled: false,
  })
  // Capture initialView at first render so prop changes don't reset the map.
  const initialViewRef = useRef(initialView)
  // Latest-value refs read by handlers bound in the once-only init effect, so
  // those handlers track current props without resubscribing.
  const onViewChangeRef = useRef(onViewChange)
  useEffect(() => {
    onViewChangeRef.current = onViewChange
  }, [onViewChange])
  const regionsRef = useRef(regions)
  useEffect(() => {
    regionsRef.current = regions
  }, [regions])
  const selectionModeRef = useRef(selectionMode)
  useEffect(() => {
    selectionModeRef.current = selectionMode
  }, [selectionMode])
  const selectionRef = useRef(selection)
  useEffect(() => {
    selectionRef.current = selection
  }, [selection])
  // Refs so a mode-change effect can clear a stale rect without waiting for
  // the next mousemove.
  const hoverRectRef = useRef<L.Rectangle | null>(null)
  const lastHoverKeyRef = useRef<string | null>(null)
  // Drives single-finger / plain-left gesture intent (touch has no Ctrl /
  // right click). Users switch via the on-map toolbar.
  const [tool, setTool] = useState<SelectionTool>('pan')
  const toolRef = useRef(tool)
  useEffect(() => {
    toolRef.current = tool
  }, [tool])
  // Skip hover preview on coarse pointers (touch/pen) — synthesized mousemove
  // on tap can leave stuck rectangles otherwise.
  const isCoarsePointer = useMemo(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return false
    return window.matchMedia('(pointer: coarse)').matches
  }, [])

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return
    const initial = initialViewRef.current
    const map = L.map(containerRef.current, {
      crs: L.CRS.Simple,
      minZoom: -4,
      maxZoom: 4,
      zoom: initial?.zoom ?? 0,
      center: initial ? blockToLatLng(initial.cx, initial.cz) : [0, 0],
      attributionControl: false,
      zoomControl: false,
      preferCanvas: true,
    })
    mapRef.current = map
    overlayLayerRef.current = L.layerGroup().addTo(map)
    selectionLayerRef.current = L.layerGroup().addTo(map)

    // Bound after L.map() so construction-time events don't leak as phantom
    // view-changes. zoomend covers keyboard/button zooms with no center change.
    const emitView = () => {
      const cb = onViewChangeRef.current
      if (!cb) return
      const c = map.getCenter()
      cb({
        zoom: Math.round(map.getZoom()),
        cx: Math.round(c.lng),
        cz: Math.round(-c.lat),
      })
    }
    map.on('moveend', emitView)
    map.on('zoomend', emitView)

    // Cursor block-coord readout via direct DOM updates (no per-mousemove rerender).
    class CoordControl extends L.Control {
      private cleanup?: () => void
      constructor() {
        super({ position: 'bottomleft' })
      }
      onAdd(m: L.Map): HTMLElement {
        const div = L.DomUtil.create('div', 'leaflet-control')
        div.style.background = 'rgba(0, 0, 0, 0.65)'
        div.style.color = '#fff'
        div.style.padding = '4px 8px'
        div.style.fontFamily = 'monospace'
        div.style.fontSize = '12px'
        div.style.borderRadius = '6px'
        div.style.pointerEvents = 'none'
        div.style.userSelect = 'none'
        const placeholder = 'X: —  Z: —'
        div.textContent = placeholder
        const onMove = (e: L.LeafletMouseEvent) => {
          const bx = Math.round(e.latlng.lng)
          const bz = Math.round(-e.latlng.lat)
          const rx = Math.floor(e.latlng.lng / BLOCKS_PER_REGION)
          const rz = Math.floor(-e.latlng.lat / BLOCKS_PER_REGION)
          // Prepend the MCA filename only over existing regions.
          const mca = regionsRef.current.has(`${rx},${rz}`)
            ? `r.${rx}.${rz}.mca   `
            : ''
          div.textContent = `${mca}X: ${bx}  Z: ${bz}`
        }
        const onOut = () => {
          div.textContent = placeholder
        }
        m.on('mousemove', onMove)
        m.on('mouseout', onOut)
        this.cleanup = () => {
          m.off('mousemove', onMove)
          m.off('mouseout', onOut)
        }
        return div
      }
      onRemove(): void {
        this.cleanup?.()
      }
    }
    new CoordControl().addTo(map)

    // Hover frame around the cursor cell, gated on parent region existing
    // in the manifest. lastHoverKey gate prevents churning on sub-pixel moves.
    const hoverGroup = L.layerGroup().addTo(map)
    const onHoverMove = (e: L.LeafletMouseEvent) => {
      // Drag ghost is the relevant feedback during that gesture.
      if (dragStateRef.current.active) {
        if (hoverRectRef.current) {
          hoverRectRef.current.remove()
          hoverRectRef.current = null
          lastHoverKeyRef.current = null
        }
        return
      }
      const mode = selectionModeRef.current
      let key: string
      let bounds: [LatLngPair, LatLngPair]
      let regionKey: string
      if (mode === 'chunk') {
        const cx = Math.floor(e.latlng.lng / BLOCKS_PER_CHUNK)
        const cz = Math.floor(-e.latlng.lat / BLOCKS_PER_CHUNK)
        const rx = cx >> 5
        const rz = cz >> 5
        key = `c:${cx},${cz}`
        regionKey = `${rx},${rz}`
        bounds = chunkBounds(cx, cz)
      } else {
        const rx = Math.floor(e.latlng.lng / BLOCKS_PER_REGION)
        const rz = Math.floor(-e.latlng.lat / BLOCKS_PER_REGION)
        key = `r:${rx},${rz}`
        regionKey = `${rx},${rz}`
        bounds = regionBounds(rx, rz)
      }
      if (key === lastHoverKeyRef.current) return
      lastHoverKeyRef.current = key
      hoverRectRef.current?.remove()
      hoverRectRef.current = null
      if (!regionsRef.current.has(regionKey)) return
      hoverRectRef.current = L.rectangle(bounds, {
        color: '#ffffff',
        weight: 2,
        opacity: 0.7,
        fill: false,
        interactive: false,
      }).addTo(hoverGroup)
    }
    const onHoverOut = () => {
      hoverRectRef.current?.remove()
      hoverRectRef.current = null
      lastHoverKeyRef.current = null
    }
    if (!isCoarsePointer) {
      map.on('mousemove', onHoverMove)
      map.on('mouseout', onHoverOut)
    }

    // Right-click drag must subtract from selection, so suppress the menu.
    const onContextMenu = (e: L.LeafletMouseEvent) => {
      e.originalEvent.preventDefault()
    }
    map.on('contextmenu', onContextMenu)

    // tabIndex makes the container focusable so keydown fires before a click.
    const container = containerRef.current
    if (container) {
      container.tabIndex = 0
    }

    return () => {
      map.off('moveend', emitView)
      map.off('zoomend', emitView)
      if (!isCoarsePointer) {
        map.off('mousemove', onHoverMove)
        map.off('mouseout', onHoverOut)
      }
      map.off('contextmenu', onContextMenu)
      map.remove()
      mapRef.current = null
      tileLayerRef.current = null
      overlayLayerRef.current = null
      selectionLayerRef.current = null
      hoverRectRef.current = null
      lastHoverKeyRef.current = null
    }
    // isCoarsePointer is memoized with [] deps so this effect never re-runs.
  }, [isCoarsePointer])

  // Drop the hover rect on mode flip so the next mousemove redraws fresh.
  useEffect(() => {
    hoverRectRef.current?.remove()
    hoverRectRef.current = null
    lastHoverKeyRef.current = null
  }, [selectionMode])

  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    if (tileLayerRef.current) {
      map.removeLayer(tileLayerRef.current)
      tileLayerRef.current = null
    }
    const layer = new ServerMapTileLayer({
      serverId,
      regionPath,
      regions,
      noWrap: true,
      keepBuffer: 2,
      // mcmap emits a single resolution; pin native zoom so Leaflet scales
      // the same tiles across all zoom levels.
      minZoom: -4,
      maxZoom: 4,
      minNativeZoom: 0,
      maxNativeZoom: 0,
    })
    layer.addTo(map)
    tileLayerRef.current = layer
  }, [serverId, regionPath, regions])

  useEffect(() => {
    const map = mapRef.current
    const group = overlayLayerRef.current
    if (!map || !group) return
    group.clearLayers()
    if (!overlays) return
    for (const o of overlays) {
      group.addLayer(o.render(map))
    }
  }, [overlays])

  // Region mode renders fully-covered regions only; chunk mode falls back to
  // region rectangles past REGION_OVERLAY_THRESHOLD for canvas perf. The
  // underlying chunk set stays authoritative; only the visualization degrades.
  useEffect(() => {
    const group = selectionLayerRef.current
    if (!group) return
    group.clearLayers()
    if (!selection || selection.size === 0) return
    const renderer = L.canvas()
    if (selectionMode === 'region') {
      for (const r of chunksToFullyCoveredRegions(selection)) {
        L.rectangle(regionBounds(r.rx, r.rz), {
          renderer,
          color: '#3b82f6',
          weight: 1,
          fillOpacity: 0.2,
        }).addTo(group)
      }
      return
    }
    if (selection.size > REGION_OVERLAY_THRESHOLD) {
      for (const r of chunksToCoveredRegions(selection)) {
        L.rectangle(regionBounds(r.rx, r.rz), {
          renderer,
          color: '#3b82f6',
          weight: 1,
          fillOpacity: 0.2,
        }).addTo(group)
      }
      return
    }
    for (const k of selection) {
      const { cx, cz } = chunkKeyToCoord(k)
      L.rectangle(chunkBounds(cx, cz), {
        renderer,
        color: '#3b82f6',
        weight: 1,
        fillOpacity: 0.25,
      }).addTo(group)
    }
  }, [selection, selectionMode])

  // Tool decides drag behavior on every device. Desktop also honors Ctrl-drag
  // (add), right-button-drag (remove), and Escape (clear).
  //
  // Listening at the container's capture phase + preventDefault on pointerdown
  // suppresses Leaflet's drag handler so it never starts a pan — without
  // calling `map.dragging.disable()`, which would leave Leaflet wedged on
  // mid-gesture unmount. On touch, a secondary pointer aborts our gesture;
  // its touchstart still reaches Leaflet so pinch-zoom takes over cleanly.
  //
  // Drag-ghost updates run under requestAnimationFrame to coalesce moves.
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    if (selectionMode === 'none') return
    const container = containerRef.current
    if (!container) return

    const dragState = dragStateRef.current

    // Block-aligned box snapped to chunk or region granularity; clicks
    // collapse to a single cell.
    const cellsCovered = (a: L.LatLng, b: L.LatLng): Set<ChunkKey> => {
      const minBx = Math.min(a.lng, b.lng)
      const maxBx = Math.max(a.lng, b.lng)
      const minBz = Math.min(-a.lat, -b.lat)
      const maxBz = Math.max(-a.lat, -b.lat)
      const out = new Set<ChunkKey>()
      if (selectionMode === 'region') {
        const minRx = Math.floor(minBx / BLOCKS_PER_REGION)
        const maxRx = Math.floor(maxBx / BLOCKS_PER_REGION)
        const minRz = Math.floor(minBz / BLOCKS_PER_REGION)
        const maxRz = Math.floor(maxBz / BLOCKS_PER_REGION)
        for (let rz = minRz; rz <= maxRz; rz++) {
          for (let rx = minRx; rx <= maxRx; rx++) {
            for (const k of regionToChunkKeys({ rx, rz })) {
              out.add(k)
            }
          }
        }
        return out
      }
      for (const c of chunksInBlockBox(
        { bx: minBx, bz: minBz },
        { bx: maxBx, bz: maxBz },
      )) {
        out.add(chunkKey(c))
      }
      return out
    }

    const removeGhost = () => {
      dragGhostRef.current?.remove()
      dragGhostRef.current = null
    }

    const updateGhost = () => {
      dragState.rafScheduled = false
      if (!dragState.active || !dragState.start || !dragState.last) return
      const sw: LatLngPair = [
        Math.min(dragState.start.lat, dragState.last.lat),
        Math.min(dragState.start.lng, dragState.last.lng),
      ]
      const ne: LatLngPair = [
        Math.max(dragState.start.lat, dragState.last.lat),
        Math.max(dragState.start.lng, dragState.last.lng),
      ]
      const color = dragState.mode === 'remove' ? '#ef4444' : '#3b82f6'
      if (!dragGhostRef.current) {
        dragGhostRef.current = L.rectangle([sw, ne], {
          color,
          weight: 1,
          fillOpacity: 0.1,
          interactive: false,
        }).addTo(map)
      } else {
        dragGhostRef.current.setBounds(L.latLngBounds(sw, ne))
        dragGhostRef.current.setStyle({ color })
      }
    }

    const finishDrag = (end: L.LatLng | null) => {
      if (!dragState.active) return
      const start = dragState.start
      const last = end ?? dragState.last
      const mode = dragState.mode
      dragState.active = false
      dragState.start = null
      dragState.last = null
      dragState.rafScheduled = false
      removeGhost()
      if (!onSelectionChange || !start || !last) return
      const cells = cellsCovered(start, last)
      if (cells.size === 0) return
      const next = new Set<ChunkKey>(selectionRef.current ?? [])
      if (mode === 'remove') {
        for (const k of cells) next.delete(k)
      } else {
        for (const k of cells) next.add(k)
      }
      onSelectionChange(next)
    }

    const cancelDrag = () => {
      dragState.active = false
      dragState.start = null
      dragState.last = null
      dragState.rafScheduled = false
      removeGhost()
    }

    let detachWindow: (() => void) | null = null

    const onContainerPointerDown = (ev: PointerEvent) => {
      // Secondary touches abort via a separate listener (pinch-zoom takes over).
      if (!ev.isPrimary) return
      const tool = toolRef.current
      const isMouse = ev.pointerType === 'mouse'
      let mode: 'add' | 'remove' | null = null
      if (isMouse) {
        const isLeft = ev.button === 0
        const isRight = ev.button === 2
        if (isLeft && (ev.ctrlKey || tool === 'add')) mode = 'add'
        else if (isRight || (isLeft && tool === 'erase')) mode = 'remove'
      } else {
        // Touch / pen: tool is the only signal.
        if (tool === 'add') mode = 'add'
        else if (tool === 'erase') mode = 'remove'
      }
      if (!mode) return
      ev.stopImmediatePropagation()
      ev.preventDefault()

      const pointerId = ev.pointerId
      const startLatLng = map.mouseEventToLatLng(ev)
      dragState.active = true
      dragState.start = startLatLng
      dragState.last = startLatLng
      dragState.mode = mode
      dragState.rafScheduled = false
      removeGhost()
      updateGhost()

      const onPointerMove = (e: PointerEvent) => {
        if (e.pointerId !== pointerId) return
        if (!dragState.active) return
        dragState.last = map.mouseEventToLatLng(e)
        if (!dragState.rafScheduled) {
          dragState.rafScheduled = true
          requestAnimationFrame(updateGhost)
        }
      }
      const onPointerUp = (e: PointerEvent) => {
        if (e.pointerId !== pointerId) return
        finishDrag(map.mouseEventToLatLng(e))
        detachWindow?.()
      }
      const onPointerCancel = (e: PointerEvent) => {
        if (e.pointerId !== pointerId) return
        cancelDrag()
        detachWindow?.()
      }
      // Touch only: a second pointer mid-drag aborts so Leaflet pinch-zooms.
      const onSecondaryPointerDown = (e: PointerEvent) => {
        if (e.pointerId === pointerId) return
        if (isMouse) return
        cancelDrag()
        detachWindow?.()
      }

      window.addEventListener('pointermove', onPointerMove)
      window.addEventListener('pointerup', onPointerUp)
      window.addEventListener('pointercancel', onPointerCancel)
      window.addEventListener('pointerdown', onSecondaryPointerDown)
      detachWindow = () => {
        window.removeEventListener('pointermove', onPointerMove)
        window.removeEventListener('pointerup', onPointerUp)
        window.removeEventListener('pointercancel', onPointerCancel)
        window.removeEventListener('pointerdown', onSecondaryPointerDown)
        detachWindow = null
      }
    }
    container.addEventListener('pointerdown', onContainerPointerDown, true)

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      if (!onSelectionChange) return
      onSelectionChange(new Set())
    }
    container.addEventListener('keydown', onKeyDown)

    return () => {
      container.removeEventListener('pointerdown', onContainerPointerDown, true)
      container.removeEventListener('keydown', onKeyDown)
      detachWindow?.()
      removeGhost()
      dragState.active = false
      dragState.start = null
      dragState.last = null
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- selectionRef is a stable ref
  }, [selectionMode, onSelectionChange])

  // Inline `bg-card` overrides Leaflet's default `.leaflet-container` background.
  const mapStyle = useMemo(
    () => ({ background: 'var(--card)' }),
    [],
  )

  const handleClear = () => {
    onSelectionChange?.(new Set())
  }

  const handleJump = (bx: number, bz: number) => {
    const map = mapRef.current
    if (!map) return
    map.setView(blockToLatLng(bx, bz), map.getZoom(), { animate: true })
  }

  return (
    <div className={cn('relative isolate h-full w-full', className)}>
      <div
        ref={containerRef}
        className="absolute inset-0"
        style={mapStyle}
        data-testid="server-map"
      />
      <CoordinateJumpControl onJump={handleJump} />
      {selectionMode !== 'none' && (
        <SelectionToolbar
          tool={tool}
          onToolChange={setTool}
          onClear={handleClear}
          canClear={!!selection && selection.size > 0}
        />
      )}
    </div>
  )
}

interface CoordinateJumpControlProps {
  onJump: (bx: number, bz: number) => void
}

const CoordinateJumpControl: React.FC<CoordinateJumpControlProps> = ({
  onJump,
}) => {
  const [xStr, setXStr] = useState('')
  const [zStr, setZStr] = useState('')

  const submit = () => {
    if (xStr === '' || zStr === '') return
    const x = Number(xStr)
    const z = Number(zStr)
    if (!Number.isFinite(x) || !Number.isFinite(z)) return
    onJump(x, z)
  }

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      submit()
    }
  }

  return (
    <div className="absolute top-2 left-2 z-1000 flex items-center gap-1 rounded-lg border border-border bg-background/95 p-1 shadow-md backdrop-blur supports-backdrop-filter:bg-background/80">
      <Input
        type="number"
        step="1"
        value={xStr}
        onChange={(e) => setXStr(e.target.value)}
        onKeyDown={onKeyDown}
        placeholder="X"
        aria-label="X 坐标"
        className="h-7 w-20 px-2 text-xs"
      />
      <Input
        type="number"
        step="1"
        value={zStr}
        onChange={(e) => setZStr(e.target.value)}
        onKeyDown={onKeyDown}
        placeholder="Z"
        aria-label="Z 坐标"
        className="h-7 w-20 px-2 text-xs"
      />
      <Button
        size="icon-sm"
        variant="ghost"
        aria-label="跳转坐标"
        title="跳转坐标"
        onClick={submit}
      >
        <LocateFixed className="h-4 w-4" />
      </Button>
      <Button
        size="icon-sm"
        variant="ghost"
        aria-label="清空输入"
        title="清空输入"
        disabled={xStr === '' && zStr === ''}
        onClick={() => {
          setXStr('')
          setZStr('')
        }}
      >
        <X className="h-4 w-4" />
      </Button>
    </div>
  )
}

interface SelectionToolbarProps {
  tool: SelectionTool
  onToolChange: (next: SelectionTool) => void
  onClear: () => void
  canClear: boolean
}

const SelectionToolbar: React.FC<SelectionToolbarProps> = ({
  tool,
  onToolChange,
  onClear,
  canClear,
}) => {
  const item = (
    value: SelectionTool,
    label: string,
    Icon: typeof Hand,
  ): React.ReactElement => (
    <Button
      key={value}
      variant={tool === value ? 'default' : 'ghost'}
      size="icon-sm"
      aria-label={label}
      title={label}
      aria-pressed={tool === value}
      onClick={() => onToolChange(value)}
    >
      <Icon className="h-4 w-4" />
    </Button>
  )
  return (
    <div className="absolute top-2 right-2 z-1000 flex flex-col items-end gap-1.5">
      <div className="flex flex-col gap-0.5 rounded-lg border border-border bg-background/95 p-1 shadow-md backdrop-blur supports-backdrop-filter:bg-background/80">
        {item('pan', '平移', Hand)}
        {item('add', '添加', Plus)}
        {item('erase', '擦除', Eraser)}
      </div>
      <div className="rounded-lg border border-border bg-background/95 p-1 shadow-md backdrop-blur supports-backdrop-filter:bg-background/80">
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label="清空选区"
          title="清空选区"
          disabled={!canClear}
          onClick={onClear}
        >
          <Trash2 className="h-4 w-4" />
        </Button>
      </div>
    </div>
  )
}

export default ServerMap
