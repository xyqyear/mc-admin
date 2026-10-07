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
pnpm exec vitest run src/features/backups/preview.integration.test.tsx # related-file example
pnpm check:boundaries # executable import rules
pnpm generate:contracts # isolated backend OpenAPI -> selected complete DTOs
pnpm check:contracts # check generated DTO freshness (requires backend uv deps)
```

Backend URL is configured in `vite.config.ts` (default `http://localhost:5678`).

Local tests must select cases directly related to the change and cases affected through shared dependencies. Use explicit test files with `pnpm exec vitest run <related-file>`; add `-t '<related test name>'` when only part of a file is relevant. Do not run entire project, component or browser test suites locally, including reconstructing a full run through directory batches or subagents. Related architecture cases also require explicit test-name selection.

`pnpm test` always runs the complete architecture suite before Vitest, so it cannot be used for local targeting. `pnpm test`, `pnpm test:architecture` and unfiltered `pnpm test:browser` are full-suite CI entry points. Local browser checks use the owned Go wrapper with an explicit related spec file and title filter; see `docs/browser-tests.md`. The local test limit does not replace existing lint, TypeScript diagnostics, import-boundary, generated-contract or build guidance. Complete validation depends on all required GitHub Actions gates for the latest commit SHA under `../AGENTS.md`.

Production builds split hashed output into `assets/vendor`, `assets/workers`, `assets/fonts`, `assets/styles`, `assets/media`, and `assets/app`; the root Dockerfile copies those directories as separate runtime layers.

The Static Checks push workflow runs lint, typecheck, operation-flow tests and bundling as separate steps. Vitest uploads JSON results with individual test durations. Docker uses `pnpm build:bundle` to produce assets; TypeScript diagnostics are reported by the independent static workflow.

Browser qualification freezes the complete Playwright inventory and compatible audited timing history, then plans bounded 300-second shards including owned world setup and cleanup. Every shard has an independent world and one serial worker. `browser/shardReporter.ts` identifies cases by project, file relative to Playwright `rootDir`, and full title; unmarked files stay atomic and explicit `shard_group` annotations preserve shared groups. Current isolated cases declare `shard_isolation=independent`. Exact-once coverage, outcomes, candidate identity and cleanup must pass before history publication. See `docs/browser-tests.md`.

Query integration tests wait for observer-driven cache or UI effects with `waitFor`; awaiting a query refetch alone does not establish that React effects have run. Preview cancellation tests observe a running task after cancellation acceptance before its terminal state. Profile-cache tests assert the initial cached name and cache update before rerendering.

React Router 7 is used in declarative mode; import router APIs from `react-router`.

## Data and feature boundaries

Features own their contracts, API calls, query policy, commands/controllers and UI. Modules are `servers`, `configuration`, `files`, `world`, `archives`, `backups`, `players`, `schedules`, `templates`, `tasks`, `users`, `settings`, `health`, `dns` and `system`. A feature's `contracts.ts` owns DTOs; `api.ts` contains transport only; `queries.ts` owns keys, retries, polling and reusable TanStack `queryOptions`; `commands.ts` owns writes and immediate invalidation. Feature controllers coordinate user workflows, while screens and UI present them.

Read and write modules expose concrete hooks, including 20 named query hooks and 34 named mutation hooks at the resource interfaces. Hooks capture their own QueryClient and required server/router context; query options retain the domain policy and caller override order. Download commands remain ordinary hooks backed by the download manager. See `docs/data-architecture.md`.

`app/` owns the authenticated shell, aggregate overview, operation observation and version notification. `shared/` owns HTTP/SSE transport, reusable UI, editors, generic hooks and finite request ownership. It cannot import feature or application code. Server route adapters under `pages/` only read route parameters and mount feature screens.

`app/version/config.ts` owns release notes and SemVer precedence, including prerelease identifiers and ignored build metadata. The notification hook, newest-first dialog and current-version selection share that comparator; release entries are appended to the list.

`scripts/import-boundaries.mjs` declares executable public entries: contracts/API/queries/commands, operation resource registries, reusable `ui/`, and a small explicit set of read helpers. Screens are for application/route composition only. Cross-feature private imports, reverse dependencies and deleted compatibility-layer imports fail `pnpm check:boundaries` (also part of lint). No large universal barrel loads all feature implementations.

`app/overview/useOverviewData.ts` and `features/servers/useServerDetailData.ts` share resource query-option factories; consumers do not copy polling/retry policy. Player profile streams populate individual Query entries, and map consumers observe those entries without a second profile store. Restore/prune player tabs expose non-blocking finite-stream failures and explicit profile retry while keeping cached profiles and locations usable.

`features/players/identity.ts` is a public pure helper shared by profile queries, world controllers, player lists and map layers. It normalizes UUID syntax to dashless lowercase 32-hex strings; backend online-mode eligibility remains separate.

HTTP consumers use the normalized `ApiError` (`Error.message`, `status`, `code`, original `detail`) from `shared/http/api.ts`; Axios response internals stay in the interceptor. `shouldRetryQuery` applies the shared status policy. A refresh handler that reports success/failure must use `refetch({ throwOnError: true })` or explicitly inspect its result.

`features/configuration/` owns the existing-server Compose/template-parameter/conversion workflow: typed API contracts, query options, version-required commands, baseline/draft/remote edit sessions, conflict comparisons, and UI. `pages/server/servers/ServerCompose.tsx` is its route adapter. Global template CRUD and default variables belong to `features/templates/`.

`shared/utils/formatUtils.ts` owns byte-size and duration display helpers and filesystem-safe browser-local timestamps; callers retain their zero-value, precision, unit-range and day/hour policies. Archive commands transmit browser-local `client_timestamp`; archive and directory-export names contain the server and timestamp without random identifiers. Server creation and restart request DTOs belong to `features/servers/contracts.ts`; lifecycle results and filesystem-sync DTOs belong to `lifecycleContracts.ts`.

`shared/hooks/useEditorDraft.ts` owns local text/JSON drafts for other resource editors. Remote updates replace pristine content, preserve authored changes, and never establish an empty draft from a failed initial read. Explicit reload resets the draft after a successful read. See `docs/data-architecture.md` for editor and integration-test boundaries.

Server creation keys its template draft by template ID; schema/port refetches preserve authored values. The restart card creates managed server schedules through the server endpoint and opens their exact cron details with `/cron?job=<id>`. Task observers can read journal-retained outcomes after list dismissal or restart; missing/expired details end observation with an explicit message. Archive selection uses file paths as stable row identities.

When to bypass the query layer: one-off flow-local requests that should not be globally cached (e.g. modal-only preview/check calls), or stream/progress operations.

`features/archives/uploads/` owns archive pause/resume and verification. `features/files/useMultiFileUpload.ts` owns ordinary-file conflict checking, overwrite policy and sequential batches. Dialogs render flow state; raw API functions each issue one request.

## Query keys & invalidation (mandatory)

- Use `queryKeys.*` from `shared/http/api.ts`, or the task feature’s `taskQueryKeys` from `features/tasks/queries.ts`. No inline string literals.
- Query hooks and invalidation must reference the same factory path.
- Prefer prefix invalidation via stable parents (`queryKeys.snapshots.all`) for broad fanout.
- Single-resource update → invalidate that detail key. List/aggregate change → invalidate related list and summary keys. Cross-domain side effects → invalidate dependent domains (DNS, restart schedule, players, snapshot usage).
- Prefer `invalidateQueries`; use `refetchQueries` only for explicit user-triggered "refresh now" actions.

**Operation completion**: commands invalidate task and operation discovery keys on submission. `app/operations/OperationObserver.tsx`, mounted in the authenticated layout, polls the operation journal and applies configuration/files/world/servers/health/dns `operationResources.ts` registries once per terminal operation, including failed/partial outcomes. It survives page navigation, resynchronizes on reconnect/focus, and clears session state on logout/cache clear. `RebuildProgressDialog`, `PopulateProgressDialog`, compression/ownership presentation and restore/prune views never own terminal business invalidation. Synchronous file commands and browser-owned partial uploads still invalidate their immediate write results.

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

`features/files/` contains contracts, API, queries, commands, language/search rules, upload controller and UI. `useFileNavigation` owns path/search URL state; `useFileEditor` owns the loaded baseline/draft; `useFileBrowser` coordinates CRUD and task presentation. `FileBatchActions` binds explicit real selections to shared snapshot, recovery, packing, deletion and directory export commands. `useDirectoryDownload` captures local directory authorization; its streaming executor reports aggregate browser-owned tasks independently of the current page. `pages/server/servers/ServerFiles.tsx` delegates to `FileBrowserScreen`. See `docs/file-operations.md` for selection identities, path layouts and browser capability feedback.

`features/world/` owns layout/dimensions/map/claims/player-layer contracts, API and queries. `useWorldMapController` groups its state and actions under `server`, `map`, `claims` and `players`. `WorldDimensionSelect`, `WorldMapInitialization` and `WorldPlayerLocationList` bind concrete shared presentation inputs. Restore and prune controllers own their respective selection and preview/apply lifecycles; route files delegate to feature screens. Claims/player implementations do not depend on the restore feature.

`WorldRestoreSidebar` keeps the backup panel mounted at a stable position while map status, layout and optional layer tabs load. Snapshot and restoration-history drawers retain their local state across these responses; map rendering readiness does not gate access to recovery history.

`features/backups/useSnapshotOperation` owns common file/world recovery task observation and immutable accepted scopes. Acceptance and read failures keep the original progress UI blocked; navigation only detaches observation. World UI composes the public backup contracts, commands and history/progress components. `features/backups/useSnapshotPreview` observes common preview tasks, heartbeats ready sessions and submits cleanup on close/unmount; expired sessions require regeneration. Independent prune/populate/compression tasks continue after views close. Prune state includes feature-owned preview metadata/projections even after task-center dismissal; only a matching ready preview can apply. Historical restores with `binding_issue` remain readable but cannot roll back into another server generation.

`features/backups` owns snapshot creation and editing notes up to 500 Unicode characters. Lists and file/world recovery selectors display the same notes; a completed snapshot whose note fails to save offers only a metadata retry. `features/players/ui/OnlinePlayersCard` opens the shared player detail dialog by UUID in place and keeps its owner mounted when the online list disappears.

## Server Map Reuse

`features/world/map/ServerMap.tsx` is the shared Leaflet surface. Map pages compose optional `ServerMapOverlay` layers; FTB claims and player locations are imported from `features/world/layers/*`, and world/dimension relpath helpers live in `features/world/map/worldDimensions.ts`.

`mapConfig.blockToLatLng` preserves `[-Z, X]`; `coords.ts` uses floor division for negative block/chunk/region cells. The common controller applies a pending pan only on the matching dimension's overlay render, before layer attachment, then clears it in a microtask. Hidden player markers retain the initialized overlay callback. See `docs/server-map.md` and `docs/player-locations-overlay.md`.

## SSE consumer

`shared/http/eventStream.ts` is the canonical authenticated SSE reader: fetch + `AbortController` + `\n\n` block parser, same-origin cookies, and CSRF header injection for unsafe methods. Snapshot recovery instead observes independent tasks and clones the confirmed target before submission. HTTP failures retain structured `ApiError.detail` and status. EOF before an explicit terminal event is a connection failure.

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
- **Promote design depth to `docs/`.** If a change introduces design rationale or a multi-component flow too long for a single rule, write or extend `docs/<topic>.md`. Keep AGENTS.md focused on day-to-day rules and gotchas.
- **One source of truth.** Don't duplicate facts between AGENTS.md and `docs/`. If a rule belongs in AGENTS.md (project-wide convention), the doc references it; if it's design depth, this file points to the doc.

## External documentation

Use the Context7 MCP tool: `/facebook/react`, `/shadcn-ui/ui`, `/mui/base-ui`, `/tailwindlabs/tailwindcss`, `/lucide-icons/lucide`, `/tanstack/query`, `/tanstack/table`, `/microsoft/monaco-editor`, `/remix-run/react-router`, `/pmndrs/zustand`. Resolve library id first, then fetch with a topic.

`features/tasks/commands.ts` owns `waitForTaskResult`: mutations remain pending through actual task completion, failed status reads reconnect without unblocking, and observation abort does not cancel backend work. Map initialization and self-check keep their live stage/findings UI; server controls show the maintenance reason and task entry. See `../backend/docs/non-snapshot-operations.md`.

`features/backups` owns manual snapshot scope/task contracts, file recovery observation and paginated history/rollback UI. File controls compose these public entries. Creation mutations stay pending through the actual task result; restoration polls task status and resumes active restores through the database-only discovery endpoint on entry and re-enabling. One feature-owned polling observer per QueryClient/server scope serves all file, world and history consumers: empty results poll every 30 seconds, active/unknown/failed results every two seconds. Fresh entry checks and errors retain admission guards; history lists refresh on entry, actions and invalidation instead of periodic repository reads. Failed reads retain busy state and closing guards. The shared restore progress card, creation dialog and history live in `features/backups/ui`; file and world pages compose them. `FileSnapshotRecovery` owns one recovery session per file page, independent of table rows and pagination. Targets use lightweight ignore-rule feedback; writes still enforce the authoritative backend policy.

`features/world/map/revision.ts` retains the newest relevant terminal operation timestamp/ID per server and globally in the query cache. `OperationObserver` updates it for changed world inputs; the map adds it to tile URLs alongside MCA mtime, so MCC-only and same-mtime replacements refresh browser images. Read-only previews and backups do not change the token.
