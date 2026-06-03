# Data Architecture

Three layers separate transport, server-state caching, and writes. Page-level code only sees domain hooks; raw Axios and React Query primitives stay encapsulated.

## Why three layers

Mixing Axios calls, query keys, and cache invalidation inside components produces drift fast: two components ask for "snapshots" with two different keys; one mutation invalidates `["snapshots"]` while another invalidates `["snapshots", "list"]`; a poll cadence bumps unintentionally because someone copied a 5s interval into a 30s context. Splitting the responsibility makes each layer's job small enough to enforce by review.

## Layer 1 — `hooks/api/*Api.ts`

Raw Axios. Per-domain modules: `serverApi`, `playerApi`, `snapshotApi`, `archiveApi`, `cronApi`, `dnsApi`, `configApi`, `mapApi`, `worldRestoreApi`, `templateApi`, `taskApi`, `fileApi`, `userApi`, `authApi`, `systemApi`. Each exports typed functions returning typed responses (`ApiResponse<T>`).

The shared Axios instance lives in `utils/api.ts`:

- 60s timeout, JSON content-type
- Sends same-origin cookies (`withCredentials`) for the HttpOnly JWT session
- Mirrors the readable CSRF cookie into `X-CSRF-Token` for unsafe requests
- Response interceptor: extracts `detail` / `message` from backend errors into a normalized `ApiError`; on authenticated-route 401s, broadcasts an auth-expired event so the app clears cached server state and returns to login

No caching at this layer. No React.

## Layer 2 — `hooks/queries/base/use*Queries.ts`

Per-resource `useQuery` hooks. Owns:

- Query keys (always from the `queryKeys.*` factory in `utils/api.ts`, never inline)
- `staleTime` and `refetchInterval` (volatility-based; see below)
- `enabled` gates (e.g. don't poll runtime metrics for stopped servers)
- Retry logic (skip 4xx except 408/429; specifically short-circuit 409 "not running" so we don't hammer offline servers)

## Layer 3 — `hooks/queries/page/use*Queries.ts`

Composes layer-2 hooks for a specific page. `useOverviewData` aggregates per-server data filtered to running servers; `useServerDetailQueries` joins server info, status, runtime, players. Pages pull *one* hook from this layer instead of stitching ten layer-2 hooks together.

## Mutations — `hooks/mutations/use*Mutations.ts`

All writes plus cache invalidation on success:

- **Single-resource update** → invalidate the detail key.
- **List/aggregate change** → invalidate the parent `all` key (prefix invalidation covers everything below).
- **Cross-domain side effects** — server lifecycle ops invalidate `system.info()` (host resources change). Restart-schedule mutations invalidate both `restartSchedule.detail(id)` and `cron.all` because the schedule lives in both shapes.
- **Server lifecycle** mutations wait 1s before invalidating: Docker container state lags the API response, so an immediate refetch sees the old status.
- Prefer `invalidateQueries`; reserve `refetchQueries` for explicit user-driven "refresh now" buttons.

## Task-driven flows (special case)

Long operations (compose update, populate, rebuild, template conversion) submit a background task and return a `task_id`. **Don't invalidate business queries on submission** — the work hasn't happened yet. Instead:

1. Submit the mutation → invalidate `taskQueryKeys.all` so the task center sees it.
2. Poll the task detail (`useTask(task_id)`).
3. When the task reaches `completed`, invalidate the affected business keys *in one place* — the progress modal's completion handler.

This keeps the cache truthful: business state is invalidated exactly when it actually changes, not when the request to change it is accepted.

## `queryKeys` factory

Defined in `utils/api.ts`. Hierarchical: `all` → `list / detail / sub-resource`. Examples:

- `queryKeys.servers()` (top-level shortcut)
- `queryKeys.serverInfos.all` / `.detail(id)`
- `queryKeys.serverRuntimes.cpu(id)` / `.memory(id)` / `.ioStats(id)` / `.disk(id)`
- `queryKeys.serverStatuses.batch(ids)`
- `queryKeys.players.detailByUUID(uuid)` / `.serverOnline(serverId)` / `.sessions(playerDbId, params)`
- `queryKeys.snapshots.global()` / `.repositoryUsage()` / `.locks()` / `.forPath(serverId, path)`
- `queryKeys.cron.detail(id)` / `.executions(id, limit)` / `.nextRunTime(id)`
- `queryKeys.dns.status()` / `.records()` / `.routes()` / `.enabled()`
- `queryKeys.map.status(serverId)` / `.regions(serverId, region)`
- `queryKeys.worldRestore.layout(serverId)` / `.eligible(serverId, selection)` / `.history(serverId)` / `.restoration(serverId, id)`
- `queryKeys.templates.detail(id)` / `.schema(id)` / `.serverConfig(serverId)` / `.defaultVariables()`

Hook reads and mutation invalidations must reference the same factory path. Adding a key means adding to the factory, not to a string somewhere.

## Volatility-based polling defaults

| Query                               | refetchInterval | staleTime | Gate                                    |
| ----------------------------------- | --------------- | --------- | --------------------------------------- |
| `serverStatuses.detail(id)`         | 5 s             | 2 s       | always                                  |
| `serverRuntimes.cpu/memory(id)`     | 3 s             | 1 s       | status ∈ RUNNING / STARTING / HEALTHY   |
| `serverRuntimes.ioStats(id)`        | 5 s             | 2 s       | same                                    |
| `serverRuntimes.disk(id)`           | 30 s            | 15 s      | always                                  |
| `players.serverOnline(serverId)`    | 10 s            | —         | status = HEALTHY                        |
| `snapshots.repositoryUsage()`       | 30 s            | 15 s      | retry skipped on `restic` 500           |
| `serverInfos.detail(id)`            | —               | 5 m       | manual invalidate on mutation           |
| `templates.list()`                  | —               | ∞         | manual invalidate on mutation           |

Pick the bucket based on how fast the underlying state actually changes — not on what the page "feels like" it should refresh at.
