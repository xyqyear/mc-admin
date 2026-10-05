# Server Lifecycle (create / remove / sync)

Server creation, removal and filesystem↔DB sync submit feature-owned background tasks. Commands keep their mutations pending through confirmed task completion, including recoverable status-read failures. The filesystem↔DB sync feature is owner-only and lives in a dedicated dialog.

## Hooks

- `useCreateServer` — posts `{ yaml_content | template_id + variable_values, restart_schedule? }` to `POST /servers/{id}` and waits for the accepted task to return `CreateServerResult`. Populate (archive extraction) stays a separate follow-up call because it runs as a background task.
- `useServerOperation({ action: "remove" })` — posts to `POST /servers/{id}/operations`; the `"remove"` task returns `RemoveServerResult` and the mutation surfaces the count of cancelled restart cronjobs in the success toast.
- `useSyncServers` — drives `SyncWithFilesystemDialog`. Calls `POST /servers/sync` with `{ dry_run: true }` for the preview, then `{ dry_run: false }` to apply. A 409 from the empty-filesystem guard enables a "强制应用" button that retries with `{ force: true }`.

## OWNER gating

The sync trigger in `Overview.tsx` is rendered only when `useCurrentUser().role === UserRole.OWNER`. The backend re-enforces the role guard regardless.

## Types

`src/features/servers/contracts.ts` owns `CreateServerRequest` and its optional `RestartScheduleRequest`. API transport and creation commands use this single request shape.

`src/features/servers/lifecycleContracts.ts` owns `CreateServerResult`, `RemoveServerResult`, `SyncRequest` and `SyncResult`, including adoption/removal results, dry-run preview entries and per-entry errors. These contracts mirror the corresponding backend lifecycle DTOs.

## Components

`ServerNewScreen.tsx` uses the shared editor draft keyed by selected template ID.
Schema defaults and available ports initialize untouched forms; refetches preserve
authored values. Selecting another template initializes a new draft.

- `src/features/servers/ui/SyncWithFilesystemDialog.tsx` — preview / apply UI, force-mode escalation, OWNER role-gated trigger.

## Cache invalidation

`useSyncServers.onSuccess` invalidates `queryKeys.servers()`, `queryKeys.dns.all`, and `queryKeys.cron.all` only when `result.applied` is true (the dry-run path leaves caches untouched).
