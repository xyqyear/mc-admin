# MC Admin Backend

FastAPI + SQLAlchemy 2.0 async on Python 3.13+. Manages Minecraft servers running as Docker Compose stacks.

## Commands

```bash
uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 5678 --reload
uv run alembic upgrade head   # optional manual maintenance; startup also migrates
uv run pytest tests/ --require-capabilities
uv run pytest tests/ --run-docker --require-capabilities  # explicit Docker opt-in
uv run pyright
uv run ruff check .
uv run pytest tests/architecture/ -o addopts=''
```

- **Use `uv`**, never `pip`/`venv` directly.
- **Do not run `black`** — formatting is not enforced.
- **Run `uv run pyright` after backend code changes.**
- **Run `uv run ruff check .` after backend code changes.** Ruff is pinned in development dependencies; configuration identifies the shared logger and FastAPI declaration factories without disabling rule families.
- Pydantic models use `model_config = ConfigDict(...)`; preserve field aliases and defaults when changing model configuration.
- Annotate `@asynccontextmanager` generators with `collections.abc.AsyncGenerator[T]`; use `AsyncIterator[T]` for interfaces that only promise iteration.
- **Alembic migrations run during startup** before DB-backed subsystems start; see `docs/database-migrations.md`.
- Tests run with isolated configuration/data roots by default. Capability markers declare Docker, external services and real CLI dependencies; Docker/external cases require explicit opt-in. CI balances four independent runners using whole-file historical costs and explicit `shard_group` fixture boundaries. Plans, exact node-ID union, capability policy and successful setup/call/teardown evidence are audited; `--timing-report` records phase costs and failures. Local `--test-group` selection remains available. See `docs/testing.md`.
- Observable backend feature changes require real API E2E coverage in `../e2e/suites/` and an update to `../e2e/docs/coverage.md`. The standalone runner deploys the current application image; see `../e2e/README.md` and `../e2e/docs/architecture.md` for execution and environment contracts.

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
├── operations/            # journal, resource leases, process ownership and recovery
├── config.py              # TOML + env settings
├── api_schema.py          # stable public OpenAPI names across internal DTO ownership
├── dependencies.py        # DI for sessions, auth, role guards
├── audit.py               # operation audit middleware
├── archive/               # archive resource scopes, atomic publication, resumable uploads and SHA256
├── auth/                  # owned identity service, user persistence/DTOs, cookies, CSRF and login codes
├── db/                    # async engine, declarative base, explicit metadata registration and migrations
├── events/                # public event wire models + in-memory external subscriber bus
├── routers/               # HTTP/WS routers (servers/* per-server endpoints; servers/sync OWNER-only fs↔DB reconciler)
├── servers/               # identity/CRUD, public queries/commands, restart scheduling and lifecycle
├── configuration/         # immutable preparation, versioned state, staged application and source metadata
├── minecraft/             # Docker Compose lifecycle + cgroup v2 monitoring
├── players/               # owned identity/session service, producers, dynamic filters, chat, achievements and skins
├── log_monitor/           # latest.log parsing, watchfiles notifications and idle tail reconciliation
├── files/                 # confined CRUD/search/upload, canonical resource scopes, population and ownership
├── snapshots/             # backup application with parent leases, Restic adapter and scoped restore planner
├── cron/                  # desired plans, scheduler registration/reconciliation and durable execution history
├── self_check/            # owned service/dependencies, isolated checks, retained history and notification sinks
├── dns/                   # desired connectivity, partial observations, incremental provider/router adapters
├── templates/             # server template system (typed variables)
├── dynamic_config/        # schema-versioned runtime config
├── background_tasks/      # owned task workers and durable history projection
├── grid_geometry.py       # shared 4-connected grid components and boundary-ring geometry
├── mcmap/                 # server map: typed mcmap CLI integration, tile cache under data/.mcmap/
├── chunk_prune/           # versioned inputs, retained preview registry, geometry, execution and guarded apply
├── ftb_claims/            # FTB Utilities / FTB Chunks claim extraction via mcmap extract-ftb-claims
├── player_locations/      # saved player-position extraction via mcmap extract-players
├── world/                 # selection planning, scope execution, generation-bound history, preview artifacts and finalization
├── websocket/console.py   # docker attach console
└── utils/                 # async_fs, exec, system, compression, SSE helpers
```

Persistence tables, enums and HTTP DTOs live with their feature. `app.db.base` owns the declarative base and `app.db.metadata` explicitly imports every table for Alembic; domain code imports concrete owners, not a model barrel. Router modules adapt HTTP/WS/SSE and do not own shared business models. Preserve public OpenAPI references through `api_schema.py` where internal type names collide.

## Filesystem I/O — never block the event loop

In `async def`, pick in this order:

1. **`aiofiles`** when it covers the call: `aiofiles.open`, `aiofiles.os.{stat,makedirs,unlink,rename,listdir,...}`, `aiofiles.os.path.{exists,isdir,isfile,...}`.
2. **`app.utils.async_fs`** for everything else (`rmtree`, `copy2`, `copytree`, `move`, `disk_usage`, `copyfileobj`, `chown`, `chmod`, `iterdir`, `resolve`, `touch`, `extract_skin_avatar`).
3. **Subprocess**: `asyncio.create_subprocess_exec`, or `app.utils.exec.{exec_command,exec_command_stream}`.

Adding a wrapper to `async_fs`: only when aiofiles has no equivalent. Use `asyncio.to_thread` directly — do **not** reintroduce `asyncer.asyncify`.

## Background tasks

Long-running operations are async generators yielding `TaskProgress(progress, message, result)`, submitted via `await task_manager.submit_durable(...)` (in `app.background_tasks`). Every `/api/tasks` operation requires a current user; cookie-authenticated mutations also require CSRF protection. The global task center polls summary-only lists; feature pages may use `/api/tasks/{id}` details or server-scoped state endpoints when task visibility must not cross server boundaries. Used by archive compression, server population, server rebuild, file ownership repair and chunk prune.

Cancellation directly interrupts the owned worker, closes nested generators, and waits for registered subprocesses and finite cleanup before publishing a terminal status. The durable journal remains authoritative after late cancellation or restart; interrupted work maps to existing failed task/cron states and is never replayed. Filesystem refusal may leave partial output behind. See `docs/background-tasks.md` and `docs/operations.md`.

World restoration remains a request-owned SSE flow with durable restoration history. Stream closure records interruption, releasing maintenance after confirmed writer termination and required cleanup; uncertain writers retain recovery blocks, and rollback requires an existing safety snapshot and restoration record. See `docs/world-restore.md`.

## Dynamic config

Read runtime-tunable dynamic config at the point of behavior, not in long-lived constructors. Constructor-captured dynamic config needs an explicit refresh/rebuild path.

`create_app(settings=...)` or `create_app(runtime=...)` constructs independent application state. Typed accessors return actual owned resources created by `runtime_factories.py`. `current_runtime()` requires an explicit binding; no module registers a factory or creates an implicit default runtime. Service constructors capture their owning database, configuration view and adapters. Requests, streams and child work bind the owning runtime, and detached side work clears the parent operation context. Use `spawn_background` for application-owned side work, or register workers with a subsystem that is drained by `Runtime.close()`. Startup migrates and reconciles interrupted operations before producers and write admission. Shutdown stops producers and drains writers before clients, previews, database and log handlers. See `docs/runtime.md`.

`BaseConfigSchema.validate_update()` validates authored values before persistence and cache publication. Keep save-time validation separate from legacy configuration loading so invalid historical values remain repairable through the UI.

## Server lifecycle imports

Use `app.servers.commands.ServerCommands` for manual or scheduled lifecycle commands, and `app.servers.queries` for shared reads. Lifecycle orchestration stays in `app.servers.lifecycle`; cron invokes public commands. Domain code cannot depend on routers.

Configuration preparation, versions, staged application and matching metadata belong to `app.configuration`; callers import its owning modules directly. Saves accept optional `expected_version`; conflicts preserve HTTP 409 or task `error_code="configuration_conflict"`. Application preserves the initial running intent and owns source persistence before completion. See `docs/configuration.md`.

Restart scheduling belongs to `app.servers.restart_schedule`. Managed plans bind to retained server generation and purpose; display names never select ownership, and unresolved historical bindings remain visible without reassignment. See `docs/cron.md`. Lifecycle services do not import routers. Shared maintenance state is exposed by `/api/servers/{server_id}/maintenance`; startup/rebuild/cron restart share the mutex. Deletion freezes new writers and rejects unsettled tasks, request-owned restores and map workers before touching metadata or files. Ordinary file restoration remains available while a server runs.

Delayed operations capture `app.servers.references.ServerRef` and revalidate generation and confined paths when acquiring resources. Directory presence alone does not register a server. `app.operations.coordinator` reserves declared resources atomically and validates explicit parent lease reuse; deletion admission freezes separately from execution leases. Operation history is readable by authenticated users; resolving interrupted work requires OWNER authority and fresh ownership/consistency checks.

Journal queries and short write transactions finish cursor consumption, commit or rollback, and session closure before propagating cancellation. Waiting for the journal mutex remains cancellable; cancellation prevents the caller from continuing into external side effects. Request and task entrypoints use `operations.execution.accept_operation` to own a committed record before cancellation or session closure can fail; see `docs/operations.md`.

File writes claim both lexical and canonical paths. Backup applications declare all affected paths and maintenance resources before acquiring a lease; nested safety snapshots reuse that lease without upgrading it. World changes include map-cache ownership, while ordinary online file edits and unrelated paths remain available. Settle writer ownership and recovery blocks before releasing leases. Archive publication uses an owned stage in the destination filesystem; cleanup never guesses ownership from a shared filename prefix.

Live map queues own server cache paths. Preview queues receive an explicit
`PreviewRenderTarget` with real server identity, generation and session directory;
temporary preview output must never be treated as server-project FILES. Each
preview render retains journal/process ownership and its artifact reference until
the writer stops. Global cron backups declare their global FILES scope before
entering the backup application; a busy lease remains a skipped run, not a failed
parent operation. Final upload publication waits for the same archive target and
rechecks existence, preserving the existing concurrent-upload 409 response.

World restoration persists `server_generation` and `binding_issue` through migration `2026092503`; uncertain historical ownership stays readable but cannot target a same-name replacement. `world/selection.py`, `scope_execution.py`, `restoration_store.py`, `finalization.py` and `preview_application.py` isolate planning, adapters, history, cleanup and previews from orchestration. Feature artifacts use installation-scoped directories, active references and journal recovery references. Unknown writers retain their artifacts. Prune applies revalidate mcmap 0.8.4 input versions before acceptance and again under the execution lease; a consumed or expired preview cannot be applied again. See `docs/chunk-prune.md` and `docs/world-restore.md`.

Keep game-port initialization validation at reusable template save and new-server creation boundaries. Legacy reads, snapshot edits, rebuilds, and lifecycle operations use the permissive Compose parser; see `docs/minecraft.md` and `docs/self-check.md`.

Docker and Compose label values may contain equals signs. The shared label parser preserves them so valid labels do not cause lifecycle health checks to report a running container as unready.

## Audit middleware

`app.audit` logs POST/PUT/PATCH/DELETE operations with user context, IP, and request body. Configured `sensitive_fields` substrings (default `password`, `token`, `secret`, `key`) and `sensitive_exact_fields` names (default `ak`, `sk`, `code`, `ticket`) are masked recursively in JSON and form fields; Opaque `yaml_content`, `yaml_template`, and `content` fields are always masked without parsing their contents; unstructured bodies retain only content type and size. Configured via `[audit]` in `config.toml`. Login-code values are excluded from ordinary application logs.

## Public errors and logs

`app/main.py` flattens validation errors into a string `detail`. Explicit HTTP exceptions preserve string or structured `detail` and headers. Unexpected HTTP failures return a generic Chinese 500; SQL parameter logging is disabled and parameters are hidden in SQL exceptions. `app.errors` owns safe failure messages/logging for HTTP, task and snapshot SSE boundaries. Only explicitly authored `PublicOperationError` messages are public; ordinary exceptions use the generic message. Preserve the existing string task/SSE fields when representing structured detail. Do not log raw credentials, exception values, request query strings or headers.

## Design background

Long-form, current-state design docs live under `backend/docs/`:

- `docs/administration-contracts.md` — user journeys, wire/deployment contracts and regression owners
- `docs/testing.md` — isolated fixtures, capability inventory, migration/API fixtures and workloads
- `docs/workload-measurements.md` — fixed-binary and deployed HTTP comparisons, content/request checks and measured process ownership overhead
- `docs/servers.md` — DB-driven server discovery, bundled lifecycle orchestrators, filesystem↔DB sync endpoint
- `docs/database-migrations.md` — Alembic startup gate, supported DB states, revision IDs
- `docs/minecraft.md` — Docker Compose lifecycle, `MCInstance`, compose validation, cgroup v2 monitoring
- `docs/player-identity.md` — usercache-first identity resolution, v4 UUID gates, Mojang fallback
- `docs/players.md` — owned identity/session service, producers and DB models
- `docs/log-monitor.md` — watchfiles tail loop, regex chain and shared player-service dispatch
- `docs/files.md` — file CRUD helpers, session-based multi-file upload, `fd`-backed deep search
- `docs/archive-upload.md` — resumable archive upload protocol, temp files, offset handling, SHA256 SSE
- `docs/snapshots.md` — restic client, ignored paths (`<LEVEL_NAME>`), restore planner, retention, lock interaction
- `docs/cron.md` — APScheduler integration, registry metadata, system jobs, built-in jobs
- `docs/self-check.md` — check catalog, triggers, persistence, notification extension point
- `docs/dns.md` — DNSPod / Huawei providers, mc-router sync, reconciliation flow
- `docs/templates.md` — variable definitions, `TemplateSnapshot`, two-mode editing, conversion
- `docs/configuration.md` — immutable preparation, optional version checks, staged application, source consistency and recovery
- `docs/dynamic-config.md` — schema-versioned runtime config with Pydantic migration
- `docs/runtime.md` — independent app construction, lifecycle ownership, failure cleanup and isolation tests
- `docs/operations.md` — durable operation journal, resource ownership, recovery blocks and resolution API
- `docs/background-tasks.md` — async-generator task manager, `TaskProgress` pattern
- `docs/server-map.md` — `app.mcmap` rendering pipeline, palette currency, render queue, cancellation
- `docs/ftb-claims.md` — `app.ftb_claims` mcmap subprocess, dim resolution, clustering, no-cache rationale
- `docs/player-locations.md` — `app.player_locations`, saved positions, dim resolution, profile cache fallback
- `docs/world-restore.md` — `app.world` scopes, locks, safety snapshots, preview sessions, crash recovery
- `docs/chunk-prune.md` — `app.chunk_prune`, server-level prune-inhabited tasks, terminal preview geometry, FTB-claim protection
- `docs/websocket-console.md` — docker-py attach socket bridge, message protocol
- `docs/auth.md` — JWT cookies, CSRF, password login, master token, WebSocket-code login flow
- `docs/audit.md` — middleware, sensitive-field masking, log rotation
- `docs/bot-integration-apis.md` — external automation APIs: RCON, in-game messages, event stream, server overview

Add a `docs/<topic>.md` whenever a new system has design rationale (business logic, invariants, lifecycle ordering) that doesn't fit on one line in this file. Each doc is self-contained and reflects current state — no changelog, no "previously…" notes.

## Keeping this file in sync

When changing function signatures, module structure, or any project-wide convention or invariant, update this file in the same commit:

- **Reflect current state, not history.** Rewrite the affected sentence as if it were the original — no "added X", "now does Y", "previously was Z" notes.
- **Stay terse.** Most changes don't need a new section. Edit the existing sentence; replace the rule that changed; don't append paragraphs explaining a one-line change.
- **Drop what's no longer true.** Remove the corresponding text when code is removed or replaced.
- **Promote design depth to `docs/`.** If a change adds rationale, business logic, or new invariants too long for the module map, write or extend `docs/<topic>.md`. Keep CLAUDE.md focused on day-to-day rules and module orientation.
- **One source of truth.** Don't duplicate facts between CLAUDE.md and `docs/`. If a rule belongs in CLAUDE.md (project-wide convention), the doc references it; if it's design depth, this file points to the doc.

## External documentation

Use the Context7 MCP tool: `/tiangolo/fastapi`, `/websites/sqlalchemy-en-20`, `/pydantic/pydantic`, `/restic/restic`. Resolve library id first, then fetch with a topic.
