# World Restore (`app.world`)

Selective rollback of Minecraft world data at four granularities — chunk, region, dimension, or whole world. Built on Restic for snapshot storage and the `mcmap replace-chunks` / `remove-chunks` subcommands for sub-region splicing. Every restore creates a safety snapshot first, so any rollback is undoable with one click.

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

This means every successful restore has a one-click undo. It also means **a partial / interrupted restore can still be undone** — see "Crash recovery".

## Per-server lock

`server_operation_lock` (in `app.world.locks`) is a singleton holding one `asyncio.Lock` per server id (or `__global__`). The lock is acquired with a `ServerOperationKind` of `BACKUP` (manual or scheduled snapshot creation) or `RESTORE` (restore + rollback) and held for the full operation including the safety snapshot.

`LockHolder` records `kind`, `started_at`, optional `user_id`, a human-readable description, and the active `restoration_id` so the UI can attribute the wait to the right user and operation.

The cron backup job uses `try_acquire()` with either the target server id or `__global__`. If the lock is held, the run is skipped with a structured log entry plus an Uptime Kuma "skipped" notification when configured. Backups never collide with restores; cron pressure never pushes a backup into an active restore window. Map render queues do not take this lock because they only read source MCAs and write cached PNGs.

## Preview sessions

Previewing a restore means showing the user what the world *would* look like after the restore, without touching live data.

- **One session per server.** Starting a new preview tears down the prior session for that server.
- **Tmpdir layout.** Sessions live under `/tmp/mc-admin-world-restore/<session_id>/`. Source MCAs are staged into `source/`; chunk-merged copies into `preview/` so the live world is untouched.
- **Lazy tile rendering.** `begin_preview` stages MCAs with restic, runs the chunk merge for CHUNKS scope, and attaches a per-session `ServerRenderQueue` for REGIONS/CHUNKS previews before emitting `ready`. The first request for each tile triggers an mcmap render via the same batching/coalescing/cancellation queue used by the live map. The queue's worker exits after 60 s of idle, so a quiet preview costs nothing. `PreviewMapCache` provides a `ServerMapCache`-shaped path resolver pointing at the staged MCAs and a session-local `tiles/` output. `request_preview_tile` is the orchestrator's tile entry point — file-fast-path for already-rendered PNGs, queue-await otherwise (subject to `config.mcmap.request_timeout_seconds`); raises `FileNotFoundError` for tiles outside the staged affected-region set or for scopes without an attached render queue.
- **Heartbeat-driven TTL.** Default 30 minutes. The browser pings every 30 s; on close, `DELETE /preview/{session_id}` tears down. A janitor task running every `preview_janitor_interval_seconds` reaps expired sessions and orphaned dirs. Tearing down a session also calls `ServerRenderQueue.shutdown()` to cancel the worker, fail outstanding waiters, and terminate any running mcmap subprocess.
- **Disk threshold guard.** Estimated cost is `affected_regions × preview_avg_region_bytes × 2`; REGIONS uses the selected region count, CHUNKS uses the unique parent-region count, and WORLD/DIMENSION use a conservative default. If the FS lacks headroom, the preview SSE emits an `error` event with `free` and `required`.

The preview stream reports staging and chunk-merge progress only (`start`, `stage`, `merge_region`, `ready`, `error`). Tile rendering happens later through tile requests, not through the preview SSE.

## Subprocess ownership

mcmap subcommands (`replace-chunks`, `remove-chunks`, `render`) run with the backend's privileges. When the backend is root, `_chown_args_for(data_path)` in `app.mcmap.runner` appends `--chown UID:GID` so mcmap chowns its outputs (atomic replacements of target MCAs and rendered tile PNGs) to the data dir's owner. There is no preexec demotion, so the subprocess can read restic-restored staging trees under `<session_dir>/source/` and the chunk-flow tempdir directly — no separate chown step is required before merging.

## Map tile cache invalidation

After a restore or rollback completes, `_invalidate_map_cache()` deletes cached PNG tiles for affected region MCAs and emits an `invalidate_cache` progress event. WORLD/DIMENSION invalidation derives affected regions from restic verbose-status items. REGIONS/CHUNKS invalidation uses the explicit selection because that is the authoritative affected set. Only `region/` MCAs map to PNGs; `entities/` and `poi/` sidecars are skipped.

The frontend invalidates world-restore and map query keys after completion. The map tile layer reloads the region manifest and uses MCA mtimes as cache-busting query params.

## Crash recovery

If the backend crashes mid-restore, the `Restoration` row is left in `RUNNING` status but no further work happens.

On startup, `mark_running_restorations_interrupted()` flips any such rows to `INTERRUPTED` with `error_message="server restarted before completion"`. The frontend history drawer surfaces rollback on these when the safety snapshot still exists — because the safety snapshot was created *before* the partial restore began, rolling back to it cleanly recovers the pre-restore state regardless of how far the restore got.

Rollback rows are flat `Restoration` rows with `is_rollback=true`. A rollback also creates its own safety snapshot, so a successful rollback can itself be undone while that safety snapshot remains in restic.

## Lifespan wiring

`app.main` lifespan, in order:

1. `mark_running_restorations_interrupted()` flips stuck rows.
2. `initialize_world_restore_orchestrator()` builds the singleton when Restic is configured. Dynamic preview values are read by the preview manager at session/janitor runtime.
3. `start_janitor()` launches the preview janitor task; `stop_janitor()` cancels it on shutdown.

The router accesses the orchestrator via `from ... import world as world_subsystem` and reads `world_subsystem.world_restore_orchestrator` *at request time* — so the lifespan-time reassignment is observed even though the binding is module-level.

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
