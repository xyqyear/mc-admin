# Backend architecture

This document maps production modules and dependency direction. Day-to-day
commands and constraints belong to [backend instructions](../AGENTS.md);
[the topic index](README.md) routes feature-specific work.

## Application boundaries

`create_app` composes an independent runtime and mounts the authenticated API.
The production root application also serves the built SPA. Requests, streams,
background workers and CLI operations bind an explicit runtime; see
[runtime ownership](runtime.md).

Features own persistence, DTOs, queries and commands. Routers adapt public
protocols to those owners. The operation journal coordinates consequential work;
feature workers implement it. Snapshot commands own common recovery contracts,
while world modules adapt selection and chunk execution. The frontend consumes
public APIs and operation changes; E2E observes an independently deployed image.

## Module map

```text
app/
├── main.py                # create_app factory, compatibility entrypoints and mounted API
├── runtime.py             # per-application resources and ordered startup/shutdown
├── runtime_factories.py   # explicit construction of actual owned resources
├── runtime_resources.py   # required context binding and tracked background work
├── runtime_http.py        # HTTP/WS/SSE runtime binding and request draining
├── runtime_logging.py     # application-owned log handlers
├── errors.py              # safe public errors and exception logging
├── operation_admission.py # deletion freeze and active writer accounting
├── operations/            # journal, bounded refresh notifications, resource leases and recovery
├── config.py              # TOML + env settings; directory roots resolved on load
├── api_schema.py          # stable public OpenAPI names across internal DTO ownership
├── dependencies.py        # DI for sessions, auth, role guards
├── audit.py               # operation audit middleware
├── archive/               # archive resource scopes, atomic publication, resumable uploads and SHA256
├── auth/                  # owned identity service, user persistence/DTOs, cookies, CSRF and login codes
├── db/                    # async engine, declarative base, explicit metadata registration and migrations
├── events/                # public event wire models + in-memory external subscriber bus
├── routers/               # HTTP/WS routers; servers/sync is OWNER-only task submission
├── servers/               # identity/CRUD, commands, restart scheduling, lifecycle tasks and fs↔DB reconciliation
├── configuration/         # immutable preparation, versioned state, staged application and source metadata
├── minecraft/             # Docker Compose lifecycle + cgroup v2 monitoring
├── players/               # owned identity/session service, producers, dynamic filters, chat, achievements and skins
├── log_monitor/           # latest.log parsing, watchfiles notifications and idle tail reconciliation
├── files/                 # confined CRUD/search/upload, canonical resource scopes, population and ownership
├── snapshots/             # scoped task commands, restoration history, protection, Restic planning and adapters
├── cron/                  # desired plans, scheduler registration/reconciliation and durable execution history
├── self_check/            # owned service/dependencies, isolated checks, retained history
├── dns/                   # desired connectivity, partial observations, incremental provider/router adapters
├── templates/             # server template system (typed variables)
├── dynamic_config/        # schema-versioned runtime config
├── background_tasks/      # owned task workers and durable history projection
├── grid_geometry.py       # shared 4-connected grid components and boundary-ring geometry
├── mcmap/                 # server map: typed mcmap CLI integration, tile cache under data/.mcmap/
├── chunk_prune/           # versioned inputs, retained preview registry, geometry, execution and guarded apply
├── ftb_claims/            # FTB Utilities / FTB Chunks claim extraction via mcmap extract-ftb-claims
├── player_locations/      # saved player-position extraction via mcmap extract-players
├── world/                 # selection planning, selected chunk merging, preview rendering and cache finalization
├── websocket/console.py   # docker attach console
└── utils/                 # async_fs, exec, system, compression, SSE helpers
```

Persistence tables, enums and HTTP DTOs live with their feature. `app.db.base` owns the declarative base and `app.db.metadata` explicitly imports every table for Alembic; domain code imports concrete owners, not a model barrel. Router modules adapt HTTP/WS/SSE and do not own shared business models. Preserve public OpenAPI references through `api_schema.py` where internal type names collide.

## Executable boundaries and verification

`tests/architecture/test_import_boundaries.py` checks dependency direction.
Runtime isolation, resource ownership and observable behavior need their own
integration tests; passing an import check does not establish those properties.
See [testing](testing.md) for fixture ownership and targeted selection.

Use the [administration contracts](administration-contracts.md) when a change
crosses API, persistence or deployment compatibility. Startup/shutdown ordering
belongs to [runtime](runtime.md), operation evidence to [operations](operations.md),
and interruption handling to [recovery](operation-recovery.md).
