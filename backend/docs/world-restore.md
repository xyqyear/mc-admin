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
directories named `region` up to five components below the world root, then
keeps only those containing valid `r.X.Z.mca` files. This covers root
overworlds, legacy/custom root-child dimensions such as `DIM88`, modern
`dimensions/<namespace>/<name>` dimensions, and deeper FTB team dimensions
such as `dimensions/ftbteamdimensions/team/<uuid>`. If `fd` is missing or
fails, layout discovery fails with `WorldLayoutDiscoveryError`.

Dimension labels come from `app.world.dimension_labels`: the root dimension is
Overworld, `DIM-1` is Nether, `DIM1` is End, vanilla
`dimensions/minecraft/*` directories map to their vanilla names, and custom
dimensions use their world-root-relative path without a leading `dimensions/`.
The server map endpoint uses the same discovered layout, so both features
present identical labels.

`app.world.layout_cache` wraps layout discovery with a short in-memory TTL and
coalesces concurrent requests per `data_path`. The world-restore page opens
layout and claims together, so both requests share one filesystem discovery
while still reflecting disk changes within a few seconds.

## Safety snapshots

Before any restore touches the live world, the orchestrator creates a Restic snapshot at the same scope as the planned restore (a "safety snapshot"). Its id is recorded on the `Restoration` row. Rollback simply runs the restore in reverse: the safety snapshot is the source, the same `selection` is the target.

This means every successful restore has a one-click undo. It also means **a partial / interrupted restore can still be undone** — see "Crash recovery".

## Per-server lock

`server_operation_lock` (in `app.world.locks`) is a singleton holding one `asyncio.Lock` per server id (or `__global__`). The lock is acquired with a `ServerOperationKind` of `BACKUP` (snapshot creation) or `RESTORE` (restore + rollback) and held for the full operation including the safety snapshot.

`LockHolder` records `kind`, `started_at`, optional `user_id`, a human-readable description, and the active `restoration_id` so the UI can attribute the wait to the right user and operation.

The cron backup job calls `server_operation_lock.is_locked(server_id)` before running and skips with a structured "skipped" log entry plus an Uptime Kuma notification when the lock is held. Backups never collide with restores; cron pressure never pushes a backup into an active restore window.

## Preview sessions

Previewing a restore means showing the user what the world *would* look like after the restore, without touching live data.

- **One session per server.** Starting a new preview tears down the prior session for that server.
- **Tmpdir layout.** Sessions live under `restore_temp_dir/<session_id>/` (default `/tmp/mc-admin-world-restore/`). Source MCAs are staged into `source/`; chunk-merged copies into `preview/` so the live world is untouched.
- **Lazy tile rendering.** `begin_preview` only stages MCAs (restic restore + optional chunk merge) and attaches a per-session `ServerRenderQueue` before emitting `ready`. The first request for each tile triggers an mcmap render via the same batching/coalescing/cancellation queue used by the live map. The queue's worker exits after 60 s of idle, so a quiet preview costs nothing. `PreviewMapCache` provides a `ServerMapCache`-shaped path resolver pointing at the staged MCAs and a session-local `tiles/` output. `request_preview_tile` is the orchestrator's tile entry point — file-fast-path for already-rendered PNGs, queue-await otherwise (subject to `config.mcmap.request_timeout_seconds`); raises `FileNotFoundError` for tiles outside the staged affected-region set.
- **Heartbeat-driven TTL.** Default 30 minutes. The browser pings every 30 s; on close, `DELETE /preview/{session_id}` tears down. A janitor task running every `preview_janitor_interval_seconds` reaps expired sessions and orphaned dirs. Tearing down a session also calls `ServerRenderQueue.shutdown()` to cancel the worker, fail outstanding waiters, and terminate any running mcmap subprocess.
- **Disk threshold guard.** Estimated cost is `affected_regions × 8 MiB × 2`; preview returns 507 with `{"free", "required"}` if the FS lacks the headroom.

## Subprocess ownership

mcmap subcommands (`replace-chunks`, `remove-chunks`, `render`) run with the backend's privileges. When the backend is root, `_chown_args_for(data_path)` in `app.mcmap.runner` appends `--chown UID:GID` so mcmap chowns its outputs (atomic replacements of target MCAs and rendered tile PNGs) to the data dir's owner. There is no preexec demotion, so the subprocess can read restic-restored staging trees under `<session_dir>/source/` and the chunk-flow tempdir directly — no separate chown step is required before merging.

## Crash recovery

If the backend crashes mid-restore, the `Restoration` row is left in `RUNNING` status but no further work happens.

On startup, `mark_running_restorations_interrupted()` flips any such rows to `INTERRUPTED` with `error_message="server restarted before completion"`. The frontend history drawer surfaces a "rollback" CTA on these — because the safety snapshot was created *before* the partial restore began, rolling back to it cleanly recovers the pre-restore state regardless of how far the restore got.

## Lifespan wiring

`app.main` lifespan, in order:

1. `mark_running_restorations_interrupted()` flips stuck rows.
2. `initialize_world_restore_orchestrator()` builds the singleton with values from `config.snapshots.world_restore.*`. No-op if restic isn't configured.
3. `start_janitor()` launches the preview janitor task; `stop_janitor()` cancels it on shutdown.

The router accesses the orchestrator via `from ... import world as world_subsystem` and reads `world_subsystem.world_restore_orchestrator` *at request time* — so the lifespan-time reassignment is observed even though the binding is module-level.

## Settings

Dynamic (`snapshots.world_restore` schema): `restore_temp_dir`, `temp_disk_threshold_bytes`, `preview_session_ttl_seconds`, `preview_janitor_interval_seconds`.

## Endpoints

Mounted under `/api/servers/{server_id}/world-restore/`:

- `GET /layout` — cached world roots + dimensions (shared dimension labels; per-dimension `region_dir`, `entities_dir`, `poi_dir` paths)
- `POST /eligible-snapshots` (body: `RestorationSelection`) — newest-first list of snapshots that cover *all* paths the selection resolves to (uses `ResticManager.find_snapshots_covering`)
- `POST /snapshots` (body: `RestorationSelection`) — creates a backup at the requested scope; returns 423 if the server lock is held
- `POST /preview` (body: `{source_snapshot_id, selection}`) — SSE stream of `PreviewEvent` (start → stage → merge_region → render_progress → ready); returns `session_id` in the `ready` event
- `POST /preview/{session_id}/heartbeat` — extends the TTL; 404 if the session is unknown
- `DELETE /preview/{session_id}` — idempotent teardown
- `GET /preview/{session_id}/tile/{rx}/{rz}.png` — preview tile (also heartbeats)
- `POST /restore` (body: `{source_snapshot_id, selection}`) — SSE stream of `RestoreEvent`; pre-checks return 409 (server running) or 423 (locked) before SSE handshake so the frontend can render distinct UI
- `GET /restorations` / `GET /restorations/{id}` — restoration history rows
- `POST /restorations/{id}/rollback` — SSE stream of `RestoreEvent`; uses the row's `safety_snapshot_id` as the source
