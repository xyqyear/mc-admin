# Snapshots (`app.snapshots`)

Restic-backed backup integration. Wraps the `restic` CLI behind an async API and exposes the bits the rest of the app needs: snapshot creation, listing, retention pruning, restore (with progress), staging, and lock recovery — with configurable **ignored paths** that are excluded from backups and protected from restores.

## Why Restic

Restic deduplicates at the chunk level, encrypts at rest, and supports forget/prune retention out of the box. We don't reinvent any of that — we shell out and parse JSON. The trade-off is process spawning per operation; cost is negligible compared to the backup itself.

## Architecture

```text
app/snapshots/
├── models.py    # ResticSnapshot, ResticSnapshotWithSummary, ResticRestoreEvent, NodeKind
├── note_models.py # repository/snapshot-bound editable note persistence
├── notes.py     # bounded note reads and SQLite upserts
├── restic.py    # ResticClient — stateless CLI wrapper, one method per restic command
├── ignores.py   # ignore-path resolution (<LEVEL_NAME> expansion) and pattern translation
├── path_mapping.py # logical selection identities and frozen execution projections
├── evidence.py  # bounded logical selection and absence tags on snapshots
├── rules.py     # generation-bound logical rules for shared frontend decisions
├── coverage.py  # exclude-aware "does this snapshot cover this path" predicate
├── planner.py   # build_restore_plan(): targets + ignores → one restic invocation per step
├── application.py # confined listing/cron path resolution and maintenance conflict type
├── policy.py    # manual backup time-window policy
├── scopes.py    # explicit global/project/data-path/world selection and resource claims
├── protection.py # frozen current/source/chain exclusions and execution revalidation
├── repository_use.py # active repository readers and exclusive destructive maintenance
├── restoration_models.py # retained restoration evidence, including server generations
├── selection_models.py # world selection contracts shared by snapshot adapters
├── restoration_store.py # history persistence and interruption reconciliation
├── recovery.py  # startup reconciliation of pending/running restoration history
├── service.py   # SnapshotService — owned Restic planning/execution
├── commands.py  # task acceptance, safety evidence, file/world recovery and rollback
├── queries.py   # journal-backed active/history state and rollback availability
├── preparation.py # target planning, scope checks and frozen restore evidence
├── previews.py  # task preparation, binding checks, metadata and cleanup commands
├── preview_sessions.py # bounded shared session lifetime and artifact references
├── preview_actions.py # file action summaries and pagination
├── preview_version.py # observed target versions for preview validation
├── maintenance.py # task-owned deletion and stale-lock cleanup
└── file_restore.py # stopped-world checks and derived-tile cleanup for file scopes
```

`get_snapshot_service()` returns the active runtime’s actual `SnapshotService`, or `None` when Restic is not configured. The composition root creates its Restic adapter and injects its Minecraft manager and database-bound note store. Routers, cron jobs, self-checks and world restoration use this owned service; application callers do not construct competing repository clients.

The explicit scope contract distinguishes the servers root, an entire server
project, paths relative to `data`, and world selections. It collapses duplicate
or nested logical targets and retains their separate logical-to-execution
mappings, lexical and canonical file claims. `SnapshotProtection` freezes
logical current exclusions together with source and retained-chain protection.
Execution rechecks exclusions and mappings, rejecting configuration,
`LEVEL_NAME` or accepted link-target drift before invoking Restic.

Repository readers can coexist. Manual tasks hold repository references from acceptance through queued work and subprocess cleanup; ready file and map previews retain
their source through close/expiry and outstanding tile reads. Forget/prune and
lock cleanup reject while those references exist. Completed history does not
permanently prevent retention. References are bounded per runtime.

## Ignored paths

`dynamic_config.snapshots.ignored_paths` holds literal paths **relative to each server's data directory** (default `[".mcmap"]`, keeping tile caches out of the repo). A `<LEVEL_NAME>` segment expands per-server to the `level-name` from `server.properties` (`app.minecraft.properties.read_level_name`). Configured and expanded paths must remain relative literal paths; absolute names, traversal and globs are rejected. Ignore matching uses logical names without following symbolic links.

Semantics:

- If `B` links to `A`, ignoring `A` protects `A` and its logical descendants while direct selection through `B` remains allowed; ignoring `B` protects `B` and leaves direct selection of `A` allowed. Parent traversal backs up the link node and does not traverse its target.
- **Backup** projects each logical exclusion inside a selected root to that root's frozen execution tree and passes absolute `--exclude` paths to Restic. Several selected aliases can share storage while retaining different logical protection. Data allowed through another selected alias is included; irreducible overlapping nested roots fail with `多个链接范围的排除规则重叠，请分别创建快照` before a snapshot is written.
- **Restore** never overwrites *or deletes* protected logical paths, even though restores run with `--delete`. Current rules, the source's logical selection evidence, its recorded physical `excludes` projected through the selected roots, and retained restoration-chain exclusions combine before execution.
- **Coverage** (`find_snapshots_covering`, path-filtered listing, self-check freshness) is exclude-aware: a snapshot whose recorded excludes contain the queried path does not count as covering it, while an exclude strictly below the queried path doesn't disqualify the snapshot (`coverage.py`).
- Snapshotting or restoring a target that itself lies under an ignored path raises `TargetIgnoredError` (HTTP 400 before task acceptance).

Application snapshots carry a bounded `mc-admin-logical-v2:` tag containing
logical exclusions and compressed non-identity path mappings. Exact stored
roots also bind identity selections without one tag entry per speculative MCC.
A changed source root link target omits that source from eligible candidates,
including when the request selects a child of an identity root;
an explicit restore fails during source validation before safety backup or
writes. Sources taken over a parent directory retain ordinary subtree coverage.
Historical snapshots and ordinary history without links keep their recorded
paths and exclusions; historical symbolic-link path reinterpretation is outside
the supported compatibility boundary.

## Restore planning

Restic forbids combining `--include` with `--exclude`, so a single include-based
restore cannot protect ignored paths from `--delete`. `build_restore_plan` probes
each unique parent directory once and checks directory targets for empty trees.
It splits the request into Restic steps and explicit empty-selection cleanup:

- **`DirStep`** — a target directory present in the snapshot. Restored subtree-addressed (`restic restore <snap>:<dir> --target <dir> --delete`), with subtree-relative `--exclude` patterns for ignored paths under it. Restic matches restore patterns relative to the subtree root — absolute patterns silently match nothing.
- **`FileStep`** — file targets grouped by parent directory, restored via the parent subtree with `--include /<name>` patterns. `--delete` then only considers included names: an on-disk file missing from the snapshot is deleted, non-included siblings are untouched. Speculative includes of paths in neither place (the world-restore MCC enumeration) are no-ops.
- **`EmptyStep`** — the snapshot explicitly contains an empty target directory, or its parent exists but none of the selected file names exists in that snapshot. Restic can skip deletion when its effective selection is empty. The application therefore deletes only selected live content, preserving the directory root and the union of current and recorded ignored descendants. Unselected siblings and absence markers remain untouched.

Targets whose parent directory is absent from the snapshot are skipped — restic can neither restore them nor traverse-delete there. (Known restic limitation, unchanged from the previous architecture: deletion-by-include cannot reach through directories the snapshot lacks; the chunks restore scope compensates with `mcmap remove-chunks`.)

`SnapshotService` groups selected logical roots by their projected execution exclusions before building Restic steps. It executes plans in two modes: **in-place** (`restore`, `--delete` on, target = source dir) and **staged** (`stage`, no delete, full absolute execution path mirrored under a stage root — callers use `SnapshotProtection.execution_path` before `SnapshotService.stage_destination`). `restore(dry_run=True)` executes the same plan without writing. Status percents are rescaled across steps into one monotonic progress stream, and per-step summaries are merged into a single final `summary` event.

Empty-selection cleanup first checks its complete removal list against the owned
server and selected scope, rejects escaping symlinks and never traverses symlink
directories. It repeats confinement checks during finite cleanup and waits for
that cleanup on cancellation. Preview emits matching `deleted` events without
writing; staged restores retain the original Restic step with deletion disabled,
including when a caller supplies a populated staging destination.

## Event normalization

Restore events arrive as NDJSON (`status` / `verbose_status` / `summary`). Restic reports restored/updated items relative to the restore subtree but deleted items as absolute on-disk paths. `ResticClient.restore` normalizes events to absolute execution paths; `SnapshotService` translates file events into the selected logical path space for previews. File restoration translates those items back to execution paths for PNG-tile invalidation. Stderr is drained concurrently to avoid a pipe-buffer deadlock during long restores.

## Subprocess pattern

All commands run through `ResticClient.binary_path`, which defaults to `settings.restic_binary_path`. That setting comes from `restic_binary_path` / `RESTIC_BINARY_PATH` when configured; otherwise it resolves once at startup from `PATH`, `/usr/local/bin/restic`, then `/usr/bin/restic`. The subprocess env carries `RESTIC_REPOSITORY` and, for protected repos, `RESTIC_PASSWORD`; unprotected repos get `--insecure-no-password`.

## Time-restriction guard

`dynamic_config.snapshots.time_restriction` lets an admin block manual snapshot creation during peak hours — useful when the repo lives on slow shared storage. The HTTP adapter invokes the shared time-window policy before delegating to the application. Scheduled and nested safety backups retain their own admission semantics.

## Path containment

Request-supplied `server_id` and `paths` are joined into filesystem paths, so the snapshots router and the cron backup job validate every resolved path (symlinks followed) with `async_fs.resolve_inside`: the server's project path must stay under the servers root and each sub-path under the server's data directory. Escapes reject with HTTP 400 / a failed job — restore runs with delete semantics, so this is enforced before any restic call.

## Lock interaction

`SnapshotCommands` resolves affected servers and file paths, then
atomically acquires maintenance and `FILES` claims with kind BACKUP. Busy targets
reject conflicting admission or wait within an accepted task; scheduled backups skip busy resources. Whole-root backups declare the
global file root as well as captured generations. Servers can remain running;
these leases coordinate application operations and do not freeze Minecraft writes.

Nested safety backups pass their outer operation's live lease. Every requested
scope must already be covered; a child cannot acquire additional paths or upgrade
a normal file restore into maintenance. Safety planning can explicitly allow
speculative missing sidecars while requiring at least one existing target.
Manual requests retain missing-target validation. Ignored-path, coverage and
restore planning remain shared through `SnapshotService`.

Manual creation uses `POST /snapshots {scope, note?}`. File and world recovery use
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
Versioned history retains selected logical paths, frozen execution mappings and
missing execution ancestors with their logical projections. A dangling internal
directory link can therefore restore its missing real directory; rollback removes
newly created empty real ancestors and preserves the link node. Accepted target
claims cover these ancestors, and scope/mapping evidence is checked after restart.

Every restore owns its target file scope. Whole-server/data targets and paths
intersecting known world roots additionally require stopped servers and maintenance
ownership, the server's `MAP_CACHE` scope and the concrete
`FILES(data/.mcmap/tiles)` cache path; ordinary configuration/plugin/file restores
remain available online.
A normal file restore can run beside world maintenance when their file scopes do
not overlap. Dry-run preview and reads do not acquire these leases. Running/busy
and path checks repeat after acquisition. Invalid unrelated server.properties
values do not prevent recovery: world-name lookup reads only level-name.

Closing observation of a recovery does not stop it. Explicit task cancellation
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

世界执行使用相同的命令、历史和保护规划，mcmap 仅承担区块合并。`preparation.py` 解析目标、实例、缺失范围与源保护，供恢复和预览共用。cron 通过 `SnapshotCommands.backup` 执行同一创建逻辑，不另建手动任务或重复历史；维护冲突记录 `skipped`。备份已完成但保留策略因活动引用被拒绝时，cron 明确记录已创建快照及跳过清理的原因。

## 预览与仓库维护任务

`POST /api/snapshots/previews` 接受相同的 `scope` 与完整 `source_snapshot_id`，返回 202 任务。`snapshots/previews.py` 负责准备、绑定与查询，`preview_sessions.py` 统一心跳、有效期和清理，`world/preview_rendering.py` 只处理地图临时副本及瓦片。预览不创建安全快照，不写入恢复历史或在线目标。

文件预览保存 JSONL 明细，`GET /previews/{id}/actions?cursor=...&limit=...` 每页最多 200 条；响应提供下一页位置，零字节文件和目录动作也保留在明细中。明细总量上限为 64 MiB，单行上限为 32 KiB。超过限制时任务失败并要求缩小范围，不把截断结果当作完整预览。任务结果只含计数、说明和至多 100 个忽略路径。

就绪结果可由 `GET /previews/{id}` 读取，`POST /previews/{id}/heartbeat` 延长有效期。`DELETE /previews/{id}` 返回清理任务，等待读取与渲染退出后才完成。准备中关闭观察不取消任务；显式停止使用通用任务取消接口。每台服务器最多一个活动预览，全局预览同时占用其捕获的服务器集合。重启后结果不可再应用；未知写入者的临时目录和阻断证据仍保留。

带 `preview_id` 恢复时，受理和实际写入前都核对源 ID、规范化范围、服务器代次、当前保护规则和已观测目标版本。版本结合选中目标的文件元数据与相关路径的操作记录；普通在线文件不扫描整棵目录、不承诺外部程序的原子状态。范围外的文件写入不会使预览失效。直接恢复仍可用，安全快照始终捕获执行前的真实状态。

`GET /api/snapshots/usage`、`GET /locks` 为普通读取。`DELETE /{snapshot_id}` 和 `POST /unlock` 返回任务；仓库独占占用从受理保留至所属进程及收尾结束，期间拒绝新的快照依赖。清锁只移除 Restic 判断已失效的锁，不能强制移除活跃锁。

## Snapshot notes

`snapshot_notes` uses the real repository ID returned by `restic cat config` and
the complete 64-character snapshot ID as its composite key. Repository location
or a snapshot's abbreviated ID cannot select a note. Reads obtain the current
repository identity rather than caching a location-derived identity. Notes default
to empty for historical snapshots and contain at most 500 Unicode characters.
Bounded SQL batches project the same note into ordinary lists, eligible sources
and service detail reads; editing uses authenticated `PUT /snapshots/{id}/note`.

Notes belong to the application database and its backups. Their creation and
editing never change Restic tags, IDs, content, restoration evidence or preview
bindings. A manual creation task returning `note_warning` still returns its
created snapshot as a successful content result. The shared creation dialog keeps
that identity visible and offers a separate note save retry. It never resubmits
snapshot creation to repair metadata.

`POST /snapshots/eligible` requires every non-world selected root to be permitted
by the union of current and source protection. A source entirely excluding one
root cannot qualify by covering the others. Exclusions strictly inside selected
directories retain the existing protected-descendant skip behavior.

## Observation and target feedback

`GET /snapshots/targets/rules?server_id=...` returns the current server generation,
rule version and expanded logical relative paths without running Restic or
scanning the file tree. File, search and ordinary snapshot controls share this
result and match literal path ancestry locally. `POST /snapshots/targets/check`
accepts only a world scope and checks confinement and protection without running
Restic or creating history. Fully ignored world scopes are unavailable; mixed
scopes report a bounded skip list and total, including protected MCC logical
counterparts. Both forms provide advisory UI feedback: acceptance and execution
repeat authoritative checks, including source and rollback-chain protection.

`GET /snapshots/restorations/active?server_id=...` reads only the journal and restoration tables. It includes queued, running, cancelling and finalizing work, including global restores targeting the selected server. Offset/limit pagination is bounded to 200 rows per request. History supports `kind`, `status`, `entry_point` and server filters before pagination, and projects all captured server generations. A failed history repository check does not prevent active task observation.

Preview preparation records its session identity in the submitted worker context. Non-successful completion awaits session closure before publishing terminal task status, even if cancellation arrives after a ready result. Unknown writers still retain protected artifacts and block unsafe reuse.
