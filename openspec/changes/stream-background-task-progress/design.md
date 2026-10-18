## Context

[Background tasks](../../../backend/docs/background-tasks.md) own durable workers,
result-before-publication and cancellation cleanup. [Task center](../../../frontend-react/docs/task-center.md)
currently polls, including two independent consumers: query hooks and an imperative
waiter. [Snapshots](../../../backend/docs/snapshots.md) already stream restore
output, but backup buffers stdout until completion. See proposal.md for motivation.

## Goals / Non-Goals

**Goals:** One shared progress transport, bounded observation cost, existing UI
guards, and actual backup progress through the current worker ownership.

**Non-Goals:** Another task store, per-task persistent connections, durable replay
of progress, changing operation-discovery polling, or changing recovery semantics.

## Decisions

- Add `GET /tasks/events` before the task-id route. Data frames are
  `{type:"snapshot",tasks:[summary...]}`, `{type:"upsert",task:summary}` and
  `{type:"remove",task_id}`. Use existing summary DTOs with nulls intact; omit
  result bodies. Use existing SSE response cleanup/headers and comment keepalive.
- Each subscriber retains at most 256 dirty task IDs, coalescing intermediate
  states. Overflow requests a current snapshot. Registration and initial snapshot
  have no intervening await. Publication never waits for the network or reads DB.
  This provides current-state recovery without an unbounded event log/cursor.
- Notify acceptance, running, progress/result changes, cancellation requests,
  settled outcomes and dismissal. A shared synchronous `update_progress` method
  factors memory updates and notifications. Keep existing journal persistence
  before yielded results; publish terminal only at the existing settlement point.
- Bound Uvicorn's HTTP graceful-shutdown wait to two seconds. It waits for open
  responses before lifespan teardown, so an unbounded SSE response would otherwise
  prevent runtime worker cleanup. Cancellation of the response only detaches the
  observer; the existing runtime then drains workers and finalization. Deployment
  stop deadlines must leave time for that cleanup after the HTTP wait.
- Frontend transport is reference-counted per QueryClient, with connection-only
  bookkeeping outside Query cache. Hooks and waiters retain it. Reuse the existing
  event-stream reader; optional raw activity callbacks support idle watchdogs.
  Reconnect with backoff and initial snapshot; HTTP recovery remains available
  while not connected. Healthy streams disable periodic task progress polling.
- Preserve HTTP detail shapes. Normal progress merges summary fields; existing
  result remains intact. Map/self-check progress metadata uses coalesced detail
  reads triggered by updates. Terminal notifications trigger a deduplicated full
  detail read; consumers cannot observe completed-with-missing-result. Dismissal
  removes list visibility without removing retained detail. Abort/generation and
  authentication/cache-reset handling prevent stale-session cache writes.
- Keep `backup` and `create_snapshot` awaitable with an optional asynchronous
  progress callback. Read owned Restic stdout NDJSON incrementally, concurrently
  drain bounded stderr, report valid `status.percent_done` or unknown progress,
  and retain final summary parsing. Confirm exit/cleanup before returning the
  existing result. Snapshot commands report into their current accepted task;
  scheduled execution remains a direct awaited backup without UI reporting.

## Risks / Trade-offs

- Coalesced progress is not an audit log → retained outcome/detail remain authoritative.
- Missing progress result metadata → event-triggered detail reads preserve existing
  map and self-check presentation without broadcasting large result payloads.
- Late GET or old-session events → generation guards, cached-data merging and
  terminal detail barriers; test delayed responses and cache/session replacement.
- Summary or 100 before cleanup → hold real subprocess/test gates before terminal
  publication and assert actual bytes/recovery references independently.
- Pipe pressure and cancelled callbacks → one stdout reader, concurrent bounded
  stderr drainer and verified stop/join before releasing leases.

## Migration Plan

Ship backend and frontend together with existing HTTP compatibility. No database,
configuration, dependency or storage migration is needed; rollback keeps the same
durable records and returns observation to HTTP. Update task/snapshot topics,
frontend task/browser topics and deployed coverage. Root agent instructions and
CLAUDE.md need no structural changes; documented Uvicorn commands include the
finite HTTP shutdown grace. Qualification must cover the exact pushed
SHA with publish=false before delivery.
