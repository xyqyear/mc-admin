# MC Admin Backend

FastAPI + SQLAlchemy 2.0 async on Python 3.13+. Manages Minecraft servers running as Docker Compose stacks.

## Commands

Run local pytest only for files, nodes, or small directories directly related to the change. Choose the matching example below; they are not a checklist to run together. Complete backend collection and execution, including its full shard plan, belong to GitHub Actions on the latest committed SHA. Do not reproduce a full local suite by splitting directories, looping shards, or delegating portions to other agents.

```bash
uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 5678 --reload
uv run alembic upgrade head   # optional manual maintenance; startup also migrates
uv run pytest tests/files/test_file_operations.py --require-capabilities
uv run pytest tests/test_instance.py::test_server_status_lifecycle_with_docker --run-docker --require-capabilities
uv run pyright
uv run ruff check .
# For changes to module boundaries or architecture rules.
uv run pytest tests/architecture/ -o addopts=''
```

- **Use `uv`**, never `pip`/`venv` directly.
- **Do not run `black`** — formatting is not enforced.
- **Run `uv run pyright` after backend code changes.**
- **Run `uv run ruff check .` after backend code changes.** Ruff is pinned in development dependencies; configuration identifies the shared logger and FastAPI declaration factories without disabling rule families.
- Pydantic models use `model_config = ConfigDict(...)`; preserve field aliases and defaults when changing model configuration.
- Annotate `@asynccontextmanager` generators with `collections.abc.AsyncGenerator[T]`; use `AsyncIterator[T]` for interfaces that only promise iteration.
- **Alembic migrations run during startup** before DB-backed subsystems start; see `docs/database-migrations.md`.
- Tests run with isolated configuration/data roots by default. Capability markers declare Docker, external services and real CLI dependencies; Docker/external cases require explicit opt-in. CI restores the latest comparable audited phase history across trusted repository branches and plans up to 32 shards for a 300-second execution target, with at most 16 independent runners. Whole files and explicit `shard_group` fixture boundaries remain indivisible; oversized units and capacity limits are reported without shortening deadlines or dropping tests. Plans, exact node-ID union, capability policy and successful setup/call/teardown evidence are audited before publishing reusable timing history. Local `--test-group` selection remains available for a directly related group, subject to the same scope restriction. See `docs/testing.md`.
- Mark only tests that invoke a real binary. Test-owned managers stop in fixture teardown or `finally` before their database/runtime patches close. Streaming tests gate process completion until intermediate progress is observed; elapsed time and final progress alone do not establish streaming.
- WebSocket input and resize tests wait for a subsequent processed-message response before reading adapter effects. Tests of process cancellation hold an owned live process until cancellation and verify reaping before completion; persistence tests read committed state through a fresh session.
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
├── world/                 # selection planning, protected chunk merging, preview rendering and cache finalization
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

Long-running operations are async generators yielding `TaskProgress(progress, message, result)`, submitted via `await task_manager.submit_durable(...)` (in `app.background_tasks`). Every `/api/tasks` operation requires a current user; cookie-authenticated mutations also require CSRF protection. The global task center polls summary-only lists; feature pages may use `/api/tasks/{id}` details or server-scoped state endpoints when task visibility must not cross server boundaries. Lifecycle/create/sync, file/archive deletion, map initialization, manual self-check/DNS and upload hashing/publication return 202 task acceptance; compression, population, rebuild, ownership repair and chunk prune retain their existing task contracts. The operation inventory and blocking rules are in `docs/non-snapshot-operations.md`.

Cancellation directly interrupts the owned worker, closes nested generators, and waits for registered subprocesses and finite cleanup before publishing a terminal status. The durable journal remains authoritative after late cancellation or restart; interrupted work maps to existing failed task/cron states and is never replayed. Task result payloads are journaled before publication and loaded only for detail reads, including after dismissal or restart. Population prepares a complete data tree and atomically exchanges directories on the same Linux filesystem; failure before publication preserves original data. Other filesystem writes may leave partial output behind. See `docs/background-tasks.md`, `docs/files.md` and `docs/operations.md`.

Manual snapshot creation and file/world restore/rollback return common durable tasks. `snapshots/commands.py` owns accepted target/repository references, safety evidence before writes and terminal history hooks. `snapshots/queries.py` projects authoritative journal state and rollback availability. File recovery history is available under `/snapshots/restorations`; the synchronous file restore route is absent. World and file recovery use the same acceptance, protection, safety evidence, rollback and history boundary. Closing an observer does not cancel execution. Explicit task cancellation releases maintenance only after confirmed writer termination and cleanup; uncertain writers retain recovery blocks. File/map preview tasks and lifetime belong to `snapshots/previews.py` and `preview_sessions.py`; `world/preview_rendering.py` owns map copies and rendering. See `docs/world-restore.md`.

## Dynamic config

Read runtime-tunable dynamic config at the point of behavior, not in long-lived constructors. Constructor-captured dynamic config needs an explicit refresh/rebuild path.

`create_app(settings=...)` or `create_app(runtime=...)` constructs independent application state. Concrete typed runtime properties lazily construct owned resources through `runtime_factories.py`; disabled optional resources retain `None` independently of uninitialized fields. Typed accessors return those properties. `current_runtime()` requires an explicit binding; no module registers a factory or creates an implicit default runtime. Service constructors capture their owning database, configuration view and adapters. Requests, streams and child work bind the owning runtime, and detached side work clears the parent operation context. Use `spawn_background` for application-owned side work, or register workers with a subsystem that is drained by `Runtime.close()`. Startup migrates and reconciles interrupted operations before producers and write admission. Shutdown stops producers and drains writers before clients, previews, database and log handlers. See `docs/runtime.md`.

`BaseConfigSchema.validate_update()` validates authored values before persistence and cache publication. Keep save-time validation separate from legacy configuration loading so invalid historical values remain repairable through the UI.

`Settings` resolves `static_path`, `cgroup_path`, `server_path`, `logs_dir` and `archive_path` to absolute paths when loaded, including defaults and symbolic links. Relative directories use the process working directory, not the configuration file's directory. Binary command names, database URLs and Restic repository addresses retain their own semantics.

## Server lifecycle imports

Use `app.servers.commands.ServerCommands` for manual or scheduled lifecycle commands, and `app.servers.queries` for shared reads. Lifecycle orchestration stays in `app.servers.lifecycle`; cron invokes public commands. Domain code cannot depend on routers.

Configuration preparation, versions, staged application and matching metadata belong to `app.configuration`; callers import its owning modules directly. Saves accept optional `expected_version`; conflicts preserve HTTP 409 or task `error_code="configuration_conflict"`. Application preserves the initial running intent and owns source persistence before completion. See `docs/configuration.md`.

Restart scheduling belongs to `app.servers.restart_schedule`. Managed plans bind to retained server generation and purpose; display names never select ownership, and unresolved historical bindings remain visible without reassignment. See `docs/cron.md`. Lifecycle services do not import routers. Shared maintenance state is exposed by `/api/servers/{server_id}/maintenance`; startup/rebuild/cron restart share the mutex. Accepted, queued and executing snapshot tasks reject deletion with HTTP 423 and a task ID, including global scopes. The check runs before cancellation of other work and inside deletion freeze/exclusion. Deletion freezes new writers, cancels and drains server tasks, and rejects remaining request-owned writes and map workers before touching metadata or files. Ordinary file restoration remains available while a server runs.

Delayed operations capture `app.servers.references.ServerRef` and revalidate generation and confined paths when acquiring resources. Directory presence alone does not register a server. `app.operations.coordinator` reserves declared resources atomically and validates explicit parent lease reuse; deletion admission freezes separately from execution leases. Operation history is readable by authenticated users; resolving interrupted work requires OWNER authority and fresh ownership/consistency checks.

Journal queries, short write transactions and `operations.context.revalidate_targets` finish cursor consumption, commit or rollback, and session closure before propagating cancellation. Task startup and resource-lease revalidation cannot leave a SQLite reader blocking terminal journal writes. Waiting for the journal mutex remains cancellable; cancellation prevents the caller from continuing into external side effects. Request and task entrypoints use `operations.execution.accept_operation` to own a committed record before cancellation or session closure can fail; see `docs/operations.md`.

File writes claim both lexical and canonical paths. File and archive deletion reject active scope conflicts and recovery blocks before accepting a task; workers reacquire resources before writing. Backup applications declare all affected paths and maintenance resources before acquiring a lease; nested safety snapshots reuse that lease without upgrading it. World changes include map-cache ownership, while ordinary online file edits and unrelated paths remain available. Settle writer ownership and recovery blocks before releasing leases. Archive publication uses an owned stage in the destination filesystem and never replaces an existing destination; cleanup never guesses ownership from a shared filename prefix. Compression names use the server and validated browser-local `client_timestamp`, with a server-local fallback for legacy API callers and numeric collision suffixes.

Live map queues own server cache paths. Preview queues receive an explicit
`PreviewRenderTarget` with real server identity, generation and session directory;
temporary preview output must never be treated as server-project FILES. Each
preview render retains journal/process ownership and its artifact reference until
the writer stops. Global cron backups declare their global FILES scope before
entering the backup application; a busy lease remains a skipped run, not a failed
parent operation. Final upload publication waits for the same archive target and
rechecks existence, preserving the existing concurrent-upload 409 response.

Restoration evidence belongs to `snapshots/restoration_models.py` and `restoration_store.py`, with shared selection contracts and startup reconciliation in `snapshots`. Migration `2026093000` preserves world history and generation bindings while adding versioned scopes, target references, protection and operation/rollback associations. Uncertain historical ownership stays readable but cannot target a same-name replacement. `world/selection.py`, `scope_execution.py`, `finalization.py` and `preview_rendering.py` isolate world planning, adapters, cleanup and previews. Repository references protect executing snapshots and valid file/map previews from destructive maintenance. Feature artifacts use installation-scoped directories, active references and journal recovery references. Unknown writers retain their artifacts. Prune applies revalidate mcmap 0.8.4 input versions before acceptance and again under the execution lease; a consumed or expired preview cannot be applied again. See `docs/chunk-prune.md` and `docs/world-restore.md`.

Keep game-port initialization validation at reusable template save and new-server creation boundaries. Legacy reads, snapshot edits, rebuilds, and lifecycle operations use the permissive Compose parser; see `docs/minecraft.md` and `docs/self-check.md`.

Docker and Compose label values may contain equals signs. The shared label parser preserves them so valid labels do not cause lifecycle health checks to report a running container as unready.

## Audit middleware

`app.audit` logs POST/PUT/PATCH/DELETE operations with user context, IP, and request body. Configured `sensitive_fields` substrings (default `password`, `token`, `secret`, `key`) and `sensitive_exact_fields` names (default `ak`, `sk`, `code`, `ticket`) are masked recursively in JSON and form fields; Opaque `yaml_content`, `yaml_template`, and `content` fields are always masked without parsing their contents; unstructured bodies retain only content type and size. Configured via `[audit]` in `config.toml`. Login-code values are excluded from ordinary application logs.

## Public errors and logs

`app/main.py` flattens validation errors into a string `detail`. Explicit HTTP exceptions preserve string or structured `detail` and headers. Unexpected HTTP failures return a generic Chinese 500; SQL parameter logging is disabled and parameters are hidden in SQL exceptions. `app.errors` owns safe failure messages/logging for HTTP, task and remaining request-stream boundaries. Only explicitly authored `PublicOperationError` messages are public; ordinary exceptions use the generic message. Preserve the existing string task/SSE fields when representing structured detail. Do not log raw credentials, exception values, request query strings or headers.

## Design background

Long-form, current-state design docs live under `backend/docs/`:

- `docs/administration-contracts.md` — user journeys, wire/deployment contracts and regression owners
- `docs/testing.md` — isolated fixtures, capability inventory, world recovery regression ownership, migration/API fixtures
- `docs/servers.md` — DB-driven server discovery, bundled lifecycle orchestrators, filesystem↔DB sync endpoint
- `docs/database-migrations.md` — Alembic startup gate, supported DB states, revision IDs
- `docs/minecraft.md` — Docker Compose lifecycle, `MCInstance`, compose validation, cgroup v2 monitoring
- `docs/player-identity.md` — usercache-first identity resolution, v4 UUID gates, Mojang fallback
- `docs/players.md` — owned identity/session service, producers and DB models
- `docs/log-monitor.md` — watchfiles tail loop, regex chain and shared player-service dispatch
- `docs/files.md` — file CRUD helpers, batch deletion, bounded generation-bound download manifests, multi-path compression, upload sessions and `fd`-backed deep search
- `docs/archive-upload.md` — resumable archive upload protocol, temp files, offset handling, SHA256 and publication tasks
- `docs/snapshots.md` — Restic identity, SQLite snapshot notes, ignored paths (`<LEVEL_NAME>`), restore planner, retention and lock interaction
- `docs/cron.md` — APScheduler integration, registry metadata, system jobs, built-in jobs
- `docs/self-check.md` — check catalog, triggers, persistence, notification extension point
- `docs/dns.md` — DNSPod / paginated Huawei providers, guarded CNAME replacement, mc-router sync and independent partial reconciliation
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
- **Promote design depth to `docs/`.** If a change adds rationale, business logic, or new invariants too long for the module map, write or extend `docs/<topic>.md`. Keep AGENTS.md focused on day-to-day rules and module orientation.
- **One source of truth.** Don't duplicate facts between AGENTS.md and `docs/`. If a rule belongs in AGENTS.md (project-wide convention), the doc references it; if it's design depth, this file points to the doc.

## External documentation

Use the Context7 MCP tool: `/tiangolo/fastapi`, `/websites/sqlalchemy-en-20`, `/pydantic/pydantic`, `/restic/restic`. Resolve library id first, then fetch with a topic.

`servers/tasks.py`, `servers/synchronization.py`, `mcmap/initialization.py`, `self_check/tasks.py` and `dns/tasks.py` own detached non-snapshot execution. File/archive applications submit deletion; archive uploads coordinate hashing/publication input with task lifetime. New management routes return 202 task acceptance; obsolete execution SSE routes are absent. See `docs/non-snapshot-operations.md`.

Snapshot target rules (`GET /snapshots/targets/rules?server_id=...`) expose generation-bound logical relative exclusions for shared file/search UI decisions; ignore matching never follows links. `POST /snapshots/targets/check` accepts only world scopes and checks protection including MCA/MCC coupling. Both avoid Restic and task/history creation. Snapshot scopes retain logical identities, frozen execution mappings and claims for both paths; execution and history revalidate those bindings. Bounded logical tags preserve source protection, while missing real ancestors retain logical cleanup projections. See `docs/snapshots.md`. Active restoration discovery (`GET /snapshots/restorations/active`) uses the journal and retained global target identities, so observation works while the repository is unavailable. History supports server/scope/status/entry filters and exposes target generations. Failed or cancelled preview preparation waits for session cleanup before publishing its terminal task state, including cancellation after result creation.
