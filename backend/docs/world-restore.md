# World Restore (`app.world`)

Selective rollback of Minecraft world data at four granularities — chunk, region, dimension, or whole world. Built on Restic for snapshot storage and the `mcmap replace-chunks` / `remove-chunks` subcommands for sub-region splicing. Restoration saves safety evidence before writes; rollback availability depends on retained snapshot references and server identity.

`snapshots/commands.py` owns common task acceptance, recovery and rollback. `selection.py` plans confined paths
and resource scopes; `scope_execution.py` merges selected chunks with mcmap; `snapshots/file_restore.py` applies file replacements; `snapshots/restoration_store.py` owns short history transactions; `finalization.py`
invalidates caches; `snapshots/previews.py` owns preview tasks and binding; `preview_rendering.py` builds map copies using the
reference-counted manager in `snapshots/preview_sessions.py`. `artifacts.py` ties feature scratch
directories to operation recovery evidence. Adapters do not discover the
current server again after an operation has captured its `ServerRef`.

## Why selective rollback

Whole-world restores are blunt: a player who griefs one chunk forces the admin to choose between losing everyone else's progress since the last backup or accepting the damage. Chunk- and region-level restores invert that tradeoff — surgical undo of the affected area, the rest of the world untouched.

## Four scopes

`RestorationSelection` has four shapes, distinguished by `type`:

- **WORLD** — restic restore against *every* valid world root on the server. Bukkit/Paper multi-world setups are covered in one operation; all dimensions of every root are included. Carries no `region_dir_relpath`.
- **DIMENSION** — restic restore scoped to a single `region/`+`entities/`+`poi/` triple. The dimension is identified by `region_dir_relpath` (data-relative, e.g. `world/region`, `world/DIM88/region`, `world/dimensions/minecraft/the_nether/region`, `world_creative/DIM-1/region`).
- **REGIONS** — restic restore filtered to specific `r.X.Z.mca` files inside the dimension named by `region_dir_relpath`. Includes the matching `entities/` and `poi/` sidecars and `c.<absX>.<absZ>.mcc` overflow chunks for the affected region grid, so partial regions never desync.
- **CHUNKS** — stage source MCAs from the snapshot into a tempdir, then run `mcmap replace-chunks` to splice the selected chunks into the live MCAs (or `remove-chunks` for chunks the snapshot didn't have). Same restic include-path expansion as REGIONS for entities/poi.

### Why `region_dir_relpath` is enough

The world root directory's name is the first segment of the relpath (`world/region`, `world_nether/region`, …). That makes the relpath unique across all roots on a server, so chunk/region/dimension scopes don't need a separate "root" parameter. Multi-world Bukkit/Paper setups stay unambiguous with a single string.

## Layout discovery

`app.world.layout` first identifies world roots from `server.properties`
`level-name` plus immediate `data/` children that contain `level.dat`, so
Bukkit/Paper multi-world folders stay separate roots. The primary root is
returned first; other roots are sorted by name.

Within each root, discovery looks for real terrain `region/` directories
rather than branching by dimension family. The backend requires `fd`: it finds
directories named `region` up to the configured world-layout depth, then keeps
only those containing valid `r.X.Z.mca` files. This covers root
overworlds, legacy/custom root-child dimensions such as `DIM88`, modern
`dimensions/<namespace>/<name>` dimensions, and deeper FTB team dimensions
such as `dimensions/ftbteamdimensions/team/<uuid>`. If `fd` is missing or
fails, layout discovery fails with `WorldLayoutDiscoveryError`.

Layout discovery is path-only; `WorldRoot` and `DimensionInfo` do not carry
display labels. `GET /dimension-labels` returns `config.world.dimension_labels`,
keyed by world-root-relative dimension path. Defaults cover the root dimension
as Overworld, `DIM-1` as Nether, `DIM1` as End, and vanilla
`dimensions/minecraft/*` directories. Frontend code translates discovered paths
with that mapping and falls back to the world-root-relative path without a
leading `dimensions/`.

`discover_world_root_paths` performs the cheap root-path portion of discovery
without `fd`; mcmap extractors use it before resolving only the dimension
folders present in mcmap output. `discover_world_roots` performs the full
dimension scan for endpoints and restore flows that need the complete layout.

## Safety snapshots

[Common restoration](snapshot-restoration.md) owns task acceptance, safety snapshots,
generation-bound history and rollback. World creation, candidate queries, previews,
safety snapshots, restoration and rollback ignore current, source and historical
exclusions. Terrain, entities, POI and MCC data follow the full selected scope;
chunk operations preserve unselected chunks. Data absent inside a covered source
root is restored as absent, including data omitted by a backup exclusion.

世界布局发现保留服务器数据目录内链接根的逻辑名称，搜索实际根后将维度路径映射回该名称；数据目录外的链接根不进入布局。路径边界、资源冲突和执行前链接变化检查仍使用真实路径。Restic 暂存文件按真实路径落地，世界适配将文件级链接的 MCA/MCC 副本整理到同一逻辑区域目录，保证 mcmap 与地图预览按文件名找到对应溢出数据。

区块目标的 MCA 或选中 MCC 通过文件级链接指向其它目录或名称时，先复制在线区域及溢出数据到任务拥有的工作目录，在副本中合并，再发布允许的 MCC 与 MCA 到冻结的真实目标。所有发布目标在第一次写入前一起重验，每次发布再确认当前边界；同目录临时文件经原子替换发布并有限清理，逻辑链接节点保留。合并失败不发布在线数据；发布中失败可能留下部分允许结果，安全快照与恢复记录提供回滚。未选中的溢出数据不发布。普通目录链接的区域直接使用真实目标目录，预览合并始终只修改会话副本。

手动维度快照以 `mc-admin-absence-v1:` Restic 标签保存当时缺失的附属目录。标签是有界、版本化的路径证据。来源未覆盖选中范围且没有缺失证据时拒绝恢复；覆盖父目录但其中缺少选中文件时按源缺失处理。

History retains the planned world selection and logical-to-execution mapping,
so rollback does not require the current world to contain MCAs. Shared absence
evidence and empty-ancestor cleanup follow the common restoration contract.

保留旧 `selection_json` 中的 `world_roots`、`absent_directories` 和 `absent_sidecar_dirs` 解码。旧世界记录缺少根目录时，只从安全快照中推导数据目录内的严格子路径；拒绝整个 data 根目录、外部路径或符号链接逃逸。归属不明或同名新实例不能使用旧记录写入。

## Per-server lock

`server_operation_lock` (in `app.world.locks`) exposes maintenance ownership
through the shared resource coordinator. Backup, restore, prune, startup and
rebuild (`BACKUP`, `RESTORE`, `PRUNE`, `START`, `REBUILD`) share that resource.
World restores atomically reserve maintenance, selected FILES scopes and cache
resources before any write. Claims include lexical paths and canonical symlink
targets, and reject paths outside server data. Nested safety backups validate and
reuse the parent lease without acquiring more resources. Restore/prune recheck
stopped status after acquisition; start/up/restart and rebuild retain ownership
through process/configuration settlement. Map rendering takes its own cache and
output-file resources, so conflicting cache writes wait without holding
maintenance. Unrelated ordinary online file work remains available.
Accepted tasks retain target references through finalization and reject server deletion, including while queued.

`LockHolder` records kind, start time, optional user, description and restoration ID. `GET /api/servers/{server_id}/maintenance` exposes the current holder's active flag, kind and description. Shared frontend operation buttons poll this state; the prune page also immediately disables startup while its apply task is active.

Global and scheduled backup locking belongs to [snapshot resource ownership](snapshots.md).
World adapters reuse the accepted parent lease for safety capture.

## Preview sessions

Previewing a restore means showing the user what the world *would* look like after the restore, without touching live data.

- **Tmpdir layout.** Sessions live under `/tmp/mc-admin-world-artifacts/<installation>/restore/<session_id>/`. Source MCAs are staged into `source/`; chunk-merged copies into `preview/` so the live world is untouched. Chunk restore stages use a separate `restore-stage/` feature directory in the same installation namespace.
- **Lazy tile rendering.** `WorldPreviewRenderer.prepare` stages MCAs with restic, runs the chunk merge for CHUNKS scope, and attaches a per-session `ServerRenderQueue` for REGIONS/CHUNKS previews before the preparation task completes. The first request for each tile triggers an mcmap render via the same batching/coalescing/cancellation queue used by the live map. The queue's worker exits after 60 s of idle, so a quiet preview costs nothing. `PreviewMapCache` provides a `ServerMapCache`-shaped path resolver pointing at the staged MCAs and a session-local `tiles/` output. `SnapshotPreviews.tile` is the tile entry point — file-fast-path for already-rendered PNGs, queue-await otherwise (subject to `config.mcmap.request_timeout_seconds`); raises `FileNotFoundError` for tiles outside the staged affected-region set or for scopes without an attached render queue.


- **Disk threshold guard.** Estimated cost is `affected_regions × preview_avg_region_bytes × 2`; REGIONS uses the selected region count, CHUNKS uses the unique parent-region count, and WORLD/DIMENSION use a conservative default. If the FS lacks headroom, the preparation task reports insufficient temporary disk space.

[Common preview lifetime](snapshot-restoration.md#预览与仓库维护任务) owns preparation,
heartbeat, replacement, expiry and cleanup. World tile reads pin the session while
reading PNG bytes, and cleanup closes the render queue and waits for readers.
Preparation completes after staging and chunk merging; tiles render on demand.
Owned orphan cleanup retains unresolved recovery references, and restart never
re-authorizes an old map preview.

Each lazy render owns a `world_preview_render` operation with the real server ID
and generation. `PreviewRenderTarget` carries the separate session identity and
directory. MCA inputs and PNG output stay inside that session; the shared live
palette has an exact FILES claim, while a `previews/<session>` MAP_CACHE scope
coordinates with broad world operations without taking maintenance. Its
`world_preview` recovery reference remains unresolved until the writer stops.
Unknown writers preserve the artifact; the temporary output never claims a
fictional path inside the server project.

## Subprocess ownership

mcmap subcommands (`replace-chunks`, `remove-chunks`, `render`) run with the backend's privileges. When the backend is root, `_chown_args_for(data_path)` in `app.mcmap.runner` appends `--chown UID:GID` so mcmap chowns its outputs (atomic replacements of target MCAs and rendered tile PNGs) to the data dir's owner. There is no preexec demotion, so the subprocess can read restic-restored staging trees under `<session_dir>/source/` and the chunk-flow tempdir directly — no separate chown step is required before merging.

## Map tile cache invalidation

Restore/rollback finalization invalidates cached PNG tiles for affected region
MCAs and MCC overflow files, including after partial failure or cancellation. Task completion follows confirmed cache finalization. Successful WORLD/DIMENSION invalidation
uses Restic verbose-status items; interrupted broad restores clear the confined
server/dimension tile subtree even if Restic emitted no file event before
interruption. REGIONS/CHUNKS use the explicit selection. Only `region/` MCAs map
to PNGs; `entities/` and `poi/` sidecars are skipped. Missing tiles count as
invalidated, but other deletion failures propagate and persist cache degradation.

[Application operation refresh](../../frontend-react/docs/operation-refresh.md)
owns cross-page query invalidation and tile URL revisions, including MCC-only
changes and unchanged MCA mtimes.

## Cancellation and crash recovery

Common cancellation and crash classification are documented in
[restoration](snapshot-restoration.md#acceptance-safety-and-rollback) and
[operation recovery](operation-recovery.md). World finalization invalidates the
captured map scope before publishing a terminal task state, including partial
failure. Unknown writers retain resource blocks; cache-cleanup failure records
degradation rather than reporting success.

Startup calls `mark_running_restorations_interrupted()` for abandoned history,
retaining safety references and the diagnostic `server restarted before completion`.
History exposes rollback only when the required snapshot and original binding
remain usable. Interrupted work is not replayed automatically.

`SnapshotPreviews.prepare()` reaps eligible orphan previews and restore stages
before producers and admission. The runtime starts the janitor and drains preview
queues before deleting unreferenced artifacts; see [runtime ordering](runtime.md).

## Settings

Dynamic (`snapshots.world_restore` schema): `preview_session_ttl_seconds`, `preview_janitor_interval_seconds`, `preview_avg_region_bytes`.

Dynamic (`world` schema): `region_stat_workers`, `dimension_max_depth_from_world_root`, `dimension_labels`.

## Endpoints

Mounted under `/api/servers/{server_id}/world-restore/`:

- `GET /layout` — world roots + path-only dimensions (`region_dir`, `entities_dir`, `poi_dir`)
- `GET /dimension-labels` — dynamic dimension label mapping consumed by the frontend display layer
- `GET /claims` — FTB claims extracted from the primary world root via mcmap; returns `available=false` when no supported FTB data is detected
- `GET /player-locations` — saved player positions extracted from the primary world root via mcmap, with dimension ids resolved to `region_dir_relpath` when possible

Claims and player locations also have `/api/servers/{server_id}/claims` and `/player-locations` aliases. World execution and history have no separate routes.

World commands pass `{kind: "world", server_id, selection}` through the
[common snapshot API](snapshot-restoration.md). `POST /api/snapshots/targets/check`
accepts only world scopes and validates the selected layout and confined paths without reading
Restic or exclusion settings; its response contains only `allowed` and `reason`. Source eligibility separately checks coverage without requiring speculative
MCC files that do not exist.

Map previews use `GET /api/snapshots/previews/{id}/tiles/{rx}/{rz}.png` for
REGIONS/CHUNKS selections. Region copies use selected source data; chunk
copies start from online MCA/MCC data and merge selected chunks.
Unselected overflow chunks remain intact. File actions, preview
binding and lifetime use the common contracts above.
