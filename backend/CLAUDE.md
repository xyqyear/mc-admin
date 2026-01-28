# MC Admin Backend - FastAPI Development Guide

## What This Component Is

Backend REST API for the MC Admin Minecraft server management platform. Built with FastAPI + SQLAlchemy 2.0 on Python 3.13+, providing comprehensive server management APIs, JWT authentication with WebSocket login flow, real-time system monitoring, fully integrated Minecraft Docker management, enterprise-grade Restic backup system, player tracking with event-driven architecture, DNS management with multi-provider support, advanced cron job system, log monitoring, and dynamic configuration management.

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
- **WebSocket Console** (app.websocket): Direct container attach for real-time terminal

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

```
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
│   └── servers/
│       ├── compose.py      # Docker Compose config
│       ├── create.py       # Server creation
│       ├── operations.py   # Start/stop/restart
│       ├── resources.py    # Resource monitoring
│       ├── players.py      # Online player list
│       ├── files.py        # File management
│       ├── console.py      # WebSocket console endpoint
│       ├── populate.py     # Archive population
│       └── restart_schedule.py
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
│   ├── compression.py      # 7z compression
│   └── decompression.py    # Archive extraction
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
**Archives**: `/api/archives/` - upload, list, delete, SHA256
**Cron**: `/api/cron/` - job management, execution history
**DNS**: `/api/dns/` - status, records, update, sync
**Config**: `/api/config/` - modules, schemas, update

## Database Patterns

**Async SQLAlchemy 2.0:**
```python
from app.db.database import get_db

async def get_user(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()
```

**Models**: User, Player, PlayerSession, PlayerChat, PlayerAchievement, CronJob, CronJobExecution, DynamicConfig, ServerHeartbeat

**Migrations**: Use Alembic for schema changes (only needed for existing table modifications, not new tables)

## Testing Guidelines

**Safe Tests** (no Docker containers):
- All tests in `tests/players/`, `tests/dns/`, `tests/cron/`, `tests/files/`
- Snapshot basic tests, archive tests, config tests
- Use these for rapid development iteration

**Docker Tests** (slow):
- `tests/test_monitoring.py` (all functions end with `_with_docker`)
- `tests/test_integration.py`
- Run sparingly with `--timeout=600`

**Test Structure:**
```
tests/
├── players/           # Player system tests
├── files/             # File operation tests (search, multi-upload)
├── dns/               # DNS management tests
├── cron/              # Cron job tests
├── snapshots/         # Snapshot tests
├── dynamic_config/    # Config system tests
├── server_tracker/    # Server tracker tests
└── fixtures/          # Test utilities
```

## Operation Audit System

**Middleware-based logging** for state-changing operations:

- Logs POST/PUT/PATCH/DELETE operations
- Captures user context, IP, request body
- Masks sensitive fields (password, token, secret, key)
- Structured JSON with rotation
- Configured via `[audit]` settings

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
