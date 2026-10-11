# MC Admin Backend

FastAPI and SQLAlchemy async on Python 3.13+. Inherit [repository rules](../AGENTS.md).
Use the [backend documentation index](docs/README.md) for architecture and feature details.

## Commands and validation

Run these from `backend/`. Select only tests for changed behavior and affected
call paths; the examples are alternatives, not a checklist.

```bash
uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 5678 --reload
uv run pytest tests/files/test_file_operations.py --require-capabilities
uv run pytest tests/test_instance.py::test_server_status_lifecycle_with_docker --run-docker --require-capabilities
uv run pyright
uv run ruff check .
```

- Use `uv`, never direct `pip`/`venv`. Do not run `black`; formatting is not enforced.
- After backend code changes, run Pyright and Ruff. Use explicit related files/nodes for pytest, including architecture checks when imports or boundaries change.
- Full collection, execution and shard loops belong to CI. Docker/external tests require explicit capability opt-in. Read [testing](docs/testing.md) before changing fixtures or test selection.
- Observable behavior changes need deployed API E2E coverage and an update to [the coverage inventory](../e2e/docs/coverage.md).
- Migrations run at startup before DB consumers. Read [migration operations](docs/database-migrations.md) before adding revisions or performing manual maintenance.

## Dependencies and resource ownership

- Persistence tables, enums and DTOs belong to their feature; import their concrete owners. `app.db.metadata` explicitly registers tables for Alembic. Preserve public OpenAPI names through `api_schema.py` when internal names collide.
- Routers adapt HTTP/WS/SSE and do not own shared business logic. Domain code cannot import routers. Use `app.servers.commands.ServerCommands` for manual/scheduled lifecycle commands and `app.servers.queries` for shared reads.
- Configuration preparation, versions, staged application and source metadata belong to `app.configuration`; use its owning modules. Preserve optimistic conflicts and the accepted running intent.
- Capture dependencies from the owning runtime. Do not create import-time clients, implicit default runtimes or resource-registration side effects. Register application-owned side work with `spawn_background` or a subsystem drained by `Runtime.close()`.
- Read dynamic configuration at the point of behavior. Constructor-captured values require an explicit refresh/rebuild path. Keep save-time validation separate from loading repairable legacy values.
- Delayed work captures `ServerRef` and revalidates generation and confined paths when acquiring resources. Declare all lexical/canonical file, archive, cache and maintenance resources before effects; nested operations may only reuse a validated covering lease.
- Durable task acceptance, terminal publication and cleanup follow the journal. A 202 response, 100% progress or a disconnected observer is not completion. Confirm writer termination before releasing ownership; uncertain writers retain recovery blocks and artifacts.
- Do not introduce execution-time snapshot protection or identity rules in adapters. Shared scopes, protection, recovery history and previews belong to `app.snapshots`; world modules own selection, chunk execution and map finalization.

## Async filesystem I/O

Do not block the event loop in `async def`. Choose in this order:

1. `aiofiles` / `aiofiles.os` / `aiofiles.os.path` when they cover the call.
2. `app.utils.async_fs` for unsupported filesystem operations.
3. `asyncio.create_subprocess_exec` or `app.utils.exec` for subprocesses.

Add an `async_fs` wrapper only when aiofiles lacks an equivalent. Implement it
with `asyncio.to_thread`; do not reintroduce `asyncer.asyncify`. Annotate
`@asynccontextmanager` generators as `collections.abc.AsyncGenerator[T]`; use
`AsyncIterator[T]` for interfaces promising iteration only.

## API, errors and compatibility

- Pydantic models use `model_config = ConfigDict(...)`; preserve aliases and defaults.
- Preserve string/structured HTTP `detail`, headers and existing string task/SSE error fields. Use `app.errors` and explicitly authored `PublicOperationError` messages for safe public failures.
- Never log raw credentials, exception values, query strings or headers. Audit masking and safe traceback behavior are described in [audit](docs/audit.md) and [administration contracts](docs/administration-contracts.md).
- Game-port initialization validation belongs to reusable-template saves and new-server creation. Legacy reads, snapshot edits, rebuilds and lifecycle operations retain the permissive Compose parser.

## Read for the task

| Change | Read before implementation |
| --- | --- |
| Module ownership or new subsystem | [Architecture](docs/architecture.md), [runtime](docs/runtime.md) |
| Tasks, cancellation, filesystem writers or deletion | [Background tasks](docs/background-tasks.md), [operations](docs/operations.md), [server admission](docs/servers.md) |
| Snapshot/restore protection or history | [Snapshot architecture](docs/snapshots.md), [restoration](docs/snapshot-restoration.md), [world adapters](docs/world-restore.md) |
| Compose/template application | [Configuration](docs/configuration.md), [Minecraft adapter](docs/minecraft.md) |
| Database migration or compatibility | [Migration operations](docs/database-migrations.md), [schema reference](docs/database-schema.md) |
| Test fixtures or CI planning | [Testing](docs/testing.md), [backend test planning](docs/test-planning.md), [repository CI](../docs/ci.md) |

Update the owning topic for implementation changes. Modify this file only for
commands, development constraints or reading routes; follow the repository's
[documentation policy](../docs/documentation.md).
