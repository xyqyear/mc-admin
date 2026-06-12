# Snapshots (`app.snapshots`)

Restic-backed backup integration. Wraps the `restic` CLI behind an async API and exposes the bits the rest of the app needs: snapshot creation, listing, retention pruning, restore (with progress), staging, and lock recovery — with configurable **ignored paths** that are excluded from backups and protected from restores.

## Why Restic

Restic deduplicates at the chunk level, encrypts at rest, and supports forget/prune retention out of the box. We don't reinvent any of that — we shell out and parse JSON. The trade-off is process spawning per operation; cost is negligible compared to the backup itself.

## Architecture

```text
app/snapshots/
├── models.py    # ResticSnapshot, ResticSnapshotWithSummary, ResticRestoreEvent, NodeKind
├── restic.py    # ResticClient — stateless CLI wrapper, one method per restic command
├── ignores.py   # ignore-path resolution (<LEVEL_NAME> expansion) and pattern translation
├── coverage.py  # exclude-aware "does this snapshot cover this path" predicate
├── planner.py   # build_restore_plan(): targets + ignores → one restic invocation per step
└── service.py   # SnapshotService — the app-facing API; the wired singleton lives in __init__.py
```

`snapshot_service` is the singleton (`None` when restic isn't configured, so dev environments without a repo work fine). Routers, cron jobs, self-checks, and the world-restore orchestrator all go through it; nothing outside the package touches `ResticClient` directly.

## Ignored paths

`dynamic_config.snapshots.ignored_paths` holds literal paths **relative to each server's data directory** (default `[".mcmap"]`, keeping tile caches out of the repo). A `<LEVEL_NAME>` segment expands per-server to the `level-name` from `server.properties` (`app.minecraft.properties.read_level_name`). Globs are rejected at the schema level — restore-time protection needs literal containment math.

Semantics:

- **Backup** passes each ignored path under a backup root as an absolute `--exclude`. Restic records these in the snapshot metadata (`excludes`).
- **Restore** never overwrites *or deletes* ignored paths, even though restores run with `--delete`. The effective ignore set is the union of current config and the snapshot's recorded `excludes`, so snapshots taken under an older ignore config stay protected after config changes — in both directions.
- **Coverage** (`find_snapshots_covering`, path-filtered listing, self-check freshness) is exclude-aware: a snapshot whose recorded excludes contain the queried path does not count as covering it, while an exclude strictly below the queried path doesn't disqualify the snapshot (`coverage.py`).
- Snapshotting or restoring a target that itself lies under an ignored path raises `TargetIgnoredError` (HTTP 400 / SSE error).

## Restore planning

Restic forbids combining `--include` with `--exclude`, so a single include-based restore can't protect ignored paths from `--delete`. Instead, `build_restore_plan` probes the snapshot tree (`restic ls`, one call per unique parent directory) and splits the request into steps, each one restic invocation:

- **`DirStep`** — a target directory present in the snapshot. Restored subtree-addressed (`restic restore <snap>:<dir> --target <dir> --delete`), with subtree-relative `--exclude` patterns for ignored paths under it. Restic matches restore patterns relative to the subtree root — absolute patterns silently match nothing.
- **`FileStep`** — file targets grouped by parent directory, restored via the parent subtree with `--include /<name>` patterns. `--delete` then only considers included names: an on-disk file missing from the snapshot is deleted, non-included siblings are untouched. Speculative includes of paths in neither place (the world-restore MCC enumeration) are no-ops.

Targets whose parent directory is absent from the snapshot are skipped — restic can neither restore them nor traverse-delete there. (Known restic limitation, unchanged from the previous architecture: deletion-by-include cannot reach through directories the snapshot lacks; the chunks restore scope compensates with `mcmap remove-chunks`.)

`SnapshotService` executes plans in two modes: **in-place** (`restore`, `--delete` on, target = source dir) and **staged** (`stage`, no delete, full absolute path mirrored under a stage root — `SnapshotService.stage_destination` maps live paths to staged ones). `preview` is the same plan with `--dry-run`. Status percents are rescaled across steps into one monotonic progress stream, and per-step summaries are merged into a single final `summary` event.

## Event normalization

Restore events arrive as NDJSON (`status` / `verbose_status` / `summary`). Restic reports restored/updated items relative to the restore subtree but deleted items as absolute on-disk paths; `ResticClient.restore` normalizes everything to absolute on-disk paths before yielding, so consumers (SSE streams, PNG-tile invalidation) see one path space. Stderr is drained concurrently to avoid a pipe-buffer deadlock during long restores.

## Subprocess pattern

All commands run through `ResticClient.binary_path`, which defaults to `settings.restic_binary_path`. That setting comes from `restic_binary_path` / `RESTIC_BINARY_PATH` when configured; otherwise it resolves once at startup from `PATH`, `/usr/local/bin/restic`, then `/usr/bin/restic`. The subprocess env carries `RESTIC_REPOSITORY` and, for protected repos, `RESTIC_PASSWORD`; unprotected repos get `--insecure-no-password`.

## Time-restriction guard

`dynamic_config.snapshots.time_restriction` lets an admin block manual snapshot creation during peak hours — useful when the repo lives on slow shared storage. The router checks this before delegating to the service.

## Path containment

Request-supplied `server_id` and `paths` are joined into filesystem paths, so the snapshots router and the cron backup job validate every resolved path (symlinks followed) with `async_fs.resolve_inside`: the server's project path must stay under the servers root and each sub-path under the server's data directory. Escapes reject with HTTP 400 / a failed job — restore runs with delete semantics, so this is enforced before any restic call.

## Lock interaction

Snapshot creation goes through `server_operation_lock.acquire(server_id, kind=BACKUP)` (see `app.world.locks` / `docs/world-restore.md`). Manual snapshot endpoints respect the same lock so they can't collide with an in-flight restore.
