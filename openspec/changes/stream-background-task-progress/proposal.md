## Why

Issue #150's background execution is already present, but task views still poll
and snapshot creation hides Restic's intermediate progress. Users need live
progress without coupling the worker's lifetime to a browser connection.

## What Changes

- Add one authenticated task event stream with an initial current-state snapshot,
  live summary updates and removals, bounded slow-consumer recovery and keepalive.
- Share that connection across task lists, detail observers and initiating
  workflows; retain HTTP reads for history, detailed results and recovery when
  the stream is unavailable. Preserve session isolation and terminal guards.
- Forward actual Restic backup status into manual creation and recovery's safety
  snapshot phase, preserving process ownership and successful-exit verification.
- Add transport, progress, cancellation, reconnect and deployed behavior coverage.
- Non-goals: replacing the worker/journal, durable replay of every progress frame,
  changing scheduled backup behavior, converting the separate operation refresh
  feed, UI redesign, schema migrations or dependency/version upgrades.

## Capabilities

### New Capabilities

- `background-task-progress`: live shared task observation and truthful backup
  progress with independent worker lifetime and authoritative completion.

### Modified Capabilities

None. Existing snapshot, execution ownership and recovery contracts remain in
force; this adds transport and progress guarantees.

## Impact

Backend task manager/router and snapshot subprocess integration; frontend task
queries/waiters and affected progress consumers; deployed API/browser tests and
owning task/snapshot documentation. The task SSE endpoint is additive; existing
task HTTP contracts and large result payloads remain available. No breaking API,
configuration or persistence changes are intended. Deployment adds a bounded
HTTP-stream shutdown grace so open observers do not prevent application cleanup;
Docker packaging and dependencies retain their current versions.
