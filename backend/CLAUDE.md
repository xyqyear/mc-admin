# MC Admin Backend - FastAPI Development Guide

## What This Component Is

Backend REST API for the MC Admin Minecraft server management platform. Built with FastAPI + SQLAlchemy 2.0 on Python 3.12+, providing comprehensive server management APIs, JWT authentication with WebSocket login flow, and real-time system monitoring.

## Tech Stack

- **Language**: Python 3.12+ with Poetry package management
- **Web Framework**: FastAPI + Uvicorn ASGI server with CORS middleware 
- **Database**: SQLAlchemy 2.0 Declarative Models (async) + SQLite + aiosqlite driver
- **Authentication**: JWT (joserfc) + OAuth2 password flow + WebSocket login codes
- **Validation**: Pydantic v2 + pydantic-settings (TOML + environment variables)
- **Container Integration**: minecraft-docker-manager-lib v0.3.1 (git dependency)
- **Async Support**: Full async/await with greenlet for SQLAlchemy async operations
- **System Monitoring**: psutil for CPU, memory, and disk metrics
- **Development**: pytest, black formatter, ipykernel for notebooks
- **Additional**: python-multipart, asyncer, alembic (dev)

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
│   └── system.py           # System metrics endpoints
└── system/
    └── resources.py        # psutil wrappers for system info
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