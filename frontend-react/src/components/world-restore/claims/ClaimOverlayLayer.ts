// Build a Leaflet LayerGroup for the FTB claims overlay.
//
// The group contains, per cluster: one `L.polygon` (outline + fill), one
// `L.divIcon` marker (label pill), and any number of small force-loaded hatch
// polylines. The builder is called from inside ServerMap's overlays effect;
// it returns the LayerGroup AND populates `polygonRefs` / `labelRefs` so the
// React hook can mutate styles imperatively (highlight pulse) without
// rebuilding the entire overlay on every hover.

import L from 'leaflet'

import { BLOCKS_PER_CHUNK } from '@/components/map/coords'
import type {
  FtbClusterEntry,
  FtbTeamEntry,
} from '@/types/FtbClaims'

import { computeBoundaryRings, type Ring } from './computeBoundary'
import { pickLabelEdge } from './pickLabelEdge'
import { teamColors } from './teamColors'
import type { TeamColor } from './teamColors'

// CRS.Simple: lat = -z, lng = x.
const blockToLatLng = (bx: number, bz: number): L.LatLngExpression => [-bz, bx]

function ringToLatLngs(ring: Ring): L.LatLngExpression[] {
  return ring.map(([cx, cz]) =>
    blockToLatLng(cx * BLOCKS_PER_CHUNK, cz * BLOCKS_PER_CHUNK),
  )
}

function clusterPolygon(
  cluster: FtbClusterEntry,
  color: TeamColor,
  hoverHtml: string,
): L.Polygon {
  const rings = computeBoundaryRings(cluster.chunks)
  // Sort by length so the longest ring (presumed outer) leads; any later
  // rings become holes. For simply-connected clusters there's only one ring.
  rings.sort((a, b) => b.length - a.length)
  const latLngRings = rings.map(ringToLatLngs)
  const polygon = L.polygon(latLngRings as L.LatLngExpression[][], {
    color: color.stroke,
    weight: 1.5,
    opacity: 0.9,
    fillColor: color.stroke,
    fillOpacity: 0.22,
    interactive: true,
    bubblingMouseEvents: false,
  })
  // Polygon is hover-only — the label is the click target per design.
  polygon.bindTooltip(hoverHtml, {
    sticky: true,
    direction: 'top',
    opacity: 0.95,
  })
  return polygon
}

function forceLoadedHatch(
  cluster: FtbClusterEntry,
): L.Layer | null {
  if (cluster.force_loaded.length === 0) return null
  // Three diagonals per chunk; CSS pattern would be cleaner but requires a
  // custom SVG renderer; this stays in the canvas path the rest of the page uses.
  const renderer = L.canvas({ padding: 0.1 })
  const lines: L.Polyline[] = []
  for (const [cx, cz] of cluster.force_loaded) {
    const x0 = cx * BLOCKS_PER_CHUNK
    const z0 = cz * BLOCKS_PER_CHUNK
    const x1 = x0 + BLOCKS_PER_CHUNK
    const z1 = z0 + BLOCKS_PER_CHUNK
    for (const t of [0.25, 0.5, 0.75]) {
      // A family of NW→SE diagonals offset along the cell. Each line spans
      // one chunk; collectively they read as a hatched fill at all zoom levels.
      const start: L.LatLngExpression = blockToLatLng(x0, z0 + t * BLOCKS_PER_CHUNK)
      const end: L.LatLngExpression = blockToLatLng(
        x0 + (1 - t) * BLOCKS_PER_CHUNK,
        z1,
      )
      lines.push(
        L.polyline([start, end], {
          renderer,
          color: '#ef4444',
          weight: 1,
          opacity: 0.7,
          interactive: false,
        }),
      )
      const start2: L.LatLngExpression = blockToLatLng(x0 + t * BLOCKS_PER_CHUNK, z0)
      const end2: L.LatLngExpression = blockToLatLng(
        x1,
        z0 + (1 - t) * BLOCKS_PER_CHUNK,
      )
      lines.push(
        L.polyline([start2, end2], {
          renderer,
          color: '#ef4444',
          weight: 1,
          opacity: 0.7,
          interactive: false,
        }),
      )
    }
  }
  return L.layerGroup(lines)
}

function clusterLabel(
  cluster: FtbClusterEntry,
  team: FtbTeamEntry,
  color: TeamColor,
  onClick: (clusterId: string, anchorEl: HTMLElement) => void,
): L.Marker | null {
  const edge = pickLabelEdge(cluster.chunks)
  if (!edge) return null
  // Sit a few blocks beyond the chunk edge so the pill never overlaps the polygon stroke.
  const outwardOffsetBlocks = edge.side === 'top' ? -2 : 2
  const anchorBz = edge.bz + outwardOffsetBlocks
  const labelText = escapeHtml(team.display_name)
  // translateY shifts the label off the marker's lat/lng point; the CSS in
  // claims.css handles the X centering and the pill styling.
  const translateY = edge.side === 'top' ? '-100%' : '0%'
  const html =
    `<div class="ftb-claim-label-anchor" ` +
    `data-cluster-id="${escapeHtml(cluster.id)}" ` +
    `style="background:${color.fill};color:${color.text};border-color:${color.stroke};` +
    `transform:translate(-50%, ${translateY})">${labelText}</div>`
  const icon = L.divIcon({
    html,
    className: 'ftb-claim-label-icon',
    iconSize: [0, 0],
    iconAnchor: [0, 0],
  })
  const marker = L.marker(blockToLatLng(edge.bx, anchorBz), {
    icon,
    interactive: true,
    riseOnHover: true,
    keyboard: false,
  })
  marker.on('add', () => {
    const el = marker.getElement()
    if (!el) return
    const anchor = el.querySelector<HTMLElement>('.ftb-claim-label-anchor')
    if (!anchor) return
    // Stop propagation so the click doesn't reach the map (which would start
    // a pan or a selection drag depending on tool).
    const handler = (e: Event) => {
      e.stopPropagation()
      onClick(cluster.id, anchor)
    }
    anchor.addEventListener('mousedown', (e) => e.stopPropagation(), true)
    anchor.addEventListener('pointerdown', (e) => e.stopPropagation(), true)
    anchor.addEventListener('click', handler)
  })
  return marker
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

export interface ClaimsLayerRefs {
  polygonsByClusterId: Map<string, L.Polygon>
  labelsByClusterId: Map<string, L.Marker>
  teamIdByClusterId: Map<string, string>
}

export interface BuildClaimsLayerOptions {
  teams: FtbTeamEntry[]
  currentDimRelpath: string | null
  onLabelClick: (clusterId: string, anchorEl: HTMLElement) => void
  refs: ClaimsLayerRefs
}

export function buildClaimsLayer({
  teams,
  currentDimRelpath,
  onLabelClick,
  refs,
}: BuildClaimsLayerOptions): L.LayerGroup {
  refs.polygonsByClusterId.clear()
  refs.labelsByClusterId.clear()
  refs.teamIdByClusterId.clear()

  const group = L.layerGroup()
  if (!currentDimRelpath) return group
  for (const team of teams) {
    const color = teamColors(team.id, team.type)
    for (const cluster of team.clusters) {
      if (cluster.region_dir_relpath !== currentDimRelpath) continue
      const memberPreview =
        team.members.length === 0
          ? ''
          : team.members.length === 1
            ? team.members[0].name ?? team.members[0].uuid ?? ''
            : `${team.members.length} members`
      const hoverHtml = `<div style="font-size:12px;line-height:1.35;max-width:240px">
  <div style="font-weight:600">${escapeHtml(team.display_name)}</div>
  <div style="opacity:0.8">${escapeHtml(team.type)} · ${cluster.chunks.length} chunks${
    cluster.force_loaded.length > 0
      ? ` · ${cluster.force_loaded.length} force-loaded`
      : ''
  }</div>
  ${memberPreview ? `<div style="opacity:0.7;margin-top:2px">${escapeHtml(memberPreview)}</div>` : ''}
</div>`
      const polygon = clusterPolygon(cluster, color, hoverHtml)
      group.addLayer(polygon)
      refs.polygonsByClusterId.set(cluster.id, polygon)
      refs.teamIdByClusterId.set(cluster.id, team.id)

      const hatch = forceLoadedHatch(cluster)
      if (hatch) group.addLayer(hatch)

      const label = clusterLabel(cluster, team, color, onLabelClick)
      if (label) {
        group.addLayer(label)
        refs.labelsByClusterId.set(cluster.id, label)
      }
    }
  }
  return group
}
