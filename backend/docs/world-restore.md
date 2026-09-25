# World Restore (`app.world`)

Selective rollback of Minecraft world data at four granularities — chunk, region, dimension, or whole world. Built on Restic for snapshot storage and the `mcmap replace-chunks` / `remove-chunks` subcommands for sub-region splicing. Every restore creates a safety snapshot first, so any rollback is undoable with one click.

`restore.py` owns application orchestration. `selection.py` plans confined paths
and resource scopes; `scope_execution.py` performs scope-specific Restic/mcmap
work; `restoration_store.py` owns short history transactions; `finalization.py`
invalidates caches; `preview_application.py` builds previews using the
reference-counted manager in `preview.py`. `artifacts.py` ties feature scratch
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

Before any restore touches the live world, the orchestrator creates a Restic snapshot at the same scope as the planned restore (a "safety snapshot"). Its id is recorded on the `Restoration` row. Rollback simply runs the restore in reverse: the safety snapshot is the source, the same `selection` is the target.

The history row and recovery references exist before the SSE event containing
the completed safety snapshot is sent. Disconnecting at that event leaves a
recoverable interrupted row. History captures the server's persistent instance
generation; rollback validates it before the stream and again under the lease.
Migration `2026092503` binds historical rows only when lifetime evidence is
unambiguous. `server_generation` and `binding_issue` remain visible in history;
unknown ownership and same-name replacements return HTTP 409 with
`restoration_identity_conflict` instead of applying old history to new data.

Successful, failed and interrupted restorations can be rolled back while their
safety snapshot exists. Selection JSON records `world_roots` for WORLD restores
and `absent_directories` for selected directories and their missing ancestors,
all relative to server data. Reads retain compatibility with
`absent_sidecar_dirs`. When older WORLD history lacks roots, rollback derives
them only from its safety snapshot's paths and rejects the data root, outside
paths and escaping symlinks. Restoring away the last MCA therefore does not make
history depend on rediscovering a currently populated world.

A safety snapshot of a fully missing range uses empty directories inside the
already declared scope. File selections use unique `.mc-admin-absence-*` empty
markers only where no selected file exists, so unrelated sibling MCAs do not
enter the backup. Finite cleanup removes the owned markers and newly created
empty ancestors. Leases include required missing ancestors before acquisition
and recheck them under ownership. Rollback restores the saved absence only within
its selected scope, honors ignores, and removes empty ancestors with `rmdir`.
Region rollback deletes only selected region/overflow files; chunk rollback
removes selected chunks and newly empty MCA files. Every rollback records its
own safety state, including absence, so it can itself be undone.

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
Request-scoped restoration also participates in deletion admission.

`LockHolder` records kind, start time, optional user, description and restoration ID. `GET /api/servers/{server_id}/maintenance` exposes the current holder's active flag, kind and description. Shared frontend operation buttons poll this state; the prune page also immediately disables startup while its apply task is active.

Manual snapshots and scheduled backups resolve their actual server targets and
acquire declared resources together. A whole-server-root backup also holds a
global FILES scope that conflicts with concurrent creation/adoption, including
servers absent from its initial target discovery. If resources are busy, manual
requests return 423 or cron skips with its existing notification. Ordinary
non-world snapshot restoration retains online availability. See `snapshots.md`.

## Preview sessions

Previewing a restore means showing the user what the world *would* look like after the restore, without touching live data.

- **One session per server.** Starting a new preview tears down the prior session for that server.
- **Tmpdir layout.** Sessions live under `/tmp/mc-admin-world-artifacts/<installation>/restore/<session_id>/`. Source MCAs are staged into `source/`; chunk-merged copies into `preview/` so the live world is untouched. Chunk restore stages use a separate `restore-stage/` feature directory in the same installation namespace.
- **Lazy tile rendering.** `begin_preview` stages MCAs with restic, runs the chunk merge for CHUNKS scope, and attaches a per-session `ServerRenderQueue` for REGIONS/CHUNKS previews before emitting `ready`. The first request for each tile triggers an mcmap render via the same batching/coalescing/cancellation queue used by the live map. The queue's worker exits after 60 s of idle, so a quiet preview costs nothing. `PreviewMapCache` provides a `ServerMapCache`-shaped path resolver pointing at the staged MCAs and a session-local `tiles/` output. `request_preview_tile` is the orchestrator's tile entry point — file-fast-path for already-rendered PNGs, queue-await otherwise (subject to `config.mcmap.request_timeout_seconds`); raises `FileNotFoundError` for tiles outside the staged affected-region set or for scopes without an attached render queue.
- **Heartbeat-driven TTL.** Default 30 minutes. The browser pings every 30 s; on close, `DELETE /preview/{session_id}` tears down. A janitor task running every `preview_janitor_interval_seconds` reaps expired sessions and orphaned dirs. Tearing down a session also calls `ServerRenderQueue.shutdown()` to cancel the worker, fail outstanding waiters, and terminate any running mcmap subprocess.
- **Disk threshold guard.** Estimated cost is `affected_regions × preview_avg_region_bytes × 2`; REGIONS uses the selected region count, CHUNKS uses the unique parent-region count, and WORLD/DIMENSION use a conservative default. If the FS lacks headroom, the preview SSE emits an `error` event with `free` and `required`.

Builds and tile reads hold active references. The tile endpoint reads the PNG
bytes while pinned and then returns the response, so response delivery cannot
race with file deletion. Closing, replacement or expiry
detaches the session from new requests and waits for active users before deleting
its files. A heartbeat cannot revive an already expired session. Requests verify
both server ID and generation. Startup and periodic orphan cleanup inspect only
owned token directories, recheck current sessions after asynchronous enumeration,
and retain unresolved recovery references. An old task/history record does not
resume or re-authorize a preview after restart.

The preview stream reports staging and chunk-merge progress only (`start`, `stage`, `merge_region`, `ready`, `error`). Tile rendering happens later through tile requests, not through the preview SSE. An error event records a failed operation outcome even when the generator handles the exception to preserve the SSE contract.

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
MCAs, including after partial failure or cancellation. Successful streams emit
`invalidate_cache` before `complete`. Successful WORLD/DIMENSION invalidation
uses Restic verbose-status items; interrupted broad restores clear the confined
server/dimension tile subtree even if Restic emitted no file event before
interruption. REGIONS/CHUNKS use the explicit selection. Only `region/` MCAs map
to PNGs; `entities/` and `poi/` sidecars are skipped. Missing tiles count as
invalidated, but other deletion failures propagate and persist cache degradation.

The frontend application operation observer invalidates world-restore, map and
affected file query keys after terminal outcomes, including partial failure.
This works after leaving the initiating page. The map tile layer reloads the
region manifest and uses MCA mtimes as cache-busting query params.

## Cancellation and crash recovery

Disconnecting the SSE stream cancels the current restore; it does not create a detached background operation. Response, router, orchestrator and Restic generators close their owned child streams explicitly. Subprocess reaping, cache cleanup and history finalization are shielded from request cancel scopes and finish before maintenance ownership is released. An interrupted connection records `INTERRUPTED` immediately without restarting the backend; ordinary restore/cache failures record `FAILED`. Failed history with a retained safety snapshot offers rollback too. The API does not automatically retry or undo destructive operations.

If the backend crashes mid-restore, its `Restoration` row can remain `RUNNING` and an external writer may still exist. Before starting producers or admitting writes, operation recovery verifies recorded process ownership, reconciles the captured server generation and invalidates affected map caches. Unconfirmed writers block their resource; failed cache cleanup degrades the cache without permanently freezing server management.

On startup, `mark_running_restorations_interrupted()` flips any such rows to `INTERRUPTED` with `error_message="server restarted before completion"`. The frontend history drawer surfaces rollback on these when the safety snapshot still exists — because the safety snapshot was created *before* the partial restore began, rolling back to it cleanly recovers the pre-restore state regardless of how far the restore got.

Rollback rows are flat `Restoration` rows with `is_rollback=true`. A rollback also creates its own safety snapshot, so a successful rollback can itself be undone while that safety snapshot remains in restic.

## Lifespan wiring

The application runtime, in order:

1. Recover journal ownership and resources, then mark abandoned restoration rows interrupted.
2. `initialize_world_restore_orchestrator()` builds the runtime's orchestrator when Restic is configured. Dynamic preview values are read by the preview manager at session/janitor runtime.
3. `prepare()` reaps eligible orphan previews and restore stages before producers and admission; `start_janitor()` launches periodic preview cleanup. Shutdown drains request writers and closes preview queues before deleting unreferenced artifacts whose writers have stopped.

The router accesses the orchestrator through the current runtime’s typed `get_world_restore_orchestrator()` accessor. Restoration operations retain safety snapshot references before emitting them, and completion SSE events wait for journal finalization. Unexpected adapter failures produce safe public messages in both streams and restoration history.

## Settings

Dynamic (`snapshots.world_restore` schema): `preview_session_ttl_seconds`, `preview_janitor_interval_seconds`, `preview_avg_region_bytes`.

Dynamic (`world` schema): `region_stat_workers`, `dimension_max_depth_from_world_root`, `dimension_labels`.

## Endpoints

Mounted under `/api/servers/{server_id}/world-restore/`:

- `GET /layout` — world roots + path-only dimensions (`region_dir`, `entities_dir`, `poi_dir`)
- `GET /dimension-labels` — dynamic dimension label mapping consumed by the frontend display layer
- `GET /claims` — FTB claims extracted from the primary world root via mcmap; returns `available=false` when no supported FTB data is detected
- `GET /player-locations` — saved player positions extracted from the primary world root via mcmap, with dimension ids resolved to `region_dir_relpath` when possible
- `POST /eligible-snapshots` (body: `RestorationSelection`) — newest-first list of snapshots that cover *all* MCA paths the selection resolves to (uses `SnapshotService.find_snapshots_covering`; speculative MCC sidecars are excluded from eligibility)
- `POST /snapshots` (body: `{type: "world"|"dimension", region_dir_relpath?}`) — creates a manual snapshot at world or dimension scope; returns 423 if the server lock is held
- `POST /preview` (body: `{source_snapshot_id, selection}`) — SSE stream of `PreviewEvent` (`start` → `stage` → optional `merge_region` → `ready`, or `error`); returns `session_id` in the `ready` event
- `POST /preview/{session_id}/heartbeat` — extends the TTL; 404 if the session is unknown
- `DELETE /preview/{session_id}` — idempotent teardown
- `GET /preview/{session_id}/tile/{rx}/{rz}.png` — preview tile (also heartbeats)
- `POST /restore` (body: `{source_snapshot_id, selection}`) — SSE stream of `RestoreEvent`; pre-checks return 409 (server running) or 423 (locked) before SSE handshake so the frontend can render distinct UI
- `GET /restorations?limit=&offset=` / `GET /restorations/{id}` — restoration history rows, including source/safety snapshot existence flags
- `POST /restorations/{id}/rollback` — SSE stream of `RestoreEvent`; uses the row's `safety_snapshot_id` as the source and pre-checks 400 (missing/deleted safety snapshot), 409 (server running), and 423 (locked)
