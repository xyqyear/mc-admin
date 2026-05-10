# Cron (`app.cron`)

Scheduled background jobs. Built on APScheduler with database persistence so jobs survive restarts. The job set is small and fixed (backup + server restart) — adding a new job type is a code change, not a config change.

## Singletons

- **`cron_manager`** — APScheduler facade. Creates/updates/cancels jobs, persists them to the `CronJob` table, and wires them through `cron_registry` for type lookup.
- **`cron_registry`** — `@register("identifier")` decorator collects job functions at import time. The identifier (e.g. `"server_backup"`, `"server_restart"`) is what the database stores and what the frontend's job-type dropdown shows.
- **`restart_scheduler`** — RestartScheduler picks restart minutes that don't collide with active backup jobs. Used by per-server "restart on schedule" config.

## Job execution model

Each registered job function is `async (context: ExecutionContext) -> None`. `ExecutionContext` carries:

- `params: dict` — typed via the job's Pydantic params model
- `logger` — pre-bound; output streams into the job's execution row
- `status` (read-only) — current run status

Status transitions: `RUNNING → SUCCESS | FAILED | SKIPPED`. The history is kept in `CronJobExecution` rows so the frontend's detail modal can show the last N runs.

## Built-in jobs

### `backup_cronjob` (`jobs/backup.py`)

Params: `BackupJobParams(server_id, path, forget retention fields, uptimekuma_url?)`.

1. **Lock check first**. Calls `server_operation_lock.is_locked(server_id)`. If held (a restore is running, or another backup), emits a structured "skipped" log and pushes Uptime Kuma `status=down&msg=skipped` if `uptimekuma_url` is set. **Never blocks waiting for the lock** — overlapping with a restore would defeat the safety-snapshot design.
2. **Backup**. `restic_manager.backup([path])` under `kind=BACKUP`.
3. **Forget/prune** with the configured retention.
4. **Notify**. Push Uptime Kuma `status=up&msg=ok&ping=<elapsed_ms>` on success, `status=down&msg=<error>` on failure.

### `restart_server_cronjob` (`jobs/restart.py`)

Params: `ServerRestartParams(server_id)`. Calls `instance.restart()`. The frontend's restart-schedule UI uses `restart_scheduler` to pick minutes that don't collide with the server's backup minute.

## Uptime Kuma protocol

Jobs notify via plain HTTP GET to the configured push URL with query params:

- `status=up|down` — outcome
- `msg=<short_text>` — human-readable status
- `ping=<ms>` — for `up`, the elapsed milliseconds

## Files

- `manager.py` — `CronManager`
- `registry.py` — `CronRegistry`, `@register` decorator
- `instance.py` — `cron_manager` singleton
- `restart_scheduler.py` — `RestartScheduler`
- `types.py` — `ExecutionContext`, `CronJobConfig`, `AsyncCronJobFunction`, `TaskStatus`, `TaskProgress`
- `crud.py` — DB ops on `CronJob` / `CronJobExecution`
- `jobs/backup.py` — backup job + Uptime Kuma push
- `jobs/restart.py` — restart job

## Lifespan wiring

`cron_manager.initialize()` runs in `app.main` lifespan, *before* the player system. On shutdown, `cron_manager.shutdown()` is called after the player system stops, so in-flight jobs aren't interrupted by half-torn-down dependencies.
