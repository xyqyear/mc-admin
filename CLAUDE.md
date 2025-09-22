# MC Admin - Minecraft Server Management Platform

## Project Overview

MC Admin is a comprehensive web-based platform for managing Minecraft servers using Docker containers. The project consists of two main components working together to provide a complete server management solution with enterprise-grade backup and recovery capabilities.

**Components:**
1. **Backend API** (FastAPI + Python 3.12+) - RESTful API with integrated Minecraft management, JWT authentication, WebSocket support, and Restic-based snapshot system
2. **Frontend Web UI** (React 18 + TypeScript + Ant Design 5) - Modern SPA with real-time updates, Monaco editor integration, and comprehensive backup management

**Key Features:**
- Complete Minecraft server lifecycle management (create, start, stop, monitor, delete)
- **Enterprise Snapshot System** - Full backup and restoration using Restic with global and server-specific snapshots
- **Archive Management System** - Comprehensive archive file management with SHA256 verification, compression/decompression support, and server population from archives
- **DNS Management System** - Integrated DNS record management with DNSPod and Huawei Cloud support, automatic updates after server operations
- **Cron Job System** - Advanced scheduled task management with APScheduler, database persistence, backup jobs, and Uptime Kuma notifications
- **Server Restart Scheduling** - Automated server restart management with backup conflict detection and timezone-aware execution
- **Download Manager System** - File download progress tracking with cancellation support and real-time status updates
- **Dynamic Configuration System** - Runtime configuration management with schema migration, validation, memory caching, and web-based management interface
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
- **Version Update System** - Automatic version update notifications with configurable reminder system
- **Development Debug Tools** - Built-in debug modal and tools for development environment
- **Server File Compression** - 7z archive creation for server files and directories with progress tracking
- **Enhanced Drag-and-Drop** - File upload validation with format-specific error messages
- **Server Address Management** - Real router-based address display with automatic configuration detection
- **CI/CD Integration** - Automated Docker image building and GitHub Actions workflows

## Architecture

**System Architecture:**
- **Database**: SQLite with async support (SQLAlchemy 2.0 + aiosqlite)
- **Authentication**: JWT tokens with OAuth2 password flow + WebSocket rotating login codes + Master token fallback
- **Container Management**: Integrated Docker Compose management (not external dependency)
- **Backup System**: Restic-based snapshot management with configurable repositories
- **Archive System**: Complete archive lifecycle with compression/decompression, validation, and server population
- **DNS Management**: Integrated DNS record management with DNSPod and Huawei Cloud providers, automatic server operation integration
- **Cron System**: APScheduler-based job scheduling with database persistence, backup jobs, and Uptime Kuma notifications
- **Restart Scheduling**: Automated server restart management with backup conflict detection and timezone support
- **Download Manager**: File download progress tracking with cancellation support and real-time status updates
- **Dynamic Configuration**: Runtime config management with schema migration, memory caching, and web-based interface
- **Communication**: RESTful API + WebSocket for real-time features (console streaming, login codes)
- **Configuration**: TOML-based settings with environment variable overrides
- **Monitoring**: cgroup v2 direct filesystem monitoring for container resources
- **API Architecture**: Modular router-based design with separated concerns (operations, compose, files, resources, players, cron, config, dns, restart_schedule)
- **Audit System**: FastAPI middleware with automatic operation logging to structured JSON files

**Data Flow:**
Frontend (React Query) ↔ Backend API (FastAPI) ↔ Integrated Minecraft Module ↔ Docker Engine
                                                ↔ Restic Backup System ↔ Backup Repository
                                                ↔ Archive Management ↔ File System
                                                ↔ DNS Management System ↔ DNS Providers (DNSPod/Huawei)
                                                ↔ Cron Job System ↔ APScheduler
                                                ↔ Download Manager ↔ File System
                                                ↔ Dynamic Config System ↔ Config Database

## Technology Stack Summary

### Backend (Python 3.12+)
- **Web Framework**: FastAPI + Uvicorn ASGI server with CORS middleware
- **Database**: SQLAlchemy 2.0 (async) + SQLite + aiosqlite driver
- **Authentication**: JWT (joserfc) + OAuth2 + WebSocket login codes + Master token system
- **Validation**: Pydantic v2 + pydantic-settings with TOML support
- **System Monitoring**: psutil + direct cgroup v2 filesystem monitoring
- **Container Integration**: **Integrated** Minecraft Docker management module (app.minecraft)
- **Backup System**: **Integrated** Restic snapshot management (app.snapshots)
- **Archive System**: **Integrated** archive management with compression/decompression utilities (app.utils.compression, app.utils.decompression)
- **DNS Management**: **Integrated** DNS record management with DNSPod and Huawei Cloud clients (app.dns)
- **Cron System**: **Integrated** APScheduler-based task scheduling with database persistence, backup jobs, and Uptime Kuma notifications (app.cron)
- **Restart Scheduling**: **Integrated** automated server restart management with conflict detection (app.cron.restart_scheduler)
- **Dynamic Configuration**: **Integrated** runtime configuration management with schema migration (app.dynamic_config)
- **Common Operations**: Shared file operations module (app.common.file_operations)
- **WebSocket Support**: FastAPI WebSocket + Watchdog file monitoring for console streaming
- **Package Management**: Poetry
- **Development**: pytest + black + pytest-asyncio for comprehensive async testing with separated unit/integration tests

### Frontend (Node.js 18+)
- **Framework**: React 18 + TypeScript 5 with strict compiler options
- **Build Tool**: Vite 5 with React plugin, path alias (@), and hot reload
- **UI Library**: Ant Design 5 + @ant-design/icons + @ant-design/pro-components
- **Styling**: Tailwind CSS 3 + PostCSS (preflight disabled for AntD compatibility)
- **State Management**: Zustand v4.5.0 with localStorage persistence middleware, download task management
- **Data Fetching**: TanStack React Query v5.85.5 with sophisticated three-layer architecture
- **Code Editor**: Monaco Editor v0.52.2 + monaco-yaml v5.4.0 with Docker Compose schema
- **Form Management**: Advanced form builders with cron expression support and JSON schema rendering
- **Routing**: React Router v6 with nested routes and future flags enabled
- **Error Handling**: react-error-boundary for graceful error boundaries
- **Linting**: ESLint v9 with TypeScript and React plugins (modern flat config)
- **Package Management**: pnpm (preferred - pnpm-lock.yaml present)
- **Version Management**: Built-in version update system with localStorage persistence and configurable notifications

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
│   │   ├── dns/             # DNS management with DNSPod/Huawei providers
│   │   ├── cron/            # APScheduler-based cron job system
│   │   │   ├── jobs/        # Backup and restart job implementations
│   │   │   └── restart_scheduler.py  # Server restart conflict management
│   │   ├── dynamic_config/  # Runtime configuration management
│   │   └── routers/
│   │       ├── archive.py        # Archive management API
│   │       ├── snapshots.py      # Global snapshot management
│   │       ├── cron.py           # Cron job management API
│   │       ├── config.py         # Dynamic configuration API
│   │       ├── dns.py            # DNS management API
│   │       └── servers/          # Server-specific endpoints
│   │           ├── compose.py    # Docker Compose management
│   │           ├── create.py     # Server creation
│   │           ├── operations.py # Server operations (start/stop)
│   │           ├── resources.py  # Resource monitoring
│   │           ├── players.py    # Player management
│   │           ├── populate.py   # Server population from archives
│   │           └── restart_schedule.py  # Server restart scheduling
├── frontend-react/   # React frontend application
│   ├── src/
│   │   ├── components/
│   │   │   ├── modals/           # Organized modal components
│   │   │   │   ├── ServerFiles/  # Server file management modals
│   │   │   │   │   ├── CompressionConfirmModal.tsx
│   │   │   │   │   └── CompressionResultModal.tsx
│   │   │   │   ├── cron/         # Cron job management modals
│   │   │   │   │   ├── CreateCronJobModal.tsx
│   │   │   │   │   └── CronJobDetailModal.tsx
│   │   │   │   ├── ArchiveSelectionModal.tsx
│   │   │   │   ├── ServerTemplateModal.tsx
│   │   │   │   └── SHA256HelpModal.tsx
│   │   │   ├── server/           # Server-specific components
│   │   │   │   ├── ServerOperationButtons.tsx
│   │   │   │   ├── ServerTerminal.tsx
│   │   │   │   ├── ServerAddressCard.tsx
│   │   │   │   └── ServerRestartScheduleCard.tsx
│   │   │   ├── cron/             # Cron job display components
│   │   │   ├── forms/            # Advanced form builders
│   │   │   │   ├── CronExpressionBuilder.tsx
│   │   │   │   └── SchemaForm.tsx
│   │   │   ├── layout/           # Layout components
│   │   │   │   └── DownloadTaskContainer.tsx
│   │   │   ├── debug/            # Development debug tools
│   │   │   │   ├── DebugModal.tsx
│   │   │   │   └── DebugTool.tsx
│   │   │   └── VersionUpdateModal.tsx  # Version update notification
│   │   ├── hooks/
│   │   │   ├── api/             # Raw API layer
│   │   │   │   ├── archiveApi.ts
│   │   │   │   ├── serverApi.ts
│   │   │   │   ├── cronApi.ts
│   │   │   │   ├── dnsApi.ts
│   │   │   │   └── configApi.ts
│   │   │   ├── queries/
│   │   │   │   ├── base/        # Resource-focused query hooks
│   │   │   │   │   ├── useArchiveQueries.ts
│   │   │   │   │   ├── useCronQueries.ts
│   │   │   │   │   ├── useDnsQueries.ts
│   │   │   │   │   └── useConfigQueries.ts
│   │   │   │   └── page/        # Composed page-level queries
│   │   │   ├── mutations/       # Organized mutation hooks
│   │   │   │   ├── useArchiveMutations.ts
│   │   │   │   ├── useCronMutations.ts
│   │   │   │   ├── useDnsMutations.ts
│   │   │   │   └── useConfigMutations.ts
│   │   │   ├── usePageDragUpload.ts  # Drag-and-drop validation
│   │   │   └── useVersionCheck.ts    # Version update checking
│   │   ├── stores/
│   │   │   └── useDownloadStore.ts   # Download task state management
│   │   ├── config/
│   │   │   └── versionConfig.ts      # Version management configuration
│   │   └── pages/
│   │       ├── ArchiveManagement.tsx  # Archive management
│   │       ├── Snapshots.tsx          # Global snapshot management
│   │       ├── CronManagement.tsx     # Cron job management
│   │       ├── DnsManagement.tsx      # DNS record management
│   │       └── DynamicConfig.tsx      # Configuration management
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
- **Version Update System**: Automatic detection and notification of version updates with configurable reminders
- **Development Debug Tools**: Built-in debug modal and tools visible only in development environment
- **Enhanced User Experience**: Drag-and-drop validation with format-specific error messages and improved file handling
- **Component Reusability**: Modular server operation buttons and terminal components for better code organization

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
- **Compression Utilities**: 7z archive creation for server files and directories with progress tracking (`app.utils.compression`)
- **Decompression Utilities**: Support for ZIP, TAR, TAR.GZ formats with validation (`app.utils.decompression`)
- **Server Population**: Integrated archive-to-server deployment via populate endpoint
- **SHA256 Verification**: Built-in file integrity checking for uploaded archives
- **Common File Operations**: Shared utilities for file management across archive and server operations

### Frontend Archive Features
- **Archive Management Page**: Dedicated UI for viewing, uploading, and managing archive files
- **Archive Selection Modal**: Streamlined archive selection interface for server creation
- **SHA256 Verification UI**: Visual feedback for file integrity checking with dedicated help modal
- **Server Population Integration**: Seamless archive deployment to new servers
- **Progress Tracking**: Real-time feedback for upload and deployment operations
- **File Compression**: Server file and directory compression with confirmation and result modals
- **Enhanced Drag-and-Drop**: Format validation with specific error messages for unsupported file types

## DNS Management System

### Backend DNS Architecture
- **DNS Module**: Integrated DNS management system (`app.dns`) with provider abstraction
- **Provider Support**: DNSPod and Huawei Cloud DNS clients with unified interface
- **DNS Router**: Comprehensive DNS operations (`/api/dns/`) - status, records, batch updates
- **Auto-Integration**: Automatic DNS updates triggered by server operations and creation
- **Configuration Management**: Dynamic DNS settings with validation and real-time updates
- **Record Management**: Support for A records, TTL configuration, and batch operations

### Frontend DNS Features
- **DNS Management Page**: Dedicated UI for viewing and managing DNS records and providers
- **Provider Configuration**: Dynamic configuration interface for DNS provider settings
- **Record Status Display**: Real-time DNS record status and synchronization tracking
- **Batch Operations**: Efficient management of multiple DNS records
- **Integration Feedback**: Visual confirmation of automatic DNS updates during server operations

## Cron Job Management System

### Backend Cron Architecture
- **Enhanced Cron System**: APScheduler-based job scheduling with specialized job types
- **Backup Jobs**: Automated backup scheduling with retention policies and Uptime Kuma notifications
- **Restart Scheduler**: Server restart management with backup conflict detection and timezone support
- **Job Registry**: Extensible job type system with database persistence and execution tracking
- **Conflict Detection**: Automatic validation to prevent restart-backup time conflicts
- **Notification Integration**: Uptime Kuma push notifications for job status updates

### Frontend Cron Features
- **Cron Management Page**: Comprehensive interface for creating, viewing, and managing scheduled tasks
- **Cron Expression Builder**: Visual cron expression creation with field-by-field input
- **Job Detail Modal**: Detailed job information with execution logs and status tracking
- **Conflict Warnings**: Real-time validation and warnings for scheduling conflicts
- **Status Visualization**: Job status tags and next execution time displays

## Server Restart Scheduling System

### Backend Restart Scheduling
- **RestartScheduler Class**: Intelligent restart scheduling with conflict avoidance
- **Backup Integration**: Automatic detection and avoidance of backup job conflicts
- **Timezone Support**: Proper timezone handling for scheduled restart operations
- **Status Management**: Active/inactive state management with automatic job lifecycle
- **Server Integration**: Seamless integration with server operation workflow

### Frontend Restart Scheduling
- **Server Restart Card**: Dedicated UI component for restart schedule management
- **Schedule Configuration**: Easy setup and modification of restart schedules
- **Status Display**: Visual indication of restart schedule status and next execution
- **Conflict Prevention**: Built-in warnings for potential scheduling conflicts

## Download Manager System

### Backend Download Management
- **Progress Tracking**: Real-time file download progress monitoring
- **Cancellation Support**: Ability to cancel in-progress downloads
- **Status Management**: Comprehensive download status tracking and reporting

### Frontend Download Management
- **Download Task Container**: Persistent download progress display
- **Progress Visualization**: Real-time progress bars and status updates
- **Task Management**: Download cancellation and status monitoring
- **State Persistence**: Download task state management with Zustand store

## Dynamic Configuration Management System

### Backend Configuration Architecture
- **Enhanced Schema System**: Advanced Pydantic schema handling with Union field validation and Annotated type support
- **JSON Schema Generation**: Automatic schema generation from Pydantic models with oneOf field handling
- **Configuration API**: RESTful configuration management with validation and real-time updates
- **Memory Caching**: Efficient configuration caching with automatic invalidation
- **Migration Support**: Schema migration capabilities for configuration updates

### Frontend Configuration Features
- **Dynamic Configuration Page**: Web-based interface for runtime configuration management
- **Schema-Driven Forms**: Automatic form generation based on JSON schemas
- **Real-Time Validation**: Client-side validation with server-side schema enforcement
- **Configuration Categories**: Organized configuration management by functional areas
- **Update Confirmation**: Visual feedback for configuration changes and validation

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

## Version Update System

### Frontend Version Management (`src/config/versionConfig.ts`)
- **Version Configuration**: Centralized version definition with automatic current version detection (currently v0.3.1)
- **Update History**: Comprehensive structured version records including DNS management, cron enhancements, and server restart scheduling
- **Version Comparison**: Semantic version comparison utility for update detection
- **Update Modal**: User-friendly version update notification with detailed changelog
- **Reminder System**: Configurable "remind later" functionality with 1-hour delay
- **localStorage Persistence**: Tracks last seen version and reminder preferences

### Version Update Features
- **Automatic Detection**: Checks for version updates on application startup
- **Detailed Changelog**: Displays features, fixes, and improvements between versions with Chinese localization
- **User Control**: "Remind later" and "Got it" options for managing update notifications
- **Development Integration**: Seamless integration with build and deployment workflows
- **Feature Tracking**: Complete history from initial release (v0.1.0) through current DNS integration (v0.3.1)

## Development Tools System

### Debug Tools (`src/components/debug/`)
- **Development-Only Access**: Debug tools visible only in development environment
- **Debug Modal**: Centralized debugging interface with development utilities
- **Sidebar Integration**: Easy access through application sidebar
- **Tool Collection**: Expandable framework for adding development-specific debugging features

## Current Architecture Integration

- **No External Docker Library**: Minecraft management is fully integrated in `backend/app/minecraft/`
- **Integrated Backup System**: Restic snapshot management built into `backend/app/snapshots/`
- **Frontend API Configuration**: Configurable base URL via vite proxy (default: http://localhost:5678/api)
- **WebSocket Auto-Derivation**: WS endpoints automatically derived from HTTP base URL
- **CORS Configuration**: Backend configured for localhost:3000 development
- **Consistent Async Patterns**: Full async/await throughout both components
- **Separated API Endpoints**: Disk usage information separated from I/O statistics for better reliability
- **Three-Layer Frontend Architecture**: Complete separation between API, base queries, and page compositions
- **Version Management**: Centralized version configuration with automatic update detection
- **Development Tools**: Integrated debug tools and development utilities
- **CI/CD Pipeline**: Automated Docker image building with GitHub Actions

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
- New major features (like backup/snapshot system, version update system)
- Version management configuration changes
- Development tools and debugging features
- UI/UX enhancements (like drag-and-drop validation)
- CI/CD pipeline updates and deployment automation
- Component architecture improvements

These CLAUDE.md files are automatically loaded into Claude's context - keep them accurate, concise, and focused on development-relevant information that reflects the actual codebase implementation.