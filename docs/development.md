# Development environment

This guide covers a local MC Admin checkout. For test selection and delivery,
read [repository instructions](../AGENTS.md); for deployment and artifact
identity, read [release qualification](release.md).

## Prerequisites

- Python 3.13+ and `uv`; dependency versions live in `backend/pyproject.toml` and `uv.lock`.
- Node.js 24 and `pnpm`; the frontend lockfile owns dependency versions.
- Docker Engine and Docker Compose on the host for managed Minecraft servers.
- `fd`, Restic and `mcmap` for file/world discovery, snapshots and map processing.
  The production image pins them through `FD_VERSION`, `RESTIC_VERSION` and
  `MCMAP_VERSION` in the root Dockerfile. Install the matching tools for related
  local workflows; tests declare their required capabilities.
- The independent E2E executable has its own [runtime/build requirements](../e2e/README.md).

Use native Linux commands in `/root` or `/home`. In Windows-mounted WSL
directories such as `/mnt/c`, run environment-dependent `uv`/`pnpm` commands
through `cmd.exe /c` so they use the environment owning those files.

## Start the backend

From `backend/`:

```bash
uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 5678 --reload
```

Settings load TOML/environment configuration. Directory settings resolve to
absolute paths relative to the process working directory, including defaults
and symbolic links. Use owned development data and configuration; see
[runtime setup](../backend/docs/runtime.md) and
[dynamic configuration](../backend/docs/dynamic-config.md) for their distinct roles.
Startup applies database migrations before starting DB-backed subsystems.

`fd_binary_path`, `restic_binary_path` and `mcmap_binary_path`, or their uppercase
environment variables, override binary discovery. Omitted paths resolve once at
startup from `PATH`, then `/usr/local/bin`, then `/usr/bin`. Repository addresses
and database URLs retain their own semantics.

## Start the frontend

In a separate terminal, from `frontend-react/`:

```bash
pnpm install --frozen-lockfile
pnpm dev
```

Open `http://localhost:3000`. Vite proxies `/api` HTTP and WebSocket traffic to
`http://localhost:5678`; `frontend-react/vite.config.ts` owns that setting.
[Frontend instructions](../frontend-react/AGENTS.md) list lint, type, build and
targeted verification commands.

## Production shape

The root Dockerfile builds one image: Uvicorn serves both API and built SPA.
Base images are pinned by digest. Separate dependency, backend, frontend vendor,
worker, font, stylesheet and application layers allow unchanged blobs to be reused.
The E2E runner is built separately from the same checked source for qualification.

Run one backend worker/replica per database and managed server root on a
filesystem supporting consistent local kernel locks. Application ownership does
not fence external programs that edit managed data. See
[deployment ownership](../backend/docs/operation-recovery.md#supported-deployment-ownership).
Production Uvicorn uses INFO; protocol DEBUG frame logs can expose login tickets.
