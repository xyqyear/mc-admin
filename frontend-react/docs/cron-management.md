# Cron Management

Page at `/cron` for managing scheduled jobs backed by the backend's APScheduler integration. The interesting work is in two pieces of UI: the visual cron expression builder and the schema-driven job-params form.

## Status model

A user-managed job moves through `active → paused → active` (pause / resume) or `active → cancelled` (cancel, terminal). The default filter on the list page hides cancelled rows so the table stays focused on operational jobs. Pause/resume/cancel are mutation-driven with `useConfirm` confirmations.

System jobs display a `System` badge. The UI hides pause/resume/cancel controls for them. The edit dialog keeps the job type locked and allows name, cron expression, seconds field, and params to be edited.

## Visual cron expression builder

`components/forms/CronExpressionBuilder.tsx` is the standout. Two modes:

- **Visual** — five `<Select>` dropdowns (minute, hour, day, month, day-of-week) plus an optional second field. Presets dropdown for common shapes (`every hour`, `every day at midnight`, `every Monday`, …).
- **Raw** — plain text input for users who already know the expression syntax.

Toggling between modes parses/serializes — you can paste a raw expression, switch to visual, and the dropdowns reflect the parsed values when the expression fits one of the recognized shapes.

`CronExpressionDisplay.tsx` renders an expression as human-readable Chinese (`每天 0:00`). Used in the table and detail modal.

## Schema-driven job params

Each registered job type on the backend exports a Pydantic params schema (`BackupJobParams`, `ServerRestartParams`, `SelfCheckJobParams`). The backend's `/cron/registered` returns these schemas as JSON Schema plus system/default metadata. `CreateCronJobDialog.tsx` is multi-step:

1. Job name + identifier (registered job-type dropdown)
2. **Schema form** — `<SchemaForm>` (rjsf) renders the params editor from the JSON Schema
3. **Cron expression** — built via `CronExpressionBuilder`
4. Submit → POST `/cron/`

This means *adding a new backend job type only requires backend changes* — the frontend renders the params form automatically.

## Detail modal

`CronJobDetailDialog.tsx` shows:

- Job metadata + cron expression
- Execution history table (last N runs, paginated)
- Per-execution log output (collapsible)
The execution table polls every few seconds while the modal is open so an in-flight run shows up live.

## Restart-schedule integration

Per-server restart schedules are configured separately (`ServerRestartScheduleCard.tsx` on the server overview), but they create entries in the same `CronJob` table. The schedule UI uses `restartSchedule.detail(serverId)` query; the backend's `RestartScheduler` picks restart minutes that don't collide with the server's backup minute, so the user doesn't have to think about conflict avoidance.

## Files

- `pages/CronManagement.tsx`
- `components/cron/CronJobFilters.tsx`, `CronJobStatusTag.tsx`, `CronExpressionDisplay.tsx`, `ExecutionStatusTag.tsx`, `NextRunTimeCell.tsx`
- `components/dialogs/cron/CreateCronJobDialog.tsx`, `CronJobDetailDialog.tsx`
- `components/forms/CronExpressionBuilder.tsx`, `CronFieldInput.tsx`, `SchemaForm.tsx`
- `hooks/api/cronApi.ts`, `hooks/queries/base/useCronQueries.ts`, `hooks/mutations/useCronMutations.ts`
