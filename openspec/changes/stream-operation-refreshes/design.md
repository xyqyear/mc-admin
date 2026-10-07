## Context

`backend/docs/operations.md` defines the single-writer deployment, journal ownership, committed metadata and retained task results. `frontend-react/docs/data-architecture.md` assigns terminal cache invalidation to one authenticated application observer; map revisions also invalidate browser tile URLs. The observer currently polls the created-time-sorted history and separately checks old active operations. See proposal.md for motivation.

## Goals / Non-Goals

Goals: bound notification memory, avoid database work on unchanged observation, preserve cross-page and reconnect correctness, and recover safely when notifications are unavailable.

Non-goals: durable notification replay, multi-writer distribution, changing task presentation or operation history, new external dependencies, database/schema migration, or changing Docker deployment ownership.

## Decisions

- The runtime-owned journal owns a bounded in-memory feed, keeping the existing runtime resource surface. Defaults are 2,000 records and 4 MiB of serialized notification data; per-entry shape and metadata remain bounded. Oversized entries advance the retention boundary and force resynchronization instead of failing committed business work. Active tracking is bounded by journal admission capacity and initialized before startup recovery.
- Short write transactions capture immutable relevant metadata and publish synchronously after successful commit. Acceptance, terminal outcomes, resource/data changes and effective terminal recovery changes notify; raw phase/process progress and task result payload updates do not. Rollback emits nothing.
- GET `/api/operations/changes` is an authenticated static route before the ID route. It accepts an opaque instance/sequence cursor with a pinned page upper bound; limit defaults to 200 and permits 1..1,000. Responses contain `items` with `sequence`, `operation_id`, `kind`, `state`, `data_changed`, `updated_at`, `ended_at`, `resources`, and `next_cursor`, `has_more`, `active_count`, `reset_required`. No database read or per-client server state is needed for observation.
- Missing, malformed, different-instance, future or expired cursors return an empty reset response and the current head. First entry uses the same mechanism to synchronize any existing feature cache. Each page rechecks retention; newly committed changes remain available after the pinned window completes.
- The observer owns a session-scoped continuation and processes each bounded batch before advancing it. A separate QueryClient checkpoint survives fetch cancellation and retains only the last processed cursor and active count. It cancels older affected reads before coalesced invalidation, including initial requests without cached data, and orders tile revisions by notification sequence. Reset invalidates the operation-related feature prefixes, resets the sequence baseline and changes an independent global tile token, preserving local authored editor state. Changes arriving during resynchronization are consumed from the response's head.
- Polling uses active count: 2 seconds active, 30 seconds idle, no hidden-tab interval; focus, reconnect and command discovery invalidation wake observation. HTTP/read failure or abort does not commit an unprocessed continuation. The client retains only bounded current observation state, not an ever-growing ID set or historical changes.
- Durable change storage was considered but adds persistence for disposable cache notifications. Timestamp-only continuation was rejected because ties and clock changes can lose updates. Unbounded in-memory history was rejected because disconnected clients can recover by refreshing authoritative business state.

## Risks / Trade-offs

- Notification eviction or restart → explicit reset and feature/image cache refresh; original task results remain durable.
- Reset/read races → return the reset head before business refresh, then replay changes after it; session/cancellation guards reject obsolete work.
- Bursts during paging → bounded page windows and retention checks; reset safely replaces unavailable replay.
- Idle changes from another client can wait up to 30 seconds → focus/reconnect/submission refresh immediately and active work switches to two seconds.
- Notification byte accounting excludes normal Python container overhead → bound both entry count and metadata size; no retained ORM objects or complete operation results.

## Migration Plan

Deploy backend and frontend in the existing single image. Existing history/detail/resolve and task interfaces remain intact, and rollback requires no data conversion. Update backend/frontend operation design documents and scoped/root AGENTS descriptions. Add focused backend/frontend tests and a real API E2E case, run static checks, then commit/push and qualify the exact branch revision with publishing disabled.
