## Why

Starting a server can hold maintenance ownership while Docker prepares images and containers, but the interface only disables buttons until the request returns. Other long operations also remain request-owned or outside the task center, so users cannot reliably tell what is running or leave the initiating page to check later.

## What Changes

- Move interactive non-snapshot long operations into the existing durable background-task system: server start/up/restart/stop/down/remove, server creation and registry synchronization, recursive server/archive deletion, map initialization, manual self-check, manual DNS/router synchronization, and server-side archive upload hashing and verified publication.
- Keep already detached configuration rebuild, population, compression, ownership repair and chunk-prune operations on the same task system; audit their discovery and completion presentation rather than introduce another executor.
- Return acceptance promptly while preserving each entrypoint's existing blocking and progress UI. Keep loading, disabled actions and dialog-close restrictions until the task reaches the appropriate terminal outcome; replace request/SSE-driven observation with task-status reads. Show maintenance reasons beside affected controls and link to the corresponding task when available.
- Keep accepted work and results discoverable after browser disconnection or refresh without making previously blocking interactions dismissible. Task acceptance or a failed status read is not operation completion.
- Separate task completion from Minecraft readiness. Expose actual execution stages; show indeterminate progress when no measurable percentage is available.
- Preserve authentication, confirmations, generation-bound targets, scope locks, deletion draining, cleanup ordering and restart recovery. Define explicit cancellation capabilities rather than suggesting that cancelling a task reverses its effects.
- **BREAKING:** replace covered synchronous/SSE execution endpoints with task acceptance and task-status reads. Update frontend and API test callers together; delete unused endpoints and response/stream adapters instead of keeping compatibility layers.
- Record the subsequent unified snapshot/recovery work in `docs/snapshot-recovery.md`; do not implement it in this change.

Non-goals: snapshot creation, restore, restore preview, rollback, snapshot deletion/retention/repository maintenance; replacing Restic or the task manager; backgrounding routine reads, RCON interaction, browser transfer bytes or small metadata edits; changing Minecraft running intent; automatic retries of interrupted mutations; publishing a release.

## Capabilities

### New Capabilities

- `non-snapshot-background-operations`: detached acceptance, understandable stage and maintenance feedback, durable outcome discovery, scoped execution and compatible interaction for non-snapshot management work.

### Modified Capabilities

None. Existing operation consistency, recovery and administration compatibility guarantees continue to apply.

## Impact

Backend task kinds/submission, server commands/lifecycle, file/archive application services, map initialization, self-check/DNS adapters and upload-session ownership. Frontend feature contracts, commands/controllers, task center, maintenance feedback and application-level completion observation. Backend, frontend, browser and deployed API regression coverage plus current-state documentation.

Covered API response contracts change to task acceptance; obsolete execution streams are removed. Backend and frontend deploy together, so old-client compatibility is not required. No new queue service, Docker dependency or database migration is planned. The durable journal remains the outcome authority. Creation and multi-server synchronization need explicit resource identities rather than pretending every task belongs to one already registered server.
