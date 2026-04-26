import React, { useEffect, useMemo, useRef } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

import type { ChunkKey, SelectionMode } from '@/types/MapTypes'

import {
  BLOCKS_PER_CHUNK,
  BLOCKS_PER_REGION,
  blockToChunk,
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
  // Drag-rect selection (shift-drag adds, right-button-drag removes). State
  // lives in refs so mousemove can update the ghost rectangle without
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
  //   • Single click           : toggle one chunk (chunk mode) or a region's
  //                              1024 chunks (region mode).
  //   • Shift + drag           : additive rectangle selection.
  //   • Right-button + drag    : subtractive rectangle selection.
  //   • Escape (map focused)   : clear selection.
  //
  // The drag ghost is updated under requestAnimationFrame so a high-frequency
  // mousemove stream still produces at most one rectangle setBounds per frame.
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    if (selectionMode === 'none') {
      map.dragging.enable()
      return
    }

    // Block-aligned bounding box of the latlng pair, snapped to chunk or region
    // granularity according to selectionMode.
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
      // chunk mode — enumerate every chunk inside the inclusive block box
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
      const st = dragStateRef.current
      st.rafScheduled = false
      if (!st.active || !st.start || !st.last) return
      const sw: LatLngPair = [
        Math.min(st.start.lat, st.last.lat),
        Math.min(st.start.lng, st.last.lng),
      ]
      const ne: LatLngPair = [
        Math.max(st.start.lat, st.last.lat),
        Math.max(st.start.lng, st.last.lng),
      ]
      const color = st.mode === 'remove' ? '#ef4444' : '#3b82f6'
      if (!dragGhostRef.current) {
        dragGhostRef.current = L.rectangle([sw, ne], {
          color,
          weight: 1,
          fillOpacity: 0.1,
        }).addTo(map)
      } else {
        dragGhostRef.current.setBounds(L.latLngBounds(sw, ne))
        dragGhostRef.current.setStyle({ color })
      }
    }

    const onClick = (e: L.LeafletMouseEvent) => {
      if (!onSelectionChange) return
      // Shift-click is reserved for the drag start; treat a stray
      // shift-click (no movement) as a drag of zero size and ignore it.
      if (e.originalEvent.shiftKey) return
      const bx = Math.floor(e.latlng.lng)
      const bz = Math.floor(-e.latlng.lat)
      const next = new Set<ChunkKey>(selection ?? [])
      if (selectionMode === 'region') {
        const rx = Math.floor(bx / BLOCKS_PER_REGION)
        const rz = Math.floor(bz / BLOCKS_PER_REGION)
        const keys = regionToChunkKeys({ rx, rz })
        // Toggle: if every chunk of the region is present, remove all;
        // otherwise add all. Single-chunk noise inside the region is
        // promoted to a full region select on click.
        const allPresent = keys.every((k) => next.has(k))
        if (allPresent) {
          for (const k of keys) next.delete(k)
        } else {
          for (const k of keys) next.add(k)
        }
      } else {
        const c = blockToChunk({ bx, bz })
        const k = chunkKey(c)
        if (next.has(k)) next.delete(k)
        else next.add(k)
      }
      onSelectionChange(next)
    }

    const onMouseDown = (e: L.LeafletMouseEvent) => {
      const ev = e.originalEvent
      const isShift = ev.shiftKey
      const isRight = ev.button === 2
      if (!isShift && !isRight) return
      // Shift drags reuse the left button — disable map panning so the gesture
      // doesn't move the map. Right-button drag never engages map dragging.
      if (isShift) map.dragging.disable()
      const st = dragStateRef.current
      st.active = true
      st.start = e.latlng
      st.last = e.latlng
      st.mode = isRight ? 'remove' : 'add'
      st.rafScheduled = false
      removeGhost()
      updateGhost()
    }

    const onMouseMove = (e: L.LeafletMouseEvent) => {
      const st = dragStateRef.current
      if (!st.active) return
      st.last = e.latlng
      if (!st.rafScheduled) {
        st.rafScheduled = true
        requestAnimationFrame(updateGhost)
      }
    }

    const finishDrag = (end: L.LatLng | null) => {
      const st = dragStateRef.current
      if (!st.active) {
        map.dragging.enable()
        return
      }
      const start = st.start
      const last = end ?? st.last
      st.active = false
      st.start = null
      st.last = null
      st.rafScheduled = false
      removeGhost()
      map.dragging.enable()
      if (!onSelectionChange || !start || !last) return
      const cells = cellsCovered(start, last)
      if (cells.size === 0) return
      const next = new Set<ChunkKey>(selection ?? [])
      if (st.mode === 'remove') {
        for (const k of cells) next.delete(k)
      } else {
        for (const k of cells) next.add(k)
      }
      onSelectionChange(next)
    }

    const onMouseUp = (e: L.LeafletMouseEvent) => finishDrag(e.latlng)

    // Outside-the-map mouseup never fires Leaflet's `mouseup`. Hook the window
    // so a release outside the canvas still finishes the drag — leaving a
    // ghost rectangle stuck on screen until the next interaction is jarring.
    const onWindowMouseUp = () => {
      if (dragStateRef.current.active) finishDrag(null)
    }
    window.addEventListener('mouseup', onWindowMouseUp)

    const container = containerRef.current
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      if (!onSelectionChange) return
      onSelectionChange(new Set())
    }
    container?.addEventListener('keydown', onKeyDown)

    map.on('click', onClick)
    map.on('mousedown', onMouseDown)
    map.on('mousemove', onMouseMove)
    map.on('mouseup', onMouseUp)
    return () => {
      map.off('click', onClick)
      map.off('mousedown', onMouseDown)
      map.off('mousemove', onMouseMove)
      map.off('mouseup', onMouseUp)
      window.removeEventListener('mouseup', onWindowMouseUp)
      container?.removeEventListener('keydown', onKeyDown)
      removeGhost()
      dragStateRef.current.active = false
      dragStateRef.current.start = null
      dragStateRef.current.last = null
      map.dragging.enable()
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
