# MC Admin Frontend

React 19 + TypeScript + Vite 8 on Node 24. Path alias: `@` → `src/`.

## Commands

```bash
pnpm install
pnpm dev        # port 3000
pnpm build      # tsc + vite build
pnpm lint
```

Backend URL is configured in `vite.config.ts` (default `http://localhost:5678`).

Production builds split hashed output into `assets/vendor`, `assets/workers`, `assets/fonts`, `assets/styles`, `assets/media`, and `assets/app`; the root Dockerfile copies those directories as separate runtime layers.

React Router 7 is used in declarative mode; import router APIs from `react-router`.

## Three-layer data architecture

Every server-state operation goes through one of three layers. **Don't mix concerns across layers.**

1. **`hooks/api/*Api.ts`** — raw Axios calls and types. No caching, no React.
2. **`hooks/queries/base/use*Queries.ts`** — resource-focused `useQuery` hooks with stale-time / polling strategy.
3. **`hooks/queries/page/use*Queries.ts`** — composed page-level queries that combine layer-2 hooks.

Mutations live in `hooks/mutations/use*Mutations.ts` (writes + cache invalidation on success).

When to bypass the query layer: one-off flow-local requests that should not be globally cached (e.g. modal-only preview/check calls), or stream/progress operations.

## Query keys & invalidation (mandatory)

- **Always** use the `queryKeys.*` factories from `utils/api.ts`. No inline string literals.
- Query hooks and invalidation must reference the same factory path.
- Prefer prefix invalidation via stable parents (`queryKeys.snapshots.all`) for broad fanout.
- Single-resource update → invalidate that detail key. List/aggregate change → invalidate related list and summary keys. Cross-domain side effects → invalidate dependent domains (DNS, restart schedule, players, snapshot usage).
- Prefer `invalidateQueries`; use `refetchQueries` only for explicit user-triggered "refresh now" actions.

**Task-driven flows** (rebuild / populate / template conversion): submit the mutation, invalidate `taskQueryKeys`, poll the task detail, **then** invalidate affected business keys in the progress modal's completion handler. Don't immediately invalidate business queries on submission.

**Polling defaults by volatility**: status/runtime/online players → seconds-level. Disk usage / task lists → medium. Schemas / static config → long stale time + manual invalidation on mutation.

## UI stack — shadcn on base-ui (not Radix)

shadcn here is built on `@base-ui/react` primitives, not Radix. Project-specific gotchas:

- **No `asChild`.** Use base-ui's `useRender` with the `render` prop, or compose via controlled state.
- **`TooltipProvider` is mounted once in `src/main.tsx`.** Do not wrap individual components in another one.
- **`Select`** (`@/components/ui/select`) needs `itemToStringLabel={(v) => "..."}` whenever the trigger label differs from the option value (e.g. value `"10"` rendered as `"10条/页"`).
- **Toasts**: `import { toast } from 'sonner'`.
- **Confirmation dialogs**: `useConfirm` (in `hooks/useConfirm.tsx`). Accepts `title`, `description`, `confirmText`, `cancelText`, `variant`, `onConfirm` — **no `content` field**. For rich confirmations (diff previews etc.), use a state-driven `<Dialog>` instead.
- Legacy Ant Design has been removed — no `antd`, `@ant-design/icons`, or `@rjsf/antd`.

## Auth

Browser auth is an HttpOnly JWT cookie plus a readable CSRF cookie. Route guards use `useCurrentUser()` (`GET /api/user/me`) as the session source of truth. Axios is configured in `utils/api.ts` with credentials and XSRF cookie/header names; fetch-based SSE adds the CSRF header manually.

## Routes

The protected root route `/` is the system self-check dashboard. The former feature-card home page is not part of the app.

## Stores (Zustand, persisted to localStorage)

- `useSidebarStore` — sidebar collapse state, `openKeys` for nested sections
- `useLoginPreferenceStore` — user's preferred auth method
- `useDownloadStore` — download tasks
- `useBackgroundTaskStore` — background task state (mirrors backend)
- `useTaskCenterStore` — task center panel open + tab
- `useWorldRestoreSelectionStore` — per-server world-restore selection (**not** persisted; selection is transient)

## SSE consumer

`utils/eventStream.ts` is the canonical authenticated SSE reader: fetch + `AbortController` + `\n\n` block parser, same-origin cookies, and CSRF header injection for unsafe methods. `hooks/useEventStream.ts` wraps it for state-driven component use (`useEventStream<TEvent>({ enabled, url, method, body, onEvent, onClose, onError, onResponse })`). Body fingerprinting uses `JSON.stringify`, so pass stable bodies when stream restarts matter.

## Monaco editor

- YAML worker at `yaml.worker.js` (registered in `main.tsx`).
- `snbtLanguage.ts` registers a custom Monaco language for Minecraft NBT files.
- Docker Compose schema with docker-minecraft-server hints lives at `public/static/mc-server-compose-schema.json`.

## Design background

Long-form, current-state design docs live under `frontend-react/docs/`:

- `docs/data-architecture.md` — three-layer hooks pattern, query keys, invalidation rules, polling cadences
- `docs/self-check.md` — root dashboard, streamed manual runs, retained history, cron-system-job UI handling
- `docs/task-center.md` — global task panel, backend task polling, browser download tracking
- `docs/player-management.md` — global page, detail drawer tabs, online-players card
- `docs/file-management.md` — file browser, multi-file upload session flow, deep search, compression tasks
- `docs/archive-upload.md` — resumable archive upload dialog, pause/resume, SHA256 verification, SSE reader split
- `docs/cron-management.md` — visual expression builder, schema-driven job params, status flow
- `docs/dns-management.md` — diff display, conditional layout, manual update flow
- `docs/templates.md` — three-tab editor, variable validation, mode-conversion wizard
- `docs/console.md` — xterm.js + WebSocket lifecycle, reconnection, fit handling
- `docs/monaco-editor.md` — worker setup, compose schema, SNBT custom language
- `docs/version-updates.md` — manual changelog list, detection hook, snooze flow
- `docs/server-lifecycle.md` — bundled create/remove round-trips, OWNER-only filesystem↔DB sync dialog, `types/lifecycle.ts`
- `docs/server-map.md` — embedded Leaflet map, native Leaflet tile URLs, sparse manifest, browser image cache
- `docs/world-restore-page.md` — URL-driven dim/mode, selection state, preview/restore/rollback flows, history drawer
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
