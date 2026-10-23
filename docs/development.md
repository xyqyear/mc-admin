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

## Windows editing with a WSL backend

Keep one checkout on Windows. Windows owns Git, Node 24, pnpm, the frontend
development server, Vitest and Playwright. WSL reads the same source through
`/mnt/<drive>/...` and owns backend execution, pytest, Docker and API E2E.
No source synchronization service is needed.

Install PowerShell 7.3+ on Windows. The WSL distribution defaults to `Debian`;
set `$env:MC_ADMIN_WSL_DISTRO` in the launching Windows process to select another
installed distribution. WSL needs Linux uv, Docker Engine/Compose, the binaries
listed above, and the Go version in `e2e/go.mod` when building the API runner.
Docker must use a local Linux Unix socket and see the same absolute paths as
the runner; Docker Desktop path translation is not supported by API E2E.

From the repository root in PowerShell:

```powershell
uv sync --locked --project backend
pnpm --dir frontend-react install --frozen-lockfile
.\scripts\dev\backend.ps1 sync
code mc-admin.code-workspace
```

The root `mc-admin.code-workspace` owns shared editor settings, tasks and
debug configurations. Folder-local `.vscode` files are not required; duplicate
settings can override the workspace and duplicate tasks can obscure its
launchers. Tailwind IntelliSense excludes the generated `src/shared/ui` files.

The Windows `backend/.venv` supplies Python completion and static analysis.
The workspace sets `ruff.path` to its Windows Ruff executable, keeping the
editor on the version pinned by the backend instead of the extension's bundled
version. After changing this setting, run **Ruff: Restart Server** if the editor
still reports a version mismatch. The backend's Pyright target remains Linux.

WSL project commands explicitly use `~/.venvs/mc-admin-backend` through
`UV_PROJECT_ENVIRONMENT`, including when the source is under `/mnt`.
Never run an unqualified Linux `uv sync` in this
checkout: it would target the Windows `.venv`. Use `backend.ps1` from Windows
or `bash scripts/dev/backend.sh` from WSL. Frontend pnpm commands use Windows
Node and `node_modules`; from WSL use `cmd.exe /c` for those commands.

`sync` creates private development configuration at
`~/.config/mc-admin-dev/config.toml` and `.env`, and a separate empty development
data root at `~/.local/share/mc-admin-dev`. Credentials are generated locally
with private permissions. Repeated initialization preserves existing config
and data. The database, server directories, logs, archives and temporary test
files stay on Linux storage. The frontend public assets are linked into the
development static directory; use Vite for application pages.

To use existing WSL development data, set its absolute Linux paths in this
configuration while the previous backend is stopped. Initialization does not
move or delete old databases, servers, environments or synchronization services.
`MC_ADMIN_LINUX_VENV`, `MC_ADMIN_DEV_CONFIG` and `MC_ADMIN_DEV_DATA` can override
the defaults with absolute Linux paths. The PowerShell entry forwards these
variables to WSL. Do not share one virtual environment between separate
checkouts with different dependency locks.

### Start, debug and stop

```powershell
.\scripts\dev\backend.ps1 dev
.\scripts\dev\backend.ps1 debug
.\scripts\dev\backend.ps1 stop
```

Choose either `dev` or `debug`. Both serve `127.0.0.1:5678`, force watchfiles
polling at a default 500 ms interval, and watch only `backend/app` and
`backend/alembic`. Windows file notifications are not required. Restart after
editing dependencies or development configuration. A reload still waits for
the old backend's normal resource cleanup.

The workspace's **Backend: WSL** launch starts debugpy on `127.0.0.1:5679`,
maps the backend folder to the remote working directory and enables subprocess
debugging for reloads. **MC Admin: Windows + WSL** starts the backend debugger
and Windows Chrome with Vite. The post-debug task stops the recorded backend;
`stop` verifies process identity and waits for graceful exit without killing
whatever happens to occupy a port. Terminate the foreground frontend task with
Ctrl+C. Port conflicts fail instead of silently selecting another server.

**Frontend: Windows Chrome Preview** runs `pnpm build` before serving the
production build on `http://127.0.0.1:4173`. It uses the same WSL backend as
development; start **Backend: WSL** separately when API access is needed.
Terminate the preview task with Ctrl+C when finished.

Select `backend/.venv/Scripts/python.exe` if an old interpreter was selected.
The workspace disables local backend pytest discovery. Use **Backend: test
selected file or node in WSL** or the CLI below. Windows Python does not run
the Linux tests.

### Targeted verification

```powershell
.\scripts\dev\backend.ps1 test tests/files/test_file_operations.py
.\scripts\dev\backend.ps1 run pyright
.\scripts\dev\backend.ps1 run ruff check . ../scripts
pnpm --dir frontend-react check:contracts
.\scripts\dev\e2e.ps1 build
.\scripts\dev\e2e.ps1 run --backend-image mc-admin:dev --tag regression --case '^files\.directories-search-and-errors$'
```

Build the application image from the checked source in WSL before API/browser
execution, for example `wsl -d Debian -- docker build -t mc-admin:dev .` from
the repository root. The E2E executable defaults to
`~/.cache/mc-admin/e2e/mc-admin-e2e`; its owned run data defaults to
`~/.local/share/mc-admin-e2e`. `MC_ADMIN_E2E_BINARY` and `MC_ADMIN_E2E_OUTPUT`
select other Linux paths. Rebuild after changing the Go runner.
The Linux build disables optional Git index refreshes so its VCS inspection
does not replace the Windows checkout's cached filesystem metadata.

Frontend Vitest runs through Windows pnpm with explicit related file filters.
Contract generation/checking invokes WSL Python on Windows and native uv on
Linux CI. Windows Playwright uses the WSL-owned deployment through the
[browser entry point](../frontend-react/docs/browser-tests.md#windows-browser-with-a-wsl-owned-deployment).
Complete suites run only in CI under the repository delivery rules.

For launcher changes, run the selected development tests with:

```powershell
.\scripts\dev\backend.ps1 run python -m unittest discover -s ../scripts/dev -p test_development.py -v
.\scripts\dev\backend.ps1 run python -m unittest discover -s ../scripts/dev -p test_browser_windows.py -v
```

Cross-filesystem source reads still have overhead. Linux virtual environments
and runtime data avoid placing dependency and database I/O on the mounted
Windows drive. If localhost forwarding is disabled in WSL, restore it before
using the default Vite proxy and debugger configuration.

## Native Linux development

For a checkout and virtual environment owned entirely by Linux, from `backend/`:

```bash
uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 5678 --reload --timeout-graceful-shutdown 2
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
