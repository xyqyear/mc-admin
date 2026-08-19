## Context

See `proposal.md` for motivation. MC Admin stores cron expressions in its own `CronJob` rows and reconstructs in-memory APScheduler jobs during startup. Every production submission path already constructs triggers through `CronManager._build_cron_trigger()`, making that boundary the single place to reconcile conventional crontab input with APScheduler 3's Monday-zero weekday field.

The visual builder, human-readable display, presets, API payloads, and persisted values use or imply conventional crontab numbering. APScheduler 3 must remain on the stable series, and stored expressions must remain readable and portable rather than exposing scheduler-specific numbering.

## Goals / Non-Goals

**Goals:**

- Use conventional weekday semantics for UI, API, and persisted cron expressions.
- Convert the complete weekday expression into a deterministic set before passing it to APScheduler 3.
- Keep one normalization path for create, update, resume, recovery, and system-job scheduling.
- Reject invalid weekday syntax before mutating the active scheduler.
- Preserve current execution, persistence, authorization, and concurrency architecture.

**Non-Goals:**

- Implement a general-purpose cron parser for fields other than weekday.
- Emulate every POSIX or implementation-specific crontab behavior.
- Change timezone selection or day-of-month/day-of-week interaction semantics.
- Upgrade APScheduler or add a parsing dependency.
- Rewrite persisted cron expressions or infer whether an existing expression was manually adjusted for APScheduler 3.

## Decisions

### Normalize only at trigger construction

The fifth persisted field remains conventional crontab text. `_build_cron_trigger()` will pass that field through a dedicated weekday normalizer and provide only the normalized result to APScheduler.

This keeps API responses, editing, display, and future migration independent of APScheduler 3. Converting values before persistence was rejected because it would leak internal numbering to clients and make existing expressions misleading.

### Expand to a semantic weekday set

The normalizer will parse comma-separated terms composed from individual values or names, ascending ranges, and positive steps. It will expand them against the conventional ordered domain `0` through `7`, collapse `7` onto Sunday, deduplicate the calendar-day set, translate each day with `(cron_day - 1) % 7`, and emit a sorted comma-separated APScheduler list.

Examples:

| Conventional field | Calendar-day set | APScheduler 3 field |
|---|---|---|
| `1` | Monday | `0` |
| `0` or `7` | Sunday | `6` |
| `1-5` | Monday-Friday | `0,1,2,3,4` |
| `0-2` | Sunday-Tuesday | `0,1,6` |
| `*/2` | Sunday, Tuesday, Thursday, Saturday | `1,3,5,6` |
| `0,6,7` | Saturday-Sunday | `5,6` |

A bare `*` will remain `*` because every weekday is selected under both conventions. Named days and named ranges will be resolved by the same parser so mixed expressions have one validation path. Expanding to a set was chosen over decrementing numeric tokens because mapped ranges can cross APScheduler's numeric boundary and steps depend on the source convention's ordering.

### Validate before scheduler mutation

The normalizer will reject malformed terms, values outside `0` through `7`, descending ranges, and zero or negative steps with `ValueError`. Existing manager methods already build and validate a trigger before database or scheduler mutation for create and update; tests will preserve that ordering.

APScheduler will continue validating the remaining four cron fields and the optional seconds field. This avoids duplicating its parser outside the compatibility issue being fixed.

### Preserve stored data and declare compatibility behavior

No database migration will rewrite cron strings. On deployment, startup recovery will submit every active stored expression through the new normalizer. This immediately corrects expressions authored according to the UI and conventional crontab semantics.

There is no reliable way to distinguish a conventional expression from one manually compensated for APScheduler 3. Release documentation must identify the behavior change so operators can audit numeric weekday schedules. Named weekdays are unaffected.

### Keep documentation aligned with the boundary

`backend/docs/cron.md` will describe the conventional public format and internal normalization. `frontend-react/docs/cron-management.md` and raw-mode help will state weekday range `0-7` with Sunday aliases. No CLAUDE.md update is required because module structure and project-wide conventions do not change.

## Risks / Trade-offs

- [Manually compensated schedules move to a different day] -> Document the breaking behavior and advise auditing active numeric weekday expressions before deployment.
- [Parser behavior diverges from a user's preferred cron implementation] -> Specify and test the supported weekday grammar, while explicitly limiting compatibility claims to weekday normalization.
- [Range or step mapping introduces boundary errors] -> Expand source values before translation and test calendar-day results for simple, wrapped, stepped, and duplicate-Sunday cases.
- [Recovery behaves differently from creation] -> Keep normalization inside the shared trigger builder and add a recovery integration test.
- [Invalid existing expressions fail recovery] -> Log the existing recovery warning with the validation reason; leave the persisted row intact so it can be corrected through the API.

## Migration Plan

1. Add the weekday parser/normalizer with direct unit coverage.
2. Apply it in the shared trigger builder and add lifecycle integration coverage.
3. Correct frontend help text and current-state cron design documentation.
4. Before deployment, identify active expressions with a non-wildcard numeric fifth field and review any that were intentionally compensated for APScheduler 3.
5. Deploy normally. Application startup recreates active in-memory schedules using normalized weekdays; no database migration is required.

Rollback consists of reverting the scheduler-boundary normalization and restarting the application. Stored expressions remain unchanged, although rollback also restores the original numeric-weekday mismatch.
