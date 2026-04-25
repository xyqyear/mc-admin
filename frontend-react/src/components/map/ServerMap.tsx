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
} from './coords'
import { ServerMapTileLayer } from './ServerMapTileLayer'

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

function regionBoundsAroundBlock(
  bx: number,
  bz: number
): [LatLngPair, LatLngPair] {
  const rx = Math.floor(bx / BLOCKS_PER_REGION)
  const rz = Math.floor(bz / BLOCKS_PER_REGION)
  const sw = blockToLatLng(rx * BLOCKS_PER_REGION, (rz + 1) * BLOCKS_PER_REGION)
  const ne = blockToLatLng(
    (rx + 1) * BLOCKS_PER_REGION,
    rz * BLOCKS_PER_REGION
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
  const dragRectRef = useRef<L.Rectangle | null>(null)
  const dragStartRef = useRef<L.LatLng | null>(null)
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

    return () => {
      map.off('moveend', emitView)
      map.off('zoomend', emitView)
      map.off('mousemove', onHoverMove)
      map.off('mouseout', onHoverOut)
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
  useEffect(() => {
    const group = selectionLayerRef.current
    if (!group) return
    group.clearLayers()
    if (!selection || selection.size === 0) return
    const renderer = L.canvas()
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
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    if (selectionMode === 'none') {
      map.dragging.enable()
      return
    }

    const cellsCovered = (
      a: L.LatLng,
      b: L.LatLng
    ): Set<ChunkKey> => {
      const minBx = Math.min(a.lng, b.lng)
      const maxBx = Math.max(a.lng, b.lng)
      const minBz = Math.min(-a.lat, -b.lat)
      const maxBz = Math.max(-a.lat, -b.lat)
      const out = new Set<ChunkKey>()
      const granularity =
        selectionMode === 'region' ? BLOCKS_PER_REGION : BLOCKS_PER_CHUNK
      for (let bz = minBz; bz <= maxBz; bz += granularity) {
        for (let bx = minBx; bx <= maxBx; bx += granularity) {
          for (const c of chunksInBlockBox(
            { bx, bz },
            { bx: Math.min(bx + granularity, maxBx), bz: Math.min(bz + granularity, maxBz) }
          )) {
            out.add(chunkKey(c))
          }
        }
      }
      return out
    }

    const onClick = (e: L.LeafletMouseEvent) => {
      if (!onSelectionChange) return
      const { latlng, originalEvent } = e
      const ctrl = originalEvent.ctrlKey || originalEvent.metaKey
      const bx = Math.floor(latlng.lng)
      const bz = Math.floor(-latlng.lat)
      const next = new Set<ChunkKey>(ctrl ? selection ?? [] : [])
      if (selectionMode === 'region') {
        const sw = regionBoundsAroundBlock(bx, bz)
        // Region selection contributes 32×32 chunks
        const minBx = Math.floor(bx / BLOCKS_PER_REGION) * BLOCKS_PER_REGION
        const minBz = Math.floor(bz / BLOCKS_PER_REGION) * BLOCKS_PER_REGION
        for (const c of chunksInBlockBox(
          { bx: minBx, bz: minBz },
          { bx: minBx + BLOCKS_PER_REGION - 1, bz: minBz + BLOCKS_PER_REGION - 1 }
        )) {
          const k = chunkKey(c)
          if (ctrl && next.has(k)) next.delete(k)
          else next.add(k)
        }
        // sw is unused but documents the bounds we selected
        void sw
      } else {
        const c = blockToChunk({ bx, bz })
        const k = chunkKey(c)
        if (ctrl && next.has(k)) next.delete(k)
        else next.add(k)
      }
      onSelectionChange(next)
    }

    const onMouseDown = (e: L.LeafletMouseEvent) => {
      const { originalEvent } = e
      if (!(originalEvent.ctrlKey || originalEvent.metaKey)) return
      map.dragging.disable()
      dragStartRef.current = e.latlng
      dragRectRef.current?.remove()
      const seed: LatLngPair = [e.latlng.lat, e.latlng.lng]
      dragRectRef.current = L.rectangle([seed, seed], {
        color: '#3b82f6',
        weight: 1,
        fillOpacity: 0.1,
      }).addTo(map)
    }

    const onMouseMove = (e: L.LeafletMouseEvent) => {
      if (!dragStartRef.current || !dragRectRef.current) return
      const a = dragStartRef.current
      const b = e.latlng
      const sw: LatLngPair = [Math.min(a.lat, b.lat), Math.min(a.lng, b.lng)]
      const ne: LatLngPair = [Math.max(a.lat, b.lat), Math.max(a.lng, b.lng)]
      dragRectRef.current.setBounds(L.latLngBounds(sw, ne))
    }

    const onMouseUp = (e: L.LeafletMouseEvent) => {
      if (!dragStartRef.current) {
        map.dragging.enable()
        return
      }
      const start = dragStartRef.current
      dragStartRef.current = null
      dragRectRef.current?.remove()
      dragRectRef.current = null
      map.dragging.enable()
      if (!onSelectionChange) return
      const additions = cellsCovered(start, e.latlng)
      if (additions.size === 0) return
      const next = new Set<ChunkKey>(selection ?? [])
      for (const k of additions) next.add(k)
      onSelectionChange(next)
    }

    map.on('click', onClick)
    map.on('mousedown', onMouseDown)
    map.on('mousemove', onMouseMove)
    map.on('mouseup', onMouseUp)
    return () => {
      map.off('click', onClick)
      map.off('mousedown', onMouseDown)
      map.off('mousemove', onMouseMove)
      map.off('mouseup', onMouseUp)
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
