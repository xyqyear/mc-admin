# Server Lifecycle (create / remove / sync)

Server creation and removal each issue exactly **one** request to the backend; the orchestrators on the other side handle compose write, DB row, restart schedule, log monitor, and DNS update atomically. The filesystem↔DB sync feature is owner-only and lives in a dedicated dialog.

## Hooks

- `useCreateServer` — posts `{ yaml_content | template_id + variable_values, restart_schedule? }` to `POST /servers/{id}` and returns `CreateServerResult`. Populate (archive extraction) stays a separate follow-up call because it runs as a background task.
- `useServerOperation({ action: "remove" })` — posts to `POST /servers/{id}/operations`; the `"remove"` action returns `RemoveServerResult` and the mutation surfaces the count of cancelled restart cronjobs in the success toast.
- `useSyncServers` — drives `SyncWithFilesystemDialog`. Calls `POST /servers/sync` with `{ dry_run: true }` for the preview, then `{ dry_run: false }` to apply. A 409 from the empty-filesystem guard enables a "强制应用" button that retries with `{ force: true }`.

## OWNER gating

The sync trigger in `Overview.tsx` is rendered only when `useCurrentUser().role === UserRole.OWNER`. The backend re-enforces the role guard regardless.

## Types

All shapes live in `src/types/lifecycle.ts` and mirror the backend Pydantic models in `app.servers.lifecycle.types`:

- `CreateServerRequest` / `CreateServerResult`
- `RemoveServerResult`
- `SyncRequest` / `SyncResult` (with per-row `Adoption`, `Deactivation` entries)
- `RestartScheduleRequest` (bundled into `CreateServerRequest`)

When the backend changes any of these, update this file in the same commit.

## Components

- `src/components/dialogs/SyncWithFilesystemDialog.tsx` — preview / apply UI, force-mode escalation, OWNER role-gated trigger.

## Cache invalidation

`useSyncServers.onSuccess` invalidates `queryKeys.servers()`, `queryKeys.dns.all`, and `queryKeys.cron.all` only when `result.applied` is true (the dry-run path leaves caches untouched).
