# MC Admin Frontend

React 19 + TypeScript + Vite 8 on Node 24. Path alias: `@` → `src/`.

## Commands

```bash
pnpm install
pnpm dev        # port 3000
pnpm build      # typecheck + bundle
pnpm typecheck  # tsc -b
pnpm build:bundle # vite build
pnpm lint
pnpm test       # architecture checks + Vitest HTTP/query integration tests
pnpm test:browser # Playwright through the owned Go browser wrapper
pnpm check:boundaries # executable import rules
pnpm generate:contracts # isolated backend OpenAPI -> selected complete DTOs
pnpm check:contracts # check generated DTO freshness (requires backend uv deps)
```

Backend URL is configured in `vite.config.ts` (default `http://localhost:5678`).

Production builds split hashed output into `assets/vendor`, `assets/workers`, `assets/fonts`, `assets/styles`, `assets/media`, and `assets/app`; the root Dockerfile copies those directories as separate runtime layers.

The Static Checks push workflow runs lint, typecheck, operation-flow tests and bundling as separate steps. Docker uses `pnpm build:bundle` to produce assets; TypeScript diagnostics are reported by the independent static workflow.

React Router 7 is used in declarative mode; import router APIs from `react-router`.

## Data and feature boundaries

Features own their contracts, API calls, query policy, commands/controllers and UI. Modules are `servers`, `configuration`, `files`, `world`, `archives`, `backups`, `players`, `schedules`, `templates`, `tasks`, `users`, `settings`, `health`, `dns` and `system`. A feature's `contracts.ts` owns DTOs; `api.ts` contains transport only; `queries.ts` owns keys, retries, polling and reusable TanStack `queryOptions`; `commands.ts` owns writes and immediate invalidation. Feature controllers coordinate user workflows, while screens and UI present them.

`app/` owns the authenticated shell, aggregate overview, operation observation and version notification. `shared/` owns HTTP/SSE transport, reusable UI, editors, generic hooks and finite request ownership. It cannot import feature or application code. Server route adapters under `pages/` only read route parameters and mount feature screens.

`app/version/config.ts` owns release notes and SemVer precedence, including prerelease identifiers and ignored build metadata. The notification hook, newest-first dialog and current-version selection share that comparator; release entries are appended to the list.

`scripts/import-boundaries.mjs` declares executable public entries: contracts/API/queries/commands, operation resource registries, reusable `ui/`, and a small explicit set of read helpers. Screens are for application/route composition only. Cross-feature private imports, reverse dependencies and deleted compatibility-layer imports fail `pnpm check:boundaries` (also part of lint). No large universal barrel loads all feature implementations.

`app/overview/useOverviewData.ts` and `features/servers/useServerDetailData.ts` share resource query-option factories; consumers do not copy polling/retry policy. Player profile streams populate individual Query entries, and map consumers observe those entries without a second profile store.

HTTP consumers use the normalized `ApiError` (`Error.message`, `status`, `code`, original `detail`) from `shared/http/api.ts`; Axios response internals stay in the interceptor. `shouldRetryQuery` applies the shared status policy. A refresh handler that reports success/failure must use `refetch({ throwOnError: true })` or explicitly inspect its result.

`features/configuration/` owns the existing-server Compose/template-parameter/conversion workflow: typed API contracts, query options, version-required commands, baseline/draft/remote edit sessions, conflict comparisons, and UI. `pages/server/servers/ServerCompose.tsx` is its route adapter. Global template CRUD and default variables belong to `features/templates/`.

`shared/hooks/useEditorDraft.ts` owns local text/JSON drafts for other resource editors. Remote updates replace pristine content, preserve authored changes, and never establish an empty draft from a failed initial read. Explicit reload resets the draft after a successful read. See `docs/data-architecture.md` for editor and integration-test boundaries.

When to bypass the query layer: one-off flow-local requests that should not be globally cached (e.g. modal-only preview/check calls), or stream/progress operations.

`features/archives/uploads/` owns archive pause/resume and verification. `features/files/useMultiFileUpload.ts` owns ordinary-file conflict checking, overwrite policy and sequential batches. Dialogs render flow state; raw API functions each issue one request.

## Query keys & invalidation (mandatory)

- Use `queryKeys.*` from `shared/http/api.ts`, or the task feature’s `taskQueryKeys` from `features/tasks/queries.ts`. No inline string literals.
- Query hooks and invalidation must reference the same factory path.
- Prefer prefix invalidation via stable parents (`queryKeys.snapshots.all`) for broad fanout.
- Single-resource update → invalidate that detail key. List/aggregate change → invalidate related list and summary keys. Cross-domain side effects → invalidate dependent domains (DNS, restart schedule, players, snapshot usage).
- Prefer `invalidateQueries`; use `refetchQueries` only for explicit user-triggered "refresh now" actions.

**Operation completion**: commands invalidate task and operation discovery keys on submission. `app/operations/OperationObserver.tsx`, mounted in the authenticated layout, polls the operation journal and applies configuration/files/world `operationResources.ts` registries once per terminal operation, including failed/partial outcomes. It survives page navigation, resynchronizes on reconnect/focus, and clears session state on logout/cache clear. `RebuildProgressDialog`, `PopulateProgressDialog`, compression/ownership presentation and restore/prune views never own terminal business invalidation. Synchronous file commands and browser-owned partial uploads still invalidate their immediate write results.

Configuration writes always send the accepted `expected_version`. A synchronous `configuration_conflict` detail or async task `error_code` retains the draft and requires comparison plus explicit acceptance before resubmission. Never silently adopt a 409's `current_version`. A confirmed reload is the separate discard-and-load action. Edited template forms keep their accepted schema until the user accepts a new baseline.

Compose and template editors follow a fresh remote read while untouched, including when reopening a stale cache after a background task. Authored drafts, explicit conflicts and a submitted version remain protected. Conversion dialogs retain their captured baseline because their form edits live outside the configuration text session.

**Polling defaults by volatility**: status/runtime/online players → seconds-level. Disk usage / task lists → medium. Schemas / static config → long stale time + manual invalidation on mutation.

## UI stack — shadcn on base-ui (not Radix)

shadcn here is built on `@base-ui/react` primitives, not Radix. Project-specific gotchas:

- **No `asChild`.** Use base-ui's `useRender` with the `render` prop, or compose via controlled state.
- **`TooltipProvider` is mounted once in `src/main.tsx`.** Do not wrap individual components in another one.
- **`Select`** (`@/shared/ui/select`) needs `itemToStringLabel={(v) => "..."}` whenever the trigger label differs from the option value (e.g. value `"10"` rendered as `"10条/页"`).
- **Toasts**: `import { toast } from 'sonner'`.
- **Confirmation dialogs**: `useConfirm` (in `shared/hooks/useConfirm.tsx`). Accepts `title`, `description`, `confirmText`, `cancelText`, `variant`, `onConfirm` — **no `content` field**. For rich confirmations (diff previews etc.), use a state-driven `<Dialog>` instead.
- Legacy Ant Design has been removed — no `antd`, `@ant-design/icons`, or `@rjsf/antd`.

## Auth

Browser auth is an HttpOnly JWT cookie plus a readable CSRF cookie. Route guards use `useCurrentUser()` (`GET /api/user/me`) as the session source of truth. A 401/403 opens login; a failed initial session lookup due to network/server errors offers retry on the requested route. Axios is configured in `shared/http/api.ts` with credentials and XSRF cookie/header names; fetch-based SSE adds the CSRF header manually.

## Routes

The protected root route `/` is the system self-check dashboard. The former feature-card home page is not part of the app.

Self-check file remediation reuses `/server/:id/files` with URL-driven `path`, `q`, and `regex` state; see `docs/self-check.md`. Shared Compose editor hints remain compatible with legacy YAML; initialization requirements belong to template-save/new-server flows.

## Local UI and browser state

- `app/layout/sidebarStore.ts`: sidebar collapse and open sections.
- `features/users/loginPreferenceStore.ts`: preferred login method.
- `features/tasks/downloadStore.ts`: browser downloads; persisted records mark in-flight work cancelled on reload because AbortControllers cannot resume.
- `features/tasks/panelStore.ts`: panel/tab/drag state; only launcher position persists.
- `features/world/restore/selectionStore.ts`: transient per-server restore selection.

Backend task data is owned solely by TanStack Query. The trigger badge reads the active-task query; task DTOs and view conversion live in `features/tasks/contracts.ts` and `api.ts`. There is no background-task Zustand mirror.

Identity DTOs (UserPublic, UserCreate, LoginResponse and their schema dependencies) are generated into `features/users/generated/api.ts` from the actual isolated backend OpenAPI, with closure validation rejecting unknown references and untyped objects/maps. Other DTOs remain explicit feature contracts until their schemas are complete. SSE event and operation-result validators remain in their owning features; generated static types never replace runtime validation.

Saved cron `status` is displayed as enabled/paused/cancelled. `registration_status` and `registration_error` show actual scheduler registration separately in the list, details and server card. An enabled but unregistered user task can retry the existing resume command. Older responses without these additive fields remain readable. DNS status similarly distinguishes pending/degraded/empty from ready, exposes safe issues and unknown servers, and refreshes both provider views after partial update failure.

## File and world ownership

`features/files/` contains contracts, API, queries, commands, language/search rules, upload controller and UI. `useFileNavigation` owns path/search URL state; `useFileEditor` owns the loaded baseline/draft; `useFileBrowser` coordinates CRUD and task presentation. `pages/server/servers/ServerFiles.tsx` delegates to `FileBrowserScreen`. Ordinary online edits, deliberately empty files, deep regex filtering, diff and per-file overwrite policies remain available.

`features/world/` owns layout/dimensions/map/claims/player-layer contracts, API and queries. `useWorldMapController` owns common map initialization, URL view/dimension, layer visibility, cross-dimension pan and explicit refresh. Restore and prune controllers own their respective selection and preview/apply lifecycles; route files delegate to feature screens. Claims/player implementations do not depend on the restore feature.

`shared/operations/useRestoreRequest` owns a finite request and its immutable restore target; navigation/cleanup aborts its SSE. `features/world/restore/useRestorationStream` supplies domain routes. `useRestorePreview` owns heartbeat and session deletion on close/unmount; expired sessions require regeneration. Independent prune/populate/compression tasks continue after views close. Prune state includes feature-owned preview metadata/projections even after task-center dismissal; only a matching ready preview can apply. Historical restores with `binding_issue` remain readable but cannot roll back into another server generation.

## Server Map Reuse

`features/world/map/ServerMap.tsx` is the shared Leaflet surface. Map pages compose optional `ServerMapOverlay` layers; FTB claims and player locations are imported from `features/world/layers/*`, and world/dimension relpath helpers live in `features/world/map/worldDimensions.ts`.

## SSE consumer

`shared/http/eventStream.ts` is the canonical authenticated SSE reader: fetch + `AbortController` + `\n\n` block parser, same-origin cookies, and CSRF header injection for unsafe methods. `shared/hooks/useEventStream.ts` wraps it for state-driven component use (`useEventStream<TEvent>({ enabled, url, method, body, onEvent, onClose, onError, onResponse })`). Body fingerprinting uses `JSON.stringify`; finite restore controllers clone the confirmed target. HTTP failures retain structured `ApiError.detail` and status. EOF before an explicit terminal event is a connection failure.

## Monaco editor

- YAML worker at `yaml.worker.js` (registered in `main.tsx`).
- `snbtLanguage.ts` registers a custom Monaco language for Minecraft NBT files.
- Docker Compose schema with docker-minecraft-server hints lives at `public/static/mc-server-compose-schema.json`.

## Design background

Long-form, current-state design docs live under `frontend-react/docs/`:

- `docs/data-architecture.md` — feature ownership, executable imports, schema generation, shared query policy and invalidation
- `docs/browser-tests.md` — owned candidate browser workflows, fault boundaries, cleanup and before/after request/map observations
- `docs/self-check.md` — root dashboard, streamed manual runs, retained history, cron-system-job UI handling
- `docs/task-center.md` — global task panel, backend task polling, browser download tracking
- `docs/player-management.md` — global page, detail drawer tabs, online-players card
- `docs/file-management.md` — file browser, multi-file upload session flow, deep search, compression tasks
- `docs/archive-upload.md` — resumable archive upload dialog, pause/resume, SHA256 verification, SSE reader split
- `docs/cron-management.md` — visual expression builder, schema-driven job params, job status and execution outcomes including skipped runs
- `docs/dns-management.md` — diff display, conditional layout, manual update flow
- `docs/templates.md` — three-tab editor, variable validation, mode-conversion wizard
- `docs/console.md` — xterm.js + WebSocket lifecycle, reconnection, fit handling
- `docs/monaco-editor.md` — worker setup, compose schema, SNBT custom language
- `docs/version-updates.md` — manual changelog list, detection hook, snooze flow
- `docs/server-lifecycle.md` — bundled create/remove round-trips, OWNER-only filesystem↔DB sync dialog, `features/servers/lifecycleContracts.ts`
- `docs/server-map.md` — embedded Leaflet map, native Leaflet tile URLs, sparse manifest, browser image cache
- `docs/world-restore-page.md` — URL-driven dim/mode, selection state, preview/restore/rollback flows, history drawer
- `docs/chunk-prune-page.md` — server-level chunk prune map page, task-polled progress, dimension-filtered connected-shape overlay, apply guard
- `docs/ftb-claims-overlay.md` — always-on FTB claims overlay (when detected), polygon clustering, team/cluster side panel, popover-driven selection
- `docs/player-locations-overlay.md` — saved player positions, bulk streamed profile resolution, online-state filtering, translucent Leaflet markers

Add a `docs/<topic>.md` whenever a new system has design rationale or a non-trivial component graph that doesn't fit on one line in this file. Each doc is self-contained and reflects current state — no changelog, no "previously…" notes.

## Keeping this file in sync

When changing component contracts, hook signatures, store shapes, or any project-wide convention, update this file in the same commit:

- **Reflect current state, not history.** Rewrite the affected sentence as if it were the original — no "added X", "now does Y", "previously was Z" notes.
- **Stay terse.** Most changes don't need a new section. Edit the existing rule; replace the gotcha that changed; don't append paragraphs explaining a one-line change.
- **Drop what's no longer true.** Remove the corresponding text when code is removed or replaced.
- **Promote design depth to `docs/`.** If a change introduces design rationale or a multi-component flow too long for a single rule, write or extend `docs/<topic>.md`. Keep CLAUDE.md focused on day-to-day rules and gotchas.
- **One source of truth.** Don't duplicate facts between CLAUDE.md and `docs/`. If a rule belongs in CLAUDE.md (project-wide convention), the doc references it; if it's design depth, this file points to the doc.

## External documentation

Use the Context7 MCP tool: `/facebook/react`, `/shadcn-ui/ui`, `/mui/base-ui`, `/tailwindlabs/tailwindcss`, `/lucide-icons/lucide`, `/tanstack/query`, `/tanstack/table`, `/microsoft/monaco-editor`, `/remix-run/react-router`, `/pmndrs/zustand`. Resolve library id first, then fetch with a topic.
