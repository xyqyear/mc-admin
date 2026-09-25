# Server Core (`app.servers`)

Owns the DB-side view of managed servers: the `Server` table (CRUD with REMOVED tombstones), port-conflict checks, the bundled create/remove orchestrators, and the filesystem↔DB sync endpoint.

## Two sources of truth, deliberately split

- **DB is the source of truth for "servers we manage."** The overview list (`GET /servers/`), DNS reconciliation, and the startup log-monitor loop enumerate via `get_active_servers(db)` and per-row read each server's compose. An `ACTIVE` row whose compose has drifted (file missing / unreadable) is filtered out at the consumer (per-row try/except for the overview; warning-and-skip for DNS). The sync endpoint deactivates drifted rows.
- **Filesystem is the source of truth for "what's actually on disk."** The sync endpoint and port-conflict checks (`port_utils.get_server_used_ports`, `GET /templates/ports/available`) enumerate via `docker_mc_manager.get_all_server_names()` — port collisions are a kernel/Docker reality and orphan directories must still count.
- **Single-server operations** retain public name-based URLs. Delayed writes resolve a registered active `ServerRef` and revalidate it before mutation; Compose reads combine the active record with the confined canonical file in `app.configuration.state`. Docker adapters still provide instance existence checks where needed.

## Bundled lifecycle (`app.servers.lifecycle`)

The frontend issues one round-trip per high-level action; the orchestrators chain the underlying primitives.

- `create_server_full(db, server_id, spec)` — validates the spec, writes the compose tree, inserts the `Server` row, starts the log monitor, optionally creates a restart cron job from a bundled `RestartScheduleRequest`, and triggers a single DNS update at the tail. Failure after the filesystem write rolls back by compensation in reverse order (cancel cronjob → stop log monitor → mark row `REMOVED` → rmtree). DNS update failures are non-fatal.
- `remove_server_full(db, server_id)` — freezes write admission, refuses with 409 if containers still exist, and cancels/waits for admitted background tasks. A 30-second timeout returns 409 without removing data or changing lifecycle metadata. Request-owned restores and direct file/configuration writes must also finish; otherwise deletion returns 423. Only after drain and a repeated container check does it cancel restart cronjobs, close sessions, stop the log monitor, mark the row `REMOVED`, remove the directory and reconcile DNS. Failures after these safety checks are not transactionally rolled back.
- `adopt_server_partial` / `deactivate_server_partial` — primitives used by the sync endpoint. Adopted rows are direct-mode only; template binding can't be inferred from a compose file alone.
- `validate_adoption(db, server_id)` — side-effect-free; shared between the sync dry-run preview and the apply path so the two cannot diverge.

Lifecycle is **not transactional**. Each primitive issues its own commit; rollback is compensation, documented at the top of `orchestrators.py`. Lifecycle code touches only the public `MCInstance` surface — no `_compose_manager` reach-arounds.

## Sync endpoint

`POST /api/servers/sync` (OWNER-only) reconciles filesystem directories vs `ACTIVE` `Server` rows. Body supports `dry_run=true` (preview only — returns the same `SyncResult` shape but `applied=false`) and `force=true` (bypass the empty-filesystem safety guard that would otherwise refuse to deactivate every row when the mount fails). Concurrent calls return 409 immediately rather than queuing on the internal `asyncio.Lock`. Each apply batch ends with a single DNS update.

## Module layout

```text
servers/
├── crud.py             # Server-row CRUD (append-only; REMOVED is a tombstone, not a delete)
├── references.py       # Immutable active-instance identity and delayed-operation revalidation
├── port_utils.py       # extract_ports_from_yaml, check_port_conflicts
├── commands.py         # Public lifecycle commands shared by HTTP and cron
├── queries.py          # Shared server list read model
├── rebuild.py          # Compatibility task entrypoint for app.configuration.application
├── restart_schedule.py # Generation-bound server-managed restart plans
└── lifecycle/
    ├── types.py        # CreateServerSpec, CreateServerResult, RemoveServerResult, SyncResult
    ├── primitives.py   # cancel_and_wait_for_tasks, cron lookups, validate_adoption
    └── orchestrators.py # create_server_full, remove_server_full, adopt/deactivate partials
```

## Restart scheduling boundary

`app.servers.restart_schedule` owns the restart-plan request/result models and create/update/resume orchestration shared by lifecycle creation and the HTTP endpoint. Lifecycle services do not import router modules. `CronManager` continues to own stored jobs and scheduler operations.

Managed plans bind to `Server.id` and purpose rather than display names. Same-name
recreation cannot inherit or execute a retained old plan. Historical ambiguity is
reported without reassigning records; independent cron jobs stay independent.
Deletion cancels the current generation's active plan and matching active
independent restart tasks, preserving ambiguous and explicitly old bindings. See
[cron](cron.md) for migration and review procedures.

## Configuration boundary

`app.configuration` owns immutable preparation, versioned configuration reads,
staging/replacement and matching source-metadata application. Rebuilds preserve
the initial running intent and carry durable failure/recovery evidence. Both
Compose/template saves and metadata-only mode conversions share this boundary;
they do not write metadata from task-completion callbacks. See
[configuration](configuration.md) for optimistic version checks, short metadata
transactions and the limits of atomic replacement across filesystem/SQLite/Docker.

## Write admission and maintenance

`app.operation_admission` separates deletion admission from the execution mutex. Deletion closes admission before collecting tasks, then waits without holding a mutex needed by those tasks. Server-linked task submission and request-scoped file/configuration/restore writes reject a frozen server. Request ownership lasts through SSE closure; generic global restores count as global writers. All failure/cancellation paths release the freeze, permitting a deliberate retry. `/maintenance` reports kind `remove` while deletion drains.

`app.world.locks` exposes maintenance ownership through the runtime's operation
coordinator for backup, restore, prune, startup and rebuild. Rebuild routes reject
an existing holder with 423 and the worker rechecks ownership before any
Docker/configuration mutation. The lease remains held through metadata save,
restoring the original running intent and necessary failure reconciliation.
Scheduled restart uses the same ownership and records a skipped execution when
busy or stopped. The coordinator admits declared maintenance, file paths, map
cache, archive and shared port-allocation resources atomically; nested operations
may reuse an existing lease without expanding its scope. File and maintenance
claims remain separate so online file writes/restores retain their existing
behavior. Deletion covers all server write resources after admission is frozen
and earlier writers have drained.

## Instance references and path ownership

`resolve_server_ref(db, server_id, servers_root=...)` returns an immutable
`ServerRef` containing the public name, persistent `generation` (`Server.id`),
canonical configured root and constrained project/data paths. `server_db_id`
and `incarnation` are aliases of the same generation. Resolution requires an
existing ACTIVE row; a directory alone never registers or reactivates a server.
Missing registration/project returns 404, while inactive or ambiguous identity
returns 409 with a recovery instruction. `require_exists=False` permits checking
an active record whose files disappeared, without relaxing name/path boundaries.

Delayed work retains its resolved reference and calls `revalidate_server_ref`
after resource acquisition and before mutation. The query reads current column
values, including when the caller's ORM identity map contains an old row.
Deleting and explicitly recreating/adopting the same name yields a new ID;
old references cannot act on it. History keeps its original IDs and remains
readable. Managed restart plans persist this generation explicitly. Historical
restoration references are not automatically reassigned by server resolution.

`app.minecraft.paths` validates one literal Linux path component, preserving
safe historical spaces, Unicode, punctuation and backslashes. It rejects empty,
dot, dot-dot, slash-containing and NUL-containing names. The configured server
root may itself be a symlink. Individual project directories cannot alias a
different directory through a symlink; data links may resolve inside their own
project but cannot escape it or alias the project root. Compose and properties
files have their own confinement checks. MCInstance checks asynchronously before
filesystem and Docker operations; file rename/unlink still use the lexical path
so they operate on the symlink itself.

Creation and explicit adoption share the global port-allocation lease through
validation, DB persistence and compensation. Creation refuses pre-existing
project directories even without Compose, so its failure cannot delete older
user data. Adoption rechecks its preview's ports while holding the lease and
always creates a fresh row. A cancelled creation waits for the initial file/DB
write to settle before compensating, and retains its lease through mandatory
cleanup. Cleanup attempts every step; any failure reports the affected server
and remaining cleanup categories instead of claiming successful cleanup.
