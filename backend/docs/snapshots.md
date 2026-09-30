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
├── application.py # backup use case, confined request paths and declared file scope
├── policy.py    # manual backup time-window policy
├── scopes.py    # explicit global/project/data-path/world selection and resource claims
├── protection.py # frozen current/source/chain exclusions and execution revalidation
├── repository_use.py # active repository readers and exclusive destructive maintenance
├── restoration_models.py # retained restoration evidence, including server generations
├── selection_models.py # world selection contracts shared by snapshot adapters
├── restoration_store.py # history persistence and interruption reconciliation
├── recovery.py  # startup reconciliation of pending/running restoration history
├── service.py   # SnapshotService — owned Restic planning/execution
├── commands.py  # task acceptance, safety evidence, file restore and reversible rollback
├── queries.py   # journal-backed history state and current rollback availability
└── file_restore.py # stopped-world checks and derived-tile cleanup for file scopes
```

`get_snapshot_service()` returns the active runtime’s actual `SnapshotService`, or `None` when Restic is not configured. The composition root creates its Restic adapter and injects its Minecraft manager. Routers, cron jobs, self-checks and world restoration use this owned service; application callers do not construct competing repository clients.

The explicit scope contract distinguishes the servers root, an entire server
project, paths relative to `data`, and world selections. It collapses duplicate
targets while retaining lexical and canonical file claims. `SnapshotProtection`
freezes expanded current exclusions together with source and retained-chain
protection. Execution rechecks current exclusions and rejects configuration or
`LEVEL_NAME` drift before invoking Restic.

Repository readers can coexist. Manual tasks hold repository references from acceptance through queued work and subprocess cleanup; ready map previews retain
their source through close/expiry and outstanding tile reads. Forget/prune and
lock cleanup reject while those references exist. Completed history does not
permanently prevent retention. References are bounded per runtime.

## Ignored paths

`dynamic_config.snapshots.ignored_paths` holds literal paths **relative to each server's data directory** (default `[".mcmap"]`, keeping tile caches out of the repo). A `<LEVEL_NAME>` segment expands per-server to the `level-name` from `server.properties` (`app.minecraft.properties.read_level_name`). Globs are rejected at the schema level — restore-time protection needs literal containment math.

Semantics:

- **Backup** passes each ignored path under a backup root as an absolute `--exclude`. Restic records these in the snapshot metadata (`excludes`).
- **Restore** never overwrites *or deletes* ignored paths, even though restores run with `--delete`. The effective ignore set is the union of current config and the snapshot's recorded `excludes`, so snapshots taken under an older ignore config stay protected after config changes — in both directions.
- **Coverage** (`find_snapshots_covering`, path-filtered listing, self-check freshness) is exclude-aware: a snapshot whose recorded excludes contain the queried path does not count as covering it, while an exclude strictly below the queried path doesn't disqualify the snapshot (`coverage.py`).
- Snapshotting or restoring a target that itself lies under an ignored path raises `TargetIgnoredError` (HTTP 400 before task acceptance).

## Restore planning

Restic forbids combining `--include` with `--exclude`, so a single include-based
restore cannot protect ignored paths from `--delete`. `build_restore_plan` probes
each unique parent directory once and checks directory targets for empty trees.
It splits the request into Restic steps and explicit empty-selection cleanup:

- **`DirStep`** — a target directory present in the snapshot. Restored subtree-addressed (`restic restore <snap>:<dir> --target <dir> --delete`), with subtree-relative `--exclude` patterns for ignored paths under it. Restic matches restore patterns relative to the subtree root — absolute patterns silently match nothing.
- **`FileStep`** — file targets grouped by parent directory, restored via the parent subtree with `--include /<name>` patterns. `--delete` then only considers included names: an on-disk file missing from the snapshot is deleted, non-included siblings are untouched. Speculative includes of paths in neither place (the world-restore MCC enumeration) are no-ops.
- **`EmptyStep`** — the snapshot explicitly contains an empty target directory, or its parent exists but none of the selected file names exists in that snapshot. Restic can skip deletion when its effective selection is empty. The application therefore deletes only selected live content, preserving the directory root and the union of current and recorded ignored descendants. Unselected siblings and absence markers remain untouched.

Targets whose parent directory is absent from the snapshot are skipped — restic can neither restore them nor traverse-delete there. (Known restic limitation, unchanged from the previous architecture: deletion-by-include cannot reach through directories the snapshot lacks; the chunks restore scope compensates with `mcmap remove-chunks`.)

`SnapshotService` executes plans in two modes: **in-place** (`restore`, `--delete` on, target = source dir) and **staged** (`stage`, no delete, full absolute path mirrored under a stage root — `SnapshotService.stage_destination` maps live paths to staged ones). `preview` is the same plan with `--dry-run`. Status percents are rescaled across steps into one monotonic progress stream, and per-step summaries are merged into a single final `summary` event.

Empty-selection cleanup first checks its complete removal list against the owned
server and selected scope, rejects escaping symlinks and never traverses symlink
directories. It repeats confinement checks during finite cleanup and waits for
that cleanup on cancellation. Preview emits matching `deleted` events without
writing; staged restores retain the original Restic step with deletion disabled,
including when a caller supplies a populated staging destination.

## Event normalization

Restore events arrive as NDJSON (`status` / `verbose_status` / `summary`). Restic reports restored/updated items relative to the restore subtree but deleted items as absolute on-disk paths; `ResticClient.restore` normalizes everything to absolute on-disk paths before yielding, so consumers (SSE streams, PNG-tile invalidation) see one path space. Stderr is drained concurrently to avoid a pipe-buffer deadlock during long restores.

## Subprocess pattern

All commands run through `ResticClient.binary_path`, which defaults to `settings.restic_binary_path`. That setting comes from `restic_binary_path` / `RESTIC_BINARY_PATH` when configured; otherwise it resolves once at startup from `PATH`, `/usr/local/bin/restic`, then `/usr/bin/restic`. The subprocess env carries `RESTIC_REPOSITORY` and, for protected repos, `RESTIC_PASSWORD`; unprotected repos get `--insecure-no-password`.

## Time-restriction guard

`dynamic_config.snapshots.time_restriction` lets an admin block manual snapshot creation during peak hours — useful when the repo lives on slow shared storage. The HTTP adapter invokes the shared time-window policy before delegating to the application. Scheduled and nested safety backups retain their own admission semantics.

## Path containment

Request-supplied `server_id` and `paths` are joined into filesystem paths, so the snapshots router and the cron backup job validate every resolved path (symlinks followed) with `async_fs.resolve_inside`: the server's project path must stay under the servers root and each sub-path under the server's data directory. Escapes reject with HTTP 400 / a failed job — restore runs with delete semantics, so this is enforced before any restic call.

## Lock interaction

`SnapshotApplication.backup` resolves affected servers and file paths, then
atomically acquires maintenance and `FILES` claims with kind BACKUP. Busy targets
reject manual creation or skip scheduled backup. Whole-root backups declare the
global file root as well as captured generations. Servers can remain running;
these leases coordinate application operations and do not freeze Minecraft writes.

Nested safety backups pass their outer operation's live lease. Every requested
scope must already be covered; a child cannot acquire additional paths or upgrade
a normal file restore into maintenance. Safety planning can explicitly allow
speculative missing sidecars while requiring at least one existing target.
Manual requests retain missing-target validation. Ignored-path, coverage and
restore planning remain shared through `SnapshotService`.

Manual creation uses `POST /snapshots {scope}`. File recovery uses
`POST /snapshots/restorations {scope, source_snapshot_id}` and returns
`202 {task_id, restoration_id, skipped_paths}`. The task worker waits for its
resources, revalidates frozen identity/path/protection, creates and persists a
safety snapshot plus missing-path evidence, then applies the selected replacement.
History acceptance occurs after the journal reserves the task and before its worker
starts. Rejection, queued cancellation and failure before execution settle history.
`GET /snapshots/restorations` and its detail route project journal state; rollback
availability follows retained generations and actual repository references.

`POST /snapshots/restorations/{id}/rollback` creates another recovery task and
records its parent. It saves current contents first, including edits made since
the original restore. Missing targets use an owned temporary absence marker when
no live target exists; a rollback removes only allowed selected paths and empty
ancestors that were absent, preserving protected descendants and later siblings.
Source, current and retained-chain exclusions apply to safety creation and writes.

Every restore owns its target file scope. Whole-server/data targets and paths
intersecting known world roots additionally require stopped servers and maintenance
ownership, the server's `MAP_CACHE` scope and the concrete
`FILES(data/.mcmap/tiles)` cache path; ordinary configuration/plugin/file restores
remain available online.
A normal file restore can run beside world maintenance when their file scopes do
not overlap. Dry-run preview and reads do not acquire these leases. Running/busy
and path checks repeat after acquisition. Invalid unrelated server.properties
values do not prevent recovery: world-name lookup reads only level-name.

Closing observation of a file recovery does not stop it. Explicit task cancellation
waits for owned processes and finite cleanup. A failed or cancelled restore touching
world data clears the affected server's derived tiles even before the first Restic
file event. Successful restoration invalidates reported terrain changes. Cache
cleanup uses captured server references, so restored project metadata cannot hide
the affected cache. Unknown writers retain artifacts and mark cache degradation;
cleanup errors remain failed operations with retained history and safety evidence.

Accepted manual tasks hold deletion admission and target references through task
finalization. Server removal checks these references before cancelling other tasks
and again while frozen/exclusive; completed history does not block repository
retention. A missing safety snapshot leaves its history readable with an explicit
unavailable reason. Ordinary file restoration remains available online.

World request execution, map previews and cron backup applications still share the
same low-level protection, planner and repository reference registry. Their current
adapters are described in `world-restore.md`; common task migration is tracked by
`openspec/changes/unify-snapshot-recovery/tasks.md`.
