## 1. Task acceptance and ownership

- [x] 1.1 Add the covered task kinds and explicit acceptance contracts; preserve authenticated task access and existing domain preflight errors.
- [x] 1.2 Support prepared existing-server, prospective creation and multi-server synchronization targets without bypassing resource containment or generation checks; test name reuse and target changes before execution.
- [x] 1.3 Add atomic lifecycle conflict detection covering accepted but not yet running tasks; verify concurrent and lost-response submissions do not cause duplicate conflicting execution.

## 2. Server lifecycle

- [x] 2.1 Move start/up/restart/stop/down to feature-owned workers with honest Docker stage feedback, safe running-intent handling and unchanged readiness semantics; test detached acceptance and cleanup.
- [x] 2.2 Move server removal to an owned task and exclude only its own task identity from draining; test successful removal, unresolved writers and shutdown during deletion.
- [x] 2.3 Move server creation to an owned task with immutable prepared input, directory/port ownership and scheduling/DNS results; test rollback cleanup and concurrent same-name creation.
- [x] 2.4 Extract registry synchronization and preview into the server feature, then submit tasks with full per-server results; test OWNER access, empty-directory force protection, stale identities and partial failure.
- [x] 2.5 Migrate lifecycle/create/sync API callers to task acceptance and remove unused synchronous adapters; verify no request-scoped session survives into a worker and disconnect does not cancel accepted work.

## 3. File and map operations

- [x] 3.1 Submit recursive server-file and archive deletion as tasks with declared path claims, Chinese stage messages and finite filesystem settlement; preserve root/path refusal and unrelated-file concurrency.
- [x] 3.2 Extract map initialization from the router and run download/palette generation as a task; preserve force behavior, real CLI progress, cache ownership and finalization.
- [x] 3.3 Replace file deletion responses and map execution streams with task APIs and migrate all callers; test independent observer disconnect and explicit cancellation cleanup.

## 4. Administrative and upload operations

- [x] 4.1 Run full and individual manual self-checks as tasks with check stages, retained run links/findings and task-status results, removing unused synchronous/SSE endpoints; distinguish a completed check from a healthy result.
- [x] 4.2 Run manual DNS/router updates as tasks with existing authorization and partial/unknown-state semantics; test failures without requiring real provider credentials.
- [x] 4.3 Run archive SHA256 as a task bound to the completed upload and expose its task association in upload status; preserve byte progress and exact digest/result association.
- [x] 4.4 Run final publication as an owned task and coordinate upload expiry, explicit cancellation and shutdown with hash-input ownership; test reconnect, cancellation during reading, mismatch and conflicting final publication.

## 5. User-facing observation

- [x] 5.1 Inventory each covered entrypoint's loading, disabled actions, close/navigation guards and terminal handlers; switch request/SSE observation to task-status reads while preserving those interactions through confirmed completion, without an idle gap after acceptance.
- [x] 5.2 Show an inline maintenance/task reason beside server controls and allow locating the active task across overview/detail/console; include snapshot, scheduled and recovery holders without inventing task IDs.
- [x] 5.3 Extend task labels and feature result presentation, including removal counts, sync errors, self-check findings and upload verification; retain existing progress surfaces and blocking rules alongside the task center and cancellation capability display.
- [x] 5.4 Extend feature operation-resource registrations so terminal outcomes refresh affected views after navigation/reload, including partial failure and completion before the first poll; add frontend integration tests.
- [x] 5.5 Audit existing rebuild/populate/compression/ownership/prune flows against the inventory and verify they remain one detached task with working discovery and completion feedback.
- [x] 5.6 Test acceptance while queued/running, status-read failure and reconnect, restored blocking after refresh, non-dismissible progress dialogs and original terminal handlers; never infer completion or permit duplicate submission from a transport response alone.

## 6. Integration and validation

- [x] 6.1 Add deployed API cases for prompt task acceptance, status/result retrieval, authority checks, conflicts, disconnect survival and representative lifecycle/file/map execution; update existing response cases to the new task contracts.
- [x] 6.2 Add browser journeys for startup before container creation, visible reason/task access, retained blocking and close guards, task-driven progress, permitted navigation/refresh and terminal state synchronization; use owned fixtures and preserve existing snapshot/rollback journeys.
- [x] 6.3 Run focused backend task/operation/lifecycle/file/map/self-check/upload tests plus snapshot compatibility coverage; run `uv run pyright`, `uv run ruff check .` and architecture checks.
- [x] 6.4 Run frontend lint, typecheck, architecture/operation integration tests and bundle build, then the affected deployed API/browser suites; record outcomes and any environment limitations without weakening assertions.
- [x] 6.5 Update current-state root/backend/frontend CLAUDE.md, affected feature/task documentation and E2E coverage; verify the prospective snapshot roadmap remains separate and every in-scope operation is accounted for.
