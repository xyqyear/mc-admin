# World Restore Page

`/server/{id}/world-restore` lets an admin pick a region of the world (chunk-level, region-level, dimension-level, or whole-world) and roll it back to a Restic snapshot. The page is the largest interactive surface in the app: an embedded selection map, a side panel for actions, two SSE-driven flows (preview + restore), and a history drawer with one-click rollback.

## URL is the source of truth

The page state that survives reload — selected dimension, selection mode, map view — lives in the URL:

- `?dim=<region_dir_relpath>` — which dimension's region folder is being inspected (e.g. `world/region`, `world/dimensions/minecraft/the_nether/region`)
- `?mode=region|chunk` — region-level or chunk-level selection
- `?z`, `?cx`, `?cz` — Leaflet zoom + center, kept in sync via `onViewChange`

The set of selected chunks is *not* in the URL — it's transient state in `useWorldRestoreSelectionStore`, deliberately cleared on reload (a chunk selection that survived might not match the current world layout).

When no params are present, the page auto-selects the first world root's Overworld dimension.

### Why `?dim` carries the relpath, not separate root + dim

The world root's directory name is the first segment of `region_dir_relpath` (`world/region`, `world/dimensions/minecraft/the_nether/region`, …). That makes the relpath unique across all roots on a server, so the URL doesn't need a separate `?root=` parameter. Multi-world Bukkit/Paper setups stay unambiguous with one string.

## Layout

```
┌───────────────────────────────────────────────────────────┐
│ Header: server controls, map help, history drawer trigger │
├──────────────────────────┬────────────────────────────────┤
│ ServerStopGuard banner (when running)                     │
├──────────────────────────┼────────────────────────────────┤
│                          │ WorldRestoreSelectionPanel     │
│       ServerMap          │ - dimension picker             │
│  (embedded selection)    │ - mode tabs (区域/区块)         │
│                          │ - selection summary            │
│                          │ - 3 × create-snapshot buttons  │
│                          │ - 3 × restore buttons          │
│                          │ - history drawer trigger       │
├──────────────────────────┴────────────────────────────────┤
│ ServerStartHint (post-restore nudge)                      │
└───────────────────────────────────────────────────────────┘
```

`ServerStopGuard` shows a one-click confirm-and-stop banner when the server isn't stopped. The backend re-checks inside the lock and returns 409 if it's still running, but the pre-flight nudge is friendlier.

## Selection state

`stores/useWorldRestoreSelectionStore.ts`:

- Per-server entries keyed by `serverId`.
- **Not persisted** — selection is transient and intentionally clears on reload.
- `setMode` does the chunk → region collapse via `chunksToFullyCoveredRegions`. Region → chunk is a no-op on the data (the underlying set is already chunks).
- `setDimension(serverId, dimension)` clears the selection when `dimension` changes — chunks aren't comparable across dimensions, and the dimension relpath uniquely identifies the (root, dim) pair on its own.

`components/world-restore/selectionUtils.ts`:

- `buildSelection(...)` packages the panel's state into the backend's `RestorationSelection` shape (the discriminated union the API expects).
- `computeSelectionStats(...)` returns chunk count, covered region count, fully-covered region count.

## Mode-switch confirmation

Switching from region mode to chunk mode prompts a destructive `useConfirm` warning because chunk restore is experimental. The mode is applied only after confirmation. Any mode change clears the transient selection in `useWorldRestoreSelectionStore.setMode`.

## Snapshot picker (restore flow)

`components/world-restore/SnapshotPicker.tsx` is a right-anchored `<Sheet>` listing eligible snapshots from `useEligibleSnapshots`. Each row offers two actions:

- **Preview** → opens `<RestorePreviewModal>` (see below).
- **Restore** → destructive confirm via `useConfirm`, then drives the restore SSE through `useEventStream<RestoreEvent>` and renders progress in-place via `<RestoreProgressCard>`.

## Preview modal

`components/world-restore/RestorePreviewModal.tsx` is a `<Dialog>` containing a mini Leaflet map (`CRS.Simple`) and a custom `<PreviewTileLayer>`:

- Drives `POST /preview` via `useEventStream<PreviewEvent>`.
- Captures `session_id` from the `ready` event.
- Heartbeats every 30 s (`POST /preview/{session_id}/heartbeat`).
- Fires `DELETE /preview/{session_id}` on close.
- The preview tile layer is a clone of `ServerMapTileLayer` pointed at `/preview/{session_id}/tile/{rx}/{rz}.png`, gated by an `available` set so empty regions don't 404.

## Restoration history drawer

`components/world-restore/RestorationHistoryDrawer.tsx` lists rows from `useRestorations`, auto-refreshing every 5 s. Per-row rollback is gated on:

- `status ∈ {succeeded, interrupted}`
- `safety_snapshot_id` is set
- `is_rollback === false` (don't rollback a rollback)

The "needs rollback" alert highlights `interrupted` rows — the backend's crash-recovery path flips `RUNNING` rows to `INTERRUPTED` on startup so they surface here.

## Shared SSE reducer

`components/world-restore/restoreProgress.ts` exports `applyRestoreEvent`, a reducer that turns `RestoreEvent` SSE payloads into UI state. It's used by both the snapshot picker (forward restore) and the history drawer (rollback) so the progress UI stays consistent.

## SSE consumer

All three world-restore flows — `POST /preview`, `POST /restore`, `POST /restorations/{id}/rollback` — go through `hooks/useEventStream.ts`. It handles fetch + `AbortController` + `\n\n` block parsing, injects the JWT from `useTokenStore`, and fingerprints the body via `JSON.stringify` so caller-side inline objects don't restart the stream every render.

## Routing

```tsx
<Route path=":id/world-restore" element={<ServerWorldRestore />} />
```

Lazy-loaded in `App.tsx`. Sidebar entry: `Map` icon labeled "地图回档" under each server's submenu.
