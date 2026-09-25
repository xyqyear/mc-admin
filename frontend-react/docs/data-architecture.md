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

The shared Axios instance and `ApiError` live in `shared/http/api.ts`: same-origin cookies, CSRF, bounded timeout, structured detail preservation and session expiry notification. `shouldRetryQuery` skips cancellation and ordinary 4xx, retaining bounded retries for network/5xx/408/429 errors. Commands use the same resource keys as reads. Refresh handlers announcing success must await throwing refetches or inspect their error results.

## Generated contracts

`pnpm generate:contracts` exports `create_api_app(Runtime()).openapi()` in an isolated temporary backend environment without entering lifespan. It does not open the real database or contact services. `scripts/schema-closure.mjs` selects UserPublic, UserCreate and LoginResponse with their complete dependency closure, rejecting missing/remote references, untyped objects, missing array items and unconstrained additionalProperties. `openapi-typescript` generates only those actual schemas into `features/users/generated/api.ts`; no parallel hand-maintained schema input exists.

`pnpm check:contracts` checks generated freshness against the current backend and requires its uv dependencies. Ordinary bundling consumes the checked-in file without running Python. Other DTOs remain explicit feature contracts until their backend schema is complete. Runtime SSE and operation-result validators are preserved: compile-time generated types do not validate stream events or dynamic task results.

## Writes

Single-resource writes invalidate their detail key; list/aggregate changes invalidate parent keys. Cross-domain changes explicitly invalidate dependent resources (for example restart schedules invalidate both the server card and cron list/detail). Server lifecycle commands retain their delayed status refresh because the Docker daemon may settle after the CLI response. Independent task completion belongs to the application observer below.

## Features and operation completion

`features/configuration/contracts.ts` and `api.ts` own Compose reads/writes, template snapshot parameters, previews and both mode conversions. `queries.ts` exposes shared query options; read-only template-copy selection uses the same versioned Compose cache with a string selector. `commands.ts` requires an accepted version for every configuration write and only announces task/operation discovery after submission.

`app/operations/OperationObserver.tsx` is mounted once within the authenticated layout. Its QueryClient-backed `/operations` query reads paginated history (1,000 rows per page), polls every two seconds while operations are active and every ten seconds otherwise, and resynchronizes on reconnect/focus. Initial discovery scans history; subsequent reads stop at known records and separately recheck older active operations, avoiding full-history downloads every poll. A retained active reference whose detail now returns 404 is marked unavailable internally, synchronizes its resources once, and leaves tracking without claiming success; other read errors remain retryable failures. Query cancellation uses an AbortSignal. No second mutable task/operation store is introduced.

Features register affected keys through `operationResources.ts`; configuration registers `server_rebuild` and `configuration_apply`. Terminal operation IDs are handled once per login session. Success, failure, cancellation, interruption and skipped outcomes invalidate the affected Compose, template binding/values, server info/status/runtime/maintenance, player and task keys. Failed partial changes therefore refresh even if the submitting page or progress dialog has closed. Only registered operation kinds affect business caches in this migration.

The observer is independent of route pages. Its in-memory completion set and query data clear with logout; a new login rediscovers terminal history conservatively. `RebuildProgressDialog` owns progress and outcome presentation only. Populate/compression/ownership presentation and world restore/prune views also delegate business completion to the observer.

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
- `queryKeys.worldRestore.layout(serverId)` / `.eligible(serverId, selection)` / `.history(serverId)` / `.restoration(serverId, id)`
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

The configuration feature models an accepted baseline (including an opaque version), a local draft and current remote data separately. Untouched Compose/template editors follow fresh remote reads, including a page reopened from cached data after an independent task. Once the user authors content, accepts a comparison, or receives an applied submission, background reads cannot replace that draft. Edited template forms retain their accepted schema until explicit comparison. A remote mode change preserves the original editor until the user confirms discarding its draft and loading the new mode.

Conversion dialogs keep their captured baseline even while the text session appears untouched: selected templates, extracted variables and authored form values live outside that session. A background Compose refresh therefore still requires comparison before submitting conversion parameters. The untouched-read policy is an explicit opt-in for the Compose and template editors, not a default for every configuration flow.

Every configuration write submits the baseline version. HTTP 409 `configuration_conflict` or a background task's matching `error_code` requires a successful remote read and full baseline/remote/draft comparison. “接受此版本为新基准” preserves the draft, accepts only the displayed version, and returns to editing; a separate submit performs the write. Successful tasks return the actual applied `version`: the session accepts that submitted snapshot as its baseline while preserving any newer local draft. Already-read data from before completion is not treated as a new conflict; a fresh read with any other version still requires comparison. A further race remains a conflict. Confirmed reload is the explicit discard action and only resets after a successful read. Mode conversion preserves edited variables during conflicts and reruns the comparison after acceptance. Drafts remain local to mounted editors.

File, global template/default-variable and dynamic-config editors use `useEditorDraft` with a resource key. Remote updates replace pristine content but preserve authored content. Loading failures never establish a writable empty session; a successful empty read is valid content. Their existing write contracts are unchanged.

## HTTP/query integration tests

`src/test/http.ts` creates isolated real QueryClients and Axios-adapter responses; `TestProviders.tsx` supplies the client and router. Existing page tests preserve real query/mutation hooks while replacing transport and heavyweight editors. Query retry tests verify actual attempt counts.

`features/configuration/ConfigurationScreen.test.tsx` and `app/operations/OperationObserver.test.tsx` use MSW HTTP handlers with real QueryClients. They exercise delayed loads, intentional empty writes, draft preservation, synchronous/async conflicts, explicit acceptance and resubmission, mode conversion, leaving/returning to the page, terminal deduplication, paginated reconnection and logout cleanup. They do not mock query hooks or invalidate methods to manufacture results.

## File and world controllers

Files own typed contracts/API/query/commands, draft and navigation controllers, upload sessions and UI. World owns common layout/map/layers and feature-specific restore/prune controllers. Shared map code has no reverse dependency on restore; files and world publish their own terminal resource mappings to the application observer. File keys scope invalidation by server; explicit global file-root resources conservatively refresh all affected server caches. Archive-root resources alone do not invalidate unrelated servers.

Map initialization terminal outcomes refresh that server's map status and region
queries even after leaving the page. Individual `map_render` operations do not
invalidate map queries, which would otherwise trigger another render cycle.

Independent-task progress views only display state and offer explicit commands; closing or unmounting never supplies their business completion behavior. Finite restoration requests retain their existing cancellation semantics: immutable confirmed body, abort on unmount, terminal-event requirement, original structured HTTP details. Successful local CRUD and partial browser uploads still refresh their immediate write results.

The tests use real QueryClient caches and MSW HTTP boundaries. Coverage includes file filtering/drafts/partial batches, prune availability and late rejection, shared world URL selection, finite SSE cancellation/errors, ready-preview disposal, old-generation history guards and off-page partial-write completion.

`app/overview/queries.integration.test.tsx` verifies cross-page fresh-cache reuse, shared invalidation and stopped-server gating through real MSW endpoints. Player integration tests verify streamed/cache updates reach both single-profile and map observers. Schedule integration tests keep active-but-unregistered jobs visible, retry registration, refresh the server card and read older responses without the optional fields.

DNS integration tests exercise degraded/unknown and empty desired states, update availability, visible partial provider writes after an overall failure, and refresh failures without false success feedback.
