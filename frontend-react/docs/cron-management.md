# Cron Management

Page at `/cron` for managing scheduled jobs backed by the backend's APScheduler integration. The interesting work is in two pieces of UI: the visual cron expression builder and the schema-driven job-params form.

## Status model

Saved configuration status is separate from runtime registration. `status=active` means “已启用”; `registration_status` is `registered`, `pending`, `failed` or `inactive`, with an optional readable `registration_error`. List, detail and server restart cards show both states. Failed saved jobs remain visible; an enabled, unregistered user task exposes “重新启用” through the existing resume endpoint. Failed registration does not display a future execution countdown. Responses lacking these additive fields remain supported.

A user-managed job moves through `active → paused → active` (pause / resume) or `active → cancelled` (cancel; it can be resumed). The default filter on the list page hides cancelled rows so the table stays focused on operational jobs. Pause/resume/cancel are mutation-driven with `useConfirm` confirmations.

System jobs display a `System` badge. The UI hides pause/resume/cancel controls for them. The edit dialog keeps the job type locked and allows name, cron expression, seconds field, and params to be edited.

## Visual cron expression builder

`features/schedules/ui/CronExpressionBuilder.tsx` is the standout. Two modes:

- **Visual** — five `<Select>` dropdowns (minute, hour, day, month, day-of-week) plus an optional second field. Presets dropdown for common shapes (`every hour`, `every day at midnight`, `every Monday`, …).
- **Raw** — plain text input for users who already know the expression syntax.

Toggling between modes parses/serializes — you can paste a raw expression, switch to visual, and the dropdowns reflect the parsed values when the expression fits one of the recognized shapes.

Preset buttons only change the expression; submitting the enclosing form requires its explicit submit action.

Specific values, range endpoints and interval starts accept a legal `0`; an
explicitly cleared custom field stays empty. Mode changes retain each mode's
draft when no replacement value is supplied. Creation and update requests use
the accepted parent expression and optional second field.

`CronFieldInput` keeps a typed draft for each of its specific, range, interval,
list and custom modes. External values replace the active mode's draft while
inactive mode values remain available when switching back. Recognition and
clamping remain local to the field; the expression builder owns the five cron
fields and optional seconds value.

External field and expression values synchronize the rendered controls without
emitting an authored change. Incomplete or out-of-range numeric edits keep the
last accepted draft; a later valid edit can replace it. Switching between raw
and visual expression modes preserves the five fields and optional seconds.

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

`SchemaForm` exposes only schema, data and change handling. It uses the shared
RJSF theme, AJV validation on change and field-local errors, and suppresses the
renderer’s default submit button. Switching job type remounts the parameter
form and clears the previous job's authored values. Defaults and input types
come from the selected schema. Parameter-form submissions validate within that
form; only submission of the dialog's outer form creates or updates a job.

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

The server overview's `ServerRestartScheduleCard.tsx` creates a managed schedule through `POST /servers/{id}/restart-schedule` after confirmation. The target is the exact server name in the job parameters; the display name is independent. With multiple retained managed plans, the backend selects the earliest non-cancelled plan, or the latest cancelled plan if none remain enabled. Other plans remain independent and retain their state and history. The backend assigns a daily restart time when no custom expression is supplied. A failed read is displayed separately from a missing schedule and disables creation. The card refreshes after creation; its manage action opens `/cron?job=<id>` with that exact job's detail dialog visible. Detail shows the managed-purpose classification and target parameters alongside registration errors. The schedule UI uses `restartSchedule.detail(serverId)`; independent cron creation remains separate from managed server plans.

## Files

- `features/schedules/CronManagementScreen.tsx`
- `features/schedules/ui/CronJobFilters.tsx`, `CronJobStatusTag.tsx`, `CronExpressionDisplay.tsx`, `ExecutionStatusTag.tsx`, `NextRunTimeCell.tsx`
- `features/schedules/ui/dialogs/CreateCronJobDialog.tsx`, `CronJobDetailDialog.tsx`
- `features/schedules/ui/CronExpressionBuilder.tsx`, `CronFieldInput.tsx`, `shared/forms/SchemaForm.tsx`
- `features/schedules/api.ts`, `features/schedules/queries.ts`, `features/schedules/commands.ts`
