# Cron (`app.cron`)

Scheduled background jobs. Built on APScheduler with database persistence so
jobs survive restarts. The built-in job types are backup, server restart, and
automatic self-check.

## Runtime resources

- **`cron_manager`** — APScheduler facade. Creates, updates, pauses, resumes,
  cancels, persists, recovers, and executes jobs.
- **`cron_registry`** — registry of job functions, parameter schemas, and
  registration metadata. All jobs use the explicit
  `cron_registry.register_func(...)` registration path.
- **`restart_scheduler`** — picks restart minutes that avoid active backup
  and paused backup minutes and restart slots. Used by per-server restart schedule UI.

## Server-managed restart plans

The server schedule API identifies a managed restart plan by
`managed_purpose="restart"`, type `restart_server`, and the exact logical server
name in `params.server_id`. Display names never determine the target. When several
retained plans match, the API selects the lowest row ID among non-cancelled plans;
if all are cancelled, it selects the highest row ID. Other plans retain their
configuration, desired state and history. Recreating a plan through the server
endpoint updates and explicitly resumes the selected plan. The configuration lock
serializes selection and creation so concurrent requests cannot add duplicates.

Jobs created through the generic cron API have no managed purpose, even if their
name is exactly `restart-<server_id>`. Multiple independent restart jobs remain
supported. Managed plans can change their display name and target parameter, but
retain their restart type. Automatic time selection excludes only the selected
managed job; other plans continue to reserve their time slots.

Automatic scheduling examines five-minute slots from the configured start time,
rounded down to the nearest five minutes, and crosses hour/day boundaries. Active
and paused backup minutes and restart slots remain reserved. If all slots are
occupied, the original unrounded start time is retained. Generated expressions are
daily (`minute hour * * *`); user-provided custom expressions retain all five fields
unchanged in configuration and API responses.

Each scheduled execution resolves the current server by its configured logical
name. A different same-name instance can be the target of a later execution; an
execution already waiting for resources retains its captured `ServerRef` and
rejects a replacement before calling Docker. Missing or stopped targets record
`skipped`. Historical timestamps do not prevent valid plans from registering.
Paused and cancelled plans do not resume automatically.

Server deletion cancels active managed and independent restart jobs whose target
parameter exactly matches the public server name. Paused jobs and execution
history remain retained. Malformed parameters do not break unrelated deletion.
Resuming a retained plan is an explicit administrator action.

`GET /cron/` and `GET /cron/{cronjob_id}` include nullable `managed_purpose`;
their target is the authored parameter. Server schedule URLs and request shapes
remain stable and expose the registration state described below.

### Schema and historical plans

Revision `2026100700` follows `2026100600` and removes the permanent instance
binding columns, index and check constraint. It preserves managed-purpose
classification, all other job fields, IDs, status, execution counts and history.
SQLite enters a real transaction before batch DDL, so failed table replacement
rolls back and can be retried. Published historical revisions remain in the graph.

Downgrade to the binding schema is refused while any managed plan exists because
the logical-name configuration cannot establish a historical instance binding.
Databases containing only independent jobs can restore the old nullable columns
and constraints without changing those jobs. Rollback uses a schema-compatible
application build or a separately reviewed database recovery.

Scheduled restart holds the same maintenance mutex as API startup and rebuild.
A busy or stopped server records `skipped`, with a reason and completion time;
it does not call Docker restart or report a completed restart.

## Desired state and scheduler registration

`CronJob.status` is durable configuration intent: `active`, `paused`, or
`cancelled`. It does not assert that APScheduler accepted a trigger. Cron list,
cron detail, and the per-server restart schedule response also expose:

| Field | Meaning |
| --- | --- |
| `registration_status=registered` | The initialized scheduler has the current definition. |
| `pending` | Active configuration awaits scheduler startup or registration. |
| `failed` | The active definition is invalid, its type is unavailable, or scheduler registration failed. |
| `inactive` | Desired state is paused or cancelled. |
| `registration_error` | Nullable, safe diagnostic; no adapter exception details. |

Unknown job types and invalid persisted parameters remain in list/detail responses
with their original database configuration intact. Valid JSON objects remain
readable even when their schema is unavailable; malformed JSON projects empty
parameters with a diagnostic. Users can inspect history and cancel these rows.

Saving configuration and changing the live trigger are serialized. Registration
failure retains the saved configuration and is visible through the fields above.
The existing resume endpoint retries an active but unregistered/failed job; resume
of an already registered active job still returns 409. Validation precedes changing
a paused job to active. Next-run-time never reports a stale definition's trigger.

Every trigger carries a fingerprint of its persisted type, parameters and schedule.
At dispatch, the manager rechecks desired state and that
fingerprint before calling a command. A queued old trigger after pause, cancellation
or edit records a skipped attempt instead of executing stale configuration.
Already running commands retain ownership and finish through their normal outcome
path; changing a schedule does not cancel an active backup or restart.

Startup opens APScheduler paused, reconciles persisted active definitions and system
jobs, then resumes it. Invalid individual user jobs remain visible without stopping
unrelated jobs. A fatal startup consistency failure shuts down the paused scheduler.
Runtime operation/history recovery runs before this producer can start.

## Registration

Each job type is registered with:

- `func` — async function taking an `ExecutionContext`
- `schema_cls` — Pydantic parameter schema
- `identifier` — stable job type stored in `CronJob.identifier`
- `description` — frontend label text
- `is_system` — whether startup must maintain a protected system job
- `default_cron`, `default_second`, `default_params`, `default_name` — startup
  defaults for system jobs

System defaults live in code registration metadata, not dynamic config. Dynamic
config may tune the behavior the job performs, but it does not rewrite an
already persisted schedule.

## Cron Expression Contract

MC Admin accepts, returns, and persists five-field expressions using conventional
crontab weekday numbering in the fifth field:

- `0` and `7` are Sunday
- `1` is Monday through `6` as Saturday
- `sun` through `sat` are case-insensitive calendar-day names
- lists, ascending ranges, and positive steps are evaluated in that convention

The original expression remains unchanged in the database and API. When a trigger
is constructed, `weekdays.py` expands the fifth field to a calendar-day set and
translates that set to APScheduler 3's internal Monday-zero numbering. The shared
trigger builder applies this to creation, update, resume, startup recovery, and
system jobs.

Deployments containing numeric expressions deliberately written in APScheduler's
Monday-zero convention must review those schedules before rollout. Named weekday
expressions are unaffected because their calendar-day meaning is unambiguous.

## System Jobs

System jobs use deterministic IDs: `system:{identifier}`. During
`cron_manager.initialize()`, active database jobs are recovered first, then code
defined system registrations are created or repaired.

Startup behavior for each system registration:

- create the row when `system:{identifier}` is missing
- mark the row `is_system=true` if it exists without the flag
- reactivate the row if it was paused or cancelled
- submit it to APScheduler if no scheduler job exists
- fail startup if the persisted row's identifier differs from the registration

User-facing restrictions:

- system job type cannot be changed
- system jobs cannot be paused or cancelled
- name, cron expression, seconds field, and params remain editable

The automatic self-check job is registered as:

- identifier: `self_check`
- cron job ID: `system:self_check`
- default cron: `0 * * * *`
- default second: `0`

## Execution Model

Each registered job function is `async (context: ExecutionContext) -> None`.
`ExecutionContext` carries the cron job ID, identifier, execution ID, typed
params, timestamps, status, and log messages.

`cron/models.py` owns persisted jobs and execution rows; `cron/api_models.py`
owns their HTTP contracts. The manager commits a `running` row before invoking a
command. Terminal status, duration, messages, and the job's execution count commit
in one transaction. Finalization is idempotent: an already terminal execution is
not overwritten or counted again. During runtime startup, retained running rows
become failed with an interruption diagnostic appended to their original messages,
a completion time and duration. Their identifiers and earlier history are retained,
and commands are never replayed automatically.

Status transitions are recorded in `CronJobExecution` rows:

- `running`
- `completed`
- `skipped`
- `failed`
- `cancelled`

Jobs that do not run call `context.skip(reason)` and return. The manager marks
only still-running contexts as completed; exceptions and cancellation retain
their own terminal statuses. Skipped attempts retain timestamps, a reason in the
execution logs, and an execution count. Backup history distinguishes a skip before
snapshot creation from retention cleanup skipped after a snapshot was created.
The frontend detail dialog displays them as “跳过” rather than “成功”.

## Built-In Jobs

### `backup` (`jobs/backup.py`)

Params: `BackupJobParams(server_id, path, forget retention fields,
uptimekuma_url?)`.

1. Resolve and validate the configured path, then construct a global, project or data-path scope.
2. Call `SnapshotCommands.backup(scope)` under the existing cron execution. The common command applies protection and resource ownership without creating a nested task or restoration history.
3. If any required maintenance/resource claim is busy, record `skipped` and its reason without automatic retry; a global backup skips the entire run.
4. Apply configured forget/prune retention through the repository-use guard. If active references prevent retention, retain the created snapshot and explicitly record that cleanup was skipped.
5. Push optional Uptime Kuma status, preserving the separate cron execution history.

After snapshot creation, an HTTP 423 retention conflict records `skipped` with a
static repository-busy diagnostic and retains the snapshot. Other HTTP retention
errors propagate unchanged and record `failed`, also retaining the snapshot.
An ordinary retention exception records a safe warning and finishes `completed`.
Cancellation propagates at backup, retention and notification boundaries and
commits `cancelled`; a snapshot already created remains retained.

### `restart_server` (`jobs/restart.py`)

Params: `ServerRestartParams(server_id)`, where `server_id` is the exact logical
server name. Calls `servers.commands.ServerCommands.execute(..., only_if_running=True)`.
The same public command handles manual start/up/restart/stop/down. It captures a
`ServerRef`, revalidates generation after acquiring maintenance ownership, and
skips a stopped scheduled restart. Manual startup retains its existing behavior.
The command records Docker ownership as uncertain before dispatch and settles
failure/cancellation before releasing its maintenance lease. Stop/down remain
available as recovery actions. A nested cron invocation shares its existing
operation record and execution reference instead of creating a second owner.

### `self_check` (`app.self_check.job`)

Params: `SelfCheckJobParams(scope="global")`. Runs the self-check runner with
trigger `scheduled`. Cron execution history records every scheduled run, and
self-check run history keeps the full findings for the configured retention
period.

## Uptime Kuma Protocol

Backup jobs notify via plain HTTP GET to the configured push URL:

- `status=up|down`
- `msg=<short_text>`
- `ping=<ms>` for every notification

An intentional lock-conflict skip sends `status=up` with a `skipped:` message;
this monitor heartbeat is separate from the persisted `skipped` execution result.
Retention conflicts after snapshot creation also send an `up`/`skipped:` heartbeat;
other HTTP retention failures send `down`, while ordinary retention warnings send
`up`/`OK`. Transport and ordinary notification errors are best effort and preserve
the backup outcome. The configured URL is sent unchanged but omitted from logs and
execution history, along with adapter exception text.

## Error output

Cron keeps authored Chinese diagnostics separate from internal exception values.
Local validation and manager failures retain their original `ValueError` type and
status classification; their public messages omit dynamic identifiers and input
values. Unknown adapter exceptions use the standard internal-error message in
history and responses. An adapter `HTTPException.detail` is not trusted for cron
history or Uptime Kuma messages.

Invalid parameters retain HTTP 400 with a string detail. Diagnostics include known
schema field names, numeric indexes, error categories and authored constraints;
they omit raw input, mapping keys, validator messages and exception context.
Unexpected create/update failures retain HTTP 500. Safe logs record exception type
and stack locations without exception values, causes or locals.

## Files

- `manager.py` — `CronManager` and typed `get_cron_manager()` accessor for the active runtime
- `registry.py` — `CronRegistry` and explicit `register_func` metadata registration
- `restart_scheduler.py` — restart-minute selection
- `weekdays.py` — conventional-crontab weekday normalization for APScheduler 3
- `types.py` — `ExecutionContext`, registration/config/record types
- `crud.py` — DB operations on `CronJob` and `CronJobExecution`
- `errors.py` — authored cron diagnostics on unchanged exception types
- `jobs/backup.py` — backup job
- `jobs/restart.py` — restart job

## Lifespan Wiring

The application runtime initializes cron after migrations, dynamic config and
operation recovery. The scheduler starts paused while definitions are registered,
then resumes. Each execution persists a running row before entering its durable
operation scope; final status updates that row. Startup marks abandoned running
executions failed and retains the journal's interrupted outcome without replay.

Shutdown stops scheduling, cancels owned executions and waits for their cleanup
before closing the database. Runtime shutdown then drains the remaining producers
and request/task writers. See [runtime lifecycle](runtime.md).
