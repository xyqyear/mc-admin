# MC Admin

Web platform for managing Minecraft servers via Docker Compose, with an independent API E2E project:

- `backend/` — FastAPI + SQLAlchemy 2.0 async (see `backend/CLAUDE.md`)
- `frontend-react/` — React 19 + TanStack Query (see `frontend-react/CLAUDE.md`)
- `e2e/` — standalone Go executable, real deployed API smoke/regression tests and owned Docker environments (see `e2e/CLAUDE.md`)

The application ships as a single Docker image (`Dockerfile` at the repo root); the backend serves the built frontend as static files in production. The E2E runner is built separately. Base images are pinned by digest, and runtime layers keep Python dependencies, backend code, frontend vendor chunks, workers, fonts, styles, and app chunks separate so pulls reuse unchanged blobs.

The production image starts Uvicorn at INFO level; protocol DEBUG frame logging can expose WebSocket login credentials, including abbreviated ticket values.

The backend uses an application factory and a per-application runtime for database, configuration, tasks, events, schedulers and clients. Startup reconciles interrupted work before opening write admission; shutdown drains producers and writers before releasing resources. Tests bind independent runtimes and temporary data. The supported deployment has one backend writer for each database and managed server directory; see `backend/docs/runtime.md`.

`backend/app/configuration` owns immutable preparation, version-aware Compose/template application, matching source metadata and recovery evidence; server lifecycle and HTTP routes use this boundary. The frontend's application-level operation observer refreshes configuration and server queries for terminal outcomes independently of the initiating editor page, with session-scoped deduplication and reconnect recovery.

File, archive and snapshot application services declare their filesystem resources before execution. World restoration separates selection planning, scope execution, retained history and finalization; history binds to server generations. Prune previews carry a version of their inputs and own their retained geometry and claims artifacts. The frontend `features/files` and `features/world` own their contracts, queries, commands and controllers; the application operation observer refreshes affected file/world queries across page changes. See `backend/docs/world-restore.md`, `backend/docs/chunk-prune.md` and `frontend-react/docs/data-architecture.md`.

Player log, RCON and heartbeat producers share one runtime-owned identity/session service. Cron uses public server commands and reports configured state separately from scheduler registration. Connectivity plans DNS and router changes independently and exposes unknown provider state without inferring deletions. Identity, settings and health checks capture their owning dependencies; the composition root uses explicit factories and typed accessors with no implicit default runtime.

Persistence and API DTOs belong to their feature modules; `backend/app/db/metadata.py` explicitly registers tables for Alembic. Complete identity DTOs are generated from an isolated OpenAPI document, while event and task-result validators remain explicit. Frontend features own contracts, queries, commands and UI; `app/` composes routes and operation synchronization, and `shared/` holds transport and generic UI. Architecture checks enforce imports. User-facing version entries live in `frontend-react/src/app/version/config.ts`.

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

- `.github/workflows/backend-tests.yml` collects the actual pytest inventory, derives first-level test groups and capability requirements, runs isolated shards, and audits their exact node-ID union and capability selection policy. Docker cases require explicit opt-in; external services stay outside ordinary CI. CLI versions come from `Dockerfile`. New test directories are discovered automatically.
- `.github/workflows/static-checks.yml` runs frontend lint/TypeScript checks/operation-flow tests/asset build, backend Pyright/Ruff, and Go formatting/vet. It supports both push checks and reuse by release qualification.
- `.github/workflows/candidate.yml` builds one single-platform OCI archive and the race-tested Go runner from a checked source revision. Candidate metadata records the source fingerprint, archive hash, OCI manifest digest, Docker config digest and runner hash. API and browser jobs consume this artifact.
- `.github/workflows/e2e-tests.yml` runs three independent API regression shards, attempts owned cleanup and diagnostic upload on failure, and audits the case/shard union against the deployed OpenAPI schema. New suite directories do not need matrix entries. Manual dispatch supports smoke, external provider qualification and disabling environment reuse; DNS credentials come from the private `E2E_EXTERNAL_CONFIG` secret.
- `.github/workflows/browser-tests.yml` runs the pnpm-managed Playwright journeys against an owned application and Minecraft fixture created by the candidate Go runner. Each browser case uses a separate browser context and its declared data cleanup; application state remains real.
- `.github/workflows/docker-image.yml` qualifies a semantic-version release using the candidate, static, backend, API and browser gates. Promotion copies the tested OCI archive to GHCR with digest preservation and verifies the remote manifest. Prereleases publish their full version and source SHA tags without updating stable aliases. Missing, failed, cancelled or skipped required gates block promotion. See `docs/release.md` for evidence and deployment boundaries.

## Cross-component conventions

- CLAUDE.md files describe **current** state; never write changelog-style notes ("recently added X", "previously did Y", "now uses Z").
- New backend features and fixes that change observable behavior require API E2E coverage in `e2e/suites/` and an update to `e2e/docs/coverage.md` in the same change. See `e2e/docs/architecture.md` for isolation, environment composition and extension contracts.
- User-facing application text is Chinese, including frontend UI copy and backend-provided names, descriptions, errors, and messages that may be displayed to users.
- Long-form design background — business logic, invariants, lifecycle ordering, component graphs — lives in `backend/docs/`, `frontend-react/docs/` and `e2e/docs/`. Each `docs/<topic>.md` is self-contained, current-state, no changelog. CLAUDE.md carries day-to-day rules and points at the doc.
- `.claude/skills/` contains generated agent skills and repository-specific skills. Do not hand-edit generated `openspec-*` skills; run `openspec update` after upgrading the CLI.
- `.agents/skills/` contains generated Codex skills and is refreshed by `openspec update`.
- `openspec/specs/` is the source of truth for observable behavior. Active proposals and implementation plans live under `openspec/changes/`; completed changes are retained under `openspec/changes/archive/` after their specs are synced. Keep technical design rationale in the corresponding component's `docs/`.
