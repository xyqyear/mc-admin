# MC Admin - Minecraft Server Management Platform

## Project Overview

MC Admin is a comprehensive web-based platform for managing Minecraft servers using Docker containers. The project consists of three main components working together to provide a complete server management solution.

**Components:**
1. **Backend API** (FastAPI + Python 3.12+) - RESTful API with JWT authentication and WebSocket support
2. **Frontend Web UI** (React 18 + TypeScript + Ant Design 5) - Modern SPA with real-time updates  
3. **Docker Manager Library** (Python library) - Reusable library for Docker container operations

**Key Features:**
- Complete Minecraft server lifecycle management (create, start, stop, monitor, delete)
- Real-time system and server resource monitoring (CPU, memory, disk, network)
- Docker Compose configuration management with Monaco editor integration
- JWT-based authentication with role-based access control (USER/ADMIN/OWNER)
- WebSocket login code flow for secure authentication
- Real-time server status updates and player monitoring
- Comprehensive logging and error handling

## Architecture

**System Architecture:**
- **Database**: SQLite with async support (SQLAlchemy 2.0 + aiosqlite)
- **Authentication**: JWT tokens with OAuth2 password flow + WebSocket login codes
- **Container Management**: Docker Compose via the minecraft-docker-manager-lib
- **Communication**: RESTful API + WebSocket for real-time features
- **Configuration**: TOML-based settings with environment variable overrides

**Data Flow:**
Frontend ↔ Backend API ↔ Docker Manager Library ↔ Docker Engine

## Technology Stack Summary

### Backend (Python 3.12+)
- **Web Framework**: FastAPI + Uvicorn ASGI server
- **Database**: SQLAlchemy 2.0 (async) + SQLite/aiosqlite 
- **Authentication**: JWT (joserfc) + OAuth2 + WebSocket login codes
- **Validation**: Pydantic v2 + pydantic-settings
- **System Monitoring**: psutil for CPU, memory, disk metrics
- **Container Integration**: minecraft-docker-manager-lib (v0.3.1)
- **Package Management**: Poetry
- **Development**: pytest, black, ipykernel

### Frontend (Node.js 18+)
- **Framework**: React 18 + TypeScript 5
- **Build Tool**: Vite 5 with hot reload and path aliases
- **UI Library**: Ant Design 5 + @ant-design/icons + @ant-design/pro-components
- **Styling**: Tailwind CSS 3 (preflight disabled to avoid AntD conflicts)
- **State Management**: Zustand with localStorage persistence
- **Data Fetching**: TanStack React Query v5 with sophisticated caching strategy
- **Code Editor**: Monaco Editor with YAML support and Docker Compose schemas
- **Routing**: React Router v6 with nested routes and future flags
- **Error Handling**: react-error-boundary
- **Package Management**: pnpm (preferred)

### Docker Manager Library (Python 3.12+)
- **Container Management**: Docker SDK + Docker Compose integration
- **Async Framework**: Full async/await with asyncio
- **File Operations**: aiofiles for async I/O
- **Configuration**: Pydantic v2 + pydantic-settings
- **Monitoring**: cgroup v2-based resource monitoring
- **YAML Processing**: PyYAML for compose file parsing
- **System Metrics**: psutil integration
- **Package Management**: Poetry
- **Testing**: pytest with asyncio support

## Development Environment

### Prerequisites
- **Python**: 3.12+ (all Python components)
- **Node.js**: 18+ (frontend)
- **Docker**: Engine + Compose (for Minecraft server management)
- **Poetry**: Python package management
- **pnpm**: Node.js package management (preferred over npm)

### Quick Start Structure
```
mc-admin/
├── backend/          # FastAPI backend
├── frontend-react/   # React frontend  
└── ../minecraft-docker-manager-lib/  # Python library (separate repo)
```

Each component has dedicated development instructions in their respective CLAUDE.md files:
- `backend/CLAUDE.md` - API server development
- `frontend-react/CLAUDE.md` - React application development  
- `../minecraft-docker-manager-lib/CLAUDE.md` - Library development

## Key Development Patterns

### Backend Patterns
- All database operations use SQLAlchemy 2.0 async patterns
- JWT authentication with master token fallback for system operations
- WebSocket connection for rotating login codes
- TOML configuration with environment variable overrides
- Comprehensive logging with rotation

### Frontend Patterns  
- Three-layer data architecture: API layer → Query layer → Composed queries
- Monaco Editor integration with web workers and schema validation
- Real-time updates using React Query with intelligent refetch intervals
- Zustand stores for global state with localStorage persistence
- Ant Design components with Tailwind utility classes

### Library Patterns
- Full async/await patterns throughout
- Docker container lifecycle management with status tracking
- Resource monitoring via cgroup v2 interfaces
- Comprehensive error handling and cleanup

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

Use the resolve-library-id tool first, then get-library-docs with specific topics.

## Integration Notes

- Backend references minecraft-docker-manager-lib v0.3.1 via git dependency
- Frontend connects to backend API at configurable base URL (default: http://localhost:5678/api)
- WebSocket endpoint automatically derived from HTTP API base URL
- All components use consistent async patterns and error handling
- CORS configured for localhost:3000 development

## Maintenance Instructions

**CRITICAL FOR FUTURE CLAUDE SESSIONS**: 

When you add new technologies, APIs, dependencies, or make architectural changes:

1. **Update this main CLAUDE.md** for project-wide changes affecting multiple components
2. **Update component-specific CLAUDE.md files** for local changes within backend, frontend, or library
3. **Add new Context7 library IDs** when introducing external dependencies  
4. **Document new development commands** environment variables, or build processes
5. **Update architecture descriptions** for new services, APIs, or integration patterns
6. **Include dependency version updates** in pyproject.toml or package.json changes

**Examples of changes requiring updates:**
- New FastAPI routers or endpoints
- New React hooks or state management patterns  
- New Docker Manager Library APIs
- Database schema changes or migrations
- Authentication/authorization changes
- New external service integrations
- Build process or deployment changes

These CLAUDE.md files are automatically loaded into Claude's context - keep them accurate, concise, and focused on development-relevant information.