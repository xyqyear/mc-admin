## Why

MC Admin presents and stores five-field schedules as conventional crontab expressions, but APScheduler 3 interprets numeric weekdays with Monday as zero. This mismatch causes every numeric weekday schedule to run on the following day, so the scheduler boundary must normalize conventional crontab weekdays before constructing APScheduler triggers.

## What Changes

- Define the public and persisted weekday field as conventional crontab syntax: Sunday is `0` or `7`, Monday is `1`, and Saturday is `6`.
- Expand conventional weekday wildcards, lists, ranges, and steps into a concrete set of weekdays, then translate that set into the equivalent APScheduler 3 weekday list when constructing a trigger.
- Preserve the original cron expression in API responses and persistence; normalization is internal to scheduler submission.
- Apply the same normalization path to creation, updates, resume, startup recovery, and system cron jobs.
- Correct weekday help text and document the public convention and scheduler-boundary conversion.
- Add focused tests for individual numbers, the Sunday aliases, names, lists, ranges, steps, validation, and recovered jobs.
- **BREAKING**: Existing numeric expressions intentionally authored using APScheduler 3 numbering will change execution day. Expressions written according to MC Admin's existing UI and conventional crontab intent will begin executing on their displayed weekday. No stored data will be rewritten because the original authoring convention cannot be inferred reliably.
- Non-goals: upgrading to APScheduler 4, changing timezone behavior, or claiming compatibility with crontab semantics outside weekday-number normalization.

## Capabilities

### New Capabilities

- `cron-scheduling`: Defines MC Admin's observable cron weekday convention, validation, persistence, and execution behavior.

### Modified Capabilities

None.

## Impact

- Backend: cron trigger construction and cron scheduling tests.
- Frontend: weekday format guidance only; submitted and displayed expressions remain conventional crontab syntax.
- API: no shape changes, but numeric weekday execution semantics become conventional crontab semantics.
- Persistence: no schema migration and no expression rewrite; stored expressions remain the source of truth.
- Dependencies and Docker: no changes; APScheduler remains on the stable 3.x series.
