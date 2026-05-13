import L from 'leaflet'

import { BLOCKS_PER_CHUNK } from '@/components/map/coords'
import type {
  FtbClusterEntry,
  FtbTeamEntry,
} from '@/types/FtbClaims'

import { computeBoundaryRings, type Ring } from './computeBoundary'
import { pickLabelEdge } from './pickLabelEdge'
import type { TeamColor } from './teamColors'
import { teamColors } from './teamColors'

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
  // Longest ring leads as the outer; later rings become holes.
  rings.sort((a, b) => b.length - a.length)
  const latLngRings = rings.map(ringToLatLngs)
  const polygon = L.polygon(latLngRings as L.LatLngExpression[][], {
    color: color.stroke,
    weight: 1.5,
    opacity: 0.9,
    fillColor: color.stroke,
    fillOpacity: 0.2,
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

// Chunk-relative (z - x) offsets; 0 keeps diagonals continuous across chunk corners.
const FORCE_LOAD_HATCH_OFFSETS = [-12, -8, -4, 0, 4, 8, 12] as const

function forceLoadedOverlay(
  cluster: FtbClusterEntry,
): L.Layer | null {
  if (cluster.force_loaded.length === 0) return null
  const renderer = L.canvas({ padding: 0.1 })
  const layers: L.Layer[] = []
  for (const [cx, cz] of cluster.force_loaded) {
    const x0 = cx * BLOCKS_PER_CHUNK
    const z0 = cz * BLOCKS_PER_CHUNK
    const x1 = x0 + BLOCKS_PER_CHUNK
    const z1 = z0 + BLOCKS_PER_CHUNK
    const ring: L.LatLngExpression[] = [
      blockToLatLng(x0, z0),
      blockToLatLng(x1, z0),
      blockToLatLng(x1, z1),
      blockToLatLng(x0, z1),
    ]
    layers.push(
      L.polygon(ring, {
        renderer,
        stroke: false,
        fillColor: '#ef4444',
        fillOpacity: 0.2,
        interactive: false,
      }),
    )
    for (const k of FORCE_LOAD_HATCH_OFFSETS) {
      let sx: number, sz: number, ex: number, ez: number
      if (k >= 0) {
        sx = x0
        sz = z0 + k
        ex = x1 - k
        ez = z1
      } else {
        sx = x0 - k
        sz = z0
        ex = x1
        ez = z1 + k
      }
      layers.push(
        L.polyline([blockToLatLng(sx, sz), blockToLatLng(ex, ez)], {
          renderer,
          color: '#ef4444',
          weight: 1,
          opacity: 0.2,
          interactive: false,
        }),
      )
    }
  }
  return L.layerGroup(layers)
}

function clusterLabel(
  cluster: FtbClusterEntry,
  team: FtbTeamEntry,
  color: TeamColor,
  onClick: (clusterId: string, anchorEl: HTMLElement) => void,
): L.Marker | null {
  const edge = pickLabelEdge(cluster.chunks)
  if (!edge) return null
  // Offset outward so the pill doesn't overlap the polygon stroke.
  const outwardOffsetBlocks = edge.side === 'top' ? -2 : 2
  const anchorBz = edge.bz + outwardOffsetBlocks
  const labelText = escapeHtml(team.display_name)
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
    // Stop propagation so the click doesn't reach the map's pan/select handlers.
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

      const forceOverlay = forceLoadedOverlay(cluster)
      if (forceOverlay) group.addLayer(forceOverlay)

      const label = clusterLabel(cluster, team, color, onLabelClick)
      if (label) {
        group.addLayer(label)
        refs.labelsByClusterId.set(cluster.id, label)
      }
    }
  }
  return group
}
