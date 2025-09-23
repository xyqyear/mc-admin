# MC Admin Backend - FastAPI Development Guide

## What This Component Is

Backend REST API for the MC Admin Minecraft server management platform. Built with FastAPI + SQLAlchemy 2.0 on Python 3.12+, providing comprehensive server management APIs, JWT authentication with WebSocket login flow, real-time system monitoring, **fully integrated** Minecraft Docker management capabilities (not an external library), enterprise-grade **Restic backup system** with snapshot management, **DNS management system** with DNSPod and Huawei Cloud integration, **advanced cron job system** with APScheduler, backup jobs, and Uptime Kuma notifications, **server restart scheduling** with conflict detection, **download manager** with progress tracking, and **dynamic configuration management** with schema migration and memory caching.

## Tech Stack

### Core Backend Stack

- **Language**: Python 3.12+ with Poetry package management
- **Web Framework**: FastAPI + Uvicorn ASGI server with CORS middleware
- **Database**: SQLAlchemy 2.0 Declarative Models (async) + SQLite + aiosqlite driver
- **Database Migrations**: Alembic 1.16.5 with autogenerate support for schema management
- **Authentication**: JWT (joserfc) + OAuth2 + WebSocket login codes + Master token system
- **Validation**: Pydantic v2 + pydantic-settings (TOML + environment variables)
- **Async Support**: Full async/await with comprehensive asyncio patterns throughout
- **System Monitoring**: psutil v7.0.0 for CPU, memory, disk metrics
- **Development**: pytest v8.3.3 + pytest-asyncio + black formatter
- **Audit System**: FastAPI middleware with structured JSON logging and automatic log rotation
- **DNS Management**: Integrated DNS record management with DNSPod and Huawei Cloud provider support
- **Cron System**: APScheduler v3.11.0 for task scheduling with async support, backup jobs, and Uptime Kuma notifications
- **Restart Scheduling**: Automated server restart management with backup conflict detection and timezone support
- **Download Manager**: File download progress tracking with cancellation support and real-time status updates
- **Dynamic Configuration**: Pydantic-based configuration management with schema migration and validation
- **Additional**: python-multipart, asyncer v0.0.8, watchdog for file monitoring

### Integrated Minecraft Management Stack

- **Container Platform**: Docker Engine + Docker Compose integration (CLI-based, no Python SDK)
- **Async Framework**: asyncio with comprehensive async/await patterns throughout codebase
- **File Operations**: aiofiles v24.1.0 for async file I/O operations
- **YAML Processing**: PyYAML v6.0.2 for Docker Compose file parsing and generation
- **Resource Monitoring**: Real-time CPU, memory, disk I/O, and network monitoring via **direct cgroup v2 filesystem access**
- **Configuration Management**: Strongly-typed Minecraft Docker Compose file handling with Pydantic validation
- **Console Streaming**: WebSocket-based real-time log streaming with Watchdog file monitoring
- **Testing**: pytest-asyncio v0.24.0 + pytest-cov v5.0.0 for comprehensive async testing with real Docker containers

### Integrated Backup System Stack

- **Backup Tool**: Restic integration via subprocess calls for snapshot management
- **Repository Management**: Configurable backup repositories with password protection
- **Snapshot Models**: Pydantic models for ResticSnapshot, ResticSnapshotSummary, ResticSnapshotWithSummary
- **Async Operations**: Full async/await support for backup operations
- **Dual API Structure**: Global and server-specific snapshot management endpoints

### Integrated Archive Management Stack

- **Compression Support**: 7z archive creation for server files and directories via app.utils.compression
- **Decompression Support**: ZIP, TAR, TAR.GZ format support via app.utils.decompression
- **SHA256 Verification**: Built-in file integrity checking for uploaded archives
- **Server Population**: Archive-to-server deployment via populate endpoint
- **Common File Operations**: Shared utilities in app.common.file_operations
- **Archive Router**: Complete CRUD operations for archive lifecycle management

## Development Commands

### Environment Setup

```bash
poetry install      # Install dependencies and create .venv
poetry shell        # Activate virtual environment
```

### Configuration (Required)

App reads settings from TOML file with environment variable overrides.

**Configuration Files:**

- Primary: `config.toml` (configurable via `MC_ADMIN_CONFIG` env var)
- Override: `.env` (configurable via `MC_ADMIN_ENV` env var)

**Required Settings:**

```toml
database_url = "sqlite+aiosqlite:///./db.sqlite3"
master_token = "your-master-token-here"
server_path = "/path/to/minecraft/servers"
logs_dir = "./logs"  # Optional, defaults to ./logs

[jwt]
secret_key = "your-jwt-secret-key"
algorithm = "HS256"
access_token_expire_minutes = 43200  # 30 days

[audit]
enabled = true                    # Enable operation audit logging
log_file = "operations.log"       # Audit log filename in logs_dir
log_request_body = true           # Include request body in logs
max_body_size = 10240            # Max request body size to log (bytes)
sensitive_fields = ["password", "token", "secret", "key"]  # Fields to mask in logs

[restic]
repository_path = "/path/to/backup/repository"
password = "your-restic-password"
```

### Database Migrations (Alembic)

**⚠️ CRITICAL: Database schema changes require migration scripts using Alembic.**

When making database schema changes (models in `app/models.py`), you MUST create and apply migrations:

You DO NOT need to create migration skip in case of a NEW table. Only schema changes on existing tables need migration.

```bash
# Generate migration for schema changes (AUTOMATIC)
poetry run alembic revision --autogenerate -m "Descriptive migration message"

# Review the generated migration in alembic/versions/
# The autogenerate feature detects most changes but always review!

# Apply migrations to database
poetry run alembic upgrade head

# Check current migration status
poetry run alembic current

# View migration history
poetry run alembic history

# Downgrade (if needed)
poetry run alembic downgrade -1    # Go back one revision
poetry run alembic downgrade <revision_id>  # Go to specific revision
```

**Important Migration Guidelines:**

- **Never modify existing migration files** - create new ones for additional changes
- **Always review autogenerated migrations** - Alembic detects most but not all changes
- **Code should assume migrations are applied** - don't code for backward compatibility
- **SQLite limitations**: Some operations require manual migration script adjustments
- **Test migrations** on development database before production

**Alembic Configuration:**

- Migrations stored in `alembic/versions/`
- Configuration in `alembic.ini` and `alembic/env.py`
- Automatically uses database URL from `config.toml`
- Supports both online and offline migration modes

### Run Development Server

```bash
# Method 1: Using uvicorn directly (recommended for development)
poetry run uvicorn app.main:app --host 0.0.0.0 --port 5678 --reload

# The app serves routes under /api due to root_path="/api" configuration
```

### Testing and Quality

**⚠️ CRITICAL TESTING GUIDELINES:**

During development iteration, **NEVER run Docker container tests** to avoid timeouts. Only run safe tests that don't bring up containers:

```bash
# ✅ Safe for frequent development iteration
poetry run pytest tests/test_compose.py tests/test_compose_file.py tests/test_rcon_filtering.py tests/test_file_operations.py tests/test_websocket_console.py tests/snapshots/test_snapshots_basic.py tests/snapshots/test_snapshots_endpoints.py tests/test_decompression.py tests/archive/test_archive_operations.py tests/archive/test_archive_sha256.py tests/archive/test_archive_compression.py tests/test_common_file_operations.py tests/test_create_server.py tests/test_time_restriction.py tests/cron/test_cron_basic.py tests/cron/test_cron_api.py tests/dynamic_config/test_dynamic_config.py -v

# ✅ Safe unit tests (don't bring up containers)
poetry run pytest tests/test_instance.py::test_disk_space_info_dataclass tests/test_instance.py::test_minecraft_instance -v

# ✅ Skip all Docker container tests during development
poetry run pytest tests/ -v -k "not _with_docker and not test_integration and not integrated"

# ✅ Test only changes related to specific functionality (example)
poetry run pytest tests/snapshots/test_snapshots_basic.py tests/snapshots/test_snapshots_endpoints.py -v

# ✅ Test in a subdirectory
poetry run pytest tests/cron/ -v
poetry run pytest tests/dynamic_config/ -v

# ❌ AVOID - These bring up Docker containers and will timeout/slow development
# poetry run pytest tests/test_monitoring.py  # All functions end with _with_docker
# poetry run pytest tests/test_integration.py::test_integration_with_docker
# poetry run pytest tests/test_instance.py::test_server_status_lifecycle_with_docker

# ❌ NEVER run all tests during development
# poetry run pytest tests/ -v  # Will timeout due to container tests
```

**Docker Container Tests:**

- `test_monitoring.py`: All functions end with `_with_docker`
- `test_integration.py`: `test_integration_with_docker`
- `test_instance.py`: `test_server_status_lifecycle_with_docker`, `test_get_disk_space_info_with_docker`

**Code Quality:**
DO NOT use black to format code

````

**Pre-commit Testing (with container tests):**
```bash
# Run with longer timeout for container tests (use sparingly)
poetry run pytest tests/ -v --timeout=600
````

## API Architecture

### Project Structure (Actual File Layout)

```
app/                        # Main application package
├── main.py                 # FastAPI app entrypoint, CORS, audit middleware, router mounting, lifespan management, cron/config initialization
├── config.py               # Settings model with TOML + env loading (pydantic-settings)
├── models.py               # SQLAlchemy + Pydantic models with async support (includes CronJob, CronJobExecution, DynamicConfig)
├── dependencies.py         # DI: database sessions, auth, role guards, master token handling
├── logger.py               # Rotating file + stdout logging configuration
├── audit.py                # Operation audit middleware with smart filtering and sensitive data masking
├── __main__.py             # Module execution entry point
├── db/
│   ├── __init__.py
│   ├── database.py         # Async engine, session factory, init_db()
│   └── crud/
│       ├── __init__.py
│       └── user.py         # User CRUD operations with SQLAlchemy 2.0 async syntax
├── auth/
│   ├── __init__.py
│   ├── jwt_utils.py        # Password hashing (bcrypt), JWT create/verify
│   └── login_code.py       # WebSocket rotating 8-digit codes + master token verification
├── common/
│   ├── __init__.py
│   └── file_operations.py  # Shared file operations utilities
├── utils/
│   ├── __init__.py
│   ├── decompression.py    # Archive decompression utilities (ZIP, TAR, TAR.GZ)
│   └── compression.py      # Archive compression utilities (7z integration)
├── dns/                    # **NEW** - DNS management system with provider support
│   ├── __init__.py         # Public API exports (DNSManager, providers, types)
│   ├── manager.py          # DNSManager class for unified DNS operations
│   ├── dns.py              # DNS client base class and interface
│   ├── dnspod.py           # DNSPod provider implementation
│   ├── huawei.py           # Huawei Cloud DNS provider implementation
│   ├── router.py           # Router management integration
│   ├── types.py            # DNS-related type definitions and dataclasses
│   └── utils.py            # DNS utility functions and helpers
├── cron/                   # **ENHANCED** - Advanced cron job system with backup jobs and notifications
│   ├── __init__.py         # Public API exports (CronManager, types, registry)
│   ├── manager.py          # CronManager class with async job scheduling and execution tracking
│   ├── registry.py         # CronJobRegistry for registering cron job functions and schemas
│   ├── types.py            # Type definitions and dataclasses for cron job system
│   ├── instance.py         # Global cron manager instance
│   ├── restart_scheduler.py # **NEW** - RestartScheduler for server restart management with conflict detection
│   └── jobs/               # **NEW** - Specialized cron job implementations
│       ├── __init__.py
│       ├── backup.py       # Backup job with retention policies and Uptime Kuma notifications
│       └── restart.py      # Server restart job implementation
├── dynamic_config/         # **ENHANCED** - Dynamic configuration management system
│   ├── __init__.py         # Public API exports (ConfigManager, schemas, migration)
│   ├── manager.py          # ConfigManager class with memory caching and database sync
│   ├── schemas.py          # BaseConfigSchema and configuration validation with Union type support
│   ├── migration.py        # ConfigMigrator for schema version migrations
│   └── configs/            # Configuration schemas for different modules
│       └── dns.py          # DNS configuration schema for provider settings
├── routers/
│   ├── __init__.py
│   ├── auth.py             # Authentication endpoints + WebSocket /auth/code
│   ├── user.py             # User profile endpoints
│   ├── admin.py            # User administration endpoints (OWNER role required)
│   ├── system.py           # System metrics endpoints (psutil integration)
│   ├── archive.py          # Archive management endpoints (upload, list, delete, SHA256)
│   ├── snapshots.py        # Global snapshot management endpoints
│   ├── cron.py             # **ENHANCED** - Cron job management endpoints (create, pause, resume, cancel, history)
│   ├── config.py           # **ENHANCED** - Dynamic configuration endpoints (get, update, schema info)
│   ├── dns.py              # **NEW** - DNS management endpoints (status, records, provider configuration)
│   └── servers/
│       ├── __init__.py
│       ├── compose.py      # Docker Compose configuration management
│       ├── create.py       # Server creation endpoints
│       ├── operations.py   # Server operations (start, stop, restart)
│       ├── resources.py    # Resource monitoring endpoints
│       ├── players.py      # Player management endpoints
│       ├── populate.py     # Server population from archives
│       ├── restart_schedule.py # **NEW** - Server restart scheduling endpoints
│       ├── misc.py         # Miscellaneous server endpoints
│       ├── console.py      # Real-time console WebSocket endpoints
│       ├── rcon.py         # RCON command execution endpoints
│       └── files.py        # File management endpoints
├── websocket/
│   ├── __init__.py         # WebSocket module exports
│   └── console.py          # Real-time console streaming with Watchdog file monitoring
├── system/
│   ├── __init__.py
│   └── resources.py        # psutil wrappers for system resource information
├── snapshots/              # **NEW** - Integrated Restic backup system module
│   ├── __init__.py         # Public API exports (ResticManager, models)
│   └── restic.py           # ResticManager class, Pydantic models, subprocess integration
└── minecraft/              # **FULLY INTEGRATED** Minecraft Docker Management Module
    ├── __init__.py         # Public API exports (DockerMCManager, MCInstance, etc.)
    ├── manager.py          # DockerMCManager main class for multi-server management
    ├── instance.py         # MCInstance + individual server lifecycle management
    ├── compose.py          # Minecraft-specific compose file handling (MCComposeFile)
    ├── utils.py            # Async utility functions for file operations
    └── docker/             # Docker integration submodule
        ├── __init__.py     # Docker module exports
        ├── manager.py      # ComposeManager + DockerManager classes
        ├── compose_file.py # Generic ComposeFile Pydantic models with full YAML support
        ├── cgroup.py       # Container resource monitoring via **direct cgroup v2 filesystem**
        └── network.py      # Network statistics collection via /proc/{pid}/net/dev

tests/                      # Test suite (separate from app package)
├── __init__.py
├── test_compose.py         # ✅ SAFE - Compose file parsing and validation tests
├── test_compose_file.py    # ✅ SAFE - ComposeFile Pydantic model tests
├── test_rcon_filtering.py  # ✅ SAFE - RCON utility function tests
├── test_file_operations.py # ✅ SAFE - Mocked API endpoint tests
├── test_websocket_console.py # ✅ SAFE - WebSocket protocol tests with mocks
├── test_decompression.py   # ✅ SAFE - Archive decompression utility tests
├── test_common_file_operations.py # ✅ SAFE - Common file operations utility tests
├── test_create_server.py   # ✅ SAFE - Server creation logic tests
├── test_time_restriction.py # ✅ SAFE - Time-based access restriction tests
├── test_instance.py        # ⚠️ MIXED - Some safe unit tests, some _with_docker container tests
├── test_monitoring.py      # ❌ DOCKER - All functions end with _with_docker
├── test_integration.py     # ❌ DOCKER - test_integration_with_docker
├── test_populate_integration.py # ✅ SAFE - Real archive population tests
├── archive/                # **NEW** - Archive system tests (reorganized)
│   ├── __init__.py
│   ├── test_archive_operations.py # ✅ SAFE - Archive management API tests
│   ├── test_archive_sha256.py  # ✅ SAFE - SHA256 calculation and validation tests
│   └── test_archive_compression.py # ✅ SAFE - Archive compression utility tests
├── snapshots/              # **NEW** - Snapshot system tests (reorganized)
│   ├── __init__.py
│   ├── test_snapshots_basic.py # ✅ SAFE - Snapshot model and basic functionality tests
│   ├── test_snapshots_endpoints.py # ✅ SAFE - Snapshot API endpoint tests with mocks
│   └── test_snapshots_integrated.py # ✅ SAFE - Real Restic integration tests
├── dns/                    # **NEW** - DNS management system tests
│   ├── __init__.py
│   ├── test_api.py         # ✅ SAFE - DNS API endpoints with mocks
│   ├── test_dns_basic.py   # ✅ SAFE - Basic DNS functionality and utilities
│   ├── test_dns_basic_functionality.py # ✅ SAFE - Core DNS operations
│   ├── test_dns_client_diff.py # ✅ SAFE - DNS client comparison tests
│   ├── test_dns_manager_diff.py # ✅ SAFE - DNS manager functionality tests
│   ├── test_dnspod.py      # ✅ SAFE - DNSPod provider tests
│   ├── test_huawei.py      # ✅ SAFE - Huawei Cloud DNS provider tests
│   ├── test_manager.py     # ✅ SAFE - DNS manager class tests
│   ├── test_router.py      # ✅ SAFE - Router integration tests
│   └── test_utils.py       # ✅ SAFE - DNS utility function tests
├── cron/                   # **ENHANCED** - Cron job system tests with backup jobs
│   ├── __init__.py
│   ├── test_cron_basic.py  # ✅ SAFE - Cron job models and basic functionality
│   ├── test_cron_api.py    # ✅ SAFE - Cron job API endpoints with mocks
│   ├── test_cron_manager.py # ✅ SAFE - CronManager class functionality
│   ├── test_cron_persistence.py # ✅ SAFE - Database persistence functionality
│   ├── test_cron_next_run_time.py # ✅ SAFE - Next run time calculation
│   ├── test_cronjobs.py    # ✅ SAFE - Cron job registry and execution
│   ├── test_cron_scheduling.py # ✅ SAFE - Real APScheduler integration tests
│   ├── test_backup_job.py  # ✅ SAFE - Backup job implementation tests
│   └── test_restart_scheduler.py # ✅ SAFE - Restart scheduler conflict detection tests
├── dynamic_config/         # **ENHANCED** - Dynamic configuration system tests
│   ├── __init__.py
│   ├── test_dynamic_config.py # ✅ SAFE - Configuration management core functionality
│   ├── test_dynamic_config_api.py # ✅ SAFE - Configuration API endpoints
│   ├── test_dynamic_config_union_validation.py # ✅ SAFE - Union type validation
│   └── test_dynamic_config_integration.py # ✅ SAFE - Database integration tests
└── fixtures/               # Test utilities and fixtures
    ├── __init__.py
    ├── test_utils.py       # Test helper functions and cleanup utilities
    └── mcc_docker_wrapper.py # Minecraft Console Client wrapper for testing
```

### Current API Endpoints (From Actual Codebase)

**Authentication Routes (`/api/auth/`)**:

- `POST /auth/register` - User registration (requires OWNER role)
- `POST /auth/token` - OAuth2 token endpoint (username/password)
- `POST /auth/verifyCode` - Verify WebSocket login code with master token
- `WebSocket /auth/code` - Rotating 8-digit login codes (60-second TTL)

**Admin Routes (`/api/admin/`)**:

- `GET /admin/users/` - List all users (OWNER role required)
- `POST /admin/users/` - Create new user (OWNER role required)
- `PUT /admin/users/{id}` - Update user details (OWNER role required)
- `DELETE /admin/users/{id}` - Delete user (OWNER role required)

**User Routes (`/api/user/`)**:

- `GET /user/me` - Current user profile (requires JWT)

**System Routes (`/api/system/`)**:

- `GET /system/info` - System metrics (CPU, memory, disk usage for server/backup paths)

**Server Routes (`/api/servers/`)**:

- `GET /servers/` - List all servers with basic info, status, and runtime data
- `POST /servers/` - Create new server from template or archive (via create.py)
- `GET /servers/{id}/` - Get detailed configuration for a specific server
- `GET /servers/{id}/status` - Get current server status (REMOVED/EXISTS/CREATED/RUNNING/STARTING/HEALTHY)
- `GET /servers/{id}/resources` - Get system resources (CPU, memory via cgroup v2) for running servers (via resources.py)
- `GET /servers/{id}/players` - Get online players for healthy servers (via players.py)
- `GET /servers/{id}/iostats` - I/O statistics only (disk I/O, network I/O - no disk space)
- `GET /servers/{id}/disk-usage` - Disk usage only (disk space info, always available)
- `GET /servers/{id}/compose` - Get current Docker Compose configuration as YAML (via compose.py)
- `POST /servers/{id}/compose` - Update Docker Compose configuration from YAML (via compose.py)
- `POST /servers/{id}/operations` - Perform server operations (start, stop, restart, up, down, remove) (via operations.py)
- `POST /servers/{id}/populate` - Populate server from archive file (via populate.py)
- `POST /servers/{id}/rcon` - Send RCON commands to running servers
- `WebSocket /servers/{id}/console` - **Real-time console log streaming + command execution**
- `GET /servers/{id}/snapshots/` - List server-specific snapshots
- `POST /servers/{id}/snapshots/` - Create server-specific snapshot

**Archive Routes (`/api/archives/`)**:

- `GET /archives/` - List all available archive files
- `POST /archives/upload` - Upload new archive file with validation
- `DELETE /archives/{filename}` - Delete archive file
- `POST /archives/{filename}/sha256` - Calculate SHA256 hash for archive

**Global Snapshot Routes (`/api/snapshots/`)**:

- `GET /snapshots/` - List all global snapshots
- `POST /snapshots/` - Create global snapshot
- `GET /snapshots/{snapshot_id}` - Get specific snapshot details

**Cron Job Routes (`/api/cron/`)**:

- `GET /cron/jobs/` - List all cron jobs with status and execution info
- `POST /cron/jobs/` - Create new cron job with schedule and parameters
- `GET /cron/jobs/{cronjob_id}` - Get specific cron job configuration
- `POST /cron/jobs/{cronjob_id}/pause` - Pause active cron job
- `POST /cron/jobs/{cronjob_id}/resume` - Resume paused cron job
- `DELETE /cron/jobs/{cronjob_id}` - Cancel cron job (soft delete)
- `GET /cron/jobs/{cronjob_id}/executions` - Get execution history for cron job
- `GET /cron/jobs/{cronjob_id}/next-run-time` - Get next scheduled run time

**Dynamic Configuration Routes (`/api/config/`)**:

- `GET /config/modules/` - List all registered configuration modules
- `GET /config/modules/{module_name}` - Get configuration for specific module
- `PUT /config/modules/{module_name}` - Update configuration for specific module
- `POST /config/modules/{module_name}/reset` - Reset module configuration to defaults
- `GET /config/schemas/` - Get JSON schemas for all configuration modules
- `GET /config/schemas/{module_name}` - Get JSON schema for specific module

**DNS Management Routes (`/api/dns/`)**:

- `GET /dns/status` - Get DNS system status and provider connectivity
- `GET /dns/records` - List all DNS records across configured providers
- `POST /dns/records/update` - Batch update DNS records with validation
- `GET /dns/changes` - Get pending DNS changes and synchronization status
- `POST /dns/sync` - Force synchronization with DNS providers

**Server Restart Scheduling Routes (`/api/servers/{id}/restart-schedule/`)**:

- `GET /servers/{id}/restart-schedule/` - Get current restart schedule configuration
- `POST /servers/{id}/restart-schedule/` - Create or update restart schedule
- `DELETE /servers/{id}/restart-schedule/` - Remove restart schedule
- `POST /servers/{id}/restart-schedule/pause` - Pause restart schedule
- `POST /servers/{id}/restart-schedule/resume` - Resume restart schedule

### Snapshot Management System

**ResticManager Class** (`app.snapshots.ResticManager`):

- Core backup operations using subprocess integration with Restic
- Handles repository initialization and password management
- Provides async methods for snapshot creation and listing
- Manages snapshot metadata and filtering operations

**Pydantic Models** (`app.snapshots`):

```python
class ResticSnapshot(BaseModel):
    """Basic snapshot information from Restic"""
    short_id: str
    id: str
    time: datetime
    tree: str
    paths: List[str]
    hostname: str
    username: str

class ResticSnapshotSummary(BaseModel):
    """Summary statistics for a snapshot"""
    files_new: int
    files_changed: int
    files_unmodified: int
    dirs_new: int
    dirs_changed: int
    dirs_unmodified: int
    data_blobs: int
    tree_blobs: int
    data_added: int
    total_files_processed: int
    total_bytes_processed: int
    total_duration: float
    snapshot_id: str

class ResticSnapshotWithSummary(BaseModel):
    """Complete snapshot with summary information"""
    snapshot: ResticSnapshot
    summary: ResticSnapshotSummary
```

**Dual API Structure:**

- **Global Snapshots**: System-wide snapshots covering all servers and configuration
- **Server Snapshots**: Individual server backups for specific Minecraft instances
- **Configuration**: ResticSettings with repository path and password management

## DNS Management System

**DNSManager Class** (`app.dns.DNSManager`):

- Unified DNS record management across multiple DNS providers
- Automatic DNS updates triggered by server operations and creation
- Provider abstraction layer supporting DNSPod and Huawei Cloud DNS
- Record synchronization and change detection
- Configuration management through dynamic configuration system

**DNS Provider Support** (`app.dns.dnspod`, `app.dns.huawei`):

- **DNSPod Integration**: Full API support for record management and domain operations
- **Huawei Cloud DNS**: Complete DNS record lifecycle with TTL configuration
- **Provider Interface**: Unified interface for cross-provider operations
- **Authentication**: Secure credential management for each provider
- **Rate Limiting**: Automatic rate limiting and retry logic for API calls

**Router Integration** (`app.dns.router`):

- Automatic router configuration updates
- Server address mapping and domain management
- Integration with server creation and deletion workflows
- Real-time address configuration synchronization

## Enhanced Cron Job System

**CronManager Class** (`app.cron.CronManager`):

- Advanced task scheduling using APScheduler with AsyncIOScheduler for async job execution
- Database persistence for cron job configurations and execution history
- Job lifecycle management: create, pause, resume, cancel operations
- Execution tracking with detailed logging and status monitoring
- Automatic job recovery on application startup from database state
- Support for complex cron expressions with optional second-level precision

**CronJobRegistry** (`app.cron.CronJobRegistry`):

- Centralized registration system for cron job functions and their parameter schemas
- Type-safe job parameter validation using Pydantic schemas
- Automatic schema discovery and validation for registered cron jobs
- Support for dynamic job registration during application startup

**Specialized Cron Jobs** (`app.cron.jobs`):

**Backup Job** (`app.cron.jobs.backup`):
- Automated backup scheduling with retention policies
- Uptime Kuma push notification integration for status reporting
- Configurable backup targets and retention settings
- Error handling and notification on backup failures

**Restart Job** (`app.cron.jobs.restart`):
- Automated server restart scheduling
- Integration with RestartScheduler for conflict detection
- Only restarts servers that are currently running
- Timezone-aware execution with proper status management

**RestartScheduler** (`app.cron.restart_scheduler`):

- Intelligent server restart scheduling with backup conflict detection
- Automatic validation to prevent restart-backup time conflicts
- Timezone support for proper scheduling across different time zones
- Active/inactive state management with automatic job lifecycle
- Integration with cron job system for seamless restart management

**Database Models**:

```python
class CronJob(BaseModel):
    """Persistent cron job configuration"""
    cronjob_id: str           # Unique job identifier
    identifier: str           # Job type identifier (registered function)
    name: str                 # Human-readable job name
    cron: str                 # Standard cron expression (5 fields)
    second: Optional[str]     # Optional second field for precision
    params_json: str          # JSON-serialized job parameters
    status: CronJobStatus     # ACTIVE, PAUSED, CANCELLED
    execution_count: int      # Total number of executions
    created_at: datetime
    updated_at: datetime

class CronJobExecution(BaseModel):
    """Individual job execution record"""
    cronjob_id: str          # Reference to parent cron job
    execution_id: str        # Unique execution identifier
    started_at: datetime     # Execution start time
    ended_at: Optional[datetime]  # Execution end time
    duration_ms: Optional[int]    # Execution duration
    status: ExecutionStatus  # RUNNING, COMPLETED, FAILED, CANCELLED
    messages_json: str       # JSON array of log messages
```

**Integration Patterns**:

```python
# Import the cron system
from app.cron import cron_manager, cron_registry
from app.cron.types import ExecutionContext

# Register a cron job function
@cron_registry.register("backup_cleanup", BackupCleanupSchema)
async def cleanup_old_backups(context: ExecutionContext) -> None:
    context.log("Starting backup cleanup...")
    # Job implementation here
    context.log("Backup cleanup completed")

# Create and manage cron jobs
cronjob_id = await cron_manager.create_cronjob(
    identifier="backup_cleanup",
    params=BackupCleanupSchema(retention_days=30),
    cron="0 2 * * 0",  # Weekly at 2 AM on Sundays
    name="Weekly Backup Cleanup"
)

# Get execution history
history = await cron_manager.get_execution_history(cronjob_id, limit=10)
```

## Dynamic Configuration System

**ConfigManager Class** (`app.dynamic_config.ConfigManager`):

- Runtime configuration management with in-memory caching for performance
- Database persistence with automatic synchronization
- Schema-based validation using Pydantic models
- Automatic configuration migration when schemas evolve
- Thread-safe access to configurations across application components
- Default configuration generation for new modules

**BaseConfigSchema** (`app.dynamic_config.BaseConfigSchema`):

- Base class for all configuration schemas with built-in versioning
- Automatic JSON schema generation for frontend integration
- Support for complex nested configurations and union types
- Built-in validation and type safety for configuration values

**ConfigMigrator** (`app.dynamic_config.ConfigMigrator`):

- Automatic schema migration when configuration formats change
- Default value generation for new configuration fields
- Migration logging and rollback support for configuration changes
- Backward compatibility handling for legacy configuration formats

**Database Model**:

```python
class DynamicConfig(BaseModel):
    """Persistent configuration storage"""
    module_name: str              # Unique module identifier
    config_data: Dict[str, Any]   # JSON configuration data
    config_schema_version: str    # Schema version for migration
    updated_at: datetime          # Last update timestamp
```

**Configuration Schema Example**:

```python
# Define configuration schema in app/dynamic_config/configs/module_name.py
class TimeRestrictionConfig(BaseConfigSchema):
    """Time restriction configuration sub-model"""
    enabled: Annotated[bool, Field(description="是否启用快照创建时间限制")] = True
    before_seconds: Annotated[int, Field(description="备份时间前多少秒禁止创建快照", ge=0, le=300)] = 30
    after_seconds: Annotated[int, Field(description="备份时间后多少秒禁止创建快照", ge=0, le=300)] = 60

class SnapshotsConfig(BaseConfigSchema):
    """Snapshots management configuration"""
    time_restriction: Annotated[TimeRestrictionConfig, Field(description="快照创建时间限制配置")] = TimeRestrictionConfig()
    restore_safety_max_age_seconds: Annotated[int, Field(description="恢复安全检查要求的最近快照最大年龄（秒）", ge=30, le=3600)] = 60
```

**Registration and Usage Pattern**:

```python
# 1. Register configuration in app/dynamic_config/__init__.py
from .configs.snapshots import SnapshotsConfig

class ConfigProxy:
    @property
    def snapshots(self):
        return cast(SnapshotsConfig, self._manager.get_config("snapshots"))

# Register during module initialization
config_manager.register_config("snapshots", SnapshotsConfig)

# 2. Import and use in application code
from app.dynamic_config import config

# Access configuration with full type safety
if not config.snapshots.time_restriction.enabled:
    return

before_seconds = config.snapshots.time_restriction.before_seconds
max_age = config.snapshots.restore_safety_max_age_seconds

# Configuration updates through API endpoints (automatic validation)
# Runtime access is read-only through config proxy
```

**Testing with Dynamic Configuration**:

```python
# Mock configuration in tests
from unittest.mock import MagicMock

mock_time_restriction = MagicMock()
mock_time_restriction.enabled = True
mock_time_restriction.before_seconds = 30
mock_time_restriction.after_seconds = 60

mock_snapshots_config = MagicMock()
mock_snapshots_config.time_restriction = mock_time_restriction

mock_config = MagicMock()
mock_config.snapshots = mock_snapshots_config

with patch("app.routers.snapshots.config", mock_config):
    # Test code here
    pass
```

## Download Manager System

**File Download Management**:

- **Progress Tracking**: Real-time file download progress monitoring with transfer rate calculation
- **Cancellation Support**: Ability to cancel in-progress downloads with proper cleanup
- **Status Management**: Comprehensive download status tracking (PENDING, DOWNLOADING, COMPLETED, CANCELLED, FAILED)
- **Background Processing**: Async download operations that don't block API responses

**Integration with File Operations**:

- **Server Files**: Download server files and directories with progress tracking
- **Archive Files**: Download archive files with integrity verification
- **Large File Support**: Efficient handling of large file downloads with streaming
- **Error Recovery**: Proper error handling and cleanup for failed downloads

**Download Status Tracking**:

```python
class DownloadStatus(Enum):
    """Download operation status"""
    PENDING = "pending"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"

class DownloadProgress(BaseModel):
    """Download progress information"""
    bytes_downloaded: int
    total_bytes: Optional[int]
    progress_percentage: Optional[float]
    download_speed: Optional[float]  # bytes per second
    estimated_time_remaining: Optional[float]  # seconds
    status: DownloadStatus
```

## Archive Management System

**Archive Router** (`app.routers.archive`):

- Complete CRUD operations for archive lifecycle management
- File upload handling with multipart form data support
- SHA256 hash calculation for file integrity verification
- Archive deletion with proper file system cleanup

**Compression Utilities** (`app.utils.compression`):

- 7z archive creation for server files and directories with high compression ratio
- Automatic filename generation with timestamps and sanitization
- Support for both full server compression and selective file/directory compression
- Progress tracking and error handling with detailed HTTP exceptions
- Async compression operations using subprocess integration

**Decompression Utilities** (`app.utils.decompression`):

- Support for ZIP, TAR, and TAR.GZ format extraction
- Async decompression operations with proper error handling
- Validation of archive contents before extraction
- Configurable extraction paths with security checks

**Server Population** (`app.routers.servers.populate`):

- Archive-to-server deployment functionality
- Integration with decompression utilities for archive extraction
- Server directory preparation and file copying
- Rollback capabilities for failed population operations

**Common File Operations** (`app.common.file_operations`):

- Shared utilities for file system operations
- Cross-platform path handling and validation
- Async file operations with proper resource management
- Error handling and cleanup for partial operations

### Authentication Patterns

**JWT Authentication:**

- OAuth2 password bearer token flow
- Tokens expire in 30 days by default (configurable)
- Use `dependencies.get_current_user` for protected routes
- **joserfc** library for JWT handling with HS256 algorithm

**Master Token Access:**

- Any endpoint accepting JWT also accepts `Authorization: Bearer <master_token>`
- Master token acts as synthetic OWNER user for system-level operations
- Creates audit log entries when master token is used
- Required for WebSocket login code verification

**Role-Based Access:**

- Use `dependencies.RequireRole(UserRole.ADMIN)` for role gating
- Roles: ADMIN, OWNER (enum values in models.py)
- OWNER role required for user registration

**WebSocket Login Flow:**

- Client connects to `/api/auth/code` WebSocket
- Server sends rotating 8-digit codes every few seconds (60-second TTL)
- External system verifies codes via `POST /api/auth/verifyCode` with master token
- Returns JWT token on successful verification

## Database Patterns

- **Async Sessions**: Use `get_db()` dependency for database access
- **SQLAlchemy 2.0**: Modern declarative models with full async support and AsyncAttrs mixin
- **Models**: User model with id, username, hashed_password, role fields
- **Initialization**: Tables auto-create on startup via `init_db()` in app lifespan
- **CRUD**: Async patterns with SQLAlchemy 2.0 syntax (see `db/crud/user.py`)
- **Password Hashing**: bcrypt via passlib with automatic verification

## Integrated Minecraft Management Module (NOT External Library)

### Module Architecture

The `app.minecraft` module provides comprehensive Minecraft server management capabilities that are **fully integrated** into the backend codebase. This is NOT an external dependency but a complete implementation within the backend.

### Core Classes

**DockerMCManager** (`app.minecraft.DockerMCManager`):

- Main entry point for managing multiple Minecraft servers
- Handles server discovery and batch operations across server directory
- Usage: `from app.minecraft import DockerMCManager`

**MCInstance** (`app.minecraft.MCInstance`):

- Represents individual Minecraft server with complete lifecycle management
- Provides comprehensive monitoring APIs for resource usage via cgroup v2
- Manages Docker Compose operations for single server
- Supports RCON command execution and log file monitoring

**MCComposeFile** (`app.minecraft.MCComposeFile`):

- Strongly-typed wrapper for Minecraft-specific Docker Compose configurations
- Extends generic ComposeFile with Minecraft server validation
- Provides Pydantic-based configuration validation and defaults

### Server Status Lifecycle

```
REMOVED → EXISTS → CREATED → RUNNING → STARTING → HEALTHY
                                   ↗ (health checks determine STARTING vs HEALTHY)
```

**Status Definitions:**

1. **REMOVED**: Server directory/configuration doesn't exist
2. **EXISTS**: Server directory exists, no Docker container created
3. **CREATED**: Docker container created but not running
4. **RUNNING**: Container running but not yet healthy (health checks failing)
5. **STARTING**: Container running and starting up (transitional state)
6. **HEALTHY**: Container running and passing all health checks

### Resource Monitoring (cgroup v2 Direct Access)

**Available Monitoring APIs** (via MCInstance):

- `get_container_id()`: Full Docker container ID for direct Docker API access
- `get_pid()`: Container main process ID for system-level monitoring
- `get_memory_usage()`: Current memory usage in bytes (via **direct cgroup v2 filesystem access**)
- `get_cpu_percentage()`: CPU usage percentage (spends 1 seconds to collect cpu usage info)
- `get_disk_io()`: Disk I/O read/write statistics from block devices
- `get_network_io()`: Network I/O receive/transmit statistics from container interfaces (via /proc/{pid}/net/dev)
- `get_disk_space_info()`: Complete disk space information (used, total, available) - **always available**

**Monitoring Implementation:**

- Uses **direct cgroup v2 filesystem access** for accurate container-level metrics
- Path resolution: `/sys/fs/cgroup/system.slice/docker-{container_id}.scope/`
- Handles both rootful and rootless Docker configurations
- Provides real-time metrics without Docker API inspection overhead
- Error handling for missing cgroup interfaces or permissions
- Memory stats include anonymous, file, kernel, and total memory usage
- Block I/O tracks per-device read/write operations and bytes

### WebSocket Console Integration

**Real-time Console Streaming** (`app.websocket.console`):

- **File Monitoring**: Watchdog-based monitoring of `logs/latest.log` file
- **Initial Content**: Sends last 1MB of log content on WebSocket connection
- **Live Updates**: Real-time streaming of new log lines as they're written
- **Command Execution**: Accepts RCON commands via WebSocket and streams results
- **Error Handling**: Graceful cleanup of file watchers and WebSocket connections

**WebSocket Message Protocol:**

```python
# Outbound messages
{"type": "log", "content": "log line content"}
{"type": "command_result", "command": "original command", "result": "rcon result"}
{"type": "error", "message": "error description"}

# Inbound messages
{"type": "command", "command": "minecraft command to execute"}
```

### Operation Audit System

**Middleware Architecture:**
The `OperationAuditMiddleware` extends `BaseHTTPMiddleware` and automatically intercepts HTTP requests to log operations that modify server state or data.

**Implementation:**

```python
# app/main.py - Middleware registration
from .audit import OperationAuditMiddleware
app.add_middleware(OperationAuditMiddleware)

# app/audit.py - Core middleware class
class OperationAuditMiddleware(BaseHTTPMiddleware):
    AUDIT_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
    AUDIT_PATH_PATTERNS = {"/api/admin/", "/api/auth/register"}
    SERVER_OPERATION_PATTERNS = {"/operations", "/compose", "/rcon"}
```

**Configuration:**

```python
# app/config.py - Audit settings
class AuditSettings(BaseModel):
    enabled: bool = True
    log_file: str = "operations.log"
    log_request_body: bool = True
    max_body_size: int = 10240
    sensitive_fields: list[str] = ["password", "token", "secret", "key"]
```

**Logged Operations:**

- Server management: `/api/servers/{id}/operations`, `/api/servers/{id}/compose`, `/api/servers/{id}/rcon`
- Snapshot operations: `/api/snapshots/*`, `/api/servers/{id}/snapshots/*`
- User administration: All `/api/admin/*` endpoints, `/api/auth/register`
- All POST/PUT/PATCH/DELETE operations that change system state
- Automatic exclusion of query operations (GET requests)

**Security Features:**

- Sensitive field masking with configurable field list
- Request body size limits to prevent log bloat
- User authentication integration through existing `get_current_user` function
- Client IP detection with proxy header support

### Integration Patterns

```python
# Import the integrated modules
from app.minecraft import DockerMCManager, MCInstance, MCServerStatus
from app.snapshots import ResticManager

# Initialize manager with servers directory
manager = DockerMCManager(settings.server_path)

# Get all server instances
servers = await manager.get_all_server_names()

# Work with individual server
instance = manager.get_instance("my_server")
status = await instance.get_status()

# Disk space info (always available)
disk_info = await instance.get_disk_space_info()  # Returns DiskSpaceInfo with used/total/available

# Resource monitoring
memory_usage = await instance.get_memory_usage()  # Bytes from cgroup v2
cpu_percent = await instance.get_cpu_percentage()  # Percentage over time

# I/O statistics (separated from disk space)
disk_io = await instance.get_disk_io()  # Disk I/O performance only
network_io = await instance.get_network_io()  # Network I/O statistics

# RCON command execution
result = await instance.send_rcon_command("list")  # Returns command output

# Snapshot management
restic_manager = ResticManager(settings.restic)
snapshots = await restic_manager.list_snapshots()
snapshot_response = await restic_manager.create_snapshot(["/path/to/backup"])
```

## Development Conventions

### Import Patterns

- Use package-relative imports within `app/` (e.g., `from .db.database import get_db`)
- Avoid relying on current working directory for paths
- Import integrated modules: `from app.minecraft import DockerMCManager, MCInstance`
- Import snapshot system: `from app.snapshots import ResticManager`

### Configuration Management

- Settings loaded via pydantic-settings with source priority:
  1. Init args → OS env → .env file → TOML file → secrets
- Access via `from .config import settings`
- Nest TOML keys exactly as modeled in `Settings` class
- Support for Path objects and automatic type conversion
- ResticSettings nested under `[restic]` section

### Logging

- Pre-configured with rotation: `from .logger import logger`
- Logs to `${logs_dir}/app.log` (configurable via settings)
- Combines file output with stdout for development
- Structured logging with proper async handling

### Error Handling

- Use FastAPI exception handlers and HTTP status codes
- Pydantic validation errors handled automatically
- Database constraint violations should raise HTTPException
- WebSocket exceptions for WebSocket-specific error handling
- Graceful degradation for optional monitoring features
- Backup operations should handle Restic errors gracefully

### Async/Await Patterns

- **Consistent Async**: All I/O operations use async/await
- **Concurrent Operations**: `asyncio.gather()` for parallel execution
- **Resource Cleanup**: Async context managers and proper cleanup
- **File Operations**: aiofiles for all file I/O operations
- **Database**: Async sessions throughout with proper session management
- **Subprocess**: Async subprocess calls for Restic operations

## External Documentation

**Use Context7 for external library documentation:**

- FastAPI: `/tiangolo/fastapi`
- SQLAlchemy: `/websites/sqlalchemy-en-20`
- Pydantic: `/pydantic/pydantic`
- pydantic-settings: `/pydantic/pydantic-settings`
- Uvicorn: `/encode/uvicorn`
- psutil: `/giampaolo/psutil`
- joserfc: `/jose/joserfc`
- pytest-asyncio: `/pytest-dev/pytest-asyncio`
- Restic: `/restic/restic` (backup tool documentation)

Always resolve library ID first, then fetch focused docs for the specific feature you're implementing.

## Integration Notes

- **Fully Integrated**: Minecraft management is integrated in `app.minecraft`, NOT an external library
- **Integrated Backup System**: Restic snapshot management built into `app.snapshots`, NOT an external library
- **CORS**: Configured for `localhost` and `localhost:3000` origins with credentials support
- **Root Path**: All routes mounted under `/api` prefix
- **Database**: SQLite file location configurable via `database_url` setting
- **WebSocket Support**: Built-in WebSocket routing with FastAPI native support
- **File Monitoring**: Watchdog for real-time log file monitoring
- **Container Management**: Direct Docker CLI integration without Python SDK dependency
- **Separated APIs**: Disk usage and I/O statistics split for better reliability and performance
- **Backup Integration**: Restic subprocess integration with async/await patterns
- **Compression Integration**: 7z compression utilities for server file archiving with async operations
- **CI/CD Ready**: Automated testing and build pipelines compatible with GitHub Actions workflows

## Update Instructions

When adding new features, dependencies, or changing the API:

1. **Database schema changes**: **MANDATORY** - Use `alembic revision --autogenerate` for any model changes in `app/models.py`
   - NO NEED FOR MIGRATION FOR NEW TABLES. ONLY FOR SCHEMA CHANGES ON EXISTING TABLE
   - Never code for backward compatibility - assume migrations are applied
   - Review and test autogenerated migrations before applying
   - Apply migrations with `alembic upgrade head`
2. **New routers**: Add to `app/routers/` and mount in `main.py`
3. **New dependencies**: Update `pyproject.toml` and document in this file
4. **New settings**: Add to `config.py` Settings model and document required TOML structure
5. **New endpoints**: Update API documentation and authentication patterns
6. **External libraries**: Add Context7 library IDs to this file
7. **Minecraft module changes**: Update integration patterns and test coverage
8. **Snapshot system changes**: Update ResticManager integration patterns and test coverage
9. **Compression utilities**: Update `app.utils.compression` for new compression features and test with `test_archive_compression.py`
10. **WebSocket endpoints**: Follow existing patterns in `app.websocket` module
11. **Test changes**: Mark Docker container tests with `_with_docker` suffix and integration tests with `integrated`
12. **API separations**: Document endpoint purpose and data separation rationale
13. **Audit configuration**: Update audit patterns in `OperationAuditMiddleware` for new sensitive operations
14. **Time restrictions**: Update time-based access controls and test with `test_time_restriction.py`

**IMPORTANT EDITING GUIDELINES:**

**Before updating any CLAUDE.md file:**

1. **Check git history** to identify the last CLAUDE.md update commit: `git log --oneline --follow -- CLAUDE.md | head -5`
2. **Compare current state** with the last CLAUDE.md update: `git diff <last_commit>..HEAD --name-status`
3. **Analyze all changes** made since the last documentation update to ensure complete coverage
4. **Review new files, modified functionality, and architectural changes** to capture all relevant updates

**When writing CLAUDE.md updates:**

1. **Write complete, self-contained documentation** - each version should be fully accurate and comprehensive
2. **Avoid incremental/patch-like language** such as "Recent changes," "Latest updates," or "New additions"
3. **Integrate all information naturally** into the existing structure rather than appending changelog-style entries
4. **Ensure consistency** between all three CLAUDE.md files (main, backend, frontend) regarding shared concepts
5. **Reflect actual codebase state** - documentation should describe what IS, not what WAS or what changed

This approach ensures each CLAUDE.md version stands alone as complete project documentation rather than appearing as a series of patches or incremental updates.

Keep this CLAUDE.md file updated to help future development sessions understand the current backend architecture, the **integrated** Minecraft management capabilities, **integrated** Restic backup system, operation audit system, testing guidelines, and development patterns.
