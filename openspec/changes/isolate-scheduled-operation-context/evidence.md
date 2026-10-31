# Incident and regression evidence

## Production diagnosis

Read-only inspection on 2026-10-21 (times below Asia/Shanghai) found the application healthy, both schedules active, no unfinished operation or Restic process, and ample disk capacity. The installed application was 6.2.1, revision `f4efae0cf365f766b2edef9c356862a8aec622c4`, with APScheduler 3.11.2.

- 14:59: the last successful scheduled self-check completed.
- 15:45–15:46: the last successful scheduled backup produced a snapshot whose repository file exists.
- 15:49: server creation registered its automatic restart schedule inside a durable operation.
- 15:59: the scheduled self-check attempted to update an ended operation. Its error was subsequently misclassified as completed.
- 16:00 onward: backups failed before Restic because the inherited operation did not cover the requested servers. The scheduled restart was affected too.
- A later manual self-check succeeded, consistent with its already isolated entrypoint.

The causal chain was reproduced locally with the installed real scheduler: registering another job under a ContextVar changed the context observed by an already running interval job after the caller reset its own context.

## Independent review

Separate agents reviewed business ownership and producer lifetimes, implemented cron isolation, and wrote the deployed API regression. Review identified the false-success projection, ended-parent admission and long-lived log-watcher inheritance. Existing Runtime, task-manager and map-queue isolation was retained; subprocess finalization deliberately keeps its actual operation owner.

## Targeted verification

- Seven cron/architecture parameter instances passed: real scheduler timer chain, independent successful/failed self-check journals, committed success versus late cancellation, real Restic global backup, notification cancellation, and import boundaries.
- Five related instances passed: two ended-parent cases, valid nested file work, real process ownership/reaping, and real log watcher → parser → player service → SQLite persistence. The existing external skin API substitute is the only unavailable service replacement in that log test.
- After the ended-parent guard was added, the real Restic global-backup instance passed again to verify the affected nested path.
- Backend-wide Ruff and Pyright passed with no diagnostics.
- The new API scenario `cron.creation-context-isolation` reproduced the original failure against the prior candidate: failed backup messages with `completed` status. The fixed local image passed normal (61.4 seconds) and `--no-reuse` (60.9 seconds) runs, verifying distinct cron journals, unchanged creation history, actual self-check findings, failed-backup absence and successful backup restore bytes. All three owned environments reported cleaned. Go package vet and runner build passed. Full CI source/image identity and its receipt are recorded with delivery.

No production writes, restarts or deployments were performed during diagnosis or these local checks. Historical execution rows are retained rather than retroactively rewritten.
