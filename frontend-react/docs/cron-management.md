# Cron Management

Page at `/cron` for managing scheduled jobs backed by the backend's APScheduler integration. The interesting work is in two pieces of UI: the visual cron expression builder and the schema-driven job-params form.

## Status model

Saved configuration status is separate from runtime registration. `status=active` means “已启用”; `registration_status` is `registered`, `pending`, `failed`, `blocked` or `inactive`, with an optional readable `registration_error`. List, detail and server restart cards show both states. Failed or blocked saved jobs remain visible; an enabled, unregistered user task exposes “重新启用” through the existing resume endpoint. Failed registration does not display a future execution countdown. Older responses lacking these additive fields remain supported.

A user-managed job moves through `active → paused → active` (pause / resume) or `active → cancelled` (cancel; it can be resumed). The default filter on the list page hides cancelled rows so the table stays focused on operational jobs. Pause/resume/cancel are mutation-driven with `useConfirm` confirmations.

System jobs display a `System` badge. The UI hides pause/resume/cancel controls for them. The edit dialog keeps the job type locked and allows name, cron expression, seconds field, and params to be edited.

## Visual cron expression builder

`features/schedules/ui/CronExpressionBuilder.tsx` is the standout. Two modes:

- **Visual** — five `<Select>` dropdowns (minute, hour, day, month, day-of-week) plus an optional second field. Presets dropdown for common shapes (`every hour`, `every day at midnight`, `every Monday`, …).
- **Raw** — plain text input for users who already know the expression syntax.

Toggling between modes parses/serializes — you can paste a raw expression, switch to visual, and the dropdowns reflect the parsed values when the expression fits one of the recognized shapes.

The weekday field follows conventional crontab numbering: `0` and `7` are Sunday,
`1` is Monday, and `6` is Saturday. Numeric lists, ranges, and steps use that
ordering. The backend preserves the submitted expression and normalizes only the
internal APScheduler 3 trigger field, so the visual builder, raw mode, API, and
human-readable display share the same weekday meaning.

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

Execution results distinguish “成功” (`completed`), “跳过” (`skipped`), “失败”
(`failed`), and “取消” (`cancelled`). A skipped backup uses a warning badge, with
its reason in the execution logs; it does not indicate a newly created snapshot.

The execution table polls every few seconds while the modal is open so an in-flight run shows up live.

## Restart-schedule integration

Per-server restart schedules are configured separately (`ServerRestartScheduleCard.tsx` on the server overview), but they create entries in the same `CronJob` table. The schedule UI uses `restartSchedule.detail(serverId)` query; the backend's `RestartScheduler` picks restart minutes that don't collide with the server's backup minute, so the user doesn't have to think about conflict avoidance.

## Files

- `features/schedules/CronManagementScreen.tsx`
- `features/schedules/ui/CronJobFilters.tsx`, `CronJobStatusTag.tsx`, `CronExpressionDisplay.tsx`, `ExecutionStatusTag.tsx`, `NextRunTimeCell.tsx`
- `features/schedules/ui/dialogs/CreateCronJobDialog.tsx`, `CronJobDetailDialog.tsx`
- `features/schedules/ui/CronExpressionBuilder.tsx`, `CronFieldInput.tsx`, `shared/forms/SchemaForm.tsx`
- `features/schedules/api.ts`, `features/schedules/queries.ts`, `features/schedules/commands.ts`
