# MC Admin

Web platform for managing Minecraft servers via Docker Compose, with an independent API E2E project:

- `backend/` — FastAPI + SQLAlchemy 2.0 async (see `backend/CLAUDE.md`)
- `frontend-react/` — React 19 + TanStack Query (see `frontend-react/CLAUDE.md`)
- `e2e/` — standalone Go executable, real deployed API smoke/regression tests and owned Docker environments (see `e2e/CLAUDE.md`)

The application ships as a single Docker image (`Dockerfile` at the repo root); the backend serves the built frontend as static files in production. The E2E runner is built separately. Base images are pinned by digest, and runtime layers keep Python dependencies, backend code, frontend vendor chunks, workers, fonts, styles, and app chunks separate so pulls reuse unchanged blobs.

The production image starts Uvicorn at INFO level; protocol DEBUG frame logging can expose WebSocket login credentials, including abbreviated ticket values.

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
cd backend && uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 5678 --reload

# frontend
cd frontend-react && pnpm install && pnpm dev   # port 3000
```

Frontend dev server proxies `/api` to `http://localhost:5678` (see `vite.config.ts`).

## CI

- `.github/workflows/backend-tests.yml` runs backend pytest on every push with a matrix split across root-level `backend/tests/test_*.py` files and each pytest-collecting first-level test directory. CI does not filter out Docker or integration tests, and it installs pinned `fd`, Restic, and `mcmap` versions from `Dockerfile`.
- When adding a new first-level backend test directory under `backend/tests/`, add a matching matrix entry to `.github/workflows/backend-tests.yml` in the same change.
- `.github/workflows/static-checks.yml` independently runs frontend lint/TypeScript checks/asset build, backend Pyright/Ruff, and Go formatting/vet on every push.
- `.github/workflows/e2e-tests.yml` runs race-enabled framework unit tests, builds the application image and standalone runner once, runs three independent API regression shards, always attempts cleanup/diagnostic upload, and audits the case/shard union against the deployed OpenAPI schema. Static checks belong to the separate push workflow; Docker builds frontend assets with `pnpm build:bundle`. New suite directories do not need matrix entries. Manual dispatch supports smoke, external provider qualification and disabling environment reuse; DNS credentials come from the private `E2E_EXTERNAL_CONFIG` secret.
- `.github/workflows/docker-image.yml` publishes the bundled Docker image to GHCR for semantic version tags and exports a registry BuildKit cache.

## Cross-component conventions

- CLAUDE.md files describe **current** state; never write changelog-style notes ("recently added X", "previously did Y", "now uses Z").
- New backend features and fixes that change observable behavior require API E2E coverage in `e2e/suites/` and an update to `e2e/docs/coverage.md` in the same change. See `e2e/docs/architecture.md` for isolation, environment composition and extension contracts.
- User-facing application text is Chinese, including frontend UI copy and backend-provided names, descriptions, errors, and messages that may be displayed to users.
- Long-form design background — business logic, invariants, lifecycle ordering, component graphs — lives in `backend/docs/`, `frontend-react/docs/` and `e2e/docs/`. Each `docs/<topic>.md` is self-contained, current-state, no changelog. CLAUDE.md carries day-to-day rules and points at the doc.
- `.claude/skills/` contains generated agent skills and repository-specific skills. Do not hand-edit generated `openspec-*` skills; run `openspec update` after upgrading the CLI.
- `.agents/skills/` contains generated Codex skills and is refreshed by `openspec update`.
- `openspec/specs/` is the source of truth for observable behavior, while `openspec/changes/` contains proposed behavior changes and their implementation plans. Keep technical design rationale in the corresponding component's `docs/`.
