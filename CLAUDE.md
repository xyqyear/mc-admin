# MC Admin - Minecraft Server Management Platform

## Project Overview

MC Admin is a comprehensive web-based platform for managing Minecraft servers using Docker containers. The project consists of two main components working together to provide a complete server management solution.

**Components:**
1. **Backend API** (FastAPI + Python 3.12+) - RESTful API with integrated Minecraft management, JWT authentication, and WebSocket support
2. **Frontend Web UI** (React 18 + TypeScript + Ant Design 5) - Modern SPA with real-time updates and Monaco editor integration

**Key Features:**
- Complete Minecraft server lifecycle management (create, start, stop, monitor, delete)
- Real-time system and server resource monitoring (CPU, memory, disk, network via cgroup v2)
- Docker Compose configuration management with Monaco editor and schema validation
- JWT-based authentication with role-based access control (ADMIN/OWNER) + Master token system
- Dual authentication: WebSocket login code flow + traditional password authentication
- Real-time console streaming and RCON command execution via WebSocket
- Comprehensive resource monitoring with cgroup v2 integration
- Sophisticated data fetching with React Query and intelligent caching strategies
- **Separated disk usage API**: Disk space information available regardless of server status
- **Operation audit system**: Non-invasive middleware-based audit logging for all state-changing operations

## Architecture

**System Architecture:**
- **Database**: SQLite with async support (SQLAlchemy 2.0 + aiosqlite)
- **Authentication**: JWT tokens with OAuth2 password flow + WebSocket rotating login codes + Master token fallback
- **Container Management**: Integrated Docker Compose management (not external dependency)
- **Communication**: RESTful API + WebSocket for real-time features (console streaming, login codes)
- **Configuration**: TOML-based settings with environment variable overrides
- **Monitoring**: cgroup v2 direct filesystem monitoring for container resources
- **API Architecture**: Separated I/O statistics and disk usage endpoints for better reliability
- **Audit System**: FastAPI middleware with automatic operation logging to structured JSON files

**Data Flow:**
Frontend (React Query) ↔ Backend API (FastAPI) ↔ Integrated Minecraft Module ↔ Docker Engine

## Technology Stack Summary

### Backend (Python 3.12+)
- **Web Framework**: FastAPI + Uvicorn ASGI server with CORS middleware
- **Database**: SQLAlchemy 2.0 (async) + SQLite + aiosqlite driver
- **Authentication**: JWT (joserfc) + OAuth2 + WebSocket login codes + Master token system
- **Validation**: Pydantic v2 + pydantic-settings with TOML support
- **System Monitoring**: psutil + direct cgroup v2 filesystem monitoring
- **Container Integration**: **Integrated** Minecraft Docker management module (app.minecraft)
- **WebSocket Support**: FastAPI WebSocket + Watchdog file monitoring for console streaming
- **Package Management**: Poetry
- **Development**: pytest + black + pytest-asyncio for comprehensive async testing

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
- **Package Management**: pnpm (preferred - pnpm-lock.yaml present)

## Development Environment

### Prerequisites
- **Python**: 3.12+ (backend)
- **Node.js**: 18+ (frontend)
- **Docker**: Engine + Compose (for Minecraft server management)
- **Poetry**: Python package management
- **pnpm**: Node.js package management (preferred over npm)

### Project Structure
```
mc-admin/
├── backend/          # FastAPI backend with integrated Minecraft management
├── frontend-react/   # React frontend application
└── CLAUDE.md        # This project overview file
```

Each component has dedicated development instructions:
- `backend/CLAUDE.md` - Backend API development guide
- `frontend-react/CLAUDE.md` - Frontend React development guide

## Key Development Patterns

### Backend Patterns (Actual Implementation)
- **Integrated Minecraft Management**: Full Docker container lifecycle in `app.minecraft` module
- **SQLAlchemy 2.0 Async**: All database operations with async/await patterns
- **Dual Authentication**: JWT tokens + WebSocket rotating codes + Master token fallback
- **Real-time Console**: WebSocket streaming with file system watchers (Watchdog)
- **cgroup v2 Monitoring**: Direct filesystem monitoring for accurate container metrics
- **TOML Configuration**: Nested settings with environment variable override support
- **Comprehensive Testing**: pytest with asyncio support and real Docker integration
- **Separated API Design**: Disk usage info separated from I/O statistics for better reliability
- **Operation Audit**: Non-invasive middleware that automatically logs state-changing operations with user context, request details, and sensitive data masking

### Frontend Patterns (Actual Implementation)
- **Three-Layer Data Architecture**: 
  1. Raw API layer (`hooks/api/serverApi.ts`)
  2. React Query hooks (`hooks/queries/`)
  3. Composed page queries (`useServerDetailQueries`, `useServerPageQueries`)
- **Zustand State Management**: Token, sidebar, and login preference stores with persistence
- **Monaco Editor Integration**: Multi-worker setup with YAML schema validation
- **Intelligent Caching**: Different refetch intervals based on data volatility
- **Dual Authentication UI**: WebSocket code login + traditional password login
- **Real-time Updates**: WebSocket integration for console and live data
- **Error Boundaries**: Graceful error handling with fallback components

## Testing Strategy & Guidelines

### Test Categories

**Safe Tests (Fast, No Docker Containers):**
- `test_compose.py` - Pure unit tests for Pydantic models
- `test_compose_file.py` - File operations and YAML parsing
- `test_rcon_filtering.py` - Utility function testing
- `test_file_operations.py` - Mocked API endpoint testing
- `test_websocket_console.py` - WebSocket protocol testing with mocks

**Container Tests (Slow, Docker Required):**
- `test_monitoring.py` - Real container monitoring (functions end with `_with_docker`)
- `test_integration.py` - Full workflow testing (`test_integration_with_docker`)
- `test_instance.py` - Container lifecycle testing (`*_with_docker` functions)

### Development Testing Guidelines

**⚠️ CRITICAL: During development iteration, NEVER run Docker container tests to avoid timeouts:**

```bash
# ✅ Safe for development - Run these frequently
poetry run pytest tests/test_compose.py -v
poetry run pytest tests/test_compose_file.py -v
poetry run pytest tests/test_rcon_filtering.py -v
poetry run pytest tests/test_file_operations.py -v
poetry run pytest tests/test_websocket_console.py -v

# ✅ Safe unit tests from test_instance.py (don't bring up containers)
poetry run pytest tests/test_instance.py::test_disk_space_info_dataclass -v
poetry run pytest tests/test_instance.py::test_minecraft_instance -v

# ❌ AVOID during development - These bring up Docker containers
# poetry run pytest tests/test_monitoring.py  # All functions end with _with_docker
# poetry run pytest tests/test_integration.py::test_integration_with_docker
# poetry run pytest tests/test_instance.py::test_server_status_lifecycle_with_docker
# poetry run pytest tests/test_instance.py::test_get_disk_space_info_with_docker

# ✅ Skip container tests during development
poetry run pytest tests/ -v -k "not _with_docker and not test_integration"

# ✅ Test only specific changes (example for disk usage changes)
poetry run pytest tests/test_instance.py::test_disk_space_info_dataclass -v
```

**Docker Test Functions (Renamed with `_with_docker` suffix):**
- All functions in `test_monitoring.py` now end with `_with_docker`
- `test_server_status_lifecycle_with_docker` in `test_instance.py`
- `test_get_disk_space_info_with_docker` in `test_instance.py`
- `test_integration_with_docker` in `test_integration.py`

**Testing Recommendations:**
1. **During Active Development**: Only run safe tests and specific unit tests related to your changes
2. **Pre-commit**: Run container tests with longer timeout (`--timeout=600`)
3. **CI/CD**: Run full test suite with proper Docker cleanup
4. **Never run `pytest tests/` without filters** - will timeout due to container tests

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

Use the resolve-library-id tool first, then get-library-docs with specific topics.

## Current Architecture Integration

- **No External Docker Library**: Minecraft management is fully integrated in `backend/app/minecraft/`
- **Frontend API Configuration**: Configurable base URL via `VITE_API_BASE_URL` (default: http://localhost:5678/api)
- **WebSocket Auto-Derivation**: WS endpoints automatically derived from HTTP base URL
- **CORS Configuration**: Backend configured for localhost:3000 development
- **Consistent Async Patterns**: Full async/await throughout both components
- **Separated API Endpoints**: Disk usage information separated from I/O statistics for better reliability

## Recent Updates

### Operation Audit System

**Comprehensive Non-Invasive Logging:**
- **Middleware Architecture**: FastAPI `BaseHTTPMiddleware` automatically intercepts all state-changing operations
- **Smart Filtering**: Only logs operations that modify server state or data (POST/PUT/PATCH/DELETE methods plus specific paths)
- **User Context Integration**: Automatically captures authenticated user information through existing JWT system
- **Security Features**: Sensitive field masking (passwords, tokens, secrets) with configurable sensitive field lists
- **Structured Logging**: JSON format with automatic log rotation for easy parsing and future database migration

**Audit Coverage:**
- Server management operations (`/api/servers/{id}/operations`, `/api/servers/{id}/compose`, `/api/servers/{id}/rcon`)
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

**Database Migration Strategy:**
The audit system is designed with future database migration in mind:
- JSON log format maps directly to relational database tables
- Structured fields suitable for indexing and querying
- Batch import capability for existing log files
- Configurable storage backend (currently file-based, easily extensible to database)

### API Improvements
- **Separated Disk Usage API**: Created dedicated `/servers/{id}/disk-usage` endpoint
- **Improved I/O Statistics**: `/servers/{id}/iostats` now focuses on I/O performance metrics only
- **Enhanced Reliability**: Disk space information now available regardless of server status
- **Frontend Integration**: Updated React Query hooks to use new disk usage endpoint
- **Operation Audit Middleware**: Added comprehensive audit logging system integrated into FastAPI middleware pipeline

## Maintenance Instructions

**CRITICAL FOR FUTURE CLAUDE SESSIONS:**

When you add new technologies, APIs, dependencies, or make architectural changes:

1. **Update this main CLAUDE.md** for project-wide changes affecting multiple components
2. **Update component-specific CLAUDE.md files** for local changes within backend or frontend
3. **Add new Context7 library IDs** when introducing external dependencies
4. **Document new development commands**, environment variables, or build processes
5. **Update architecture descriptions** for new services, APIs, or integration patterns
6. **Include dependency version updates** in pyproject.toml or package.json changes
7. **Update test categorization** when adding new tests (safe vs Docker-requiring)
8. **Rename test functions** with `_with_docker` suffix if they bring up containers

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

**Examples of changes requiring updates:**
- New FastAPI routers or endpoints
- New React hooks or state management patterns
- Database schema changes or migrations
- Authentication/authorization changes
- New WebSocket endpoints or features
- Build process or deployment changes
- Container management improvements
- Test structure changes

These CLAUDE.md files are automatically loaded into Claude's context - keep them accurate, concise, and focused on development-relevant information that reflects the actual codebase implementation.