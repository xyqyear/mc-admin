## 1. Task observation

- [x] 1.1 Implement authenticated task SSE snapshots/updates/removals, bounded subscriptions and manager publication while preserving settlement ordering; add focused backend regressions.
- [x] 1.2 Share one client task stream across queries and waiters with reconnect, HTTP recovery, terminal-result barriers and session cleanup; add focused frontend regressions and preserve affected workflows.
- [x] 1.3 Bound HTTP stream shutdown so SIGTERM reaches application cleanup; verify a real Uvicorn process drains the SSE subscription and owned worker.

## 2. Snapshot progress

- [x] 2.1 Stream Restic backup status through manual creation and recovery safety backups, retain awaited results and owned cleanup; add gated process and snapshot integration regressions.

## 3. Deployed behavior and documentation

- [x] 3.1 Add deployed task SSE authentication, live/terminal, reconnect/dismissal and independent result assertions; update API coverage and contract fixtures.
- [x] 3.2 Verify actual browser task progress and recovery after connection faults with source/output invariants; retain existing close/cancel guards.
- [x] 3.3 Update owning task/snapshot/browser documents and sync the behavior specification.

## 4. Verification

- [x] 4.1 Pass explicitly selected backend/frontend/Go/API/browser checks, required static/contract/build validation and independent review.

Delivery additionally requires committing/pushing the implementation branch and
successful complete qualification of its exact latest SHA with publish=false.
