# Server Map

The server map is an embedded Leaflet component, not a standalone page. It's used by world restore (chunk/region selection) and chunk prune (read-only with connected preview polygons); restore preview uses the same coordinate/tile primitives. The backend renders tile PNGs on demand; the frontend's job is to display them, run the selection gestures, and let Leaflet/browser tile lifecycle handle image loading and cache eviction.

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
POST /map/initialize    →   202 task acceptance + task status polling
GET /map/tiles/X/Z.png  →                          │
                                                    └──→  ServerMap
                                                          ServerMapTileLayer
```

`useMapStatus.client_jar_present && palette_present && palette_current` gates tile rendering. When false, the page shows the init prompt (`MapInitDialog`) instead of the map; the dialog observes the two-stage initialization task and re-fetches `useMapStatus` on completion.

## Coordinate model

`features/world/map/coords.ts` is the single source of truth for conversions. Pure functions:

- `blockToChunk`, `chunkToRegion`, `chunkToBlock`, etc.
- `regionToChunkKeys(rx, rz)` — set of "cx,cz" strings inside one region
- `chunksToFullyCoveredRegions(chunkSet)` — regions where every chunk is selected
- `chunksToCoveredRegions(chunkSet)` — regions with at least one chunk selected

Mode-switch math (chunk → region) runs through these so both modes always agree on what's selected.

## `ServerMap` component

`features/world/map/ServerMap.tsx` wraps Leaflet with selection gestures and URL-driven view state:

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

`features/world/map/ServerMapTileLayer.ts` extends the shared `ServerTileLayer`, a native Leaflet `L.TileLayer` wrapper. The reasons:

- **Cookie-backed image requests.** Tile URLs are normal same-origin `/api/...png` image URLs, so the browser sends the HttpOnly session cookie and can use its native image cache.
- **Sparse-world short-circuit.** `GET /map/regions?region=...` returns the set of `[x, z]` pairs that actually exist on disk. The layer turns that into a `Set<"x,z">` and returns a blank data URL for anything outside the set, skipping a round trip.
- **Cache-stable URLs.** The layer appends the MCA mtime as `?mt=` for map tiles, so browser cache entries survive panning and zooming but bust when a region file changes.

## Tile caching

Leaflet creates normal `<img>` elements. When panning or zooming removes a tile, Leaflet drops the DOM node and the browser owns memory/cache eviction. Previously visible tiles can be reused from the HTTP image cache when the URL is unchanged.

## Init dialog

`features/world/map/MapInitDialog.tsx` 接收任务 ID，并从 `result.stages` 更新 client 和 palette 进度。重新进入可接上同服务器的活跃初始化任务。组件卸载只中止观察；显式任务取消由后台等待子进程和缓存清理。即使两个阶段均为 100%，弹窗也等待任务终态才允许关闭。读取失败保持阻塞并提示重连；成功后执行原有 onComplete。force=true 的缓存重建语义保持一致。

## Shared feature controller

`features/world/api.ts`, `contracts.ts` and `queries.ts` own layout, dimension labels, map status/manifests, claims and player positions. `useWorldMapController.ts` owns the `dim/mode/z/cx/cz` URL view, world/dimension selection, map initialization, visibility/online filters and cross-dimension pan. Restore/prune controllers build on it without reverse imports from common layers into restore. `layers/claims` and `layers/players` contain the actual implementations rather than feature-specific reexports.
