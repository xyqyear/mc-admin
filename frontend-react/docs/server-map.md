# Server Map

The server map is an embedded Leaflet component, not a standalone page. It's used by the world-restore page (chunk/region selection) and by the world-restore preview modal (read-only). The backend renders tile PNGs on demand; the frontend's job is to display them, run the selection gestures, and aggressively cancel work that's no longer needed.

## Why Leaflet with `CRS.Simple`

A Minecraft world is a 2D plane indexed by integer block coordinates, not a geographic surface. `CRS.Simple` strips Leaflet of its lat/lon projection and gives us a flat coordinate space where one map unit equals one world block. Every Leaflet feature (zoom, panning, tile loading, layer composition) still works.

## Data flow

```
backend                     hooks                         component
───────                     ─────                         ─────────
GET /map/status         →   useMapStatus
GET /world-restore/layout
GET /world-restore/dimension-labels
                         →   useWorldLayout / useWorldDimensionLabels
GET /map/regions        →   useMapRegions          ┐
POST /map/initialize    →   (SSE via useEventStream)
GET /map/tiles/X/Z.png  →                          │
                                                    └──→  ServerMap
                                                          ServerMapTileLayer
```

`useMapStatus.client_jar_present && palette_present && palette_current` gates tile rendering. When false, the page shows the init prompt (`MapInitDialog`) instead of the map; the dialog drives the two-stage initialize SSE and re-fetches `useMapStatus` on completion.

## Coordinate model

`components/map/coords.ts` is the single source of truth for conversions. Pure functions:

- `blockToChunk`, `chunkToRegion`, `chunkToBlock`, etc.
- `regionToChunkKeys(rx, rz)` — set of "cx,cz" strings inside one region
- `chunksToFullyCoveredRegions(chunkSet)` — regions where every chunk is selected
- `chunksToCoveredRegions(chunkSet)` — regions with at least one chunk selected

Mode-switch math (chunk → region) runs through these so both modes always agree on what's selected.

## `ServerMap` component

`components/map/ServerMap.tsx` wraps Leaflet with selection gestures and URL-driven view state:

- Props: `regionPath`, `regions` (manifest set), `initialView` / `onViewChange` (URL sync), `selectionMode` (`'none' | 'chunk' | 'region'`), controlled `selection` + `onSelectionChange`, `overlays`.
- Gestures:
  - Plain left-drag: pan
  - **Ctrl + click**: add the chunk/region under the cursor
  - **Ctrl + drag**: rectangle add
  - Right-click: remove
  - **Right-button + drag**: subtract rectangle
  - Escape (with the canvas focused): clear selection
- Selection paint degrades to per-region rectangles past 5,000 chunks. Drawing 5,000 individual chunk rectangles tanked Leaflet's redraw loop on lower-end hardware.

## `ServerMapTileLayer`

`components/map/ServerMapTileLayer.ts` is a custom `L.GridLayer` rather than a stock `L.TileLayer`. The reasons:

- **Authed fetches.** Tile URLs require the JWT, which lives in `useTokenStore`. Routing through the project's `axios` instance picks up the auth interceptor automatically; a stock `<img>` tag bypasses Axios.
- **Sparse-world short-circuit.** `GET /map/regions?region=...` returns the set of `[x, z]` pairs that actually exist on disk. The layer turns that into a `Set<"x,z">` and serves a blank tile for anything outside the set, skipping a round trip.
- **Cancellation and tile resource cleanup on unload.** When Leaflet calls `_removeTile` (zoom, pan, viewport change), the layer aborts the in-flight `AbortController`, revokes any pending blob URL, and clears the image source. Axios cancels, FastAPI raises `CancelledError`, the backend queue drops the consumer, and if it was the last one, the mcmap subprocess gets SIGTERM. End-to-end cancellation lets the backend reclaim render capacity instantly.

## Cancellation cascade

```
leaflet _removeTile
  → AbortController.abort()
  → axios cancels
  → backend FastAPI handler raises CancelledError
  → ServerRenderQueue refcount drop
  → if last consumer for the running batch: SIGTERM mcmap subprocess
```

This is load-bearing. Without it, browsing across a world would stack render jobs faster than they could complete.

## Init dialog

`components/dialogs/MapInitDialog.tsx` is the entry-point UI for the two-stage `POST /map/initialize` SSE. It uses a flow-local fetch + `\n\n` block parser so the dialog can own abort/close behavior. Stages are `client` (download client jar) and `palette` (build block-color palette); both stream progress events. The dialog accepts `force=true` for the destructive toolbar action, which calls `POST /map/initialize?force=true` so the backend deletes `client.jar`, `palette.json`, and `palette.hash` before redownloading/regenerating prerequisites.
