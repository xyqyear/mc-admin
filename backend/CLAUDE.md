# MC Admin Backend - FastAPI Development Guide

## What This Component Is

Backend REST API for the MC Admin Minecraft server management platform. Built with FastAPI + SQLAlchemy 2.0 on Python 3.13+, providing comprehensive server management APIs, JWT authentication with WebSocket login flow, real-time system monitoring, fully integrated Minecraft Docker management, enterprise-grade Restic backup system, player tracking with direct function calls, DNS management with multi-provider support, advanced cron job system, log monitoring, dynamic configuration management, template-based server creation with typed variables, and background task system for long-running operations.

## Tech Stack

**Core Backend:**

- Python 3.13+ with uv package management
- FastAPI + Uvicorn ASGI server with CORS middleware
- SQLAlchemy 2.0 async + SQLite + aiosqlite
- Alembic for database migrations with autogenerate
- Pydantic v2 + pydantic-settings (TOML + env variables)
- joserfc for JWT + OAuth2 authentication
- pwdlib for password hashing

**Integrated Modules:**

- **Minecraft Management** (app.minecraft): Docker Compose lifecycle, cgroup v2 monitoring
- **Player System** (app.players): Player tracking, sessions, chat, achievements, skins (direct function calls)
- **Snapshot System** (app.snapshots): Restic backup integration with deletion and unlock
- **DNS Management** (app.dns): DNSPod and Huawei Cloud DNS integration
- **Cron System** (app.cron): APScheduler task scheduling with backup jobs
- **Log Monitor** (app.log_monitor): Real-time log parsing with watchfiles, triggers player tracking directly
- **File System** (app.files): Multi-file upload, search, conflict resolution
- **Dynamic Config** (app.dynamic_config): Runtime configuration with schema migration
- **Template System** (app.templates): Template-based server creation with typed variables
- **WebSocket Console** (app.websocket): Direct container attach for real-time terminal
- **Background Tasks** (app.background_tasks): Async task manager for long-running operations
- **Server Map** (app.mcmap): On-demand world rendering via the mcmap CLI with batched, cancellable per-dimension queues
- **World Restore** (app.world): World layout discovery, per-server backup/restore lock, restore orchestrator (chunk/region/dimension/world scopes), and `/tmp` preview session manager driving the world-restore SSE flows

**Additional Libraries:**

- psutil for system monitoring
- httpx for async HTTP requests
- Watchdog for file monitoring
- APScheduler for task scheduling
- aiofiles for async file I/O
- PyYAML for Docker Compose parsing
- docker-py for container management and console streaming

## Development Commands

### Environment Setup

```bash
uv sync         # Install dependencies
```

### Configuration

Required settings in `config.toml`:

```toml
database_url = "sqlite+aiosqlite:///./db.sqlite3"
master_token = "your-master-token"
server_path = "/path/to/minecraft/servers"
logs_dir = "./logs"

[jwt]
secret_key = "your-jwt-secret"
algorithm = "HS256"
access_token_expire_minutes = 43200  # 30 days

[audit]
enabled = true
log_file = "operations.log"

[restic]
repository_path = "/path/to/backup/repository"
password = "your-restic-password"
```

### Database Migrations

**CRITICAL**: Schema changes require Alembic migrations.

```bash
# Generate migration (automatic detection)
uv run alembic revision --autogenerate -m "Description"

# Apply migrations
uv run alembic upgrade head

# Check status
uv run alembic current

# Rollback
uv run alembic downgrade -1
```

**Important**: Only existing table schema changes need migrations. New tables are auto-created.

### Run Development Server

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 5678 --reload
```

### Testing

**Development Testing** (fast, no Docker containers):

```bash
# Safe tests only (no containers)
uv run pytest tests/ -v -k "not _with_docker and not integrated"

# Specific module tests
uv run pytest tests/players/ -v
uv run pytest tests/dns/ -v
uv run pytest tests/cron/ -v
uv run pytest tests/files/ -v

# Snapshot tests
uv run pytest tests/snapshots/test_snapshots_basic.py -v
```

**DO NOT use black** for code formatting.

## Project Structure

```text
app/
├── main.py                 # App entrypoint, CORS, middleware, router mounting
├── config.py               # Settings with TOML + env support
├── models.py               # SQLAlchemy + Pydantic models
├── dependencies.py         # DI: sessions, auth, role guards
├── logger.py               # Logging with rotation and exception decorator
├── audit.py                # Operation audit middleware
│
├── db/
│   ├── database.py         # Async engine and sessions
│   └── crud/
│       ├── user.py         # User CRUD
│       ├── player.py       # Player CRUD
│       ├── player_session.py
│       └── ...
│
├── auth/
│   ├── jwt_utils.py        # JWT + password hashing (pwdlib)
│   └── login_code.py       # WebSocket login codes
│
├── routers/
│   ├── auth.py             # Authentication + WebSocket /auth/code
│   ├── user.py             # User profile
│   ├── admin.py            # User management (OWNER only)
│   ├── system.py           # System metrics
│   ├── archive.py          # Archive management
│   ├── snapshots.py        # Global snapshots
│   ├── cron.py             # Cron job management
│   ├── config.py           # Dynamic configuration
│   ├── dns.py              # DNS management
│   ├── templates.py        # Template CRUD, schema, preview, default variables
│   ├── tasks.py            # Background task queries and actions
│   └── servers/
│       ├── compose.py      # Docker Compose config
│       ├── create.py       # Server creation (template + traditional modes)
│       ├── operations.py   # Start/stop/restart/remove (remove returns RemoveServerResult)
│       ├── resources.py    # Resource monitoring
│       ├── players.py      # Online player list
│       ├── files.py        # File management
│       ├── console.py      # WebSocket console endpoint
│       ├── map.py          # Map status, dimensions, /initialize SSE, tiles, cache delete
│       ├── world_restore.py # Layout, eligible snapshots, snapshot creation, preview SSE, restore SSE, restoration history, rollback SSE
│       ├── populate.py     # Archive population
│       ├── restart_schedule.py  # CRUD + reusable schedule_auto_restart helper
│       ├── sync.py         # POST /servers/sync (OWNER-only fs↔DB reconciler)
│       ├── template_config.py     # Template config read/update for existing servers
│       └── template_migration.py  # Mode conversion (template ↔ direct)
│
├── players/                # Player tracking system
│   ├── __init__.py         # start_player_system() / stop_player_system()
│   ├── tracking.py         # Composite tracking functions (join, leave, chat, etc.)
│   ├── heartbeat.py        # HeartbeatManager singleton (crash detection)
│   ├── player_syncer.py    # PlayerSyncer singleton (RCON validation)
│   ├── skin_fetcher.py     # SkinFetcher singleton (Mojang API)
│   ├── mojang_api.py       # Mojang API client
│   └── crud/               # Player database operations
│
├── log_monitor/            # Log monitoring
│   ├── events.py           # Log event data models (Pydantic)
│   ├── monitor.py          # LogMonitor singleton (watchfiles-based)
│   └── parser.py           # LogParser (regex-based parsing)
│
├── files/                  # File operations
│   ├── base.py             # Basic file CRUD
│   ├── multi_file.py       # Multi-file upload with conflicts
│   ├── search.py           # Deep file search
│   ├── types.py            # File operation types
│   └── utils.py            # Upload session management
│
├── dynamic_config/         # Dynamic configuration
│   ├── manager.py          # ConfigManager with caching
│   ├── schemas.py          # BaseConfigSchema
│   ├── migration.py        # ConfigMigrator
│   └── configs/            # Configuration modules
│       ├── dns.py
│       ├── snapshots.py
│       ├── players.py
│       └── log_parser.py
│
├── templates/              # Server template system
│   ├── __init__.py         # Public API exports
│   ├── models.py           # VariableDefinition (discriminated union), TemplateSnapshot, API models
│   ├── manager.py          # TemplateManager: validation, rendering, schema generation
│   ├── crud.py             # Template CRUD operations
│   ├── default_variables_crud.py  # Default variable config (singleton)
│   └── yaml_utils.py       # Semantic YAML comparison
│
├── dns/                    # DNS management
│   ├── manager.py          # DNSManager
│   ├── dns.py              # Base DNS client
│   ├── dnspod.py           # DNSPod provider
│   ├── huawei.py           # Huawei Cloud provider
│   ├── router.py           # Router management
│   ├── types.py            # DNS types
│   └── utils.py
│
├── cron/                   # Cron job system
│   ├── manager.py          # CronManager (APScheduler)
│   ├── registry.py         # CronJobRegistry
│   ├── restart_scheduler.py # RestartScheduler
│   ├── types.py            # Cron types
│   └── jobs/               # Job implementations
│       ├── backup.py       # Backup job with Uptime Kuma
│       └── restart.py      # Server restart job
│
├── servers/                # Server core (DB, ports, lifecycle)
│   ├── crud.py             # Server row CRUD (append-only with REMOVED tombstones)
│   ├── port_utils.py       # Port conflict detection
│   ├── rebuild.py          # SERVER_REBUILD background task
│   └── lifecycle/          # Bundled create/remove + filesystem↔DB sync
│       ├── types.py        # Pydantic specs (CreateServerSpec, RemoveServerResult, SyncResult)
│       ├── primitives.py   # cancel_and_wait_for_tasks, cron lookups, validate_adoption
│       └── orchestrators.py # create_server_full, remove_server_full, adopt/deactivate
│
├── minecraft/              # Minecraft Docker management
│   ├── manager.py          # DockerMCManager
│   ├── instance.py         # MCInstance (server lifecycle)
│   ├── compose.py          # MCComposeFile
│   ├── properties.py       # server.properties parser
│   ├── utils.py            # Async utilities
│   └── docker/
│       ├── manager.py      # ComposeManager, DockerManager
│       ├── compose_file.py # Generic ComposeFile models
│       ├── cgroup.py       # cgroup v2 monitoring
│       └── network.py      # Network stats
│
├── snapshots/              # Restic backup integration
│   └── restic.py           # ResticManager
│
├── utils/
│   ├── compression.py      # 7z compression (async generator for background tasks)
│   └── decompression.py    # Archive extraction (async generator for background tasks)
│
├── background_tasks/       # Background task system
│   ├── __init__.py         # Exports: task_manager, TaskProgress, TaskType, etc.
│   ├── manager.py          # BackgroundTaskManager singleton
│   ├── models.py           # BackgroundTask Pydantic model
│   └── types.py            # TaskType, TaskStatus, TaskProgress, TaskResult
│
├── mcmap/                  # Server map (mcmap CLI integration)
│   ├── __init__.py         # Public exports: mcmap_manager, ServerMapCache, etc.
│   ├── runner.py           # Async subprocess wrapper, NDJSON parsing, uid/gid demotion; render + replace_chunks + remove_chunks ctx managers
│   ├── cache.py            # ServerMapCache: per-region paths and freshness checks
│   ├── palette.py          # Palette hash + invalidation, mods dir discovery
│   ├── queue.py            # ServerRenderQueue: refcount-coalesced batching with cancellation
│   ├── manager.py          # MCMapManager singleton: queues per (server, region_path)
│   └── types.py            # Pydantic models for SSE events, status, dimensions, MCMapError
│
├── world/                  # World restore (layout, locks, orchestrator, preview)
│   ├── __init__.py         # Singleton: world_restore_orchestrator + initialize/reset helpers + start/stop_janitor
│   ├── layout.py           # discover_world_roots, WorldRoot, DimensionInfo (Overworld/Nether/End by path heuristic)
│   ├── locks.py            # Per-server asyncio.Lock with LockHolder metadata; ServerOperationKind = BACKUP|RESTORE
│   ├── restore.py          # WorldRestoreOrchestrator: create_snapshot, list_eligible_snapshots, begin_restore (4 scopes), rollback, begin_preview
│   └── preview.py          # PreviewSessionManager: heartbeat-driven sessions under /tmp, janitor, disk threshold guard, one-per-server enforcement
│
└── websocket/
    └── console.py          # Console WebSocket with docker-py attach
```

## Key Integrated Systems

### Player Management System

**Direct function call architecture** for player tracking. No event dispatcher — producers call tracking functions directly.

**Composite functions** in `app/players/tracking.py`:

- `process_player_join()` — ensure player in DB + create session + trigger skin update
- `process_player_left()` — ensure player in DB + end sessions
- `record_chat_message()` — ensure player in DB + save chat
- `record_achievement()` — match player name + save achievement
- `close_server_sessions()` — end all sessions on a server
- `update_player_skin()` — fetch skin from Mojang + update DB

**Independent singletons** (each manages its own lifecycle):

- `heartbeat_manager` (app.players.heartbeat) — heartbeat loop + crash recovery
- `player_syncer` (app.players.player_syncer) — periodic RCON validation
- `skin_fetcher` (app.players.skin_fetcher) — Mojang API skin fetcher
- `log_monitor` (app.log_monitor.monitor) — watchfiles-based log monitoring

**Startup/shutdown** coordinated by `start_player_system()` / `stop_player_system()` in `app/players/__init__.py`, called from `main.py` lifespan. `start_player_system` enumerates servers from the DB (`get_active_servers`) — orphan filesystem directories are not auto-watched; the operator adopts them explicitly via the sync endpoint.

**Database Models:**

- Player (UUID, name, first_seen, skin data)
- PlayerSession (join/leave events, playtime calculation, last_seen computed)
- PlayerChat (messages with timestamps)
- PlayerAchievement (achievement tracking)
- ServerHeartbeat (crash detection)

**Integration:**

```python
from app.players.tracking import process_player_join, update_player_skin
from app.log_monitor import log_monitor

# Tracking functions called directly by LogMonitor, HeartbeatManager, PlayerSyncer, and routers
await process_player_join("server1", "Steve")
await log_monitor.start_server("server1")
```

### Log Monitoring System

**Real-time log parsing** with watchfiles:

- Monitors `logs/latest.log` in server directories
- Regex-based parsing for Minecraft log formats
- Calls player tracking functions directly on match
- Handles log rotation and file recreation
- Crash detection through heartbeat monitoring

### WebSocket Console System

**Direct container terminal access** via docker-py:

- Uses docker-py attach socket for bidirectional communication
- Real-time log streaming from container stdout/stderr
- Direct command input to container stdin
- Supports terminal features (command history, tab completion via MC server)
- Automatic reconnection handling
- No file-based log reading or mc-send-to-console dependency

### File System

**Enhanced file operations** with multi-file support:

- **Deep search**: Recursive file search with regex, size, time filters
- **Multi-file upload**: Drag-and-drop with conflict resolution
- **Upload sessions**: Session-based upload with policy management
- **Path conflict handling**: Automatic detection and resolution strategies
- **SNBT support**: Minecraft NBT file editing

### DNS Management

**Multi-provider DNS** with automatic updates:

- DNSPod and Huawei Cloud DNS integration
- Automatic DNS record creation/deletion during server operations
- Router configuration management (MC routing)
- DNS status monitoring and change detection

**Server enumeration is DB-driven.** `SimpleDNSManager.update(db)` and
`get_current_diff(db)` take an `AsyncSession`; they read the active server
list from `Server` rows (status=ACTIVE), then per-server read each compose
to extract its game port. Per-server compose-read failures are isolated in
try/except — a single missing or unreadable compose logs a warning and is
skipped, so one drifted row cannot poison the whole reconciliation tick.
The DB query itself failing still propagates (callers cannot reason about
the desired state). Callers in `app/main.py` (startup), `app/routers/dns.py`
(update/status endpoints), `app/servers/lifecycle/orchestrators.py`, and
`app/routers/servers/sync.py` all pass their existing session through.

### Dynamic Configuration

**Schema-based runtime configuration**:

```python
from app.dynamic_config import config

# Type-safe access
if config.snapshots.time_restriction.enabled:
    before = config.snapshots.time_restriction.before_seconds
```

**Features:**

- Pydantic schema validation
- Automatic migration on schema changes
- Memory caching with DB sync
- Web-based management interface
- JSON schema generation for frontend forms

### Server Discovery

Server enumeration follows a deliberate split:

- **DB is the source of truth for "servers we manage."** The overview list
  (`GET /servers/`), DNS reconciliation, and the startup log-monitor loop
  all enumerate via `get_active_servers(db)` and read each server's compose
  per-entry. ACTIVE rows whose compose has drifted (file missing / unreadable)
  are filtered out at the consumer (per-entry try/except for the overview;
  warning-and-skip for DNS). The sync endpoint deactivates drifted rows.
- **Filesystem is the source of truth for "what's actually on disk."** The
  sync endpoint (`POST /servers/sync`) and port-conflict checks
  (`port_utils.get_server_used_ports`, `GET /templates/ports/available`)
  enumerate via `docker_mc_manager.get_all_server_names()` because port
  collisions are a kernel/Docker reality and orphan directories must still
  count.
- **Single-server operations** that read/write compose or talk to Docker
  (`compose.py`, `files.py`, `operations.py`, `resources.py`, etc.) keep
  going through `docker_mc_manager.get_instance(server_id)`; they each
  perform an explicit `instance.exists()` check and return 404 if missing.

### Server Lifecycle Module

**Bundled create/remove + filesystem↔DB reconciliation** in `app/servers/lifecycle/`.
The lifecycle module owns the multi-step orchestration that used to be spread
across the frontend's chained requests.

- `create_server_full(db, server_id, spec)` — validates request, writes the
  compose tree, inserts the `Server` row, starts the log monitor, optionally
  creates a restart cron job from the bundled `RestartScheduleRequest`, and
  triggers a single DNS update at the tail. Any failure after the filesystem
  write triggers compensation in reverse order (cancel cronjob → stop log
  monitor → mark row REMOVED → rmtree). DNS update failures are non-fatal.
- `remove_server_full(db, server_id)` — refuses with 409 if containers are
  still running (uses public `instance.created()`), then cancels and
  **waits** for background tasks via `cancel_and_wait_for_tasks` (closes the
  rmtree race against in-flight `ARCHIVE_EXTRACT`), cancels restart cronjobs
  (NOT backup jobs — those are admin state), closes open player sessions,
  stops the log monitor, marks the row REMOVED, rmtrees the directory, and
  triggers DNS update.
- `adopt_server_partial` and `deactivate_server_partial` — primitives used by
  the sync endpoint. Adopted rows are direct-mode only (template binding
  cannot be inferred from a compose file).
- `validate_adoption(db, server_id)` — side-effect-free; shared between the
  sync dry-run preview and the apply path so the two cannot diverge.

**Lifecycle is NOT transactional.** Each underlying primitive issues its own
commit. Rollback is by compensation, documented at the top of `orchestrators.py`.
Lifecycle code accesses only public APIs of `MCInstance` (no `_compose_manager`
reach-arounds).

**Sync endpoint** (`POST /api/servers/sync`, OWNER-only): reconciles
filesystem directories vs `ACTIVE` `Server` rows. Supports `dry_run=true`
(preview only) and `force=true` (bypass the empty-filesystem safety guard
that prevents accidentally deactivating every row when the mount fails).
Concurrent calls return 409 immediately rather than waiting on the internal
`asyncio.Lock`. A single DNS update runs at the end of each apply batch.

### Background Task System

**In-memory async task manager** for long-running operations:

- Singleton `BackgroundTaskManager` with submit/cancel/query API
- Tasks are async generators yielding `TaskProgress` (progress, message, result)
- Supports cancellation, error handling, and result data
- `get_tasks_by_server_id(server_id)` and `get_future(task_id)` expose the
  per-server task list and the underlying `asyncio.Future` so callers can
  cancel-and-wait (used by the server lifecycle module before rmtree)
- REST API at `/api/tasks/` for listing, polling, cancelling, and cleanup
- Used by archive compression, server population (extraction)

```python
from app.background_tasks import task_manager, TaskType, TaskProgress

async def my_operation() -> AsyncGenerator[TaskProgress, None]:
    yield TaskProgress(progress=0, message="Starting...")
    # ... do work ...
    yield TaskProgress(progress=100, message="Done", result={"key": "value"})

result = task_manager.submit(
    task_type=TaskType.ARCHIVE_CREATE,
    name="Display Name",
    task_generator=my_operation(),
    server_id="survival",
    cancellable=True,
)
# result.task_id returned to frontend for polling
```

See `.claude/background-tasks-guide.md` for detailed implementation guide.

### Server Template System

**Template-based server creation** with typed variable definitions and snapshot isolation:

Server templates define reusable Docker Compose configurations with `{variable}` placeholders. Each variable has a typed definition (int, float, string, enum, bool) with validation constraints (min/max, pattern, options). When a server is created from a template, a **TemplateSnapshot** captures the template state at that moment, so the server operates independently even if the template is later modified or deleted.

**Two Server Editing Modes:**

- **Template mode**: Server is bound to a template. Users edit variable values through a form, and YAML is rendered automatically. Template updates are detected and can be applied with one-click.
- **Direct mode**: Server compose is edited directly with Monaco editor. No template association.

Servers can convert between modes at any time. Converting from direct to template mode uses variable extraction — the system matches the current compose against a template to infer variable values. If the rendered YAML differs from the current compose, a rebuild is triggered; otherwise the conversion is metadata-only.

**Key Design Patterns:**

- **Bidirectional validation**: Template YAML variables must match variable definitions exactly (no undefined or unused variables)
- **Snapshot isolation**: `Server.template_snapshot_json` stores an immutable copy of the template used at creation time
- **Semantic YAML comparison**: `are_yaml_semantically_equal()` compares parsed YAML structures, ignoring formatting differences
- **Background rebuild**: Template config updates submit a `SERVER_REBUILD` background task; database is updated only after rebuild succeeds

**Usage:**

```python
from app.templates import TemplateManager, VariableDefinition

# Validate template consistency
errors = TemplateManager.validate_template(yaml_template, variable_definitions)

# Render YAML with variable values
rendered = TemplateManager.render_yaml(yaml_template, {"name": "survival", "max_memory": 8})

# Generate JSON Schema for frontend form (rjsf)
schema = TemplateManager.generate_json_schema(variable_definitions)

# Extract variables from existing compose (for mode conversion)
values, warnings = TemplateManager.extract_variables_from_compose(
    yaml_template, compose_yaml, variable_definitions
)
```

**Database Models:**

- ServerTemplate (name, yaml_template, variable_definitions_json)
- DefaultVariableConfig (singleton, stores default variables pre-filled when creating templates)
- Server fields: template_id, template_snapshot_json, variable_values_json

### Server Map System

**On-demand world rendering** via the `mcmap` CLI (NDJSON event stream). Tile artifacts live under `data/.mcmap/` per server (excluded from Restic backups). The cache is fully regenerable.

**Pipeline:**

1. Per-server `/initialize` (SSE) downloads the Minecraft client `.jar` (`mcmap download-client`) and builds the block→color palette (`mcmap gen-palette modern`). Palette currency is tracked by a SHA256 hash of `version + sorted(mod_jar_filenames)` — written to `data/.mcmap/palette.hash` and re-checked on each request.
2. Tile requests `(x, z, region_path)` check freshness: if `mca.mtime - png.mtime < stale_timeout_seconds`, the cached PNG is served directly. Otherwise the request is enqueued.
3. A per-`(server, region_path)` `ServerRenderQueue` batches up to `batch_size` regions into a single `mcmap render --split --preserve-mtime -j N` invocation, resolves each waiter as the corresponding `region` event arrives in the NDJSON stream, and falls back to `RenderError` for any region that the subprocess never emitted (e.g. terminated mid-render).

**Key design properties:**

- **Subprocess ownership:** every mcmap invocation runs as the owner of the server's `data/` directory via `preexec_fn` (drops privileges only when the backend itself is root and the target uid differs).
- **Refcount-coalesced cancellation:** duplicate `(x, z)` requests share one `asyncio.Future`. The consumer `await` is wrapped in `asyncio.shield` so cancelling one consumer does not disturb others. When the last consumer for a key disconnects, the entry is dropped from the queue; if the running batch becomes empty, the mcmap subprocess is terminated (SIGTERM, then SIGKILL after 2 s).
- **Hard dimension isolation:** the queue key includes `region_path`, so no `mcmap render` invocation can mix regions from different dimensions (PNGs always land in the correct subfolder).
- **Region path is request-scoped** — never persisted in the database or config. Frontend tracks the selected dimension in component state and includes it on each tile fetch as a query parameter; `_resolve_region_path()` validates it stays inside `data/` and rejects traversal/absolute paths.
- **Idle worker timeout:** worker exits after 60 s of inactivity, respawns on next request.

**Settings:**

- Static (`config.toml` / env): `mcmap_binary_path` (default `/usr/local/bin/mcmap`)
- Dynamic (`mcmap` schema): `stale_timeout_seconds`, `batch_size`, `thread_count`, `request_timeout_seconds`
- Dynamic (`snapshots.world_restore` schema): `restore_temp_dir`, `temp_disk_threshold_bytes`, `preview_session_ttl_seconds`, `preview_janitor_interval_seconds`

**Endpoints (mounted under `/api/servers/{server_id}/map/`):**

- `GET /status` — initialization state + game version
- `GET /dimensions` — auto-discovers region folders (skipping `.mcmap/`); labels Overworld / Nether / End by path heuristic
- `GET /regions?region=<rel-path>` — manifest of `[x, z]` pairs for every existing `r.X.Z.mca` in the dimension; the frontend uses it to skip HTTP requests for non-existent regions in sparse worlds
- `POST /initialize` — two-stage SSE (`stage: "client"` → `stage: "palette"` → `stage: "complete"`); fast-path emits `cached: true` when nothing needs regeneration
- `GET /tiles/{x}/{z}.png?region=<rel-path>` — tile fetch; 404 if MCA missing, 409 if not initialized, 503 on render timeout
- `DELETE /cache?region=<rel-path>` — wipes one dimension's tiles

**Usage:**

```python
from app.mcmap import mcmap_manager, ServerMapCache, palette_is_current

cache = ServerMapCache(data_path=instance.get_data_path())
queue = await mcmap_manager.get_queue(server_id, region_path, cache)
png_path = await asyncio.wait_for(queue.request(x, z), timeout=cfg.request_timeout_seconds)
```

### World Restore System

**Selective world rollback** at chunk, region, dimension, or whole-world granularity. Built on Restic snapshots + mcmap v0.3.0's `replace-chunks` and `remove-chunks` subcommands. Every restore creates a **safety snapshot** first, so a one-click rollback recovers the pre-restore state.

**Four scopes:**

- **WORLD**: Restic restore against *every* valid world root on the server (Bukkit/Paper multi-world setups are covered in one operation); all dimensions of every root included. Carries no `region_dir_relpath`.
- **DIMENSION**: Restic restore scoped to a single `region/`, `entities/`, `poi/` triple. The dimension is identified by `region_dir_relpath` (data-relative, e.g. `world/region`, `world_creative/region/DIM-1`); the relpath is unique across roots because the world root dir name is its first segment.
- **REGIONS**: Restic restore filtered to specific `r.X.Z.mca` files inside the dimension named by `region_dir_relpath`; entities/poi sidecars and `c.<absX>.<absZ>.mcc` overflow chunks for the affected region grid are included so partial regions don't desync.
- **CHUNKS**: Stage source MCAs from the snapshot into a tmp dir, then run `mcmap replace-chunks` to splice the selected chunks into the live MCAs (or `remove-chunks` for chunks the snapshot didn't have) inside the dimension named by `region_dir_relpath`. Same restic include-path expansion as REGIONS for entities/poi.

**Per-server lock semantics** (`app.world.locks`):

- `server_operation_lock` is a singleton holding one `asyncio.Lock` per server id (or `__global__`). Acquired as `BACKUP` for snapshot creation and `RESTORE` for restores; held for the full operation including the safety snapshot.
- `LockHolder` records `kind`, `started_at`, optional `user_id`, human-readable description, and the active `restoration_id` so the UI can show "another admin is restoring".
- The cron backup job calls `server_operation_lock.is_locked(server_id)` before running and emits a structured "skipped" log + Uptime Kuma notification when held — backups never collide with restores.

**Preview session lifecycle** (`app.world.preview`):

- One preview session per server: starting a new preview tears down the prior session for that server.
- Sessions live under `restore_temp_dir/<session_id>/` (default `/tmp/mc-admin-world-restore/`). Source MCAs are staged into `source/`; chunk-merged copies into `preview/` so the live world is untouched.
- Heartbeat-driven TTL (default 30 min). A janitor task running every `preview_janitor_interval_seconds` reaps expired sessions and orphaned dirs.
- Disk threshold guard: estimated cost is `affected_regions × 8 MiB × 2`; preview returns 507 with `{"free", "required"}` if the FS doesn't have headroom.

**Crash recovery:**

- On startup, `mark_running_restorations_interrupted()` flips any `Restoration.status = RUNNING` rows to `INTERRUPTED` with `error_message="server restarted before completion"`. The history drawer surfaces a "rollback" CTA on these rows.

**Endpoints (mounted under `/api/servers/{server_id}/world-restore/`):**

- `GET /layout` — world roots + dimensions (Overworld/Nether/End label heuristic; per-dimension `region_dir`, `entities_dir`, `poi_dir` paths)
- `POST /eligible-snapshots` (body: `RestorationSelection`) — newest-first list of snapshots that cover *all* paths the selection resolves to (uses `ResticManager.find_snapshots_covering`)
- `POST /snapshots` (body: `RestorationSelection`) — creates a backup at the requested scope; returns 423 if the server lock is held
- `POST /preview` (body: `{source_snapshot_id, selection}`) — SSE stream of `PreviewEvent` (start → stage → merge_region → render_progress → ready); returns `session_id` in the `ready` event
- `POST /preview/{session_id}/heartbeat` — extends the TTL; 404 if the session is unknown
- `DELETE /preview/{session_id}` — idempotent teardown
- `GET /preview/{session_id}/tile/{rx}/{rz}.png` — preview tile (also heartbeats)
- `POST /restore` (body: `{source_snapshot_id, selection}`) — SSE stream of `RestoreEvent`; pre-checks return 409 (server running) or 423 (locked) before SSE handshake so the frontend can render distinct UI
- `GET /restorations` / `GET /restorations/{id}` — restoration history rows
- `POST /restorations/{id}/rollback` — SSE stream of `RestoreEvent`; uses the row's `safety_snapshot_id` as the source

**Singleton wiring** (in `app.main` lifespan):

1. `mark_running_restorations_interrupted()` flips stuck rows.
2. `initialize_world_restore_orchestrator()` builds the singleton with values from `config.snapshots.world_restore.*` (no-op if restic isn't configured).
3. `start_janitor()` launches the preview janitor task; `stop_janitor()` cancels it on shutdown.

The router accesses the orchestrator via `from ... import world as world_subsystem` and reads `world_subsystem.world_restore_orchestrator` *at request time* — so the lifespan-time reassignment is observed.

**Usage:**

```python
from app.world import world_restore_orchestrator
from app.models import RestorationSelection

# Eligible snapshots for a chunk-scope selection
snaps = await world_restore_orchestrator.list_eligible_snapshots(
    server_id="survival",
    selection=RestorationSelection(
        type="chunks", region_dir_relpath="world/region", chunks=[(0, 0)]
    ),
)

# Drive the SSE
async for event in world_restore_orchestrator.begin_restore(
    server_id="survival", source_snapshot_id=snaps[0].id, selection=sel, user_id=42,
):
    print(event.event_type, event.message)
```

## Authentication & Authorization

**JWT Authentication:**

- OAuth2 password flow
- 30-day token expiry (configurable)
- Master token fallback for system operations
- pwdlib for modern password hashing

**WebSocket Login Flow:**

- Rotating 8-digit codes (60s TTL)
- Verification via `/api/auth/verifyCode` with master token
- Returns JWT for session management

**Role-Based Access:**

- ADMIN: Standard user access
- OWNER: Full admin capabilities including user management
- Use `RequireRole(UserRole.OWNER)` dependency

## API Endpoints (Summary)

**Auth**: `/api/auth/` - register, token, verifyCode, WebSocket /code
**User**: `/api/user/` - profile management
**Admin**: `/api/admin/` - user management (OWNER only)
**System**: `/api/system/info` - system metrics
**Servers**: `/api/servers/` - CRUD (bundles restart_schedule), status, operations (remove returns `RemoveServerResult`), resources, players, WebSocket console
**Server Sync**: `POST /api/servers/sync` - OWNER-only filesystem↔DB reconciler (`dry_run`, `force`)
**Files**: `/api/servers/{id}/files/` - CRUD, upload, search, multi-upload
**Snapshots**: `/api/snapshots/`, `/api/servers/{id}/snapshots/` - backup management, deletion, unlock
**Archives**: `/api/archives/` - upload, list, delete, SHA256, compress (background task)
**Tasks**: `/api/tasks/` - background task listing, polling, cancel, delete, clear
**Cron**: `/api/cron/` - job management, execution history
**DNS**: `/api/dns/` - status, records, update, sync
**Config**: `/api/config/` - modules, schemas, update
**Templates**: `/api/templates/` - CRUD, schema, preview, default variables, available ports
**Server Template Config**: `/api/servers/{id}/template-config` - read/update template config
**Server Template Migration**: `/api/servers/{id}/convert-to-direct`, `convert-to-template`, `extract-variables`, `check-conversion`
**Server Map**: `/api/servers/{id}/map/` - status, dimensions, regions, initialize (SSE), tiles, cache delete
**World Restore**: `/api/servers/{id}/world-restore/` - layout, eligible-snapshots, snapshots (POST), preview (SSE), preview heartbeat/delete/tile, restore (SSE), restorations (list/detail), rollback (SSE)

## Database Patterns

**Async SQLAlchemy 2.0:**

```python
from app.db.database import get_db

async def get_user(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()
```

**Models**: User, Server, ServerTemplate, DefaultVariableConfig, Player, PlayerSession, PlayerChat, PlayerAchievement, CronJob, CronJobExecution, DynamicConfig, ServerHeartbeat, Restoration

**Migrations**: Use Alembic for schema changes (only needed for existing table modifications, not new tables)

## Testing Guidelines

**Safe Tests** (no Docker containers):

- All tests in `tests/players/`, `tests/dns/`, `tests/cron/`, `tests/files/`
- Background task tests in `tests/background_tasks/`
- Snapshot basic tests, archive tests, config tests
- Use these for rapid development iteration

**Docker Tests** (slow):

- `tests/test_monitoring.py` (all functions end with `_with_docker`)
- `tests/test_integration.py`
- Run sparingly with `--timeout=600`

**Test Structure:**

```text
tests/
├── players/           # Player system tests
├── files/             # File operation tests (search, multi-upload)
├── dns/               # DNS management tests
├── cron/              # Cron job tests
├── snapshots/         # Snapshot tests
├── dynamic_config/    # Config system tests
├── background_tasks/  # Background task manager tests
├── templates/         # Template manager, API, default variables, YAML utils tests
├── servers/           # Server creation (template mode), template config, lifecycle, sync tests
├── mcmap/             # Cache, palette hash, runner, queue, cancellation, dimensions, region path
├── world/             # Layout discovery, locks, restoration model, orchestrator, preview lifecycle, endpoints, crash recovery
└── fixtures/          # Test utilities
```

## Operation Audit System

**Middleware-based logging** for state-changing operations:

- Logs POST/PUT/PATCH/DELETE operations
- Captures user context, IP, request body
- Masks sensitive fields (password, token, secret, key)
- Structured JSON with rotation
- Configured via `[audit]` settings

## Error Handling

**Custom RequestValidationError handler** returns simplified error format:

- Pydantic validation errors are transformed from FastAPI's verbose array format into a single `{"detail": "field: message; field2: message2"}` string
- Consistent with the `{"detail": ...}` format used by HTTPException responses
- Defined in `app/main.py` as an exception handler on the API sub-app

## External Documentation

Use Context7 MCP tool:

- FastAPI: `/tiangolo/fastapi`
- SQLAlchemy: `/websites/sqlalchemy-en-20`
- Pydantic: `/pydantic/pydantic`
- Restic: `/restic/restic`

Resolve library ID first, then fetch docs with specific topics.

## Update Instructions

When adding features:

1. **Database changes**: Use `alembic revision --autogenerate` (only for existing table schema changes)
2. **New routers**: Add to `app/routers/` and mount in `main.py`
3. **New dependencies**: Update `pyproject.toml`
4. **New integrated modules**: Add to `app/` with `__init__.py` exports
5. **New player tracking operations**: Add to `app/players/tracking.py`
6. **New tests**: Place in appropriate `tests/` subdirectory
7. **Update this CLAUDE.md** with new patterns and integration points

**Important Guidelines:**

- Write complete documentation, not incremental patches
- Reflect actual implementation, not planned features
- Ensure consistency with main `CLAUDE.md` and `frontend-react/CLAUDE.md`
- Check git history before updating to capture all changes since last doc update

Keep this file updated to help future development sessions understand the backend architecture, integrated modules, and development patterns.
