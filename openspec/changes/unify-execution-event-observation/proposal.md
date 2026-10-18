## Why

Task summary events still trigger HTTP requests for map and self-check progress, while restoration discovery, chunk-prune state and resource refresh use independent polling loops. A single authenticated event stream should carry current execution state so progress, disconnect recovery and completion share one consistent observation lifecycle.

## What Changes

- **BREAKING**: Extend task events with structured progress and explicitly bounded, settled results; remove HTTP progress polling and per-progress detail requests from the current frontend.
- Deliver restoration discovery and chunk-prune preview/apply lifecycle state over the same stream, including expiry, invalidation and late observer snapshots.
- **BREAKING**: Replace the frontend operation-change polling loop with cursor-based stream delivery while preserving reset recovery and ordered cache refresh.
- Expose map stages, self-check findings, hash byte counts, batch deletion counts and chunk-prune counters as structured progress.
- Preserve durable acceptance, cancellation, real terminal settlement, partial-write evidence, authorization and preview safety checks.
- Non-goals: cron transport changes, old-client compatibility adapters, snapshot lease heartbeat changes, repository usage monitoring, filesystem watchers, releases or deployment changes.

## Capabilities

### New Capabilities

- `execution-observation`: Authoritative streamed restoration and chunk-prune discovery with preview lifecycle and disconnect recovery.

### Modified Capabilities

- `background-task-progress`: Structured progress and bounded settled results replace polling-based progress hydration.
- `operation-refresh-sync`: Cursor-based streamed change delivery replaces activity-based polling.

## Impact

- Backend task models, event stream, operation change feed and relevant progress producers; snapshot/prune observation providers and lifecycle notifications.
- Frontend shared task observation, operation refresh, map/self-check progress, recovery/prune discovery and task progress rendering.
- Deployed API, frontend and browser behavior coverage plus owning documentation.
- No persistence migration, configuration migration, Docker lifecycle change or new runtime dependency.
