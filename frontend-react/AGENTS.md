# MC Admin Frontend

React 19, TypeScript, Vite 8 and Node 24. `@` resolves to `src/`.
Inherit [repository rules](../AGENTS.md); use the [frontend index](docs/README.md)
for feature and implementation details.

## Commands and validation

Run from `frontend-react/`:

```bash
pnpm install --frozen-lockfile
pnpm dev
pnpm lint
pnpm typecheck
pnpm build:bundle
pnpm exec vitest run src/features/backups/preview.integration.test.tsx
pnpm check:boundaries
pnpm generate:contracts
pnpm check:contracts
```

The test file is an example: select the actual related files and add `-t` when
only particular cases are affected. `pnpm build` combines type checking and
bundling. Contract generation/checking requires backend uv dependencies.
In Windows checkouts, run frontend commands with Windows pnpm. Contract
generation/checking uses the WSL backend wrapper. Browser tests use the Windows
Playwright bridge while the WSL Go runner owns deployment and cleanup; see
[browser verification](docs/browser-tests.md#windows-browser-with-a-wsl-owned-deployment).

`pnpm test` includes the complete architecture suite; it cannot target local
validation. `pnpm test`, `pnpm test:architecture` and unfiltered
`pnpm test:browser` are CI commands. For local browser work use the owned Go
wrapper with explicit related spec/title filters. Keep lint, TypeScript,
boundary, contract-freshness and build checks appropriate to the change; see
[testing](docs/testing.md) and [browser verification](docs/browser-tests.md).

## Data and feature boundaries

- Features own contracts, transport, query policy, commands/controllers and UI. `app/` composes them; route adapters in `pages/` only read parameters and mount screens. `shared/` cannot import features or application code.
- Use public feature entries declared in `scripts/import-boundaries.mjs`. Do not import cross-feature private controllers or create a universal implementation barrel. Share query-option factories instead of copying polling/retry policy.
- Backend state, including tasks and player profiles, belongs to TanStack Query. Zustand/local state owns browser-only state. Do not add a second mirror of server data.
- Use `queryKeys.*` or the tasks feature's `taskQueryKeys`; reads and invalidations share the same factory path. Prefer stable-prefix `invalidateQueries`; reserve `refetchQueries` for explicit user refresh.
- Feature commands wake operation discovery at acceptance/settlement. Application-level observation owns independent-task terminal business refresh, including failures and off-page completion. Progress dialogs must not become the owner of that refresh.
- Read errors, 202 acceptance and 100% progress do not unlock work that requires confirmed completion. Detaching an observer does not cancel a backend task.
- Configuration writes use the accepted `expected_version`. A conflict preserves authored drafts and requires comparison plus explicit baseline acceptance; never silently adopt a 409's `current_version`.
- API consumers use normalized `ApiError`, not Axios response internals. A refresh announcing success must inspect its result or use `refetch({ throwOnError: true })`.
- Generated static DTOs do not replace runtime validation of events and task results. Generate complete identity contracts from isolated backend OpenAPI; keep other feature contracts explicit.

## Generated UI

`src/shared/ui/**`, `src/shared/hooks/use-mobile.ts` and
`src/shared/lib/utils.ts` are shadcn-generated. Create, update, migrate or
regenerate them only through the official project-locked shadcn CLI. Do not
manually edit, delete, move, merge or reformat them, including comments/imports.
Exclude them from repository-wide refactors. Compose customizations in outer
`shared/components/` or feature UI.

```bash
pnpm exec shadcn info --json
pnpm exec shadcn add <component> --dry-run
pnpm exec shadcn add <component> --diff
pnpm exec shadcn add <component> --overwrite
pnpm exec shadcn migrate cn
```

Inspect resolved paths and preview changes before updating. Keep `@/*` mappings
consistent in both TypeScript configurations. Details belong to
[UI conventions](docs/ui-conventions.md).

## UI and transport gotchas

- Use Base UI `render`/`useRender`, not Radix `asChild`. No Ant Design imports.
- Import declarative router APIs from `react-router`.
- `TooltipProvider` is mounted once in `src/main.tsx`; do not duplicate it.
- Supply `Select.itemToStringLabel` when the displayed label differs from the value.
- Use Sonner for toasts and `useConfirm` for plain confirmations. It has no `content` field; rich comparisons use a controlled `Dialog`.
- Session guards use `useCurrentUser()`. Network/server errors allow retry on the requested route; browser mutations retain cookie/CSRF protection.
- Use `shared/http/eventStream.ts` for authenticated finite SSE. EOF before an explicit terminal event is a failure. Snapshot recovery observes durable tasks.
- File/world flows compose public `features/backups` contracts, commands and UI. Preserve captured selection, generation and protection guards across asynchronous reads.

## Read for the task

| Change | Read before implementation |
| --- | --- |
| Queries, contracts or ownership | [Data architecture](docs/data-architecture.md) |
| Resource samples, status or maintenance observation | [Shared monitoring](docs/monitoring.md) |
| Task completion or cache/map refresh | [Operation refresh](docs/operation-refresh.md), [task center](docs/task-center.md) |
| Compose/template drafts or version conflicts | [Configuration editors](docs/configuration.md) |
| Files, bulk selection or directory export | [File management](docs/file-management.md), [file operations](docs/file-operations.md) |
| Snapshot creation, preview, restore or history | [Common snapshot UI](docs/snapshot-recovery.md), [world page](docs/world-restore-page.md) |
| Generated components or editor workers | [UI conventions](docs/ui-conventions.md), [Monaco](docs/monaco-editor.md) |

Update feature docs for hook, store and component details. Update this file only
when commands, constraints or reading routes change; follow
[documentation ownership](../docs/documentation.md).
