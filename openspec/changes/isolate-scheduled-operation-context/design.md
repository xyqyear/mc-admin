## Context

See proposal.md for the incident. Runtime binding and operation ownership are separate ContextVars. APScheduler 3 copies the caller context into wakeup callbacks, subsequent timers and worker tasks. Existing runtime/task/map entrypoints already clear operation ownership. The log watcher has its own lifecycle but directly creates a task. Relevant owners are backend/docs/runtime.md, cron.md and operations.md.

## Goals / Non-Goals

Keep every independent producer bound to its owning runtime and preserve normal nested resource reuse. Do not globally clear operation context: process finalization and nested commands need their existing owner. Do not introduce an extra task around cron dispatch or change cancellation ownership.

## Decisions

- Provide a fresh Context containing only the owning runtime. Override the scheduler's public wakeup entrypoint to invoke the upstream wakeup in that context, isolating the complete timer chain without depending on private timer internals. Clearing only the job wrapper would leave the scheduler and arbitrary future jobs contaminated.
- Bind runtime and clear operation at cron dispatch as an independent entrypoint, in the existing task. This also protects direct invocation and preserves cancellation/draining semantics.
- Project durable terminal outcomes only when journal origin and execution reference identify this cron occurrence. Preserve committed-success precedence for late cancellation belonging to the same operation.
- Reject ended parents at nested scope entry. Check in-memory settlement first, then durable state for still-unsettled parents; reuse that read for resource validation. Silent detachment could bypass the caller's declared resource boundaries.
- Launch log watchers with a fresh runtime context, retaining their existing manager-owned cancellation and cleanup.
- Test scheduler behavior with its real event loop, ownership with real SQLite, snapshots with Restic and actual restore bytes, and log watching with real files. A deployed API case reproduces schedule registration inside public server creation, with no subsequent scheduler mutation that could hide the bug.

## Risks / Trade-offs

- Additional journal read for nested scopes without explicit claims → limit to scope admission, not phase updates; validate real backup and restoration paths.
- Scheduler extension depends on public APScheduler 3 wakeup behavior → exercise previously registered jobs and repeated timer ticks under a real scheduler.
- Time-based E2E preparation could exceed the scheduled occurrence → assert creation/preparation finishes first and surface explicit timing failures.

## Migration Plan

No schema or persisted configuration change. Qualify the exact new commit before deployment. Replacing the application process clears existing contaminated callbacks; missed runs and historical misclassified rows are not replayed or rewritten. Production upgrade compatibility must be checked against its currently deployed release. Rollback of this code-only change uses a schema-compatible prior image. Update runtime, cron and operation owner docs; agent instructions remain unchanged.
