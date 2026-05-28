# MC Admin Backend

FastAPI + SQLAlchemy 2.0 async on Python 3.13+. Manages Minecraft servers running as Docker Compose stacks.

## Commands

```bash
uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 5678 --reload
uv run alembic upgrade head   # optional manual maintenance; startup also migrates
uv run pytest tests/ -v -k "not _with_docker and not integrated"
uv run pyright
```

- **Use `uv`**, never `pip`/`venv` directly.
- **Do not run `black`** — formatting is not enforced.
- **Run `uv run pyright` after backend code changes.**
- **Alembic migrations run during startup** before DB-backed subsystems start; see `docs/database-migrations.md`.
- Tests whose function names end in `_with_docker` or live in files containing `integrated` start real Docker containers; they're slow and excluded by the default `-k` filter above.

## Module map

```text
app/
├── main.py                # entrypoint, lifespan wiring
├── config.py              # TOML + env settings
├── models.py              # SQLAlchemy + Pydantic models
├── dependencies.py        # DI for sessions, auth, role guards
├── audit.py               # operation audit middleware
├── archive/              # archive domain services: resumable uploads and SHA256 streaming
├── auth/                  # JWT + WebSocket login codes
├── db/                    # async engine, startup migrations, CRUD modules
├── routers/               # HTTP/WS routers (servers/* per-server endpoints; servers/sync OWNER-only fs↔DB reconciler)
├── servers/               # Server core: CRUD, port utils, bundled lifecycle (create/remove/adopt/deactivate)
├── minecraft/             # Docker Compose lifecycle + cgroup v2 monitoring
├── players/               # identity resolution, dynamic name filtering, cleanup, tracking, sessions, chat, achievements, skins
├── log_monitor/           # watchfiles-based latest.log parser
├── files/                 # CRUD, deep search, multi-file upload
├── snapshots/             # Restic wrapper
├── cron/                  # APScheduler jobs (backup, restart)
├── dns/                   # DNSPod + Huawei Cloud
├── templates/             # server template system (typed variables)
├── dynamic_config/        # schema-versioned runtime config
├── background_tasks/      # in-memory async-generator task manager
├── mcmap/                 # server map: typed mcmap CLI integration, tile cache under data/.mcmap/
├── ftb_claims/            # FTB Utilities / FTB Chunks claim extraction via mcmap extract-ftb-claims
├── player_locations/      # saved player-position extraction via mcmap extract-players
├── world/                 # world root/dimension layout, mcmap folder resolution, restore locks/previews
├── websocket/console.py   # docker attach console
└── utils/                 # async_fs, exec, system, compression, SSE helpers
```

## Filesystem I/O — never block the event loop

In `async def`, pick in this order:

1. **`aiofiles`** when it covers the call: `aiofiles.open`, `aiofiles.os.{stat,makedirs,unlink,rename,listdir,...}`, `aiofiles.os.path.{exists,isdir,isfile,...}`.
2. **`app.utils.async_fs`** for everything else (`rmtree`, `copy2`, `copytree`, `move`, `disk_usage`, `copyfileobj`, `chown`, `chmod`, `iterdir`, `resolve`, `touch`, `extract_skin_avatar`).
3. **Subprocess**: `asyncio.create_subprocess_exec`, or `app.utils.exec.{exec_command,exec_command_stream}`.

Adding a wrapper to `async_fs`: only when aiofiles has no equivalent. Use `asyncio.to_thread` directly — do **not** reintroduce `asyncer.asyncify`.

## Background tasks

Long-running operations are async generators yielding `TaskProgress(progress, message, result)`, submitted via `task_manager.submit(...)` (in `app.background_tasks`). The frontend polls `/api/tasks/{id}`. Used by archive compression, server population, server rebuild, world restore. Implementation guide: `.claude/background-tasks-guide.md`.

## Dynamic config

Read runtime-tunable dynamic config at the point of behavior, not in long-lived constructors. Constructor-captured dynamic config needs an explicit refresh/rebuild path.

## Server lifecycle imports

Import lifecycle orchestration symbols from `app.servers.lifecycle`. The `app.servers` package init stays limited to CRUD, port utilities, and rebuild exports so player tracking and log monitoring do not form import cycles.

## Audit middleware

`app.audit` logs POST/PUT/PATCH/DELETE operations with user context, IP, and request body. Sensitive field names (`password`, `token`, `secret`, `key`) are masked. Configured via `[audit]` in `config.toml`.

## Validation error shape

`app/main.py` installs a `RequestValidationError` handler that flattens FastAPI's verbose array format into `{"detail": "field: message; field2: message2"}` — same shape as `HTTPException` responses. Frontend code can read `detail` as a string everywhere.

## Design background

Long-form, current-state design docs live under `backend/docs/`:

- `docs/servers.md` — DB-driven server discovery, bundled lifecycle orchestrators, filesystem↔DB sync endpoint
- `docs/database-migrations.md` — Alembic startup gate, supported DB states, revision IDs
- `docs/minecraft.md` — Docker Compose lifecycle, `MCInstance`, compose validation, cgroup v2 monitoring
- `docs/player-identity.md` — usercache-first identity resolution, v4 UUID gates, Mojang fallback
- `docs/players.md` — direct-function-call tracking, singletons (heartbeat / syncer / skin), DB models
- `docs/log-monitor.md` — watchfiles tail loop, regex chain, dispatch to tracking functions
- `docs/files.md` — file CRUD helpers, session-based multi-file upload, `fd`-backed deep search
- `docs/archive-upload.md` — resumable archive upload protocol, temp files, offset handling, SHA256 SSE
- `docs/snapshots.md` — Restic wrapper, retention, restore streaming, lock interaction
- `docs/cron.md` — APScheduler integration, registry, backup + restart jobs, Uptime Kuma push
- `docs/dns.md` — DNSPod / Huawei providers, mc-router sync, reconciliation flow
- `docs/templates.md` — variable definitions, `TemplateSnapshot`, two-mode editing, conversion
- `docs/dynamic-config.md` — schema-versioned runtime config with Pydantic migration
- `docs/background-tasks.md` — async-generator task manager, `TaskProgress` pattern
- `docs/server-map.md` — `app.mcmap` rendering pipeline, palette currency, render queue, cancellation
- `docs/ftb-claims.md` — `app.ftb_claims` mcmap subprocess, dim resolution, clustering, no-cache rationale
- `docs/player-locations.md` — `app.player_locations`, saved positions, dim resolution, profile cache fallback
- `docs/world-restore.md` — `app.world` scopes, locks, safety snapshots, preview sessions, crash recovery
- `docs/websocket-console.md` — docker-py attach socket bridge, message protocol
- `docs/auth.md` — JWT, password login, master token, WebSocket-code login flow
- `docs/audit.md` — middleware, sensitive-field masking, log rotation

Add a `docs/<topic>.md` whenever a new system has design rationale (business logic, invariants, lifecycle ordering) that doesn't fit on one line in this file. Each doc is self-contained and reflects current state — no changelog, no "previously…" notes.

## Keeping this file in sync

When changing function signatures, module structure, or any project-wide convention or invariant, update this file in the same commit:

- **Reflect current state, not history.** Rewrite the affected sentence as if it were the original — no "added X", "now does Y", "previously was Z" notes.
- **Stay terse.** Most changes don't need a new section. Edit the existing sentence; replace the rule that changed; don't append paragraphs explaining a one-line change.
- **Drop what's no longer true.** Remove the corresponding text when code is removed or replaced.
- **Promote design depth to `docs/`.** If a change adds rationale, business logic, or new invariants too long for the module map, write or extend `docs/<topic>.md`. Keep CLAUDE.md focused on day-to-day rules and module orientation.
- **One source of truth.** Don't duplicate facts between CLAUDE.md and `docs/`. If a rule belongs in CLAUDE.md (project-wide convention), the doc references it; if it's design depth, this file points to the doc.

## External documentation

Use the Context7 MCP tool: `/tiangolo/fastapi`, `/websites/sqlalchemy-en-20`, `/pydantic/pydantic`, `/restic/restic`. Resolve library id first, then fetch with a topic.
