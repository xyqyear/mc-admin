# Cron (`app.cron`)

Scheduled background jobs. Built on APScheduler with database persistence so
jobs survive restarts. The built-in job types are backup, server restart, and
automatic self-check.

## Singletons

- **`cron_manager`** — APScheduler facade. Creates, updates, pauses, resumes,
  cancels, persists, recovers, and executes jobs.
- **`cron_registry`** — registry of job functions, parameter schemas, and
  registration metadata. Built-in jobs use
  `cron_registry.register_func(...)`; the optional `register(...)` decorator is
  a helper around the same registration path.
- **`restart_scheduler`** — picks restart minutes that avoid active backup
  minutes. Used by per-server restart schedule UI.

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

Status transitions are recorded in `CronJobExecution` rows:

- `running`
- `completed`
- `failed`
- `cancelled`

The frontend detail dialog reads recent execution rows for job history.

## Built-In Jobs

### `backup` (`jobs/backup.py`)

Params: `BackupJobParams(server_id, path, forget retention fields,
uptimekuma_url?)`.

1. Resolve backup paths.
2. Check `server_operation_lock` and skip rather than block if a conflicting
   backup or restore lock is active.
3. Run `snapshot_service.create_snapshot(...)` — configured ignored paths are excluded automatically.
4. Apply configured forget/prune retention.
5. Push optional Uptime Kuma status.

### `restart_server` (`jobs/restart.py`)

Params: `ServerRestartParams(server_id)`. Calls `instance.restart()`.

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

## Files

- `manager.py` — `CronManager`
- `registry.py` — `CronRegistry`, `register_func`, optional decorator helper
- `instance.py` — `cron_manager` singleton
- `restart_scheduler.py` — restart-minute selection
- `types.py` — `ExecutionContext`, registration/config/record types
- `crud.py` — DB operations on `CronJob` and `CronJobExecution`
- `jobs/backup.py` — backup job
- `jobs/restart.py` — restart job

## Lifespan Wiring

`cron_manager.initialize()` runs in `app.main` lifespan after dynamic config and
DNS initialization. On shutdown, `cron_manager.shutdown()` is called after the
player system stops.
