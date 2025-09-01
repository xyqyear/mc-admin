# MC Admin Backend - FastAPI Development Guide

## What This Component Is

Backend REST API for the MC Admin Minecraft server management platform. Built with FastAPI + SQLAlchemy 2.0 on Python 3.12+, providing comprehensive server management APIs, JWT authentication with WebSocket login flow, real-time system monitoring, and integrated Minecraft Docker management capabilities.

## Tech Stack

### Core Backend Stack
- **Language**: Python 3.12+ with Poetry package management
- **Web Framework**: FastAPI + Uvicorn ASGI server with CORS middleware 
- **Database**: SQLAlchemy 2.0 Declarative Models (async) + SQLite + aiosqlite driver
- **Authentication**: JWT (joserfc) + OAuth2 password flow + WebSocket login codes
- **Validation**: Pydantic v2.11.7 + pydantic-settings v2.10.1 (TOML + environment variables)
- **Async Support**: Full async/await with greenlet for SQLAlchemy async operations
- **System Monitoring**: psutil v7.0.0 for CPU, memory, and disk metrics
- **Development**: pytest v8.3.3, black formatter, ipykernel for notebooks
- **Additional**: python-multipart, asyncer v0.0.8, alembic (dev)

### Integrated Minecraft Management Stack
- **Container Platform**: Docker Engine + Docker Compose integration
- **Async Framework**: asyncio with comprehensive async/await patterns throughout codebase
- **File Operations**: aiofiles v24.1.0 for async file I/O operations
- **YAML Processing**: PyYAML v6.0.2 for Docker Compose file parsing and generation
- **Resource Monitoring**: Real-time CPU, memory, disk I/O, and network monitoring via cgroup v2
- **Configuration Management**: Strongly-typed Minecraft Docker Compose file handling with Pydantic validation
- **Testing**: pytest-asyncio v0.24.0 + pytest-cov v5.0.0 for comprehensive async testing

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
```bash
poetry run pytest           # Run tests
poetry run black .          # Format code
```

## API Architecture

### Project Structure
```
app/
├── main.py                 # FastAPI app entrypoint, CORS, router mounting
├── config.py               # Settings model with TOML + env loading
├── models.py               # SQLAlchemy + Pydantic models
├── dependencies.py         # DI: database sessions, auth, role guards
├── logger.py               # Rotating file + stdout logging
├── __main__.py             # Module execution entry point
├── db/
│   ├── database.py         # Async engine, session factory, init_db()
│   └── crud/user.py        # User CRUD operations
├── auth/
│   ├── jwt_utils.py        # Password hashing, JWT create/verify
│   └── login_code.py       # WebSocket rotating codes + master token verification
├── routers/
│   ├── auth.py             # Authentication endpoints + WebSocket /auth/code
│   ├── user.py             # User profile endpoints
│   ├── system.py           # System metrics endpoints
│   └── servers.py          # Minecraft server management endpoints
├── system/
│   └── resources.py        # psutil wrappers for system info
└── minecraft/              # Integrated Minecraft Docker Management Module
    ├── __init__.py         # Public API exports (DockerMCManager, MCInstance, etc.)
    ├── manager.py          # DockerMCManager main class
    ├── instance.py         # MCInstance + server lifecycle management
    ├── compose.py          # Minecraft-specific compose file handling (MCComposeFile)
    ├── utils.py            # Async utility functions
    ├── docker/             # Docker integration submodule
    │   ├── __init__.py     # Docker module exports
    │   ├── manager.py      # ComposeManager + DockerManager classes
    │   ├── compose_file.py # Generic ComposeFile Pydantic models
    │   ├── cgroup.py       # Container resource monitoring via cgroup v2
    │   └── network.py      # Network statistics collection
    └── tests/              # Comprehensive test suite
        ├── __init__.py
        ├── test_instance.py     # MCInstance functionality
        ├── test_compose_file.py # Compose file parsing and validation
        ├── test_compose.py      # MCComposeFile functionality
        ├── test_monitoring.py   # Resource monitoring with real containers
        ├── test_integration.py  # Full integration tests (slow)
        └── fixtures/            # Test utilities and fixtures
            ├── __init__.py
            ├── test_utils.py    # Test helper functions
            └── mcc_docker_wrapper.py # Minecraft Console Client wrapper
```

### Current API Endpoints

**Authentication Routes (`/api/auth/`)**:
- `POST /auth/register` - User registration (requires OWNER role)
- `POST /auth/token` - OAuth2 token endpoint (username/password)
- `POST /auth/verifyCode` - Verify WebSocket login code with master token
- `WebSocket /auth/code` - Rotating 8-digit login codes

**User Routes (`/api/user/`)**:
- `GET /user/me` - Current user profile (requires JWT)

**System Routes (`/api/system/`)**:
- `GET /system/info` - System metrics (CPU, memory, disk usage for server/backup paths)

**Server Routes (`/api/servers/`)**:
- `GET /servers/` - List all servers with basic info, status, and runtime data
- `GET /servers/{id}/` - Get detailed configuration for a specific server
- `GET /servers/{id}/status` - Get current status of a specific server
- `GET /servers/{id}/resources` - Get system resources (CPU, memory) for running servers
- `GET /servers/{id}/players` - Get online players for healthy servers
- `GET /servers/{id}/iostats` - Get comprehensive I/O statistics (disk, network, storage)
- `POST /servers/{id}/operations` - Perform server operations (start, stop, restart, up, down, remove)

### Authentication Patterns

**JWT Authentication:**
- OAuth2 password bearer token flow
- Tokens expire in 30 days by default (configurable)
- Use `dependencies.get_current_user` for protected routes

**Master Token Access:**
- Any endpoint accepting JWT also accepts `Authorization: Bearer <master_token>`
- Master token acts as synthetic OWNER user for system-level operations
- Creates audit log entries when master token is used

**Role-Based Access:**
- Use `dependencies.RequireRole(UserRole.ADMIN)` for role gating
- Roles: USER, ADMIN, OWNER (enum values)

**WebSocket Login Flow:**
- Client connects to `/api/auth/code` WebSocket  
- Server sends rotating 8-digit codes every few seconds
- External system verifies codes via `POST /api/auth/verifyCode` with master token

## Database Patterns

- **Async Sessions**: Use `get_db()` dependency for database access
- **Models**: SQLAlchemy 2.0 Declarative models in `models.py`
- **Initialization**: Tables auto-create on startup via `init_db()` in app lifespan
- **CRUD**: Async patterns with SQLAlchemy 2.0 syntax (see `db/crud/user.py`)

## Integrated Minecraft Management Module

### Module Architecture

The `app.minecraft` module provides comprehensive Minecraft server management capabilities that were previously handled by the external `minecraft-docker-manager-lib`. This integration offers better performance, simplified deployment, and tighter integration with the backend.

### Core Classes

**DockerMCManager** (`app.minecraft.DockerMCManager`):
- Main entry point for managing multiple Minecraft servers
- Handles server discovery and batch operations across server directory
- Usage: `from app.minecraft import DockerMCManager`

**MCInstance** (`app.minecraft.MCInstance`):
- Represents individual Minecraft server with complete lifecycle management
- Provides comprehensive monitoring APIs for resource usage
- Manages Docker Compose operations for single server

**MCComposeFile** (`app.minecraft.MCComposeFile`):
- Strongly-typed wrapper for Minecraft-specific Docker Compose configurations
- Extends generic ComposeFile with Minecraft server validation
- Provides Pydantic-based configuration validation and defaults

### Server Status Lifecycle

```
REMOVED → EXISTS → CREATED → STARTING → HEALTHY
                                     ↗ RUNNING (fallback)
```

**Status Definitions:**
1. **REMOVED**: Server directory/configuration doesn't exist
2. **EXISTS**: Server directory exists, no Docker container created  
3. **CREATED**: Docker container created but not running
4. **STARTING**: Container running but not yet healthy (health checks failing)
5. **HEALTHY**: Container running and passing all health checks
6. **RUNNING**: Container operational but health status unknown (fallback state)

### Resource Monitoring

**Available Monitoring APIs** (via MCInstance):
- `get_container_id()`: Full Docker container ID for direct Docker API access
- `get_pid()`: Container main process ID for system-level monitoring  
- `get_memory_usage()`: Current memory usage in bytes (via cgroup v2)
- `get_cpu_percentage()`: CPU usage percentage (requires two calls over time interval)
- `get_disk_io()`: Disk I/O read/write statistics from block devices
- `get_network_io()`: Network I/O receive/transmit statistics from container interfaces
- `get_disk_space_info()`: Complete disk space information (used, total, available)

**Monitoring Implementation:**
- Uses cgroup v2 interfaces for accurate container-level metrics
- Handles both rootful and rootless Docker configurations
- Provides real-time metrics without container inspection overhead
- Error handling for missing cgroup interfaces or permissions

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
disk_info = await instance.get_disk_space_info()  # Returns DiskSpaceInfo with used/total/available
```

### Testing Architecture

**Test Categories:**
1. **Unit Tests**: Fast tests for individual components (majority of test suite)
2. **Integration Tests**: Full Docker workflow tests (marked for exclusion during development)
3. **Monitoring Tests**: Real container tests with session-scoped fixtures for efficiency

**Running Tests:**
```bash
# Run minecraft module tests specifically
poetry run pytest app/minecraft/tests/ -v

# Run specific test categories
poetry run pytest app/minecraft/tests/test_instance.py -v
poetry run pytest app/minecraft/tests/test_monitoring.py -v

# Avoid slow integration tests during development
poetry run pytest app/minecraft/tests/ -v -k "not test_integration"
```

## Development Conventions

### Import Patterns
- Use package-relative imports within `app/` (e.g., `from .db.database import get_db`)
- Avoid relying on current working directory for paths

### Configuration Management
- Settings loaded via pydantic-settings with source priority:
  1. Init args → OS env → .env file → TOML file → secrets
- Access via `from .config import settings`
- Nest TOML keys exactly as modeled in `Settings` class

### Logging
- Pre-configured with rotation: `from .logger import logger`
- Logs to `${logs_dir}/app.log` (configurable via settings)
- Combines file output with stdout

### Error Handling
- Use FastAPI exception handlers and HTTP status codes
- Pydantic validation errors handled automatically
- Database constraint violations should raise HTTPException

## External Documentation

**Use Context7 for external library documentation:**
- FastAPI: `/tiangolo/fastapi`
- SQLAlchemy: `/websites/sqlalchemy-en-20`  
- Pydantic: `/pydantic/pydantic`
- pydantic-settings: `/pydantic/pydantic-settings`
- Uvicorn: `/encode/uvicorn`
- psutil: `/giampaolo/psutil`
- joserfc: `/fromjose/joserfc`

Always resolve library ID first, then fetch focused docs for the specific feature you're implementing.

## Integration Notes

- **minecraft-docker-manager-lib**: Referenced as git dependency at v0.3.1
- **CORS**: Configured for `localhost` and `localhost:3000` origins
- **Root Path**: All routes mounted under `/api` prefix
- **Database**: SQLite file location configurable via `database_url` setting

## Update Instructions

When adding new features, dependencies, or changing the API:

1. **New routers**: Add to `app/routers/` and mount in `main.py`
2. **New dependencies**: Update `pyproject.toml` and document in this file
3. **Database changes**: Consider adding Alembic migrations
4. **New settings**: Add to `config.py` Settings model and document required TOML structure
5. **New endpoints**: Update API documentation and authentication patterns
6. **External libraries**: Add Context7 library IDs to this file

Keep this CLAUDE.md file updated to help future development sessions understand the current backend architecture and patterns.