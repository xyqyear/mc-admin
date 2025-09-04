# MC Admin Backend - FastAPI Development Guide

## What This Component Is

Backend REST API for the MC Admin Minecraft server management platform. Built with FastAPI + SQLAlchemy 2.0 on Python 3.12+, providing comprehensive server management APIs, JWT authentication with WebSocket login flow, real-time system monitoring, and **fully integrated** Minecraft Docker management capabilities (not an external library).

## Tech Stack

### Core Backend Stack
- **Language**: Python 3.12+ with Poetry package management
- **Web Framework**: FastAPI + Uvicorn ASGI server with CORS middleware
- **Database**: SQLAlchemy 2.0 Declarative Models (async) + SQLite + aiosqlite driver
- **Authentication**: JWT (joserfc) + OAuth2 + WebSocket login codes + Master token system
- **Validation**: Pydantic v2 + pydantic-settings (TOML + environment variables)
- **Async Support**: Full async/await with comprehensive asyncio patterns throughout
- **System Monitoring**: psutil v7.0.0 for CPU, memory, disk metrics
- **Development**: pytest v8.3.3 + pytest-asyncio + black formatter
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
backup_path = "/path/to/backups"
logs_dir = "./logs"  # Optional, defaults to ./logs

[jwt]
secret_key = "your-jwt-secret-key"
algorithm = "HS256"
access_token_expire_minutes = 43200  # 30 days
```

### Run Development Server
```bash
# Method 1: Using uvicorn directly (recommended for development)
poetry run uvicorn app.main:app --host 0.0.0.0 --port 5678 --reload

# Method 2: Run module directly  
poetry run python -m app.main

# The app serves routes under /api due to root_path="/api" configuration
```

### Testing and Quality

**⚠️ CRITICAL TESTING GUIDELINES:**

During development iteration, **NEVER run Docker container tests** to avoid timeouts. Only run safe tests that don't bring up containers:

```bash
# ✅ Safe for frequent development iteration
poetry run pytest tests/test_compose.py -v
poetry run pytest tests/test_compose_file.py -v
poetry run pytest tests/test_rcon_filtering.py -v
poetry run pytest tests/test_file_operations.py -v
poetry run pytest tests/test_websocket_console.py -v

# ✅ Safe unit tests (don't bring up containers)
poetry run pytest tests/test_instance.py::test_disk_space_info_dataclass -v
poetry run pytest tests/test_instance.py::test_minecraft_instance -v

# ✅ Skip all Docker container tests during development
poetry run pytest tests/ -v -k "not _with_docker and not test_integration"

# ✅ Test only changes related to specific functionality (example)
poetry run pytest tests/test_instance.py::test_disk_space_info_dataclass -v

# ❌ AVOID - These bring up Docker containers and will timeout/slow development
# poetry run pytest tests/test_monitoring.py  # All functions end with _with_docker
# poetry run pytest tests/test_integration.py::test_integration_with_docker
# poetry run pytest tests/test_instance.py::test_server_status_lifecycle_with_docker
# poetry run pytest tests/test_instance.py::test_get_disk_space_info_with_docker

# ❌ NEVER run all tests during development
# poetry run pytest tests/ -v  # Will timeout due to container tests
```

**Docker Container Tests (Renamed with `_with_docker` suffix):**
- `test_monitoring.py`: All 8 functions now end with `_with_docker`
- `test_integration.py`: `test_integration_with_docker` 
- `test_instance.py`: `test_server_status_lifecycle_with_docker`, `test_get_disk_space_info_with_docker`

**Code Quality:**
```bash
poetry run black .          # Format code
```

**Pre-commit Testing (with container tests):**
```bash
# Run with longer timeout for container tests (use sparingly)
poetry run pytest tests/ -v --timeout=600
```

## API Architecture

### Project Structure (Actual File Layout)
```
app/                        # Main application package
├── main.py                 # FastAPI app entrypoint, CORS, router mounting, lifespan management
├── config.py               # Settings model with TOML + env loading (pydantic-settings)
├── models.py               # SQLAlchemy + Pydantic models with async support
├── dependencies.py         # DI: database sessions, auth, role guards, master token handling
├── logger.py               # Rotating file + stdout logging configuration
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
├── routers/
│   ├── __init__.py
│   ├── auth.py             # Authentication endpoints + WebSocket /auth/code
│   ├── user.py             # User profile endpoints
│   ├── system.py           # System metrics endpoints (psutil integration)
│   └── servers/
│       ├── __init__.py
│       └── misc.py         # Minecraft server management endpoints (FULL CRUD + operations)
├── websocket/
│   ├── __init__.py         # WebSocket module exports
│   └── console.py          # Real-time console streaming with Watchdog file monitoring
├── system/
│   ├── __init__.py
│   └── resources.py        # psutil wrappers for system resource information
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
├── test_instance.py        # ⚠️ MIXED - Some safe unit tests, some _with_docker container tests
├── test_monitoring.py      # ❌ DOCKER - All functions end with _with_docker  
├── test_integration.py     # ❌ DOCKER - test_integration_with_docker
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

**User Routes (`/api/user/`)**:
- `GET /user/me` - Current user profile (requires JWT)

**System Routes (`/api/system/`)**:
- `GET /system/info` - System metrics (CPU, memory, disk usage for server/backup paths)

**Server Routes (`/api/servers/`)**:
- `GET /servers/` - List all servers with basic info, status, and runtime data
- `GET /servers/{id}/` - Get detailed configuration for a specific server
- `GET /servers/{id}/status` - Get current server status (REMOVED/EXISTS/CREATED/RUNNING/STARTING/HEALTHY)
- `GET /servers/{id}/resources` - Get system resources (CPU, memory via cgroup v2) for running servers
- `GET /servers/{id}/players` - Get online players for healthy servers
- `GET /servers/{id}/iostats` - **NEW: I/O statistics only** (disk I/O, network I/O - no disk space)
- `GET /servers/{id}/disk-usage` - **NEW: Disk usage only** (disk space info, always available)
- `GET /servers/{id}/compose` - Get current Docker Compose configuration as YAML
- `POST /servers/{id}/compose` - Update Docker Compose configuration from YAML
- `POST /servers/{id}/operations` - Perform server operations (start, stop, restart, up, down, remove)
- `POST /servers/{id}/rcon` - Send RCON commands to running servers
- `WebSocket /servers/{id}/console` - **Real-time console log streaming + command execution**

### Recent API Improvements

**Separated Disk Usage API (Latest Update):**
- **Problem**: Disk space information was bundled with I/O statistics, causing it to be unavailable when servers weren't running
- **Solution**: Split into two focused endpoints:
  - `/servers/{id}/iostats` - I/O performance metrics (disk I/O, network I/O) - requires running server
  - `/servers/{id}/disk-usage` - Disk space information (used, total, available) - always available
- **Benefits**: 
  - Disk space info now available regardless of server status
  - Cleaner API separation of concerns
  - Better frontend reliability for disk usage displays

**Pydantic Models:**
```python
# Separated models for better API design
class ServerIOStats(BaseModel):
    diskReadBytes: int
    diskWriteBytes: int
    networkReceiveBytes: int
    networkSendBytes: int

class ServerDiskUsage(BaseModel):
    diskUsageBytes: int
    diskTotalBytes: int
    diskAvailableBytes: int
```

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
- `get_cpu_percentage()`: CPU usage percentage (requires two calls over time interval)
- `get_disk_io()`: Disk I/O read/write statistics from block devices
- `get_network_io()`: Network I/O receive/transmit statistics from container interfaces (via /proc/{pid}/net/dev)
- `get_disk_space_info()`: **Enhanced**: Complete disk space information (used, total, available) - **always available**

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

### Integration Patterns

```python
# Import the integrated minecraft module
from app.minecraft import DockerMCManager, MCInstance, MCServerStatus

# Initialize manager with servers directory
manager = DockerMCManager(settings.server_path)

# Get all server instances
servers = await manager.get_all_server_names()

# Work with individual server
instance = manager.get_instance("my_server")
status = await instance.get_status()

# Enhanced disk space info (always available)
disk_info = await instance.get_disk_space_info()  # Returns DiskSpaceInfo with used/total/available

# Resource monitoring
memory_usage = await instance.get_memory_usage()  # Bytes from cgroup v2
cpu_percent = await instance.get_cpu_percentage()  # Percentage over time

# I/O statistics (separated from disk space)
disk_io = await instance.get_disk_io()  # Disk I/O performance only
network_io = await instance.get_network_io()  # Network I/O statistics

# RCON command execution
result = await instance.send_rcon_command("list")  # Returns command output
```

### Testing Architecture

**Test Categories:**
1. **✅ Safe Unit Tests**: Fast tests for individual components (majority during development)
2. **❌ Container Tests**: Full Docker workflow tests (avoid during development iteration)
3. **⚠️ Mixed Tests**: Some safe, some container tests (test selectively)

**Safe Tests for Development:**
- `test_compose.py` - Pure Pydantic model validation
- `test_compose_file.py` - File operations and YAML parsing
- `test_rcon_filtering.py` - Utility function testing
- `test_file_operations.py` - Mocked API endpoint testing
- `test_websocket_console.py` - WebSocket protocol with mocks
- `test_instance.py::test_disk_space_info_dataclass` - Data model testing
- `test_instance.py::test_minecraft_instance` - Configuration testing (no container startup)

**Container Tests (Avoid During Development):**
- `test_monitoring.py` - All functions ending with `_with_docker`
- `test_integration.py::test_integration_with_docker` - Full workflow
- `test_instance.py::test_server_status_lifecycle_with_docker` - Container lifecycle
- `test_instance.py::test_get_disk_space_info_with_docker` - Disk space with container

**Running Tests:**
```bash
# ✅ Development iteration - safe tests only
poetry run pytest tests/ -v -k "not _with_docker and not test_integration"

# ✅ Test specific functionality related to changes
poetry run pytest tests/test_instance.py::test_disk_space_info_dataclass -v

# ❌ Avoid during development (will timeout)
# poetry run pytest tests/test_monitoring.py -v

# ✅ Pre-commit (with timeout)
poetry run pytest tests/ -v --timeout=600
```

## Development Conventions

### Import Patterns
- Use package-relative imports within `app/` (e.g., `from .db.database import get_db`)
- Avoid relying on current working directory for paths
- Import integrated minecraft module: `from app.minecraft import DockerMCManager, MCInstance`

### Configuration Management
- Settings loaded via pydantic-settings with source priority:
  1. Init args → OS env → .env file → TOML file → secrets
- Access via `from .config import settings`
- Nest TOML keys exactly as modeled in `Settings` class
- Support for Path objects and automatic type conversion

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

### Async/Await Patterns
- **Consistent Async**: All I/O operations use async/await
- **Concurrent Operations**: `asyncio.gather()` for parallel execution  
- **Resource Cleanup**: Async context managers and proper cleanup
- **File Operations**: aiofiles for all file I/O operations
- **Database**: Async sessions throughout with proper session management

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

Always resolve library ID first, then fetch focused docs for the specific feature you're implementing.

## Integration Notes

- **Fully Integrated**: Minecraft management is integrated in `app.minecraft`, NOT an external library
- **CORS**: Configured for `localhost` and `localhost:3000` origins with credentials support
- **Root Path**: All routes mounted under `/api` prefix
- **Database**: SQLite file location configurable via `database_url` setting
- **WebSocket Support**: Built-in WebSocket routing with FastAPI native support
- **File Monitoring**: Watchdog for real-time log file monitoring
- **Container Management**: Direct Docker CLI integration without Python SDK dependency
- **Separated APIs**: Disk usage and I/O statistics split for better reliability and performance

## Update Instructions

When adding new features, dependencies, or changing the API:

1. **New routers**: Add to `app/routers/` and mount in `main.py`
2. **New dependencies**: Update `pyproject.toml` and document in this file
3. **Database changes**: Consider adding Alembic migrations for schema changes
4. **New settings**: Add to `config.py` Settings model and document required TOML structure
5. **New endpoints**: Update API documentation and authentication patterns
6. **External libraries**: Add Context7 library IDs to this file
7. **Minecraft module changes**: Update integration patterns and test coverage
8. **WebSocket endpoints**: Follow existing patterns in `app.websocket` module
9. **Test changes**: Mark Docker container tests with `_with_docker` suffix
10. **API separations**: Document endpoint purpose and data separation rationale

Keep this CLAUDE.md file updated to help future development sessions understand the current backend architecture, the **integrated** Minecraft management capabilities, testing guidelines, and development patterns.