## Context

See proposal.md for the observation gaps. Existing ownership and settlement rules remain in backend/docs/background-tasks.md, backend/docs/operations.md, backend/docs/snapshot-restoration.md, frontend-react/docs/task-center.md, frontend-react/docs/operation-refresh.md and frontend-react/docs/snapshot-recovery.md. The application ships its frontend and backend together.

## Goals / Non-Goals

Provide one session-scoped transport and current-state cache for execution observation. Transport loss cannot release destructive-action guards. A progress frame is replaceable current state, not an audit log. Cron observation, repository metrics and preview lease renewal retain their existing behavior.

## Decisions

### One event stream with bounded task results

Extend `/tasks/events` with task, restoration-index, prune-state and operation-change frames. Task summaries carry nullable `progress_details`; event tasks also carry `result_included` and `result`. Only known results of genuinely settled terminal tasks whose encoded result is at most 16 KiB are included. Running tasks never publish results, including when progress is 100. Unknown historical or large terminal results use one detail read. This avoids both repeated detail reads and unbounded event payloads; sending every result inline was rejected because preview geometry and partial-write evidence can be large.

Map stages, self-check current findings, bytes, item counters and region counters use feature-owned structured progress. Durable partial-write results remain independently journaled. Progress details are not a second durable journal.

### Cursor delivery shares the transport

Operation notifications wake subscribers synchronously after durable commit; each subscriber reads from the existing bounded change ring. The client serializes batches, cancels superseded business reads, invalidates affected caches, then commits its cursor. Reconnect uses only the committed cursor. A retention gap or restart produces the existing explicit reset. There is no additional operation queue or periodic HTTP read.

### Domain snapshots have explicit lifecycle notifications

The transport accepts an injected asynchronous domain snapshot provider to avoid task-core imports of snapshot/world domains. Restoration snapshots query every active journal-backed restoration, including global target scopes, after acceptance commit and terminal settlement. Prune snapshots read bounded in-memory metadata, preserving retained task references after dismissal. Registration, consumption, stale detection, eviction and expiry notify observers; a nearest-expiry timer handles time-driven validity without filesystem scans. Apply-time manifest and claims checks remain authoritative.

Subscription dirty flags are cleared before awaited reads, so concurrent notifications schedule another snapshot. Provider errors close observation for reconnect; empty successful state must never conceal a failed read.

### Client state and recovery

The shared task transport is retained by task consumers, operation observation and domain consumers. Current snapshots live in TanStack Query. Late consumers use that cache and the same connection. Progress detail hydration and periodic fallback polling are removed. Domain readiness is unknown until a successful snapshot; disconnect retains observed task identities and action guards. Small settled results can complete consumers directly; missing large results cannot complete a workflow until its authoritative detail read succeeds.

## Risks / Trade-offs

### Review corrections

Execution status remains authoritative even while its complete result is unavailable. Result consumers independently track result readiness and hold dependent-action guards until a complete result is read. Detail queries for tasks missing from the live feed must still reach retained journal history. Transient result-read failures expose explicit same-task retry in the task center and initiating workflows; retries never repeat the business command. Task dismissal removes list visibility, not result recoverability.

Settled worker/future handles are released, and runtime history uses a bounded recent projection consistent with durable journal retention. Expired durable results cannot remain available only through SSE. Completed restoration history links are distinguished from outstanding recovery obligations so ordinary success cannot permanently consume journal capacity. Uncertain writers, staging and genuine recovery blocks remain protected. Authored safe failure information survives history restoration without persisting raw exceptions.

Progress-only prune changes use task updates; domain discovery updates on identity and availability changes. Domain metadata remains available after generic dismissal. Whole progress payloads have a bounded representation, with terminal details compacted and complete evidence read on demand. Task-center connection state and task-action failures are visible; result details remain reachable after navigation. Task controls opened from a modal must participate in its modal/focus hierarchy. Pending and running prune tasks share active-state controls.

- Large or unavailable terminal results still need HTTP → one-shot reads on terminal observation, retry on subsequent observation or explicit retry; retain guards on failure.
- Coalesced findings can skip intermediate frames → publish complete current findings and document current-state semantics.
- Domain acceptance can race journal events → explicitly notify after domain transaction commit and subscribe before initial reads.
- Expiry and stale notifications can race apply → backend apply checks remain the destructive-action authority.
- Shared stream failure affects several observers → bounded reconnect, retained current state and strict session cleanup; no HTTP polling fallback.

## Migration Plan

Deploy frontend and backend together without an old-client compatibility mode. Migration `2026101800` adds nullable safe failure text to operation records; upgrade preserves existing results and recovery evidence, and downgrade removes only this optional text. Rollback replaces the application image; persisted journals and restoration history remain readable. Update the owning task, operation, recovery/prune and testing documents plus API coverage inventory. AGENTS.md does not change because commands and ownership boundaries remain valid. Validate focused behavior locally, then push and qualify the exact SHA with publishing disabled.
