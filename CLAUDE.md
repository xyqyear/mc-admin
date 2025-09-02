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

## Architecture

**System Architecture:**
- **Database**: SQLite with async support (SQLAlchemy 2.0 + aiosqlite)
- **Authentication**: JWT tokens with OAuth2 password flow + WebSocket rotating login codes + Master token fallback
- **Container Management**: Integrated Docker Compose management (not external dependency)
- **Communication**: RESTful API + WebSocket for real-time features (console streaming, login codes)
- **Configuration**: TOML-based settings with environment variable overrides
- **Monitoring**: cgroup v2 direct filesystem monitoring for container resources

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

## Maintenance Instructions

**CRITICAL FOR FUTURE CLAUDE SESSIONS:**

When you add new technologies, APIs, dependencies, or make architectural changes:

1. **Update this main CLAUDE.md** for project-wide changes affecting multiple components
2. **Update component-specific CLAUDE.md files** for local changes within backend or frontend
3. **Add new Context7 library IDs** when introducing external dependencies
4. **Document new development commands**, environment variables, or build processes
5. **Update architecture descriptions** for new services, APIs, or integration patterns
6. **Include dependency version updates** in pyproject.toml or package.json changes

**Examples of changes requiring updates:**
- New FastAPI routers or endpoints
- New React hooks or state management patterns
- Database schema changes or migrations
- Authentication/authorization changes
- New WebSocket endpoints or features
- Build process or deployment changes
- Container management improvements

These CLAUDE.md files are automatically loaded into Claude's context - keep them accurate, concise, and focused on development-relevant information that reflects the actual codebase implementation.