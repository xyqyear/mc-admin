## 1. Backend notification contract

- [x] 1.1 Implement a bounded instance-scoped feed with sequence pagination, active tracking and explicit reset for missing, invalid, expired or different-instance cursors.
- [x] 1.2 Publish relevant immutable operation changes only after successful journal commits, initialize before recovery and clear after writers stop.
- [x] 1.3 Expose authenticated GET /api/operations/changes while retaining historical operation and task interfaces.
- [x] 1.4 Add focused tests for commit/rollback, terminal and recovery changes, count/byte bounds, pagination races, startup/reset, runtime isolation and authorization.

## 2. Frontend synchronization

- [x] 2.1 Replace full history polling with bounded session-scoped incremental batch consumption and merged feature invalidation.
- [x] 2.2 Implement reset recovery for business caches and an independent map image token, including changes arriving during reset.
- [x] 2.3 Apply active/idle intervals, hidden-page suspension and immediate focus/reconnect/submission observation; retain cursor on read failure.
- [x] 2.4 Migrate affected integration fixtures and add tests for old-operation completion, repeated reads, partial failure, paging, reset, cancellation/session isolation and polling behavior.

## 3. API behavior and documentation

- [x] 3.1 Add a real API E2E case for authenticated incremental file operations, task terminal results, pagination and backend restart recovery; update coverage inventory.
- [x] 3.2 Update backend/frontend design documents and scoped/root AGENTS with current ownership and synchronization contracts; keep OpenSpec behavior specifications synchronized.

## 4. Verification and delivery

- [x] 4.1 Run directly related local backend/frontend/Go tests and required lint, type and build checks; review the combined change.
- [x] 4.2 Prepare the isolated branch, reviewed changes and issue association for commit, push and exact-revision non-publishing qualification.

Delivery is complete only after the branch is committed and pushed and every required gate in full non-publishing qualification succeeds on the latest commit SHA. Report the revision and run URL as delivery evidence.
