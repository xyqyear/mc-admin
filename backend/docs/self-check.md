# Self-Check (`app.self_check`)

Self-check is the operational health surface for MC Admin. The frontend root
route (`/`) uses this system as the first screen. Scheduled runs use the cron
system, manual runs use the HTTP API, and event-triggered runs reuse the same
runner.

## Runtime Flow

`run_self_check(trigger, requested_by_user_id?)` creates one run context, loads
dynamic config at execution time, and executes checks whose boolean toggles are
enabled in a fixed catalog order. Each check returns one or more
`SelfCheckFindingResult` objects.
If a check raises, the runner records a critical failed finding for that check
and continues with the remaining checks.

The runner can be consumed either as an async event stream or as a blocking
helper. Both paths use the same execution code. Every completed run is retained
in `self_check_run`, and every finding is retained in `self_check_finding` so
the UI can show complete healthy and unhealthy histories. Retention defaults to
14 days.

Built-in checks are grouped by operational category under
`app.self_check.checks`. `runner.py` owns execution order, streaming, persistence,
and error isolation; category modules own the actual check implementations and
their `CheckDefinition` metadata.

The current health state is derived from retained runs instead of stored in a
separate state table. The latest full run is the baseline, and the latest
single-check run for each check ID after that full run replaces that check ID's
baseline findings. The derived current state is projected through the current
per-check enabled toggles, so disabled checks do not contribute findings or
warning counts. Retained run history still contains every finding that was
recorded when the run executed.

Scheduled runs also have cron execution history in `CronJobExecution`.

## Triggers

- `manual` — `POST /api/self-check/run` or `POST /api/self-check/run/stream`
- `scheduled` — cron job `system:self_check`
- `server_created` — after a server creation request succeeds
- `server_populated` — after the archive extraction task completes
- `world_restored` — after a restore SSE stream emits `complete`
- `world_rolled_back` — after a rollback SSE stream emits `complete`

Event-triggered runs are fire-and-forget coroutines. Failures are logged and do
not fail the user operation that already succeeded.

## Dynamic Config

`config.self_check` controls behavior:

- per-check boolean toggles
- snapshot freshness minutes
- backup repository usage threshold
- server directory usage threshold
- run retention days
- backup Mod/plugin jar metadata IDs
- file owner UID mismatch limit
- event-trigger switches

The default cron schedule is owned by cron registration metadata, not dynamic
config.

## Check Catalog

- `backup.restic_configured`
- `backup.restic_reachable`
- `backup.server_snapshot_coverage`
- `backup.server_snapshot_freshness`
- `storage.backup_repository_usage`
- `storage.server_directory_usage`
- `locks.python_restic_active`
- `locks.repo_restic_active`
- `dns.drift`
- `dependency.binaries`
- `log_monitor.active`
- `server.backup_mod_removed`
- `files.permission_consistency`
- `server.filesystem_db_sync`

The two lock checks are informational. Servers newer than the configured
snapshot freshness window do not produce backup coverage warnings before their
first snapshot has had time to run.

`server.backup_mod_removed` scans `mods/*.jar` and `plugins/*.jar`. It reads jar
metadata IDs from Fabric/Quilt JSON, Forge/NeoForge TOML, legacy Forge
`mcmod.info`, and Bukkit/Paper plugin YAML, then compares those IDs with
`config.self_check.backup_mod_ids` case-insensitively. File names are not used
for backup Mod/plugin detection.

`files.permission_consistency` checks only file owner UID consistency. It uses
`fd --owner` to find entries whose owner UID differs from the server project
root and does not compare group IDs or mode bits.

## API

- `GET /api/self-check/catalog` — configured catalog with enabled flags
- `GET /api/self-check/status` — catalog, current health state, and recent run summaries
- `POST /api/self-check/run` — manual run, returns the full run result
- `POST /api/self-check/run/stream` — manual full run over SSE
- `POST /api/self-check/checks/{check_id}/run` — single-check rerun
- `GET /api/self-check/runs` — paginated retained run history
- `GET /api/self-check/runs/{id}` — retained run detail with findings

## Notifications

`SelfCheckNotificationBus` is a no-op extension point for future push
integrations. Sinks implement `publish(result)`. Sink failures are logged and do
not affect the self-check result.

## Files

- `constants.py` — check IDs and trigger names
- `types.py` — run, finding, catalog, event, and history response models
- `runner.py` — catalog access, validation, event streaming, persistence, and notification publishing
- `checks/base.py` — shared check context, definition, and finding helpers
- `checks/<category>.py` — built-in check implementations grouped by catalog category
- `jar_metadata.py` — jar metadata ID extraction for Mod/plugin detection
- `crud.py` — retained-run persistence and current-state derivation
- `job.py` — cron entry point and params schema
- `events.py` — event-triggered scheduling helper
- `notifications.py` — future push notification bus
- `routers/self_check.py` — HTTP API
