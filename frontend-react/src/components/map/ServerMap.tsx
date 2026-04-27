import React, { useEffect, useMemo, useRef } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

import type { ChunkKey, SelectionMode } from '@/types/MapTypes'

import {
  BLOCKS_PER_CHUNK,
  BLOCKS_PER_REGION,
  chunkKey,
  chunkKeyToCoord,
  chunksInBlockBox,
  chunksToCoveredRegions,
  regionToChunkKeys,
} from './coords'
import { ServerMapTileLayer } from './ServerMapTileLayer'

const REGION_OVERLAY_THRESHOLD = 5_000

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
  // Manifest of existing regions for this dimension keyed by `${x},${z}`,
  // mapped to the source MCA's mtime (epoch seconds). The tile layer uses
  // it to skip HTTP requests for non-existent regions and to cache-bust
  // tile URLs when the underlying MCA is regenerated.
  regions: ReadonlyMap<string, number>
  selectionMode?: SelectionMode
  selection?: Set<ChunkKey>
  onSelectionChange?: (next: Set<ChunkKey>) => void
  overlays?: ServerMapOverlay[]
  className?: string
  initialView?: ServerMapView
  onViewChange?: (view: ServerMapView) => void
}

// Block-space → leaflet (lat, lng): with CRS.Simple, lat = -y (south) and
// lng = x. We use 1 block = 1 unit. Tile (rx, ry) covers blocks
// [rx*512 .. rx*512+512) horizontally and [ry*512 .. ry*512+512) on the z axis.
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
  // Drag-rect selection (Ctrl/Shift+drag adds, right-button-drag removes).
  // State lives in refs so mousemove can update the ghost rectangle without
  // triggering React re-renders. The hover-frame handler in the init effect
  // also reads `active` to suppress the hover overlay during drags.
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
  // Always-fresh callback ref so the map listener closure stays stable.
  const onViewChangeRef = useRef(onViewChange)
  useEffect(() => {
    onViewChangeRef.current = onViewChange
  }, [onViewChange])
  // Latest-regions ref so handlers registered in the once-only init effect
  // can probe the manifest without resubscribing on every manifest refetch.
  const regionsRef = useRef(regions)
  useEffect(() => {
    regionsRef.current = regions
  }, [regions])

  // Initialize the leaflet map exactly once.
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
      preferCanvas: true,
    })
    mapRef.current = map
    overlayLayerRef.current = L.layerGroup().addTo(map)
    selectionLayerRef.current = L.layerGroup().addTo(map)

    // Bound after L.map() so init events fired during construction don't leak
    // out as a phantom view-change. moveend covers both pan completion and the
    // tail of a zoom; we still listen to zoomend for keyboard / button zooms
    // that complete without changing the center.
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

    // Live block-coordinate readout for the cursor position. Implemented as a
    // Leaflet control with direct DOM updates (no React re-renders on every
    // mousemove). The map's mousemove event provides world coords via
    // e.latlng — in CRS.Simple, lng = block X and -lat = block Z.
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
          // Only prepend the MCA name when the region actually exists on
          // disk; over empty grid cells the readout falls back to plain
          // block coords so we don't advertise files that aren't there.
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

    // Translucent frame around the region currently under the cursor. Only
    // drawn when the region exists in the manifest — i.e. when there's a
    // real rendered tile to highlight. The lastHoverKey gate keeps every
    // sub-pixel mousemove from churning rectangles.
    const hoverGroup = L.layerGroup().addTo(map)
    let hoverRect: L.Rectangle | null = null
    let lastHoverKey: string | null = null
    const onHoverMove = (e: L.LeafletMouseEvent) => {
      // Suppress the hover frame while a drag-rect selection is in progress —
      // the drag ghost is the relevant feedback during that gesture.
      if (dragStateRef.current.active) {
        if (hoverRect) {
          hoverRect.remove()
          hoverRect = null
          lastHoverKey = null
        }
        return
      }
      const rx = Math.floor(e.latlng.lng / BLOCKS_PER_REGION)
      const rz = Math.floor(-e.latlng.lat / BLOCKS_PER_REGION)
      const key = `${rx},${rz}`
      if (key === lastHoverKey) return
      lastHoverKey = key
      hoverRect?.remove()
      hoverRect = null
      if (!regionsRef.current.has(key)) return
      const sw = blockToLatLng(
        rx * BLOCKS_PER_REGION,
        (rz + 1) * BLOCKS_PER_REGION,
      )
      const ne = blockToLatLng(
        (rx + 1) * BLOCKS_PER_REGION,
        rz * BLOCKS_PER_REGION,
      )
      hoverRect = L.rectangle([sw, ne], {
        color: '#ffffff',
        weight: 2,
        opacity: 0.7,
        fill: false,
        interactive: false,
      }).addTo(hoverGroup)
    }
    const onHoverOut = () => {
      hoverRect?.remove()
      hoverRect = null
      lastHoverKey = null
    }
    map.on('mousemove', onHoverMove)
    map.on('mouseout', onHoverOut)

    // Suppress the browser context menu so right-click drag can subtract from
    // the selection. This is wired once at init regardless of selectionMode —
    // the selection effect decides whether to act on right-button events.
    const onContextMenu = (e: L.LeafletMouseEvent) => {
      e.originalEvent.preventDefault()
    }
    map.on('contextmenu', onContextMenu)

    // Allow keyboard interactions (Escape clears selection). Leaflet keeps the
    // container focusable when `keyboard: true` (default), but tabIndex makes
    // the focus path explicit; without it, browsers won't fire keydown on the
    // div until the user manually clicks inside.
    const container = containerRef.current
    if (container) {
      container.tabIndex = 0
    }

    return () => {
      map.off('moveend', emitView)
      map.off('zoomend', emitView)
      map.off('mousemove', onHoverMove)
      map.off('mouseout', onHoverOut)
      map.off('contextmenu', onContextMenu)
      map.remove()
      mapRef.current = null
      tileLayerRef.current = null
      overlayLayerRef.current = null
      selectionLayerRef.current = null
    }
  }, [])

  // Rebuild the tile layer when serverId, regionPath, or the regions manifest
  // changes. The manifest is captured by reference inside the layer, so a new
  // Set instance from a refetch swaps it cleanly.
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
      // mcmap produces a single tile resolution (one PNG per region). Pin a
      // native zoom so Leaflet auto-scales the same tiles across zoom levels
      // instead of requesting a new pyramid per zoom. min/maxZoom must cover
      // the map's full range or the layer hides itself outside it.
      minZoom: -4,
      maxZoom: 4,
      minNativeZoom: 0,
      maxNativeZoom: 0,
    })
    layer.addTo(map)
    tileLayerRef.current = layer
  }, [serverId, regionPath, regions])

  // Mount overlays.
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

  // Repaint selection overlay.
  //
  // For very large selections the per-chunk fill is the bottleneck (one Leaflet
  // path per chunk; with 5k+ chunks the canvas renderer churns). When the
  // selection grows past the threshold we degrade to a per-region overlay —
  // one rectangle per affected region. The underlying chunk set remains
  // authoritative; only the visualization changes.
  useEffect(() => {
    const group = selectionLayerRef.current
    if (!group) return
    group.clearLayers()
    if (!selection || selection.size === 0) return
    const renderer = L.canvas()
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
  }, [selection])

  // Selection handling.
  //
  // Interactions:
  //   • Plain left drag        : map pan (Leaflet's default, always enabled).
  //   • Ctrl + click     : add the chunk/region under the cursor.
  //   • Ctrl + drag      : additive rectangle selection.
  //   • Right click            : remove the chunk/region under the cursor.
  //   • Right-button + drag    : subtractive rectangle selection.
  //   • Escape (map focused)   : clear selection.
  //
  // Selection gestures are intercepted at the container's DOM capture phase
  // and finished via window listeners. That keeps Leaflet's drag handler out
  // of the picture entirely — we never call `map.dragging.disable()`, so the
  // handler can't be left wedged when the component unmounts mid-gesture.
  // The drag ghost updates under requestAnimationFrame so a high-frequency
  // mousemove stream produces at most one rectangle setBounds per frame.
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    if (selectionMode === 'none') return
    const container = containerRef.current
    if (!container) return

    const dragState = dragStateRef.current

    // Block-aligned bounding box of the latlng pair, snapped to chunk or region
    // granularity according to selectionMode. Single-point gestures (a click)
    // collapse to one cell.
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
      const next = new Set<ChunkKey>(selection ?? [])
      if (mode === 'remove') {
        for (const k of cells) next.delete(k)
      } else {
        for (const k of cells) next.add(k)
      }
      onSelectionChange(next)
    }

    let onWindowMove: ((ev: MouseEvent) => void) | null = null
    let onWindowUp: ((ev: MouseEvent) => void) | null = null
    const detachWindow = () => {
      if (onWindowMove) {
        window.removeEventListener('mousemove', onWindowMove)
        onWindowMove = null
      }
      if (onWindowUp) {
        window.removeEventListener('mouseup', onWindowUp)
        onWindowUp = null
      }
    }

    // Capture-phase mousedown so we run before Leaflet's bubble-phase
    // listeners on the same element. stopImmediatePropagation prevents both
    // the Map's `_handleDOMEvent` and Draggable's `_onDown` from firing,
    // which means Leaflet never sees the gesture and never starts a pan.
    const onContainerMouseDown = (ev: MouseEvent) => {
      const isLeft = ev.button === 0
      const isRight = ev.button === 2
      const isModifier = ev.ctrlKey
      let mode: 'add' | 'remove' | null = null
      if (isLeft && isModifier) mode = 'add'
      else if (isRight) mode = 'remove'
      if (!mode) return
      ev.stopImmediatePropagation()
      ev.preventDefault()

      const startLatLng = map.mouseEventToLatLng(ev)
      dragState.active = true
      dragState.start = startLatLng
      dragState.last = startLatLng
      dragState.mode = mode
      dragState.rafScheduled = false
      removeGhost()
      updateGhost()

      onWindowMove = (e: MouseEvent) => {
        if (!dragState.active) return
        dragState.last = map.mouseEventToLatLng(e)
        if (!dragState.rafScheduled) {
          dragState.rafScheduled = true
          requestAnimationFrame(updateGhost)
        }
      }
      onWindowUp = (e: MouseEvent) => {
        finishDrag(map.mouseEventToLatLng(e))
        detachWindow()
      }
      window.addEventListener('mousemove', onWindowMove)
      window.addEventListener('mouseup', onWindowUp)
    }
    container.addEventListener('mousedown', onContainerMouseDown, true)

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      if (!onSelectionChange) return
      onSelectionChange(new Set())
    }
    container.addEventListener('keydown', onKeyDown)

    return () => {
      container.removeEventListener('mousedown', onContainerMouseDown, true)
      container.removeEventListener('keydown', onKeyDown)
      detachWindow()
      removeGhost()
      dragState.active = false
      dragState.start = null
      dragState.last = null
    }
  }, [selectionMode, selection, onSelectionChange])

  // Background follows the Card's `bg-card` token so the empty areas around
  // tiles match the surrounding theme in both light and dark modes. Inline
  // style beats Leaflet's `.leaflet-container { background: #ddd }` on
  // specificity without needing a global CSS override.
  const style = useMemo(
    () => ({ width: '100%', height: '100%', background: 'var(--card)' }),
    [],
  )

  return (
    <div
      ref={containerRef}
      style={style}
      className={className}
      data-testid="server-map"
    />
  )
}

export default ServerMap
