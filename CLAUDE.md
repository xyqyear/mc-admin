# MC Admin

Web platform for managing Minecraft servers via Docker Compose. Two components:

- `backend/` — FastAPI + SQLAlchemy 2.0 async (see `backend/CLAUDE.md`)
- `frontend-react/` — React 19 + TanStack Query (see `frontend-react/CLAUDE.md`)

Everything ships as a single Docker image (`Dockerfile` at the repo root); the backend serves the built frontend as static files in production.

## Prerequisites

Beyond what `pyproject.toml` / `package.json` declare:

- Docker Engine + Docker Compose on the host (the backend manages user MC servers via docker-compose)
- `fd` — required for file search and world layout discovery; pinned by `FD_VERSION` in `Dockerfile`
- Restic — invoked as a subprocess for snapshots; pinned by `RESTIC_VERSION` in `Dockerfile`.
- `mcmap` binary — pinned by `MCMAP_VERSION` in `Dockerfile`.

Binary path settings (`fd_binary_path`, `restic_binary_path`, `mcmap_binary_path`) and their env vars override discovery. Omitted paths resolve once at startup from `PATH`, then `/usr/local/bin`, then `/usr/bin`.

## Quick start

```bash
# backend
cd backend && uv sync && uv run alembic upgrade head
uv run uvicorn app.main:app --host 0.0.0.0 --port 5678 --reload

# frontend
cd frontend-react && pnpm install && pnpm dev   # port 3000
```

Frontend dev server proxies `/api` to `http://localhost:5678` (see `vite.config.ts`).

## CI

- `.github/workflows/backend-tests.yml` runs backend pytest on every push with a matrix split across root-level `backend/tests/test_*.py` files and each pytest-collecting first-level test directory. CI does not filter out Docker or integration tests, and it installs pinned `fd`, Restic, and `mcmap` versions from `Dockerfile`.
- `.github/workflows/static-checks.yml` runs frontend lint/build and backend Pyright on every push.
- `.github/workflows/docker-image.yml` publishes the bundled Docker image to GHCR for semantic version tags.

## Cross-component conventions

- All three CLAUDE.md files describe **current** state; never write changelog-style notes ("recently added X", "previously did Y", "now uses Z").
- Long-form design background — business logic, invariants, lifecycle ordering, component graphs — lives in `backend/docs/` and `frontend-react/docs/`. Each `docs/<topic>.md` is self-contained, current-state, no changelog. CLAUDE.md carries day-to-day rules and points at the doc.
- `.claude/` holds historical artifacts (plans, migration notes, agent sessions). Don't extend these for new design work — write to `docs/` instead.
