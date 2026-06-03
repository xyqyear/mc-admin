# World Restore Page

`/server/{id}/world-restore` lets an admin inspect the rendered world map, select chunks or regions, and roll that range, a dimension, or all detected world roots back to a Restic snapshot. The page is the largest interactive surface in the app: map initialization controls, an embedded selection map, FTB-claims and player-location overlays, a tabbed side panel, SSE-driven preview/restore flows, and a history drawer with rollback.

## URL is the source of truth

The page state that survives reload — selected dimension, selection mode, map view — lives in hash params on the URL:

- `#dim=<region_dir_relpath>` — which dimension's region folder is being inspected (e.g. `world/region`, `world/dimensions/minecraft/the_nether/region`)
- `#mode=region|chunk` — region-level or chunk-level selection
- `#z`, `#cx`, `#cz` — Leaflet zoom + center, kept in sync via `onViewChange`

`dim` and `mode` are reactive page state. The view params are read for the
initial map view and then written back with replace-only, non-reactive hash
updates so panning and zooming do not rebuild the page or its Leaflet overlays.

The set of selected chunks is *not* in the URL — it's transient state in `useWorldRestoreSelectionStore`, deliberately cleared on reload (a chunk selection that survived might not match the current world layout).

When no params are present, the page auto-selects the first world root's root dimension when present, otherwise that root's first discovered dimension.

Display labels are fetched separately from `GET /world-restore/dimension-labels`.
The layout response remains path-only; the page translates each dimension's
world-root-relative path through the label mapping and falls back to the raw
path without a leading `dimensions/`.

### Why `#dim` carries the relpath, not separate root + dim

The world root's directory name is the first segment of `region_dir_relpath` (`world/region`, `world/dimensions/minecraft/the_nether/region`, …). That makes the relpath unique across all roots on a server, so the URL doesn't need a separate `?root=` parameter. Multi-world Bukkit/Paper setups stay unambiguous with one string.

## Layout

```
Header
  - map refresh / rendering-prerequisite reload when initialized
  - selection mode tabs
  - dimension picker
  - map help
  - server operation buttons

Map initialization card
  - shown when the client jar or palette is missing/stale
  - opens MapInitDialog

ServerStopGuard
  - shown when the server is running/starting/healthy

Main grid, once the map is initialized
  - ServerMap on the left
  - side card on the right with tabs:
    - Backup & restore
    - Claims, only when FTB claims data is available
    - Player locations
```

`ServerStopGuard` is a pre-flight warning only. The backend re-checks before restoring or rolling back and returns 409 if the server is still running.

The map is gated on mcmap initialization (`client_jar_present`, `palette_present`, `palette_current`). The page can refresh map metadata, force reinitialize rendering prerequisites, and reload map query keys after initialization or restore completion.

## Selection state

`stores/useWorldRestoreSelectionStore.ts`:

- Per-server entries keyed by `serverId`.
- **Not persisted** — selection is transient and intentionally clears on reload.
- `setMode` clears the selection whenever mode changes.
- `setDimension(serverId, dimension)` clears the selection when `dimension` changes — chunks aren't comparable across dimensions, and the dimension relpath uniquely identifies the (root, dim) pair on its own.

`components/world-restore/selectionUtils.ts`:

- `buildSelection(...)` packages the panel's state into the backend's `RestorationSelection` shape (the discriminated union the API expects).
- Region mode stores selected cells as chunk keys too; `buildSelection(..., scope: "regions")` converts the current set to fully-covered region coordinates with `chunksToFullyCoveredRegions`.
- `computeSelectionStats(...)` returns chunk count, covered region count, fully-covered region count.

`components/map/ServerMap.tsx` owns the Leaflet selection UX. Region mode expands selected regions to all 1024 chunk keys. Chunk mode stores exact chunk keys. The on-map toolbar selects pan/add/erase intent for touch and pointer users; desktop also supports Ctrl-drag to add, right-drag to remove, and Escape to clear. A coordinate jump control pans to block coordinates.

## Mode-switch confirmation

Switching from region mode to chunk mode prompts a destructive `useConfirm` warning because chunk restore is experimental. The mode is applied only after confirmation. Any mode change clears the transient selection through `useWorldRestoreSelectionStore.setMode`.

## Side panel actions

`WorldRestoreSelectionPanel` is the Backup & restore tab:

- Manual snapshots are available for the current dimension and the whole world only.
- Restore actions are available for the selected range, current dimension, and whole world.
- Selected-range restore is enabled only when region mode has at least one fully-covered region, or chunk mode has at least one selected chunk.
- Restore buttons in this tab are disabled while the server is not stopped; rollback checks the same condition when clicked. The backend still performs the authoritative 409 check for both flows.

## Snapshot picker (restore flow)

`components/world-restore/SnapshotPicker.tsx` is a right-anchored `<Sheet>` listing eligible snapshots from `useEligibleSnapshots`. Each row always offers Restore. It offers Preview only for REGIONS/CHUNKS selections because the preview map needs an affected-region set.

- **Restore** → destructive confirm via `useConfirm`, then drives the restore SSE through `useEventStream<RestoreEvent>` and renders progress in-place via `<RestoreProgressCard>`.
- **Preview** → opens `<RestorePreviewModal>` with the clicked snapshot id and the latched selection.

## Preview modal

`components/world-restore/RestorePreviewModal.tsx` is a `<Dialog>` containing a mini Leaflet map (`CRS.Simple`) and a custom `<PreviewTileLayer>`:

- Drives `POST /preview` via `useEventStream<PreviewEvent>`.
- Captures `session_id` from the `ready` event.
- Mounts the Leaflet map only after `ready` so tile requests do not race the backend render queue.
- Heartbeats every 30 s (`POST /preview/{session_id}/heartbeat`).
- Fires `DELETE /preview/{session_id}` on close.
- The preview tile layer is a clone of `ServerMapTileLayer` pointed at `/preview/{session_id}/tile/{rx}/{rz}.png`, gated by an `available` set so empty regions don't 404.
- Paints affected region rectangles immediately; for chunk selections up to 5,000 chunks it also paints per-chunk rectangles.
- Shows an in-dialog message instead of a blank canvas when invoked with a dimension/world selection.

## Restoration history drawer

`components/world-restore/RestorationHistoryDrawer.tsx` lists rows from `useRestorations`, auto-refreshing every 5 s. Per-row rollback is gated on:

- `status ∈ {succeeded, interrupted}`
- `safety_snapshot_id` is set
- `safety_snapshot_exists === true`

The "needs rollback" alert highlights `interrupted` rows — the backend's crash-recovery path flips `RUNNING` rows to `INTERRUPTED` on startup so they surface here.

Rollback rows are rollback-able too. Their safety snapshot captures the pre-rollback state, so rolling back a rollback is how the UI undoes that rollback.

Rows with REGIONS/CHUNKS selections also offer Preview, using the row's safety snapshot and stored selection so the admin can inspect what rollback would restore.

## Overlay tabs

FTB claims and player locations share `ServerMap`'s generic overlay hook (`overlays?: ServerMapOverlay[]`) and the same cross-dimension pending-pan path.

- Claims use `useFtbClaims(serverId, mapInitialized)`. When `available` is true, the side panel adds a Claims tab and `useClaimsOverlay` paints cluster polygons/labels for the current dimension. The list can hover-highlight, pan to clusters, select a cluster, or select all of a team's clusters in the current dimension. Details live in `docs/ftb-claims-overlay.md`.
- Player locations use `useWorldRestorePlayerLocations(serverId, mapInitialized)`, `usePlayerMapProfiles`, and `useServerOnlinePlayers`. The Player locations tab can toggle overlay visibility, filter to online players, refresh extracted positions, and click rows to pan or switch dimension. Details live in `docs/player-locations-overlay.md`.

## Shared SSE reducer

`components/world-restore/restoreProgress.ts` exports `applyRestoreEvent`, a reducer that turns `RestoreEvent` SSE payloads into UI state. It's used by both the snapshot picker (forward restore) and the history drawer (rollback) so the progress UI stays consistent.

## SSE consumer

All three world-restore flows — `POST /preview`, `POST /restore`, `POST /restorations/{id}/rollback` — go through `hooks/useEventStream.ts`. It handles fetch + `AbortController` + `\n\n` block parsing, same-origin cookies, CSRF header injection, and body fingerprinting via `JSON.stringify` so caller-side inline objects don't restart the stream every render.

## Routing

```tsx
<Route path=":id/world-restore" element={<ServerWorldRestore />} />
```

Lazy-loaded in `App.tsx`. Sidebar entry: `Map` icon under each server's submenu.
