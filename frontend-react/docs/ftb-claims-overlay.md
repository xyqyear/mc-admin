# FTB Claims Overlay (`components/world-restore/claims/`)

A Leaflet overlay on the world-restore page that paints each FTB team's
claimed chunks as a coloured polygon, with diagonal red hatch over
force-loaded chunks and a clickable label pill at the top/bottom edge of
each cluster. The side panel mirrors the same data as a two-level
team→cluster list so admins can hover-highlight, click-pan, or
select-by-cluster without ever clicking the map polygons themselves.

## URL state

The overlay is opt-in: `?claims=1` on the world-restore page enables it.
Without the flag, the query (`useFtbClaims`) stays disabled and the overlay
isn't built. The "领地" button in the page header toggles the flag.

When the overlay is active, the side panel widens from 180 px to 270 px to
hold the team list. The toggle is replace-history, not push, so back-button
navigation isn't polluted.

## Data flow

```
useFtbClaims(serverId)  ──►  ClaimsResponse{ teams, dimensions, ... }
                                  │
                                  ▼
                       useClaimsOverlay({ teams, currentDim, enabled })
                                  │
            ┌─────────────────────┼─────────────────────────────┐
            ▼                     ▼                             ▼
       overlays[]             popover                  highlightClusters / panToBlock
     (ServerMap prop)    (ClusterPopover)              (imperative — used by side panel)
```

`useClaimsOverlay` owns:

- A `ClaimsLayerRefs` ref that the layer builder fills with per-cluster
  `L.Polygon` and `L.Marker` handles. Hover-highlights from the side panel
  call `setStyle()` directly on those handles — no Leaflet layer rebuild.
- A `mapRef` captured the first time the overlay renders, used by `panToBlock`
  to recentre the map without re-creating the overlay.
- Controlled popover state — opens when a label is clicked, anchored at the
  clicked label's DOM element.

## Layer composition

`buildClaimsLayer` walks every team's cluster set, filters to the current
dimension (`region_dir_relpath`), and emits:

- One `L.polygon` per cluster, with outer ring (and holes when present)
  computed by `computeBoundary.ts`'s edge walk. Stroke + 22% fill in the
  team's hashed palette colour. `bindTooltip` shows team name + counts on
  hover.
- One `L.canvas`-rendered layer of `L.polyline` diagonal pairs per
  force-loaded chunk — three NW→SE plus three NE→SW lines per chunk in red.
  Reads as a hatched fill at every zoom level without needing an SVG pattern.
- One `L.marker` per cluster carrying a `L.divIcon` label pill at the chosen
  edge (`pickLabelEdge.ts`: longest contiguous top-edge run, fallback to
  longest bottom-edge run). The pill is the only click target — polygons
  intentionally have no click handlers per design.

The polygon shapes are intentionally **non-interactive for click** — the
plan: only labels open the popover, and side-panel rows drive selection.
Hover tooltips remain on the polygon for discoverability.

## Per-team colour

`teamColors(teamId, type)` hashes `teamId` (FNV-1a) into a 14-hue palette and
emits stroke / fill / fillStrong / text strings. Server-type teams collapse
to neutral grey so they don't compete visually with player teams; "unknown"
type lowers saturation. Stable across reloads.

## Selection mapping

`claimSelection.ts` translates a cluster (or a whole team's clusters in the
current dim) into a `Set<ChunkKey>` consistent with the current
`WorldRestoreSelectionMode`:

- **Chunk mode** — adds `cluster.chunks` directly.
- **Region mode** — expands every region in `cluster.regions` to all 1024
  chunks. `chunksToFullyCoveredRegions` then picks the cluster's regions up
  as fully covered when building the restore request.

`useWorldRestoreSelectionStore.addToSelection(serverId, keys)` unions the
new keys into the existing selection — important, so a user can stack
"select team A + cluster from team B" into one restore call.

A cluster row's "已选" badge is derived live from
`isClusterFullySelected(cluster, selection, mode)` — same logic both modes.

## Cross-dim handling

Clusters whose `region_dir_relpath !== currentDim` still appear in the team
list under their team's expand panel, but greyed out. Clicking such a row
calls `handleDimensionChange(cluster.region_dir_relpath)`, which switches
dim via URL state; that flips the store and wipes the selection (matching
the existing dim-picker UX). The cross-dim cluster doesn't get a Select
button — switching dim takes a click, then re-selecting takes another.

## File map

```
components/world-restore/claims/
├── ClaimOverlayLayer.ts   # build L.LayerGroup from teams + currentDim
├── ClusterPopover.tsx     # base-ui Popover anchored to clicked label
├── TeamClusterList.tsx    # two-level side-panel list, search + sort
├── claimSelection.ts      # cluster|team → chunk-key sets, fully-selected
├── claims.css             # styles for the divIcon label pill
├── computeBoundary.ts     # chunks → polygon rings (edge walk)
├── pickLabelEdge.ts       # chunks → top/bottom edge midpoint for the label
├── teamColors.ts          # stable hash → HSL palette, type variants
└── useClaimsOverlay.ts    # owns refs, popover state, imperative methods
```

The page glue in `pages/server/servers/ServerWorldRestore.tsx` is small: a
button to toggle `?claims=1`, an extra `<Card>` around `<TeamClusterList>`
in the side column, and the wired-up `<ClusterPopover>` at the bottom of the
JSX tree. Everything else flows through `useClaimsOverlay` and the existing
selection store.

## Performance

A typical modded world has 5–15 teams and a few hundred to ~2k claimed
chunks. The boundary walk is O(chunks), polygon rendering is one SVG path
per cluster (Leaflet's default SVG renderer), and the divIcon label
markers number at most one per cluster — well under what Leaflet copes with
fluently. Force-loaded hatches use the canvas renderer to keep many small
polylines cheap.

The overlay is rebuilt only when `teams` or `currentDim` change (not on
hover). Hover effects mutate polygon styles imperatively, which is why
`useClaimsOverlay` keeps refs to every polygon by cluster id.
