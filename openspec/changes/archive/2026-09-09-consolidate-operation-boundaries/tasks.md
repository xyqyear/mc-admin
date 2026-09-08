## 1. Configuration application

- [x] 1.1 Consolidate server snapshot preview, configuration application, metadata and completion; preserve stopped intent and move restart scheduling out of routers.
- [x] 1.2 Validate authored template definitions and correct submission UI; add targeted pytest and deployed API assertions.

## 2. World maintenance

- [x] 2.1 Centralize snapshot application and existing server maintenance ownership across restore, prune, startup and scoped scheduled backup; preserve online ordinary-file restore.
- [x] 2.2 Close cancelled restore execution/history reliably and restore missing sidecar directories with rollback semantics; add targeted and API coverage.
- [x] 2.3 Expose maintenance availability to shared frontend controls and handle finite stream premature completion.
- [x] 2.4 Persist skipped backup executions as skipped, display their outcome distinctly, and verify unit/UI and deployed API behavior.

## 3. Authentication and upload flows

- [x] 3.1 Reject deleted-user sessions, tolerate disappearing directory entries and isolate compression/publication outputs; add targeted and API coverage.
- [x] 3.2 Give archive and ordinary upload flows local lifecycle owners with serial batches, busy checking and cancellation cleanup; verify frontend flow contracts.

## 4. Local service contracts

- [x] 4.1 Validate log-parser definitions at save time and verify that accepted rules actually parse events.
- [x] 4.2 Honor DNS hot disable and settle each update before its ownership ends; add manager tests and explicit provider-case assertions.
- [x] 4.3 Preserve chat cursor allocation through cleanup and migration, and bound crash playtime; add focused tests and deployed player scenarios.

## 5. E2E budgets

- [x] 5.1 Separate capacity reservation from deployment, independent diagnostic/cleanup phases, and long-stream deadlines; cover these with deterministic framework tests.

## 6. Integration and verification

- [x] 6.1 Update scoped CLAUDE.md, domain design documents and the API coverage mapping; validate the OpenSpec change.
- [x] 6.2 Run targeted pytest, backend Pyright/Ruff, frontend lint/typecheck/bundle and E2E formatting/vet/race tests; resolve failures.
- [x] 6.3 Build the current application image, run affected real API cases and required no-reuse checks, reclaim owned environments and record verification evidence.
