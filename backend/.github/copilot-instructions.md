# Copilot repository instructions — mc-admin backend

These instructions prime any new Copilot session to work effectively in this repository. Trust these instructions first; only search the codebase when something here is missing or incorrect. If you introduce new technologies, add features, or change structure, update this file in the same PR.

## What this repo is
Backend API for a Minecraft admin dashboard. Built with FastAPI + SQLAlchemy 2.0 on Python 3.12+, using JWT auth, async database operations, and a websocket-based login code flow. SQLite with aiosqlite is the default DB; configuration is read from `config.toml` (location configurable; defaults to current working directory). Optional `.env` supported.

## Tech stack and key libraries
- Language/runtime: Python 3.12+ (local venv present). Package manager: Poetry.
- Web API: FastAPI (Starlette under the hood), Uvicorn ASGI server, CORS middleware.
- Data & ORM: SQLAlchemy 2.0 Declarative Models with async support, SQLite with aiosqlite driver.
- Async support: greenlet for SQLAlchemy async operations, full async/await patterns.
- Validation & settings: Pydantic v2, pydantic-settings (loads from TOML).
- Auth: OAuth2 password flow + JWT (joserfc). Password hashing: passlib[bcrypt].
- Async helpers: asyncer (syncify/asyncify).
- System metrics: psutil.
- Dev/test: pytest, black, ipykernel.

## Project layout (paths relative to repo root)
- `app/`
  - `main.py` — FastAPI app entrypoint, root_path `/api`; mounts routers and CORS; runs uvicorn if `__main__`.
  - `config.py` — Settings model. Loads from root `config.toml` and optional root `.env`.
  - `models.py` — SQLAlchemy 2.0 Declarative models (User, UserRole), Pydantic request/response models.
  - `db/` — DB engine/session and CRUD.
    - `database.py` — Async SQLAlchemy engine from `settings.database_url`; `init_db()` creates tables; async session factory and FastAPI dependency.
    - `crud/user.py` — async user queries and create using SQLAlchemy 2.0 patterns.
  - `auth/` — auth utilities and login-code websocket flow.
    - `jwt_utils.py` — password hashing and JWT create/verify helpers.
    - `login_code.py` — websocket code rotation + master-token verified exchange.
  - `routers/` — FastAPI routers.
    - `auth.py` — /auth endpoints: register, token, verifyCode, websocket /auth/code (all async).
    - `user.py` — /user/me returns current user (async).
    - `system.py` — /system/info server/disk/ram metrics (async).
  - `dependencies.py` — DI for async DB session, current user, role guard, and master-token check.
  - `logger.py` — timed rotating file + stdout logger to `${ROOT}/logs/app.log`.
  - `system/resources.py` — psutil wrappers for system info.
- `config.toml` — runtime configuration (recommended at repo root, but can be placed elsewhere).
- `.env` — optional overrides for settings.
- `db.sqlite3` — default SQLite database file (path can be configured).
- `logs/` — runtime logs (auto-created; location configurable or defaults to CWD).
- `notebooks/` — experimentation (not used by app runtime).
- `tests/` — exists; add tests here.
- `pyproject.toml` — Poetry config and deps.

## Build, run, and validate
Assume Linux + bash. Always use the repo’s virtualenv and Poetry.

- Bootstrap (one time per environment)
  - Ensure Python 3.12+ is available.
  - Install Poetry, then run: `poetry install` (or `poetry sync`) to create `.venv` and install deps.

- Configuration (required at runtime)
  - App reads settings via pydantic-settings. By default it looks for `config.toml` and `.env` in the current working directory. You can override paths via environment variables:
    - `MC_ADMIN_CONFIG` — path to the config TOML file (default: `config.toml` relative to CWD)
    - `MC_ADMIN_ENV` — path to the `.env` file (default: `.env` relative to CWD)
  - Ensure the config includes: `database_url`, `master_token`, `server_path`, `backup_path`, and `[jwt]` keys (`secret_key`, `algorithm`, `access_token_expire_minutes`).
  - Pitfall: importing `app.config` without a valid TOML file at the configured location will raise Pydantic validation errors.

- Run (development)
  - From repo root, run Uvicorn against `app.main:app`:
    - `poetry run uvicorn app.main:app --host 0.0.0.0 --port 5678 --reload`
  - The app mounts routes under `/api` due to `root_path="/api"`.

- Run (module directly)
  - You can also run: `poetry run python -m app.main` which calls `uvicorn.run(..., port=5678)`.

- Test
  - `poetry run pytest`

- Lint/format
  - `poetry run black .`

- Database
  - Tables auto-create on startup via `init_db()` in app lifespan.

- Auth and security
  - OAuth2 password token endpoint: `POST /api/auth/token` with form data (username, password).
  - Registration `POST /api/auth/register` requires owner role via JWT; typically seeded by creating an OWNER user directly or via DB.
  - Login-code flow: connect websocket `/api/auth/code` to receive rotating 8-digit codes; verify via `POST /api/auth/verifyCode` with `Authorization: Bearer <master_token>`.
  - Master token access: Any endpoint that depends on `dependencies.get_current_user` also accepts `Authorization: Bearer <master_token>`. When used, the request is authenticated as a synthetic user `SYSTEM` with role `owner` (not persisted). This allows OWNER-gated routes to be invoked with the master token. A log entry is written when the master token is used.

- System info endpoint
  - `GET /api/system/info` requires bearer token; uses `settings.server_path` and `settings.backup_path` for disk stats.

## Conventions and tips
- Keep settings nested under TOML keys exactly as modeled in `Settings`.
- Inside `app/`, prefer package-relative imports (e.g., `from .db.database import get_db`, `from .routers import auth`). Avoid relying on CWD.
- When adding dependencies or new subsystems, update `pyproject.toml` and this file.
- Use SQLAlchemy 2.0 Declarative models for DB entities and Pydantic BaseModel for request bodies where additional validation is needed.
- Use `dependencies.RequireRole` for role gating and `dependencies.get_current_user` for auth-protected routes.
- Database sessions: Use `get_db()` dependency for db session.
- Logging already configured: set log directory via env var `MC_ADMIN_LOG_DIR` (default: `./logs` relative to CWD). From outside the package use `from app.logger import logger`; inside the package use relative import.
  - The logs directory is configurable via settings `logs_dir` (env: `MC_ADMIN_LOG_DIR` or `LOGS_DIR`), default `./logs` relative to CWD.

## External docs with Context7
- When you need documentation for external libraries, prefer Context7 docs retrieval with these IDs:
  - FastAPI: `/tiangolo/fastapi`
  - SQLAlchemy: `/websites/sqlalchemy-en-20`
  - Pydantic: `/pydantic/pydantic`
  - pydantic-settings: `/pydantic/pydantic-settings`
  - Starlette: `/encode/starlette`
  - Uvicorn: `/encode/uvicorn`
  - psutil: `/giampaolo/psutil`
  - passlib: `/passlib/passlib`
  - jose rfc (joserfc): `/fromjose/joserfc`
- If an exact ID differs, resolve the library by name first, then fetch docs.

## CI and checks
- No CI config is present in the repo at this time. Validate locally by running the app and pytest. If you add CI (e.g., GitHub Actions), document the workflow here.

## Maintenance rule for Copilot sessions
- This file is included automatically in Copilot Chat for this repo. New sessions should read it fully before acting.
- If you add new technology, change structure, or add non-trivial features, MAKE SURE to update this file in the same PR: add tech, layout paths, and build/run steps. Keep it concise and broadly applicable.
