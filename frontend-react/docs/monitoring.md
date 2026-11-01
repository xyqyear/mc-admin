# Shared monitoring observation

`features/monitoring` owns the current `/api/monitoring` contract, transport,
query policy and sample presentation. The authenticated layout mounts one
`MonitoringObserver` per user. Overview, sidebar, server details, console and
world views subscribe to selections from that same Query cache.

The key is `queryKeys.monitoring.snapshot(userId)`, under the shared
`monitoring.all` invalidation prefix. Read-only consumers keep their subscriptions
enabled while automatic fetching is disabled. Only the layout observer owns the
two-second polling interval. Multiple observers with an identical key do not
provide this guarantee by themselves: each would own its own interval.

Polling runs only when the application is visible and online. Restoring either
condition enables a fresh read. HTTP requests consume the Query abort signal and
have a five-second timeout; failures wait for the next observation interval
rather than creating immediate retry bursts. Unmount cancels the owner's request;
authentication cache clearing and user-specific keys isolate late responses from
subsequent sessions.

Task acceptance/settlement invalidates the monitoring prefix. The existing
application operation observer maps terminal business changes to that same
prefix and cancels earlier reads before invalidation. Hidden observers retain
invalidated data until observation resumes. Task SSE remains the authority for
progress, results, snapshot discovery and completion guards.

`SampleValue` displays pending, stale and unavailable samples explicitly and
retains actual timestamps in its tooltip. Failed HTTP updates mark retained
values stale. Status consumers use only ready observations and discard status
when their read fails; backend command admission independently verifies current
state. Details match samples to the configuration's server generation.

CPU preserves a logical-core percentage, including values above 100%. Memory
preserves container accounting. I/O remains cumulative bytes; the UI does not
derive rates or join counters across incarnations. Directory size has its own
slower backend cadence, documented in [backend monitoring](../../backend/docs/monitoring.md).

`observation.integration.test.tsx` and overview/console integration tests cover
shared fetching, pauses, session replacement, partial failure and lifecycle
changes. `browser/monitoring.spec.ts` checks the built application against an
owned deployment, including real stop/start and a temporary transport failure.
