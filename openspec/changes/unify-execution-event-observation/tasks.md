## 1. Stream contract and backend observation

- [x] 1.1 Add structured task progress and bounded settled event results with focused settlement, reconnect and cleanup tests.
- [x] 1.2 Deliver operation changes with per-observer committed cursor, bounded reset recovery and session-safe subscriptions.
- [x] 1.3 Publish complete restoration and prune lifecycle indexes, including acceptance, expiry, consumption, stale detection and retained tasks.
- [x] 1.4 Populate map, self-check, hash, batch deletion and region progress without weakening durable partial-write evidence.

## 2. Frontend consumers

- [x] 2.1 Share one event transport across tasks, operation refresh and domain discovery; remove task HTTP progress hydration and periodic fallback.
- [x] 2.2 Consume map stages, self-check findings, bytes and item counters directly from structured events with guarded terminal-result recovery.
- [x] 2.3 Replace restoration and prune discovery polling, preserving disconnect guards, preview availability and independent geometry/lease requests.
- [x] 2.4 Migrate focused fixtures and behavior tests to controlled events, including late observers, disconnects, cancellation and session replacement.

## 3. Verification and delivery

- [x] 3.1 Update deployed API and selected browser coverage for the new protocol, retain independent business-result assertions and update coverage inventory.
- [x] 3.2 Synchronize main specifications and owning documentation; validate OpenSpec and run focused tests plus required static/build/contract checks.
- [x] 3.3 Prepare delivery metadata and the exact-SHA publish=false qualification invocation.

## 4. Review corrections

- [x] 4.1 Bound runtime task/result retention, release settled execution handles, align expired detail behavior with durable history, and preserve safe authored failures across restart.
- [x] 4.2 Resolve ordinary successful-restoration history references without weakening unresolved writer and recovery protection; verify bounded journal admission.
- [x] 4.3 Stop progress-driven full prune-index broadcasts, bound all streamed progress details and terminal summaries, and retain late-observer preview discovery.
- [x] 4.4 Preserve real execution status independently of result availability; recover excluded results after dismissal and transient failures with explicit same-task retry and no resubmission.
- [x] 4.5 Show unknown/disconnected task-center state, persistent per-item results and task-action errors; keep task actions reachable inside progress modals.
- [x] 4.6 Expose result retry in affected workflows, preserve safety guards, and consistently display pending prune work.
- [x] 4.7 Cover API and browser recovery/retention/transport behavior with focused tests, synchronize specifications/docs and run required static checks.
- [x] 4.8 Prepare atomic review-correction commits, the push target and the exact-SHA publish=false qualification invocation.

## Delivery gate

The implementation branch is `feat/150-task-progress-sse`, associated with #150.
After commit and push, dispatch `Qualify and Publish Application` through
`.github/workflows/docker-image.yml` on that branch with `publish=false`.
Delivery requires every gate and coverage/cleanup audit to pass for that exact
latest SHA. The Actions run owns the qualification receipt; planning checkboxes
do not assert a CI outcome. Follow docs/ci.md for the single silent wait and
final audit. Merge and release remain outside this change.
