## Context

See proposal.md for scope. Existing designs in backend/docs/servers.md, templates.md, snapshots.md, background-tasks.md, players.md, dynamic-config.md, frontend-react/docs/archive-upload.md, file-management.md and e2e/docs/architecture.md provide the retained boundaries. The application is a single process managing real Docker, files and SQLite; API E2E remains an independent deployed observer.

## Goals / Non-Goals

Goals: concentrate decisions at their actual owner and validate ordinary user journeys. Non-goals: a universal task or lock framework, internal event buses, comprehensive race matrices, online world writes during maintenance, automatic distributed rollback, and new cloud credentials or services.

## Decisions

- A concrete configuration service prepares snapshot-derived YAML and matching metadata for preview and application. Rebuild removes an existing stopped container when required, saves applied metadata before restart, and reports the complete result through the existing task manager. Routers do not launch post-success metadata callbacks. Existing saved snapshots stay readable; validation of definitions occurs at authoring boundaries.
- Existing per-server operation ownership coordinates destructive world restore/prune and server start/up. Global backup uses its actual affected server scopes. A concrete snapshot application service owns safety backup, restoration and cleanup, while SnapshotService and Restic planning remain independent of HTTP. Ordinary files outside known world scopes remain restorable online. Generator closure propagates through SSE adapters and records interruption without attempting to emit after closure; persistent resumable workflows are unnecessary.
- Archive and ordinary file uploads each get a local flow owner. Raw API functions send protocol requests; flow code owns batches and busy state. Cancellation keeps ordinary uploads' partial-write semantics. Compression filenames use an operation identity. Session publication protects its no-overwrite contract at final publication when this can be done locally.
- Authentication resolves current user identity centrally, retaining the master-token path. Log and template rule validation is applied once at the accepted definition boundary. DNS initialization, refresh, reads and updates share the manager's existing ownership boundary; concurrent write batches settle before returning, without cloud rollback.
- Chat message IDs use SQLite's explicit non-reuse allocation with a row-preserving migration. Crash recovery clamps each end timestamp to its join timestamp. Other low-priority player concurrency and tail-reading work is outside this change.
- The E2E factory exposes resource reservation separately from deployment. The engine owns phase deadlines; stream transport shares authenticated cookies/transport but has no unrelated short total-body timeout. Diagnostic and teardown deadlines are independent. Cheap controlled tests establish phase behavior; real API tests verify application effects.

## Risks / Trade-offs

- Cross-system configuration failures → retain the applied state and truthful failure reporting; no all-or-nothing transaction is promised.
- Interrupted restoration may have changed files → preserve safety snapshots and manual rollback, and finish history/ownership cleanup.
- Previously stored invalid parser rules → account for startup compatibility when adding write validation; do not silently discard usable configuration.
- SQLite table migration → preserve rows, indexes and foreign-key behavior and test upgrade from the prior revision; historical already-deleted cursor high-water marks cannot be reconstructed.
- External DNS is optional → use deterministic manager tests and extend existing opt-in real-provider cases; do not claim cloud qualification without credentials.

## Migration Plan

Deploy through the existing image and startup Alembic migration. Validate migration with retained chat history and cleanup followed by replay. Rollback of application code must account for the new revision using existing migration procedures; keeping non-reusing integer IDs is compatible with older readers. API additions preserve existing routes and payloads. Update scoped CLAUDE.md maps and domain docs to describe the final ownership rules, and update E2E coverage and verification evidence. No automatic archive or commit is part of this work.
