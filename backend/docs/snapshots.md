# Snapshots (`app.snapshots`)

Restic-backed backup integration. Wraps the `restic` CLI behind an async API and exposes the bits the rest of the app needs: snapshot creation, listing, retention pruning, restore (with progress), and lock unlock.

## Why Restic

Restic deduplicates at the chunk level, encrypts at rest, and supports forget/prune retention out of the box. We don't reinvent any of that — we shell out and parse JSON. The trade-off is process spawning per operation; cost is negligible compared to the backup itself.

## `ResticManager`

Singleton (`restic_manager`), initialized on app startup if `settings.restic.repository_path` is set. The init no-ops gracefully when restic isn't configured, so dev environments without a repo work fine.

Public methods:

- `backup(paths)` → `ResticSnapshotWithSummary` — creates a snapshot, **excluding `.mcmap/`** so per-server tile caches never inflate the repo. Returns the snapshot id plus stats (`files_new`, `data_added`, etc.).
- `list_snapshots(path_filter=None)` → newest-first list. The path filter does ancestor-match: a snapshot whose recorded paths contain `path_filter` is included. Used for "snapshots covering this server's data dir".
- `find_snapshots_covering(paths)` → snapshots whose recorded paths cover *all* of the input paths. Used by `app.world.restore` to compute eligible snapshots for a chunk/region/dimension restore.
- `restore_preview(snapshot_id, target_path, include_paths)` → list of `ResticRestorePreviewAction` rows (`unchanged | updated | restored | deleted`). A dry run that lets the UI show "this is what would change".
- `restore(snapshot_id, target_path, include_paths)` → async generator yielding `ResticRestoreEvent` (status / file / summary). Streams progress so the world-restore SSE flow can render it live.
- `forget_id(id, prune=True)` — delete a single snapshot.
- `forget(keep_last, keep_daily, keep_monthly, …, prune=True)` — apply retention.
- `list_locks()`, `unlock()` — recover from a stuck repo.

## Subprocess pattern

All commands run via `app.utils.exec.exec_command("restic", …)` with an env dict carrying `RESTIC_REPOSITORY` and `RESTIC_PASSWORD`. JSON output is parsed line-by-line; restore events arrive as NDJSON (`status` / `verbose_status` / `summary` message types). Stderr is drained concurrently to avoid a pipe-buffer deadlock during long restores.

## Time-restriction guard

`dynamic_config.snapshots.time_restriction` lets an admin block manual snapshot creation during peak hours — useful when the repo lives on slow shared storage. The router checks this before delegating to the manager.

## Files

- `restic.py` — `ResticManager`, plus the `ResticSnapshot`, `ResticSnapshotWithSummary`, `ResticSnapshotSummary`, `ResticRestoreEvent`, `ResticRestorePreviewAction` Pydantic models.

## Lock interaction

Snapshot creation goes through `server_operation_lock.acquire(server_id, kind=BACKUP)` (see `app.world.locks` / `docs/world-restore.md`). Manual snapshot endpoints respect the same lock so they can't collide with an in-flight restore.
