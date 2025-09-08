# MC Admin - Minecraft Server Management Platform

## Project Overview

MC Admin is a comprehensive web-based platform for managing Minecraft servers using Docker containers. The project consists of two main components working together to provide a complete server management solution with enterprise-grade backup and recovery capabilities.

**Components:**
1. **Backend API** (FastAPI + Python 3.12+) - RESTful API with integrated Minecraft management, JWT authentication, WebSocket support, and Restic-based snapshot system
2. **Frontend Web UI** (React 18 + TypeScript + Ant Design 5) - Modern SPA with real-time updates, Monaco editor integration, and comprehensive backup management

**Key Features:**
- Complete Minecraft server lifecycle management (create, start, stop, monitor, delete)
- **Enterprise Snapshot System** - Full backup and restoration using Restic with global and server-specific snapshots
- **Archive Management System** - Comprehensive archive file management with SHA256 verification, decompression support, and server population from archives
- Real-time system and server resource monitoring (CPU, memory, disk, network via cgroup v2)
- Docker Compose configuration management with Monaco editor and schema validation
- JWT-based authentication with role-based access control (ADMIN/OWNER) + Master token system
- Dual authentication: WebSocket login code flow + traditional password authentication
- Real-time console streaming and RCON command execution via WebSocket
- **Server Template System** - Pre-configured server templates for quick deployment
- Comprehensive resource monitoring with cgroup v2 integration
- Sophisticated data fetching with React Query three-layer architecture and intelligent caching strategies
- **Separated disk usage API**: Disk space information available regardless of server status
- **Operation audit system**: Non-invasive middleware-based audit logging for all state-changing operations
- **Modular Component Architecture** - Organized modal components and reusable UI elements

## Architecture

**System Architecture:**
- **Database**: SQLite with async support (SQLAlchemy 2.0 + aiosqlite)
- **Authentication**: JWT tokens with OAuth2 password flow + WebSocket rotating login codes + Master token fallback
- **Container Management**: Integrated Docker Compose management (not external dependency)
- **Backup System**: Restic-based snapshot management with configurable repositories
- **Archive System**: Complete archive lifecycle with decompression, validation, and server population
- **Communication**: RESTful API + WebSocket for real-time features (console streaming, login codes)
- **Configuration**: TOML-based settings with environment variable overrides
- **Monitoring**: cgroup v2 direct filesystem monitoring for container resources
- **API Architecture**: Modular router-based design with separated concerns (operations, compose, files, resources, players)
- **Audit System**: FastAPI middleware with automatic operation logging to structured JSON files

**Data Flow:**
Frontend (React Query) ↔ Backend API (FastAPI) ↔ Integrated Minecraft Module ↔ Docker Engine
                                                ↔ Restic Backup System ↔ Backup Repository
                                                ↔ Archive Management ↔ File System

## Technology Stack Summary

### Backend (Python 3.12+)
- **Web Framework**: FastAPI + Uvicorn ASGI server with CORS middleware
- **Database**: SQLAlchemy 2.0 (async) + SQLite + aiosqlite driver
- **Authentication**: JWT (joserfc) + OAuth2 + WebSocket login codes + Master token system
- **Validation**: Pydantic v2 + pydantic-settings with TOML support
- **System Monitoring**: psutil + direct cgroup v2 filesystem monitoring
- **Container Integration**: **Integrated** Minecraft Docker management module (app.minecraft)
- **Backup System**: **Integrated** Restic snapshot management (app.snapshots)
- **Archive System**: **Integrated** archive management with decompression utilities (app.utils.decompression)
- **Common Operations**: Shared file operations module (app.common.file_operations)
- **WebSocket Support**: FastAPI WebSocket + Watchdog file monitoring for console streaming
- **Package Management**: Poetry
- **Development**: pytest + black + pytest-asyncio for comprehensive async testing with separated unit/integration tests

### Frontend (Node.js 18+)
- **Framework**: React 18 + TypeScript 5 with strict compiler options
- **Build Tool**: Vite 5 with React plugin, path alias (@), and hot reload
- **UI Library**: Ant Design 5 + @ant-design/icons + @ant-design/pro-components
- **Styling**: Tailwind CSS 3 + PostCSS (preflight disabled for AntD compatibility)
- **State Management**: Zustand v4.5.0 with localStorage persistence middleware
- **Data Fetching**: TanStack React Query v5.85.5 with sophisticated three-layer architecture
- **Code Editor**: Monaco Editor v0.52.2 + monaco-yaml v5.4.0 with Docker Compose schema
- **Routing**: React Router v6 with nested routes and future flags enabled
- **Error Handling**: react-error-boundary for graceful error boundaries
- **Linting**: ESLint v9 with TypeScript and React plugins (modern flat config)
- **Package Management**: pnpm (preferred - pnpm-lock.yaml present)

## Development Environment

### Prerequisites
- **Python**: 3.12+ (backend)
- **Node.js**: 18+ (frontend)
- **Docker**: Engine + Compose (for Minecraft server management)
- **Restic**: Backup tool (automatically managed by backend)
- **Poetry**: Python package management
- **pnpm**: Node.js package management (preferred over npm)

### Project Structure
```
mc-admin/
├── backend/          # FastAPI backend with integrated Minecraft management
│   ├── app/
│   │   ├── common/          # Shared file operations
│   │   ├── utils/           # Decompression and utility functions
│   │   ├── snapshots/       # Restic backup integration
│   │   ├── minecraft/       # Docker container lifecycle
│   │   └── routers/
│   │       ├── archive.py        # Archive management API
│   │       ├── snapshots.py      # Global snapshot management
│   │       └── servers/          # Server-specific endpoints
│   │           ├── compose.py    # Docker Compose management
│   │           ├── create.py     # Server creation
│   │           ├── operations.py # Server operations (start/stop)
│   │           ├── resources.py  # Resource monitoring
│   │           ├── players.py    # Player management
│   │           └── populate.py   # Server population from archives
├── frontend-react/   # React frontend application
│   ├── src/
│   │   ├── components/
│   │   │   └── modals/           # Organized modal components
│   │   │       ├── ServerFiles/  # Server file management modals
│   │   │       ├── ArchiveSelectionModal.tsx
│   │   │       └── ServerTemplateModal.tsx
│   │   ├── hooks/
│   │   │   ├── api/             # Raw API layer
│   │   │   │   ├── archiveApi.ts
│   │   │   │   └── serverApi.ts
│   │   │   ├── queries/
│   │   │   │   ├── base/        # Resource-focused query hooks
│   │   │   │   │   └── useArchiveQueries.ts
│   │   │   │   └── page/        # Composed page-level queries
│   │   │   └── mutations/       # Organized mutation hooks
│   │   │       └── useArchiveMutations.ts
│   │   └── pages/
│   │       ├── ArchiveManagement.tsx  # Archive management
│   │       └── Snapshots.tsx          # Global snapshot management
└── CLAUDE.md        # This project overview file
```

Each component has dedicated development instructions:
- `backend/CLAUDE.md` - Backend API development guide
- `frontend-react/CLAUDE.md` - Frontend React development guide

## Key Development Patterns

### Backend Patterns (Actual Implementation)
- **Modular Router Architecture**: Separated server operations into focused routers (operations.py, compose.py, create.py, resources.py, players.py, populate.py)
- **Integrated Minecraft Management**: Full Docker container lifecycle in `app.minecraft` module
- **Restic Snapshot Integration**: Complete backup system in `app.snapshots` with ResticManager class
- **Archive Management System**: Complete archive lifecycle with decompression support and SHA256 validation
- **Common Utilities**: Shared file operations in `app.common` and decompression utilities in `app.utils`
- **SQLAlchemy 2.0 Async**: All database operations with async/await patterns
- **Dual Authentication**: JWT tokens + WebSocket rotating codes + Master token fallback
- **Real-time Console**: WebSocket streaming with file system watchers (Watchdog)
- **cgroup v2 Monitoring**: Direct filesystem monitoring for accurate container metrics
- **TOML Configuration**: Nested settings with environment variable override support including ResticSettings
- **Comprehensive Testing**: pytest with asyncio support and real Docker integration, separated unit and integration tests
- **Separated API Design**: Disk usage info separated from I/O statistics for better reliability
- **Operation Audit**: Non-invasive middleware that automatically logs state-changing operations with user context, request details, and sensitive data masking

### Frontend Patterns (Actual Implementation)
- **Three-Layer Data Architecture**: 
  1. Raw API layer (`hooks/api/` - authApi.ts, snapshotApi.ts, archiveApi.ts, etc.)
  2. Base Query layer (`hooks/queries/base/` - resource-focused hooks)
  3. Page Query layer (`hooks/queries/page/` - composed page-specific queries)
- **Organized Mutations**: Dedicated mutations directory with focused hook files (useAuthMutations, useSnapshotMutations, useFileMutations, useArchiveMutations)
- **Modular Component Architecture**: Organized modal components with barrel exports (`components/modals/ServerFiles/`)
- **Zustand State Management**: Token, sidebar, and login preference stores with persistence
- **Monaco Editor Integration**: Multi-worker setup with YAML schema validation
- **Intelligent Caching**: Different refetch intervals based on data volatility (snapshots: 2min, servers: varied)
- **Dual Authentication UI**: WebSocket code login + traditional password login
- **Real-time Updates**: WebSocket integration for console and live data
- **Error Boundaries**: Graceful error handling with fallback components
- **Modern ESLint Configuration**: Flat config with TypeScript and React plugins
- **Absolute Import System**: Consistent use of @/ alias for all imports

## Snapshot Management System

### Backend Snapshot Architecture
- **ResticManager Class**: Core backup operations using subprocess integration
- **Dual API Structure**: 
  - Global snapshots (`/api/snapshots/`) - System-wide backup management
  - Server snapshots (`/api/servers/{id}/snapshots/`) - Individual server backups
- **Pydantic Models**: `ResticSnapshot`, `ResticSnapshotSummary`, `ResticSnapshotWithSummary`
- **Configuration**: ResticSettings with repository path and password management

### Frontend Snapshot Features
- **Snapshot Management Page**: Dedicated UI for viewing, creating, and managing backups
- **Integration**: Seamless navigation from server overview to snapshot management
- **Real-time Updates**: Automatic refresh of snapshot lists and status
- **Error Handling**: Comprehensive error feedback for backup operations

## Archive Management System

### Backend Archive Architecture
- **Archive Router**: Comprehensive archive operations (`/api/archives/`) - upload, list, delete, SHA256 calculation
- **Decompression Utilities**: Support for ZIP, TAR, TAR.GZ formats with validation (`app.utils.decompression`)
- **Server Population**: Integrated archive-to-server deployment via populate endpoint
- **SHA256 Verification**: Built-in file integrity checking for uploaded archives
- **Common File Operations**: Shared utilities for file management across archive and server operations

### Frontend Archive Features
- **Archive Management Page**: Dedicated UI for viewing, uploading, and managing archive files
- **Archive Selection Modal**: Streamlined archive selection interface for server creation
- **SHA256 Verification UI**: Visual feedback for file integrity checking
- **Server Population Integration**: Seamless archive deployment to new servers
- **Progress Tracking**: Real-time feedback for upload and deployment operations

## Testing Strategy & Guidelines

### Test Categories

**Safe Tests (Fast, No Docker Containers):**
- `test_compose.py` - Pure unit tests for Pydantic models
- `test_compose_file.py` - File operations and YAML parsing
- `test_rcon_filtering.py` - Utility function testing
- `test_file_operations.py` - Mocked API endpoint testing
- `test_websocket_console.py` - WebSocket protocol testing with mocks
- `test_snapshots_basic.py` - Snapshot model and basic functionality testing
- `test_snapshots_endpoints.py` - Snapshot API endpoint testing with mocks
- `test_decompression.py` - Archive decompression utility testing
- `test_archive_operations.py` - Archive management API testing
- `test_archive_sha256.py` - SHA256 calculation and validation testing
- `test_common_file_operations.py` - Common file operations utility testing
- `test_create_server.py` - Server creation logic testing

**Container/Integration Tests (Slow, Docker Required):**
- `test_monitoring.py` - Real container monitoring (functions end with `_with_docker`)
- `test_integration.py` - Full workflow testing (`test_integration_with_docker`)
- `test_instance.py` - Container lifecycle testing (`*_with_docker` functions)
- `test_snapshots_integrated.py` - Real Restic integration tests with containers
- `test_populate_integration.py` - Real archive population testing with containers

### Development Testing Guidelines

**⚠️ CRITICAL: During development iteration, NEVER run Docker container tests to avoid timeouts:**

```bash
# ✅ Safe for development - Run these frequently
poetry run pytest tests/test_compose.py tests/test_compose_file.py tests/test_rcon_filtering.py tests/test_file_operations.py tests/test_websocket_console.py tests/test_snapshots_basic.py tests/test_snapshots_endpoints.py tests/test_decompression.py tests/test_archive_operations.py tests/test_archive_sha256.py tests/test_common_file_operations.py tests/test_create_server.py -v

# ✅ Safe unit tests from test_instance.py (don't bring up containers)
poetry run pytest tests/test_instance.py::test_disk_space_info_dataclass tests/test_instance.py::test_minecraft_instance -v

# ❌ AVOID during development - These bring up Docker containers
# poetry run pytest tests/test_monitoring.py  # All functions end with _with_docker
# poetry run pytest tests/test_integration.py::test_integration_with_docker
# poetry run pytest tests/test_instance.py::test_server_status_lifecycle_with_docker
# poetry run pytest tests/test_snapshots_integrated.py  # Real Restic operations
# poetry run pytest tests/test_populate_integration.py  # Real archive population

# ✅ Skip container tests during development
poetry run pytest tests/ -v -k "not _with_docker and not test_integration"

# ✅ Test only specific changes (example for archive changes)
poetry run pytest tests/test_archive_operations.py tests/test_decompression.py tests/test_create_server.py -v
```

**Docker Test Functions:**
- All functions in `test_monitoring.py` end with `_with_docker`
- `test_server_status_lifecycle_with_docker` in `test_instance.py`
- `test_get_disk_space_info_with_docker` in `test_instance.py`
- `test_integration_with_docker` in `test_integration.py`
- All functions in `test_populate_integration.py` require Docker containers

## External Documentation

**IMPORTANT**: Always use Context7 for external library documentation before coding with unfamiliar APIs.

**Key Context7 Library IDs:**
- FastAPI: `/tiangolo/fastapi`
- React: `/facebook/react`
- Ant Design: `/ant-design/ant-design`
- TanStack Query: `/tanstack/query`
- SQLAlchemy: `/websites/sqlalchemy-en-20`
- Pydantic: `/pydantic/pydantic`
- React Router: `/remix-run/react-router`
- Zustand: `/pmndrs/zustand`
- Monaco Editor: `/microsoft/monaco-editor`
- Vite: `/vitejs/vite`
- Restic: `/restic/restic` (backup tool documentation)

Use the resolve-library-id tool first, then get-library-docs with specific topics.

## Current Architecture Integration

- **No External Docker Library**: Minecraft management is fully integrated in `backend/app/minecraft/`
- **Integrated Backup System**: Restic snapshot management built into `backend/app/snapshots/`
- **Frontend API Configuration**: Configurable base URL via vite proxy (default: http://localhost:5678/api)
- **WebSocket Auto-Derivation**: WS endpoints automatically derived from HTTP base URL
- **CORS Configuration**: Backend configured for localhost:3000 development
- **Consistent Async Patterns**: Full async/await throughout both components
- **Separated API Endpoints**: Disk usage information separated from I/O statistics for better reliability
- **Three-Layer Frontend Architecture**: Complete separation between API, base queries, and page compositions

## Operation Audit System

**Comprehensive Non-Invasive Logging:**
- **Middleware Architecture**: FastAPI `BaseHTTPMiddleware` automatically intercepts all state-changing operations
- **Smart Filtering**: Only logs operations that modify server state or data (POST/PUT/PATCH/DELETE methods plus specific paths)
- **User Context Integration**: Automatically captures authenticated user information through existing JWT system
- **Security Features**: Sensitive field masking (passwords, tokens, secrets) with configurable sensitive field lists
- **Structured Logging**: JSON format with automatic log rotation for easy parsing and future database migration

**Audit Coverage:**
- Server management operations (`/api/servers/{id}/operations`, `/api/servers/{id}/compose`, `/api/servers/{id}/rcon`)
- Snapshot operations (`/api/snapshots/*`, `/api/servers/{id}/snapshots/*`)
- User administration (`/api/admin/*`, `/api/auth/register`)
- All POST/PUT/PATCH/DELETE operations that modify system state
- Automatic exclusion of query operations (GET requests) to reduce log noise

**Log Structure:**
```json
{
  "timestamp": "2024-01-15T10:30:45.123456",
  "method": "POST", "path": "/api/servers/myserver/operations",
  "status_code": 200, "processing_time_ms": 1250.75,
  "client_ip": "192.168.1.100", "user_agent": "Mozilla/5.0...",
  "user_id": 1, "username": "admin", "role": "OWNER",
  "path_params": {"server_id": "myserver"}, "query_params": {},
  "request_body": {"action": "start"}, "success": true
}
```

## Maintenance Instructions

**CRITICAL FOR FUTURE CLAUDE SESSIONS:**

When you add new technologies, APIs, dependencies, or make architectural changes:

1. **Update this main CLAUDE.md** for project-wide changes affecting multiple components
2. **Update component-specific CLAUDE.md files** for local changes within backend or frontend
3. **Add new Context7 library IDs** when introducing external dependencies
4. **Document new development commands**, environment variables, or build processes
5. **Update architecture descriptions** for new services, APIs, or integration patterns
6. **Include dependency version updates** in pyproject.toml or package.json changes
7. **Update test categorization** when adding new tests (safe vs Docker-requiring vs integration)
8. **Document new features** like snapshot management, authentication changes, or UI restructuring

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

**Examples of changes requiring updates:**
- New FastAPI routers or endpoints (like snapshot management)
- New React hooks or state management patterns (like query restructuring)
- Database schema changes or migrations
- Authentication/authorization changes
- New WebSocket endpoints or features
- Build process or deployment changes
- Container management improvements
- Test structure changes (like new snapshot testing)
- Frontend architecture restructuring (like base/page query organization)
- New major features (like backup/snapshot system)

These CLAUDE.md files are automatically loaded into Claude's context - keep them accurate, concise, and focused on development-relevant information that reflects the actual codebase implementation.