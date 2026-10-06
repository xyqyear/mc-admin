# Server Map

The server map is an embedded Leaflet component used by world restore for chunk/region selection and by chunk prune for read-only preview polygons. Restore preview uses the same coordinate/tile primitives. The backend renders tile PNGs on demand; the frontend displays them and handles selection gestures, while Leaflet and the browser manage image loading and cache eviction.

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

`features/world/map/coords.ts` owns block/chunk/region conversions. One chunk spans 16 blocks and one region spans 32 chunks or 512 blocks. Division uses `Math.floor`, including for negative coordinates: block X/Z `-1` belongs to chunk `-1`, and chunk `-1` belongs to region `-1`. Pure functions include:

- `blockToChunk({ bx, bz })`, `chunkToRegion({ cx, cz })`, `chunkToBlock({ cx, cz })`
- `regionToChunkKeys({ rx, rz })` — array of "cx,cz" strings inside one region
- `chunksToFullyCoveredRegions(chunkSet)` — regions where every chunk is selected
- `chunksToCoveredRegions(chunkSet)` — regions with at least one chunk selected

Selection and mode-switch math use these helpers. `mapConfig.ts` owns `blockToLatLng(bx, bz)`, which returns Leaflet coordinates `[-bz, bx]`. Claims convert chunk units to blocks before calling it; prune polygons use 16 blocks per chunk or 512 per region. Player markers and both same-dimension and cross-dimension pan use the same signed coordinates.

## `ServerMap` component

`features/world/map/ServerMap.tsx` wraps Leaflet with selection gestures and URL-driven view state:

- Props: `serverId`, `regionPath`, `regions` (manifest map from "x,z" to MCA mtime), `initialView` / `onViewChange` (URL sync), `selectionMode` (`'none' | 'chunk' | 'region'`), controlled `selection` + `onSelectionChange`, `overlays`.
- Gestures:
  - Plain left-drag: pan
  - **Ctrl + click**: add the chunk/region under the cursor
  - **Ctrl + drag**: rectangle add
  - Right-click: remove
  - **Right-button + drag**: subtract rectangle
  - Escape (with the canvas focused): clear selection
- Selection paint uses per-region rectangles past 5,000 chunks to bound Leaflet redraw work.

## `ServerMapTileLayer`

`features/world/map/ServerMapTileLayer.ts` extends the shared `ServerTileLayer`, a native Leaflet `L.TileLayer` wrapper. The reasons:

- **Cookie-backed image requests.** Tile URLs are normal same-origin `/api/...png` image URLs, so the browser sends the HttpOnly session cookie and can use its native image cache.
- **Sparse-world short-circuit.** `GET /map/regions?region=...` returns the set of `[x, z]` pairs that actually exist on disk. The layer turns that into a `Set<"x,z">` and returns a blank data URL for anything outside the set, skipping a round trip.
- **Cache-stable URLs.** The layer includes MCA mtime and the newest relevant server/global operation revision in tile URLs. Browser cache entries survive panning and zooming, while recovery refreshes them even when only an MCC changed or the restored MCA has the same mtime. Read-only previews and backups do not advance the revision.

## Tile caching

Leaflet creates normal `<img>` elements. When panning or zooming removes a tile, Leaflet drops the DOM node and the browser owns memory/cache eviction. Previously visible tiles can be reused from the HTTP image cache when the URL is unchanged.

## Init dialog

`features/world/map/MapInitDialog.tsx` 接收任务 ID，并从 `result.stages` 更新 client 和 palette 进度。重新进入可接上同服务器的活跃初始化任务。组件卸载只中止观察；显式任务取消由后台等待子进程和缓存清理。即使两个阶段均为 100%，弹窗也等待任务终态才允许关闭。读取失败保持阻塞并提示重连；成功后执行原有 onComplete。force=true 的缓存重建语义保持一致。

## Shared feature controller

`features/world/api.ts`, `contracts.ts` and `queries.ts` own layout, dimension labels, map status/manifests, claims and player positions. `useWorldMapController.ts` returns four concrete groups:

- `server`: status, server information and the stopped-state projection.
- `map`: layout, `dim/mode/z/cx/cz` URL view, dimension selection, initialization, region manifest and combined overlays.
- `claims`: teams, visibility, popover/highlighting, refresh and cluster positioning.
- `players`: saved locations, profile cache/stream, normalized online identities, visibility/filtering, refresh and row positioning.

Both screens compose `WorldDimensionSelect`, `WorldMapInitialization` and `WorldPlayerLocationList`. These components bind specific presentation inputs; restore/prune controllers retain their own selection, confirmation, preview and apply lifecycles. Restore displays map-status errors and keeps its backup sidebar mounted independently of map readiness. Prune retains its read-only claims list and its own preview guards. `layers/claims` and `layers/players` contain the actual layer implementations and do not depend on restore.

The common controller owns the pending cross-dimension target. A row click stores the target relpath and block position, changes `dim` and clears the old view coordinates. Only an overlay render for the matching dimension applies the pan, before attaching layers. The pending target is cleared in a microtask to retain StrictMode render ordering; later renders do not replay it. The initialized player overlay supplies this render callback even when its markers are hidden.
