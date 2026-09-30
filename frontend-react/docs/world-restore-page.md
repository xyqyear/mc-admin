# World Restore Page

`/server/{id}/world-restore` lets an admin inspect the rendered world map, select chunks or regions, and roll that range, a dimension, or all detected world roots back to a Restic snapshot. The page is the largest interactive surface in the app: map initialization controls, an embedded selection map, FTB-claims and player-location overlays, a tabbed side panel, task-driven recovery and map previews, and a history drawer with rollback.

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

Main area
  - ServerMap on the left when initialized, or a spinner while layout loads
  - WorldRestoreSidebar remains mounted independently of map/layout readiness
    - Backup & restore is always available
    - Tab controls appear when the map is initialized
      - Claims, only when FTB claims data is available
      - Player locations
```

`ServerStopGuard` is a pre-flight warning only. The backend re-checks before restoring or rolling back and returns 409 if the server is still running.

The map is gated on mcmap initialization (`client_jar_present`, `palette_present`, `palette_current`). The page can refresh map metadata, force reinitialize rendering prerequisites, and reload map query keys after initialization or restore completion.

`WorldRestoreSidebar` keeps the backup panel in the same mounted tab panel while map status and layout resolve independently. Opening snapshot selection or recovery history before initialization finishes preserves that drawer and its active request when the layer tabs appear. The backup panel remains mounted when another tab is selected; unavailable map/layer tabs fall back to Backup & restore.

## Selection state

`features/world/restore/selectionStore.ts`:

- Per-server entries keyed by `serverId`.
- **Not persisted** — selection is transient and intentionally clears on reload.
- `setMode` clears the selection whenever mode changes.
- `setDimension(serverId, dimension)` clears the selection when `dimension` changes — chunks aren't comparable across dimensions, and the dimension relpath uniquely identifies the (root, dim) pair on its own.

`features/world/restore/components/selectionUtils.ts`:

- `buildSelection(...)` packages the panel's state into the backend's `RestorationSelection` shape (the discriminated union the API expects).
- Region mode stores selected cells as chunk keys too; `buildSelection(..., scope: "regions")` converts the current set to fully-covered region coordinates with `chunksToFullyCoveredRegions`.
- `computeSelectionStats(...)` returns chunk count, covered region count, fully-covered region count.

`features/world/map/ServerMap.tsx` owns the Leaflet selection UX. Region mode expands selected regions to all 1024 chunk keys. Chunk mode stores exact chunk keys. The on-map toolbar selects pan/add/erase intent for touch and pointer users; desktop also supports Ctrl-drag to add, right-drag to remove, and Escape to clear. A coordinate jump control pans to block coordinates.

## Mode-switch confirmation

Switching from region mode to chunk mode prompts a destructive `useConfirm` warning because chunk restore is experimental. The mode is applied only after confirmation. Any mode change clears the transient selection through `useWorldRestoreSelectionStore.setMode`.

## Side panel actions

`WorldRestoreSelectionPanel` is the Backup & restore tab:

- Manual snapshots are available for the current dimension and the whole world only.
- Restore actions are available for the selected range, current dimension, and whole world.
- Selected-range restore is enabled only when region mode has at least one fully-covered region, or chunk mode has at least one selected chunk.
- Restore buttons in this tab are disabled while the server is not stopped; rollback checks the same condition when clicked. The backend still performs the authoritative 409 check for both flows.

Shared server operation buttons consume `useServerMaintenance` through the server API/query layers. The maintenance endpoint prevents startup during a destructive operation even after navigating or refreshing.

## Snapshot picker (restore flow)

`features/world/restore/components/SnapshotPicker.tsx` is a right-anchored `<Sheet>` listing eligible snapshots from `useEligibleSnapshots`. Each row always offers Restore. It offers Preview only for REGIONS/CHUNKS selections because the preview map needs an affected-region set.

- **Restore** → destructive confirm via `useConfirm`, then submits an immutable world scope through `features/backups/useSnapshotOperation` and observes its task and renders progress in-place via `<RestoreProgressCard>`.
- **Preview** → opens `<RestorePreviewModal>` with the clicked snapshot id and the latched selection.

## Preview modal

`features/world/restore/components/RestorePreviewModal.tsx` is a `<Dialog>` containing a mini Leaflet map (`CRS.Simple`) and a custom `<PreviewTileLayer>`:

- 使用 backups 的 `useSnapshotPreview` 提交共用预览任务，显示真实阶段和可用的进度。
- 仅在任务成功、获得 `preview_id` 后挂载地图；任务读取失败保持观察和重连提示。
- 每 30 秒发送 `/snapshots/previews/{id}/heartbeat`。404/409/410 会移除就绪地图并提示重新准备。
- 准备中关闭或卸载只停止观察；“停止准备”显式取消任务。就绪后关闭、替换或卸载提交清理任务。
- 地图请求 `/snapshots/previews/{id}/tiles/{rx}/{rz}.png`，沿用已有瓦片组件及区域集合。
- “按此预览恢复”在确认后携带预览 ID，后端在写入前复核绑定；直接恢复仍可使用。
- Paints affected region rectangles immediately; for chunk selections up to 5,000 chunks it also paints per-chunk rectangles.
- Shows an in-dialog message instead of a blank canvas when invoked with a dimension/world selection.

## Restoration history drawer

`features/world/restore/components/RestorationHistoryDrawer.tsx` composes `features/backups/ui/RestorationHistoryDialog`, with unified paginated recovery history and world preview actions. Per-row rollback is gated on:

- `status ∈ {succeeded, failed, interrupted}`
- `safety_snapshot_id` is set
- `safety_snapshot_exists === true`
- server stopped and no `binding_issue` (old or uncertain server-generation bindings remain visible with an explanation)

回滚按统一历史的 `rollback_available` 与原因提示控制，同时要求世界服务器停服。回滚会覆盖选中范围内后来的修改，并先创建新的安全快照。当前任务未结束或任务读取失败时保持阻塞；浏览器断线不会中断后台恢复。

`useWorldRestoreController` owns selection and mode confirmation. `features/backups/useSnapshotPreview` owns task observation, heartbeat and cleanup submission for both presentation types. The application operation observer refreshes file/world/history resources after terminal outcomes independently of the initiating page.

## Routing

```tsx
<Route path=":id/world-restore" element={<ServerWorldRestore />} />
```

Lazy-loaded in `App.tsx`. Sidebar entry: `Map` icon under each server's submenu.
