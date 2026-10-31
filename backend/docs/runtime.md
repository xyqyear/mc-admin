# Application construction and resource ownership

`app.main.create_app(settings=...)` creates a root FastAPI application, the mounted `/api` application, and an independent `Runtime`. `create_app(runtime=...)` accepts an explicitly configured runtime; passing both arguments is rejected. `app.main.app` and `api_app` remain compatibility entrypoints. The HTTP routes, `/api` prefix, static files, authentication cookies, WebSocket endpoints and SSE message formats retain their existing contracts.

## Owned dependencies

`Runtime(settings, hooks=...)` owns its settings, database engine and session factory, dynamic configuration cache, coordinator/admission state, task manager, event subscriptions, cron scheduler/registry, DNS clients, player producers, login codes and JWT key, map queues, world previews, prune metadata, upload sessions, and application/audit log handlers. Each resource has a concrete typed lazy property and private cache. A distinct uninitialized sentinel separates resources not yet constructed from disabled optional resources cached as `None`. Tests replace owned cache fields through explicit fixture helpers and restore their exact previous state; engine and session-factory overrides remain independent of the database object.

## Configuration paths

`Settings` resolves directory roots before runtime resources are constructed. Defaults, constructor arguments, TOML, dotenv and environment values for `static_path`, `cgroup_path`, `server_path`, `logs_dir` and `archive_path` become absolute paths with symbolic links resolved. Relative values are anchored to the working directory at settings construction; their directories need not exist yet. This keeps archive upload targets and their resource-claim roots in the same coordinate system. File operations still enforce confinement and revalidate claims before writing. Binary command names, database URLs and Restic repository addresses keep their existing interpretation.

## Composition and context binding

`runtime_factories.py` is the explicit composition root with a concrete constructor for each lazy service. Typed `get_*()` accessors return the corresponding runtime property; no resource registers its factory at import time. Services capture their database, configuration view and adapters during construction. `RuntimeMiddleware` binds a context variable for the full HTTP, WebSocket and SSE execution, and the root lifespan binds the same runtime. Child asyncio tasks and `asyncio.to_thread` inherit that context. `Runtime.bind()` provides the corresponding boundary for tests and CLI work. `current_runtime()` raises outside a bound context. CLI code that acquires application resources must construct, bind and close an explicit runtime. Alembic’s standalone entrypoint can read its own settings without constructing application resources. Tests bind a collection owner separately from each test’s isolated owner. New application code takes explicit dependencies or uses typed accessors at execution boundaries.

## Tracked execution

`runtime_context(runtime)` creates a fresh context containing only the owning
runtime. Scheduler wakeups and manager-owned log watchers use it so long-lived
callbacks cannot retain the operation that registered them. Cron dispatch also
binds its owner and clears the operation in the existing task; normal nested
commands and subprocess finalization retain their active operation ownership.

`spawn_background(coroutine, name=...)` registers side work with its runtime and clears the parent operation context for detached work. Subsystem workers remain registered with their owning manager. Requests and streams remain registered until their ASGI call completes. This lets shutdown drain the whole execution before closing database sessions and clients. Creating background work during shutdown is rejected.

## Startup

Startup closes write admission, acquires the single-writer guard for both SQLite and the managed server directory, migrates the database, loads dynamic configuration, and runs operation recovery. Recovery classifies interrupted work and installs resource blocks; it does not replay commands or infer that incomplete business operations succeeded. The legacy restoration history and task history are reconciled before producers start.

Alembic command execution is serialized within the process because its environment proxy is global even when two apps have different databases. Startup cancellation waits for the migration thread to finish before releasing the writer guard. This library boundary does not serialize normal application requests or separate servers' operations.

After journal recovery, the prune registry starts and world restoration prepares its artifacts before DNS and player producers. DNS initialization and reconciliation precede player startup. Ordinary DNS/provider failures are logged safely and leave connectivity degraded; they do not prevent player and cron startup. Cancellation still aborts startup and closes acquired resources. Player heartbeat recovery runs before player loops and log monitors, then cron jobs are loaded, and the world-preview janitor starts. Write admission opens only after startup succeeds. A failure in a required startup stage closes resources already acquired and releases the writer guard. The same runtime cannot restart after closing; create a fresh runtime.

## Shutdown

The application image gives Uvicorn a two-second HTTP graceful-shutdown window.
Open streams are cancelled after that window so lifespan shutdown can enter the
runtime's owned worker cleanup. This limit applies to HTTP draining, not the
subsequent resource cleanup; the outer container stop deadline must leave enough
time for workers, subprocesses and durable settlement to finish.

Shutdown closes admission and stops cron and player producers. It cancels and drains tracked requests/streams and side work, then the task manager. Before deleting temporary artifacts it reads unsettled journal records: a legacy failed task status is not proof that its subprocesses stopped. Residual process identities, unknown ownership, an unconfirmed writer state, or an unreadable journal preserve claims, upload files, previews and runtime scratch. Shutdown still stops preview janitors/render queues, closes DNS pools, login sockets, event subscriptions, the database engine and log handlers, and reports the incomplete cleanup. The writer guard is released last. One close failure does not skip the remaining cleanup callbacks. Repeated cancellation of the shutdown caller cannot interrupt the owned cleanup task.

## Temporary artifacts

World-preview, prune-preview and chunk-restore stages live under a stable installation namespace in the system temporary directory. The namespace hashes the database URL and server root; each artifact has a unique token and its own feature subdirectory. This allows startup to reap only owned orphan artifacts while retaining unresolved journal references. Active builds, tile requests and prune applies pin the resources they use. Expiry or dismissal cannot delete a pinned artifact, and cleanup checks current membership after asynchronous directory enumeration. Queue closure waits for render workers and subprocess termination before removal. Unknown writers preserve their artifacts; the next startup does not resume or re-authorize an old preview. Persistent server data and map caches are not runtime scratch.

## Verification

`tests/test_runtime.py` exercises two simultaneously running apps with different real temporary databases and JWT keys, isolated configuration/events/durable tasks/log files, concurrent migrations, partial startup failures, repeated shutdown cancellation, cleanup continuation, WebSocket context, stream draining before database close, and artifact preservation for unconfirmed journal writers. Other tests bind a fresh runtime through the autouse fixture in `tests/conftest.py`; explicit factory apps retain their own runtime.
`tests/test_task_stream_shutdown.py` starts real Uvicorn with the image's command
options and verifies that SIGTERM drains an open task stream, its subscription
and an owned task before lifespan shutdown completes.
