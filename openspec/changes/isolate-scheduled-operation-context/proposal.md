## Why

Registering a restart schedule during server creation can propagate that operation's context into APScheduler's wakeup/timer chain. Later backups and self-checks then reuse a completed, unrelated operation; failures may even be recorded as completed. Scheduled work must own its operation independently of the request that changed a schedule.

## What Changes

- Bind scheduler wakeups and dispatch to the owning runtime without inheriting an operation.
- Project durable cron outcomes only from the execution's own journal record.
- Reject ended nested operation contexts and isolate long-lived log watchers.
- Verify existing schedules after server creation with real SQLite, Restic, log files and deployed API scenarios.

Non-goals: change schedule expressions, replay missed jobs, rewrite historic execution rows, redesign resource leases, or alter unrelated task cancellation semantics.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `cron-scheduling`: scheduled runs have independent ownership and truthful terminal history after schedule changes inside another operation.
- `operation-consistency`: ended operation contexts cannot authorize later nested work; independent producers retain only their runtime binding.

## Impact

Backend cron dispatch, operation scopes and log watchers; backend regression tests; Go API E2E and coverage documentation. No API schema, frontend, database migration, configuration, Docker image dependency or breaking contract changes. Existing production failures remain historical evidence; deploying a fixed application replaces the contaminated in-memory scheduler.
