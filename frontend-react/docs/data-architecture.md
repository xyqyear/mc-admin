# Data Architecture

Every domain is a feature under `src/features/`. The application composes features; shared code supplies primitives and transport. Feature directories include servers, configuration, files, world, archives, backups, players, schedules, templates, tasks, users, settings, health, DNS and system metrics.

## Ownership and dependency direction

- `contracts.ts`: request/response DTOs and domain values. Contracts cannot import behavior or UI.
- `api.ts`: one raw HTTP operation per function, with no React or cache state. Authentication is the users feature’s additional `auth.ts` transport.
- `queries.ts`: resource keys, freshness, retries, enabled gates and polling. Shared `queryOptions` factories serve ordinary hooks and dynamic `useQueries` aggregations.
- `commands.ts`: writes and immediate invalidation. Controllers own the interaction’s local draft, selection, confirmation, upload or stream state.
- Feature screens/UI present these workflows. Reusable business UI is intentionally public under `ui/`; internal controllers, caches, generated files and map layers are private to the feature.

`app/` owns layout, overview, version UI and operation observation. Route adapters only read URL parameters and mount feature screens. `shared/` owns HTTP/SSE transport, reusable UI/editors/hooks and finite operation request ownership. It cannot depend on features, pages or application modules.

`pnpm check:boundaries` parses TypeScript imports/reexports, dynamic imports and imported types, resolves aliases and relative paths, and rejects reverse dependencies or private cross-feature imports. `scripts/import-boundaries.mjs` is the explicit public-entry policy; screens may only be imported by application composition. Deleted hooks/components/stores/types facade paths are forbidden. Architecture tests demonstrate both allowed composition and rejected imports. The check runs as part of lint.

## Shared query policy

`app/overview/useOverviewData.ts` composes server, system, backup and player factories instead of constructing its own metrics requests. `features/servers/useServerDetailData.ts` uses the same options. Fresh cache values survive navigation; observers share one request and the same polling/retry policy. CPU/memory/I/O queries run only for RUNNING/STARTING/HEALTHY servers; online-player queries in the overview require HEALTHY. Disk remains available when stopped.

`features/players/queries.ts` streams profiles into normalized per-UUID Query keys. The map subscribes to those entries, including while profile streaming is disabled; it does not maintain a second profile Map in state. Only stream progress/error state remains local. Backend tasks likewise exist only in Query cache; browser downloads and local panel placement are separate client-owned state.

`features/players/identity.ts` is an explicit public entry for pure UUID syntax
normalization. Profile queries, world controllers, player lists and marker layers
share its dashless lowercase 32-hex identity. Online-mode eligibility remains a
backend identity rule; this helper has no network or cache dependency.

The shared Axios instance and `ApiError` live in `shared/http/api.ts`: same-origin cookies, CSRF, bounded timeout, structured detail preservation and session expiry notification. `shouldRetryQuery` skips cancellation and ordinary 4xx, retaining bounded retries for network/5xx/408/429 errors. Commands use the same resource keys as reads. Refresh handlers announcing success must await throwing refetches or inspect their error results.

## Generated contracts

`pnpm generate:contracts` exports `create_api_app(Runtime()).openapi()` in an isolated temporary backend environment without entering lifespan. It does not open the real database or contact services. `scripts/schema-closure.mjs` selects UserPublic, UserCreate and LoginResponse with their complete dependency closure, rejecting missing/remote references, untyped objects, missing array items and unconstrained additionalProperties. `openapi-typescript` generates only those actual schemas into `features/users/generated/api.ts`; no parallel hand-maintained schema input exists.

`pnpm check:contracts` checks generated freshness against the current backend and requires its uv dependencies. Ordinary bundling consumes the checked-in file without running Python. Other DTOs remain explicit feature contracts until their backend schema is complete. Runtime SSE and operation-result validators are preserved: compile-time generated types do not validate stream events or dynamic task results.

## Writes

One-off, flow-local preview/check requests and stream/progress operations may use
their feature transport directly when they should not create shared cached state.
Ordinary server-state reads still use the query layer.

Query and mutation modules export concrete hooks such as `useServers`,
`useServerStatus`, `useCreateFile(serverId)` and `useLogin`. Each hook captures its
QueryClient and any required router, server or download context directly.
Reusable query options retain their domain polling and retry policies; caller
options are applied after those defaults. File and archive downloads remain
ordinary hooks backed by the download manager rather than mutations.

Single-resource writes invalidate their detail key; list/aggregate changes invalidate parent keys. Cross-domain changes explicitly invalidate dependent resources (for example restart schedules invalidate both the server card and cron list/detail). Long management commands return task acceptance; `features/tasks/commands.ts` observes real completion while preserving the initiating view's blocking behavior and retries failed status reads without resubmitting. Server lifecycle commands finish when their Docker command and cleanup settle; Minecraft readiness remains an independent status query. Independent task completion belongs to the application observer below.

## Features and operation completion

Feature commands wake durable-operation discovery; application-level observation
refreshes business resources across pages and after partial failures. See
[operation refresh](operation-refresh.md) for cursors, checkpoints, batching,
logout/reset behavior and tile revisions. Versioned existing-server editors
are described in [configuration](configuration.md).

## `queryKeys` factory

Defined in `shared/http/api.ts`, with task keys owned by `features/tasks/queries.ts`. Hierarchical: `all` → `list / detail / sub-resource`. Examples:

- `queryKeys.servers()` (top-level shortcut)
- `queryKeys.serverInfos.all` / `.detail(id)`
- `queryKeys.serverRuntimes.cpu(id)` / `.memory(id)` / `.ioStats(id)` / `.disk(id)`
- `queryKeys.serverStatuses.batch(ids)`
- `queryKeys.players.detailByUUID(uuid)` / `.serverOnline(serverId)` / `.sessions(playerDbId, params)`
- `queryKeys.snapshots.global()` / `.repositoryUsage()` / `.locks()` / `.forPath(serverId, path)`
- `queryKeys.cron.detail(id)` / `.executions(id, limit)` / `.nextRunTime(id)`
- `queryKeys.selfCheck.status()` / `.runs(params)` / `.run(id)`
- `queryKeys.dns.status()` / `.records()` / `.routes()` / `.enabled()`
- `queryKeys.map.status(serverId)` / `.regions(serverId, region)`
- `queryKeys.worldRestore.layout(serverId)` / `.dimensionLabels(serverId)` / `.playerLocations(serverId)`
- `queryKeys.snapshots.eligible(scope)` / `.active(serverId)` / `.history(serverId, offset, filters)` / `.target(scope)`
- `queryKeys.snapshots.rulesAll()` / `.rules(serverId)` use the independent `snapshot-target-rules` prefix so read-only snapshot completion does not refresh configuration-derived rules.
- `queryKeys.templates.detail(id)` / `.schema(id)` / `.serverConfig(serverId)` / `.defaultVariables()`

Hook reads and mutation invalidations must reference the same factory path. Adding a key means adding to the factory, not to a string somewhere.

## Volatility-based polling defaults

| Query                               | refetchInterval | staleTime | Gate                                    |
| ----------------------------------- | --------------- | --------- | --------------------------------------- |
| `serverStatuses.detail(id)`         | 5 s             | 2 s       | always                                  |
| `serverRuntimes.cpu/memory(id)`     | 3 s             | CPU 3 s / memory 1 s       | status ∈ RUNNING / STARTING / HEALTHY   |
| `serverRuntimes.ioStats(id)`        | 5 s             | 2 s       | same                                    |
| `serverRuntimes.disk(id)`           | 30 s            | 15 s      | always                                  |
| `players.serverOnline(serverId)`    | 10 s            | —         | status = HEALTHY                        |
| `snapshots.repositoryUsage()`       | 30 s            | 15 s      | retry skipped on `restic` 500           |
| `serverInfos.detail(id)`            | —               | 5 m       | manual invalidate on mutation           |
| `templates.list()`                  | —               | 5 m         | manual invalidate on mutation           |

Pick the bucket based on how fast the underlying state actually changes — not on what the page "feels like" it should refresh at.

## Editor drafts

Keep authored drafts separate from cached server data. Existing-server Compose
and template-parameter editors retain accepted versions and explicit conflict
comparison; other resource editors use `useEditorDraft` with their own write
contracts. The [configuration editor contract](configuration.md#editor-drafts)
defines fresh/pristine reads, conversion baselines and failed-load behavior.

## HTTP/query integration tests

The [testing guide](testing.md) owns QueryClient/MSW boundaries, observable
assertions, fixture ownership and related test entry points.

## File and world controllers

Files own navigation, editing and upload controllers; world owns layout/map/layer
state plus restore/prune workflows. Both compose the public backups feature for
shared recovery. See [file management](file-management.md),
[map controllers](server-map.md#shared-feature-controller) and
[common snapshot UI](snapshot-recovery.md) for their local lifecycles.

## Snapshot recovery

`features/backups` owns shared contracts, commands, previews, history and recovery
observation. [Common snapshot UI](snapshot-recovery.md) defines creation completion,
protection feedback, activity-aware discovery and rollback guards; the world
feature supplies its map-specific adapters.

## Session and browser-owned state

Session guards use `useCurrentUser()` and the backend's HttpOnly JWT cookie.
Network/server lookup failures keep the requested route available for retry;
authentication rejection opens login. Axios sends credentials and CSRF, while
the shared finite SSE reader supplies CSRF for unsafe methods and rejects EOF
before an explicit terminal event. See [backend authentication](../../backend/docs/auth.md).

| Local owner | State |
| --- | --- |
| `app/layout/sidebarStore.ts` | Sidebar collapse and open sections |
| `features/users/loginPreferenceStore.ts` | Preferred login method |
| `features/tasks/panelStore.ts` | Panel/tab/drag state; launcher position persists |
| `features/tasks/downloadStore.ts` | Browser-owned downloads; reload cancels in-flight records |
| `features/world/restore/selectionStore.ts` | Transient per-server world selection |

Backend tasks and player profiles remain Query data, not mirrored stores.
Browser downloads have their own [task-center lifecycle](task-center.md).
