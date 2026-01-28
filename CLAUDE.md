# MC Admin - Minecraft Server Management Platform

## Project Overview

MC Admin is a comprehensive web-based platform for managing Minecraft servers using Docker containers. The system provides enterprise-grade server management with real-time monitoring, automated backups, player tracking, DNS management, and scheduled task automation.

**Architecture:**
- **Backend**: FastAPI + Python 3.13+ with SQLAlchemy 2.0 async, SQLite database, Alembic migrations
- **Frontend**: React 18 + TypeScript + Ant Design 6 + TanStack Query v5
- **Container Management**: Integrated Docker Compose management with lifecycle control
- **Authentication**: Dual auth system (JWT + WebSocket login codes + Master token)
- **Real-time**: WebSocket support for console streaming and live updates via docker-py attach
- **Package Management**: uv (backend) + pnpm (frontend)

## Core Capabilities

**Server Management:**
- Complete Minecraft server lifecycle (create, start, stop, monitor, delete)
- Docker Compose configuration management with Monaco editor integration
- Real-time console streaming with direct container attach via WebSocket
- Resource monitoring (CPU, memory, disk, network) via cgroup v2
- Server templates for quick deployment
- File management with Monaco editor, deep search, multi-file/folder drag-and-drop upload
- SNBT file editing with syntax highlighting

**Backup & Recovery:**
- Enterprise-grade Restic-based snapshot system with global and server-specific backups
- Snapshot deletion and repository unlock functionality
- Automatic safety snapshot creation during restore operations
- Archive management with compression/decompression (ZIP, TAR, TAR.GZ, 7z)
- SHA256 verification for archive integrity
- Server population from archives
- Automated backup scheduling with retention policies
- Time-based snapshot restrictions to prevent conflicts

**Player Management:**
- Real-time player tracking with event-driven architecture
- Session records and online status monitoring via Query protocol or RCON as fallback
- Chat message tracking and achievement records
- Player skin management with automatic updates via Mojang API
- Crash recovery and data synchronization
- Player detail viewer with statistics and history
- Integration with server overview for online player display

**DNS & Network:**
- Integrated DNS management with DNSPod and Huawei Cloud support
- Automatic DNS record updates during server operations
- Router configuration management for MC routing
- Server address mapping and domain management
- DNS status monitoring and change detection

**Automation & Scheduling:**
- APScheduler-based cron job system with visual expression builder
- Automated backup jobs with Uptime Kuma notifications
- Server restart scheduling with conflict detection
- Job execution history and status monitoring
- Database persistence with automatic recovery on startup

**Monitoring & Logging:**
- Real-time log monitoring and parsing with Watchdog
- System-wide event dispatcher for cross-module communication
- Operation audit system with structured JSON logging and rotation
- Server tracker for lifecycle event monitoring
- Heartbeat system for crash detection and recovery
- Dynamic log parser configuration

**Configuration & Tools:**
- Dynamic configuration system with schema migration and web-based management
- Download manager with progress tracking and cancellation support
- Version update notifications with configurable reminders
- Development debug tools (dev-only)
- JSON schema-driven forms for configuration

## Development Environment

**Prerequisites:**
- Python 3.13+ with uv
- Node.js 18+ with pnpm
- Docker Engine + Docker Compose
- Restic (automatically managed)

**Quick Start:**

Backend:
```bash
cd backend
uv sync         # Install dependencies
# Configure config.toml (see backend/CLAUDE.md)
uv run alembic upgrade head  # Apply database migrations
uv run uvicorn app.main:app --host 0.0.0.0 --port 5678 --reload
```

Frontend:
```bash
cd frontend-react
pnpm install
pnpm dev  # Runs on port 3000
```

## Tech Stack Summary

**Backend:**
- FastAPI + Uvicorn, SQLAlchemy 2.0 async + SQLite + aiosqlite
- Alembic for database migrations (autogenerate support)
- JWT (joserfc) + OAuth2 authentication
- Pydantic v2 for validation and settings (TOML + env support)
- psutil for system monitoring, cgroup v2 for container metrics
- APScheduler for task scheduling with async support
- Watchdog for file monitoring
- httpx for async HTTP requests
- pwdlib for password hashing
- aiofiles for async file operations
- docker-py for container management and console streaming

**Frontend:**
- React 18 + TypeScript 5 + Vite 5
- Ant Design 6 + @ant-design/icons + @rjsf/antd v6
- Tailwind CSS 3 (preflight disabled for AntD compatibility)
- TanStack React Query v5 (three-layer architecture)
- Zustand v4 for state management with persistence
- Monaco Editor v0.52 with YAML schema validation
- React Router v6 with lazy loading
- Axios with interceptors and auto-retry
- react-error-boundary for error handling
- xterm.js for terminal emulation

## External Documentation

**Use Context7 MCP tool for library documentation:**

Backend: `/tiangolo/fastapi`, `/websites/sqlalchemy-en-20`, `/pydantic/pydantic`, `/restic/restic`
Frontend: `/facebook/react`, `/ant-design/ant-design`, `/tanstack/query`, `/microsoft/monaco-editor`

Use `mcp__context7__resolve-library-id` first, then `mcp__context7__get-library-docs` with specific topics.

## Maintenance Instructions

**CRITICAL FOR FUTURE SESSIONS:**

When making significant changes, update the appropriate CLAUDE.md files:

1. **This file (mc-admin/CLAUDE.md)**: Update for project-wide architectural changes, new major features, or technology stack updates
2. **backend/CLAUDE.md**: Update for backend-specific changes (API endpoints, database models, integrated modules, testing patterns)
3. **frontend-react/CLAUDE.md**: Update for frontend-specific changes (components, hooks, state management, UI patterns)

**Before updating any CLAUDE.md:**
1. Check git history: `git log --oneline --follow -- CLAUDE.md | head -5`
2. Compare changes since last update: `git diff <last_commit>..HEAD --name-status`
3. Review all changes to ensure complete documentation coverage

**When writing CLAUDE.md updates:**
1. Write complete, self-contained documentation (not incremental patches)
2. Avoid temporal language like "Recent changes" or "New additions"
3. Integrate information naturally into existing structure
4. Ensure consistency between all three CLAUDE.md files
5. Reflect actual codebase state (what IS, not what WAS)

**Examples of changes requiring updates:**
- New major systems (player tracking, DNS management, file search, log monitoring, event system)
- API endpoint additions or restructuring
- Database schema changes and migrations
- Authentication/authorization changes
- New WebSocket features or real-time capabilities
- Build process or deployment changes
- Test structure reorganization
- Frontend architecture changes (new hooks, state patterns)
- UI/UX enhancements (new components, modals)
- Version management and update notifications
- External dependency updates or replacements
- New integrated modules or subsystems

These CLAUDE.md files are automatically loaded into Claude's context. Keep them accurate, concise, and focused on development-relevant information that reflects actual implementation.

**Component-Specific Documentation:**
- Detailed backend information: `backend/CLAUDE.md`
- Detailed frontend information: `frontend-react/CLAUDE.md`
