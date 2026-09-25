# Cron (`app.cron`)

Scheduled background jobs. Built on APScheduler with database persistence so
jobs survive restarts. The built-in job types are backup, server restart, and
automatic self-check.

## Runtime resources

- **`cron_manager`** — APScheduler facade. Creates, updates, pauses, resumes,
  cancels, persists, recovers, and executes jobs.
- **`cron_registry`** — registry of job functions, parameter schemas, and
  registration metadata. Built-in jobs use
  `cron_registry.register_func(...)`; the optional `register(...)` decorator is
  a helper around the same registration path.
- **`restart_scheduler`** — picks restart minutes that avoid active backup
  minutes. Used by per-server restart schedule UI.

## Server-managed restart plans

The server schedule API identifies its plan by `CronJob.managed_server_generation`
and `managed_purpose="restart"`. The generation is the retained `Server.id`, whose
allocation is never reused. A unique index permits one managed plan per generation
and purpose, including paused and cancelled plans. Creating the plan again for the
same generation resumes its retained identity. Its display name can change without
changing ownership.

Jobs created through the generic cron API have no managed binding, even if their
name is exactly `restart-<server_id>`. Multiple independent restart jobs remain
supported. Automatic time selection excludes only the current managed job; a
similarly named independent job continues to reserve its time slot.

Deleting and recreating a server name creates a different generation. The new
server's schedule GET returns `null` until a plan is explicitly created, and that
plan receives a new cron job ID. Old plans and execution history remain readable.
Generic update/create-with-ID cannot retarget a bound plan; resuming a retired
generation's plan returns 409. Execution checks its persisted binding and repeats
the generation check after obtaining maintenance ownership, before calling Docker.
Unavailable or ambiguous bindings do not register during scheduler recovery. An
already dispatched attempt records `skipped` with its reason.

Server deletion cancels the current generation's active managed plan and active
independent restart jobs targeting that public server ID. Paused jobs, explicitly
bound old generations and unresolved historical candidates are retained. Malformed
parameters do not break unrelated server deletion. An administrator can explicitly resume an independent job later; this
does not turn it into the new server's managed plan.

`GET /cron/` and `GET /cron/{cronjob_id}` include three additive nullable fields:
`managed_server_generation`, `managed_purpose`, and `managed_binding_issue`.
The issue is a Chinese diagnostic for display. Server schedule URLs and request
shapes remain stable; responses also expose the registration state described below.

### Historical binding migration

Revision `2026092502` adds the nullable fields, backfills defensible bindings, then
creates the unique index. SQLite enters a real transaction before batch DDL, so a
failed constraint installation rolls back cleanly and can be retried without
removing migration artifacts by hand. It changes no pre-existing job fields, IDs, status,
execution count or execution-history rows. Fresh generic jobs are never inferred
from names at runtime.

Backfill requires all of the following:

- the exact historical name `restart-<params.server_id>` and type `restart_server`;
- valid parameters and ordered creation/update timestamps;
- the job's entire recorded lifetime fits exactly one retained server lifetime,
  and does not overlap another same-name generation;
- no other historical candidate resolves to that same generation and purpose.

A retained removed server's `updated_at` bounds its lifetime; an active server has
no end bound. Missing, inconsistent or overlapping evidence leaves the binding
unassigned. A paused old plan whose evidence identifies the old generation stays
bound to that old generation. A plan spanning a same-name recreation remains
unresolved. Separate plans with non-overlapping evidence may bind to their own
distinct generations.

Unresolved candidates retain `managed_purpose="restart"`, a null generation and a
stable issue code in `managed_binding_issue`. Migration warnings report job IDs and
codes; the columns retain that report after startup. Inspect a stopped disposable
database copy before rollout, and review the persisted report with:

```sql
SELECT cronjob_id, name, managed_server_generation, managed_binding_issue
FROM cronjob
WHERE managed_purpose = 'restart'
ORDER BY id;
```

An unresolved non-cancelled plan makes affected server schedule GET/create/update/
pause/resume/delete return 409 with a diagnostic and job ID. Generic cron detail,
list, history, pause and cancel remain available. Invalid historical JSON is
represented as empty parameters in the read response, with its explicit issue;
the original database value remains intact. Generic update or resume cannot erase
the ambiguity. After reviewing the retained records, explicitly cancel the affected
plans and create a fresh plan on the server page. Cancelled ambiguous rows retain
their evidence and history but no longer block creating a new bound plan.

Downgrading below this revision is refused while any managed binding or ambiguity
report exists. Removing the columns would let name-based older code reinterpret
those records. Rollback must use a schema-compatible application version; restoring
a database backup is a separate controlled recovery, not an automatic downgrade.

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
| `blocked` | An active managed plan has an unresolved or retired server binding. |
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
At dispatch, the manager rechecks desired state, managed identity and that
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
execution logs, and an execution count, without claiming that a backup exists.
The frontend detail dialog displays them as “跳过” rather than “成功”.

## Built-In Jobs

### `backup` (`jobs/backup.py`)

Params: `BackupJobParams(server_id, path, forget retention fields,
uptimekuma_url?)`.

1. Resolve backup paths.
2. Check `server_operation_lock` and skip rather than block if a conflicting
   backup or restore lock is active. A global backup skips the entire run if any
   affected server is busy. Skipped runs are not automatically retried.
3. Call the public `SnapshotApplication.backup(...)` command with the acquired lease;
   configured ignored paths are excluded automatically.
4. Apply configured forget/prune retention.
5. Push optional Uptime Kuma status.

### `restart_server` (`jobs/restart.py`)

Params: `ServerRestartParams(server_id)`. Managed generation metadata is carried
separately in the execution context and cannot be authored through the parameter
editor. Calls `servers.commands.ServerCommands.execute(..., only_if_running=True)`.
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
- `ping=<ms>` for successful runs

An intentional lock-conflict skip sends `status=up` with a `skipped:` message;
this monitor heartbeat is separate from the persisted `skipped` execution result.

## Files

- `manager.py` — `CronManager`
- `registry.py` — `CronRegistry`, `register_func`, optional decorator helper
- `instance.py` — typed `get_cron_manager()` accessor for the active runtime
- `restart_scheduler.py` — restart-minute selection
- `weekdays.py` — conventional-crontab weekday normalization for APScheduler 3
- `types.py` — `ExecutionContext`, registration/config/record types
- `crud.py` — DB operations on `CronJob` and `CronJobExecution`
- `bindings.py` — managed identity validation and retained ambiguity diagnostics
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
