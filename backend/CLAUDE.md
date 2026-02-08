# MC Admin Backend - FastAPI Development Guide

## What This Component Is

Backend REST API for the MC Admin Minecraft server management platform. Built with FastAPI + SQLAlchemy 2.0 on Python 3.13+, providing comprehensive server management APIs, JWT authentication with WebSocket login flow, real-time system monitoring, fully integrated Minecraft Docker management, enterprise-grade Restic backup system, player tracking with event-driven architecture, DNS management with multi-provider support, advanced cron job system, log monitoring, dynamic configuration management, template-based server creation with typed variables, and background task system for long-running operations.

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
- **Player System** (app.players): Event-driven player tracking, sessions, chat, achievements, skins
- **Snapshot System** (app.snapshots): Restic backup integration with deletion and unlock
- **DNS Management** (app.dns): DNSPod and Huawei Cloud DNS integration
- **Cron System** (app.cron): APScheduler task scheduling with backup jobs
- **Event System** (app.events): Centralized event dispatcher for cross-module communication
- **Log Monitor** (app.log_monitor): Real-time log parsing with Watchdog
- **File System** (app.files): Multi-file upload, search, conflict resolution
- **Dynamic Config** (app.dynamic_config): Runtime configuration with schema migration
- **Server Tracker** (app.server_tracker): Server lifecycle event monitoring
- **Template System** (app.templates): Template-based server creation with typed variables
- **WebSocket Console** (app.websocket): Direct container attach for real-time terminal
- **Background Tasks** (app.background_tasks): Async task manager for long-running operations

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
│       ├── operations.py   # Start/stop/restart
│       ├── resources.py    # Resource monitoring
│       ├── players.py      # Online player list
│       ├── files.py        # File management
│       ├── console.py      # WebSocket console endpoint
│       ├── populate.py     # Archive population
│       ├── restart_schedule.py
│       ├── template_config.py     # Template config read/update for existing servers
│       └── template_migration.py  # Mode conversion (template ↔ direct)
│
├── players/                # Player tracking system
│   ├── manager.py          # PlayerSystemManager (main coordinator)
│   ├── player_manager.py   # Player CRUD and skin management
│   ├── session_tracker.py  # Session records and online status
│   ├── chat_tracker.py     # Chat message tracking
│   ├── heartbeat.py        # Heartbeat and crash detection
│   ├── player_syncer.py    # Player state synchronization
│   ├── skin_fetcher.py     # Mojang API skin fetcher
│   ├── skin_updater.py     # Background skin updates
│   ├── mojang_api.py       # Mojang API client
│   └── crud/               # Player database operations
│
├── events/                 # Event system
│   ├── base.py             # BaseEvent and event definitions
│   ├── dispatcher.py       # EventDispatcher (centralized)
│   └── types.py            # EventType enum
│
├── log_monitor/            # Log monitoring
│   ├── monitor.py          # LogMonitor (Watchdog-based)
│   └── parser.py           # LogParser (regex-based parsing)
│
├── server_tracker/         # Server lifecycle tracking
│   └── tracker.py          # ServerTracker for server events
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
└── websocket/
    └── console.py          # Console WebSocket with docker-py attach
```

## Key Integrated Systems

### Player Management System

**Event-driven architecture** for comprehensive player tracking:

- **PlayerSystemManager**: Main coordinator integrating all subsystems
- **PlayerManager**: Player CRUD, UUID resolution, skin management
- **SessionTracker**: Real-time session records and online status
- **ChatTracker**: Chat message persistence
- **HeartbeatManager**: Heartbeat system with crash detection
- **PlayerSyncer**: Background sync for player state validation
- **SkinFetcher**: Mojang API integration for skins
- **LogMonitor**: Real-time log file monitoring with Watchdog

**Database Models:**

- Player (UUID, name, first_seen, skin data)
- PlayerSession (join/leave events, playtime calculation, last_seen computed)
- PlayerChat (messages with timestamps)
- PlayerAchievement (achievement tracking)
- ServerHeartbeat (crash detection)

**Integration:**

```python
from app.players import player_system_manager

# Automatically started in app lifespan
# Monitors all server logs, emits events for player actions
# Provides APIs via routers/servers/players.py
```

### Event System

**Centralized event dispatcher** for cross-module communication:

```python
from app.events import event_dispatcher, EventType

# Subscribe to events
@event_dispatcher.on_player_joined()
async def handle_join(event):
    pass

# Emit events
await event_dispatcher.emit(PlayerJoinedEvent(...))
```

**Event Types:**

- Player events (join, leave, chat, achievement)
- Server events (created, removed)
- System events (crash detected)

### Log Monitoring System

**Real-time log parsing** with Watchdog file monitoring:

- Monitors `logs/latest.log` in server directories
- Regex-based parsing for Minecraft log formats
- Emits events for player actions and server events
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

### Background Task System

**In-memory async task manager** for long-running operations:

- Singleton `BackgroundTaskManager` with submit/cancel/query API
- Tasks are async generators yielding `TaskProgress` (progress, message, result)
- Supports cancellation, error handling, and result data
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
**Servers**: `/api/servers/` - CRUD, status, operations, resources, players, WebSocket console
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

## Database Patterns

**Async SQLAlchemy 2.0:**

```python
from app.db.database import get_db

async def get_user(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()
```

**Models**: User, Server, ServerTemplate, DefaultVariableConfig, Player, PlayerSession, PlayerChat, PlayerAchievement, CronJob, CronJobExecution, DynamicConfig, ServerHeartbeat

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
├── server_tracker/    # Server tracker tests
├── background_tasks/  # Background task manager tests
├── templates/         # Template manager, API, default variables, YAML utils tests
├── servers/           # Server creation (template mode), template config tests
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
5. **New event types**: Add to `app/events/types.py` and `base.py`
6. **New tests**: Place in appropriate `tests/` subdirectory
7. **Update this CLAUDE.md** with new patterns and integration points

**Important Guidelines:**

- Write complete documentation, not incremental patches
- Reflect actual implementation, not planned features
- Ensure consistency with main `CLAUDE.md` and `frontend-react/CLAUDE.md`
- Check git history before updating to capture all changes since last doc update

Keep this file updated to help future development sessions understand the backend architecture, integrated modules, and development patterns.
