# Server Core (`app.servers`)

Owns the DB-side view of managed servers: the `Server` table (CRUD with REMOVED tombstones), port-conflict checks, the bundled create/remove orchestrators, and the filesystem↔DB sync endpoint.

## Two sources of truth, deliberately split

- **DB is the source of truth for "servers we manage."** The overview list (`GET /servers/`), DNS reconciliation, and the startup log-monitor loop enumerate via `get_active_servers(db)` and per-row read each server's compose. An `ACTIVE` row whose compose has drifted (file missing / unreadable) is filtered out at the consumer (per-row try/except for the overview; warning-and-skip for DNS). The sync endpoint deactivates drifted rows.
- **Filesystem is the source of truth for "what's actually on disk."** The sync endpoint and port-conflict checks (`port_utils.get_server_used_ports`, `GET /templates/ports/available`) enumerate via `docker_mc_manager.get_all_server_names()` — port collisions are a kernel/Docker reality and orphan directories must still count.
- **Single-server operations** (`compose`, `files`, `operations`, `resources`, ...) go through `docker_mc_manager.get_instance(server_id)` with an explicit `instance.exists()` check returning 404 if missing.

## Bundled lifecycle (`app.servers.lifecycle`)

The frontend issues one round-trip per high-level action; the orchestrators chain the underlying primitives.

- `create_server_full(db, server_id, spec)` — validates the spec, writes the compose tree, inserts the `Server` row, starts the log monitor, optionally creates a restart cron job from a bundled `RestartScheduleRequest`, and triggers a single DNS update at the tail. Failure after the filesystem write rolls back by compensation in reverse order (cancel cronjob → stop log monitor → mark row `REMOVED` → rmtree). DNS update failures are non-fatal.
- `remove_server_full(db, server_id)` — refuses with 409 if containers are still up (uses public `instance.created()`), then `cancel_and_wait_for_tasks` so an in-flight `ARCHIVE_EXTRACT` cannot race the rmtree, cancels restart cronjobs (not backup jobs — those are admin state), closes open player sessions, stops the log monitor, marks the row `REMOVED`, rmtrees the directory, and triggers DNS. Once past the containers-up gate, partial failures are *not* rolled back — removal is destructive by design.
- `adopt_server_partial` / `deactivate_server_partial` — primitives used by the sync endpoint. Adopted rows are direct-mode only; template binding can't be inferred from a compose file alone.
- `validate_adoption(db, server_id)` — side-effect-free; shared between the sync dry-run preview and the apply path so the two cannot diverge.

Lifecycle is **not transactional**. Each primitive issues its own commit; rollback is compensation, documented at the top of `orchestrators.py`. Lifecycle code touches only the public `MCInstance` surface — no `_compose_manager` reach-arounds.

## Sync endpoint

`POST /api/servers/sync` (OWNER-only) reconciles filesystem directories vs `ACTIVE` `Server` rows. Body supports `dry_run=true` (preview only — returns the same `SyncResult` shape but `applied=false`) and `force=true` (bypass the empty-filesystem safety guard that would otherwise refuse to deactivate every row when the mount fails). Concurrent calls return 409 immediately rather than queuing on the internal `asyncio.Lock`. Each apply batch ends with a single DNS update.

## Module layout

```text
servers/
├── crud.py             # Server-row CRUD (append-only; REMOVED is a tombstone, not a delete)
├── port_utils.py       # extract_ports_from_yaml, check_port_conflicts
├── rebuild.py          # SERVER_REBUILD background task
└── lifecycle/
    ├── types.py        # CreateServerSpec, CreateServerResult, RemoveServerResult, SyncResult
    ├── primitives.py   # cancel_and_wait_for_tasks, cron lookups, validate_adoption
    └── orchestrators.py # create_server_full, remove_server_full, adopt/deactivate partials
```
