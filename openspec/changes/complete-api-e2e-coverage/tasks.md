## 1. Shared contracts and inputs

- [x] 1.1 Add world environment composition and common observed SSE/duplex WebSocket transport.
- [x] 1.2 Add owned legacy/operational fixtures and external provider configuration without application imports or secret leakage.
- [x] 1.3 Add API operation coverage accounting and complete feature-to-case mapping.

## 2. Functional regression domains

- [x] 2.1 Implement and run authentication/users/login codes, configuration, cron, self-check, system/static/audit scenarios.
- [x] 2.2 Implement and run templates, servers/sync/rebuild/conversion/schedules, Minecraft/console scenarios.
- [x] 2.3 Implement and run all file/upload/archive/populate/compression and task-center operations.
- [x] 2.4 Implement and run player identity/tracking/query/profile/cleanup, public event replay and startup migration scenarios.
- [x] 2.5 Implement and run global snapshot, world restore/preview/rollback/recovery, maps, player locations, FTB claims and prune scenarios.
- [x] 2.6 Implement all DNS provider and router scenarios; validate local contracts and execute external qualification when test-domain configuration is supplied.

## 3. Defect repair

- [x] 3.1 Repair reproduced path-confinement defects with focused backend tests and image validation.
- [x] 3.2 Repair reproduced audit or other documented behavior defects with focused tests; retain visible evidence for unresolved failures.

## 4. Integration and qualification

- [x] 4.1 Integrate regression selection, coverage artifacts and CI execution; update CLAUDE and feature/environment documentation.
- [x] 4.2 Run Go formatting/vet/race tests, targeted backend pytest/Pyright, workflow lint and strict OpenSpec validation.
- [x] 4.3 Run the complete local regression selection in independent shards, verify no-reuse behavior and owned resource cleanup; record exact results and any external qualification limits.

## 5. Defect review follow-through

- [x] 5.1 Require authentication on every task-center operation and verify rejected requests preserve task state through focused tests and deployed API permission checks.
- [x] 5.2 Make exact audit field matching configurable, cover login completion tickets, remove login-code values from ordinary logs, and disable production-default protocol DEBUG frame logging; verify actual login credentials and truncated ticket fragments stay out of logs.
- [x] 5.3 Use valid Quilt metadata fixtures, reject malformed Quilt metadata without guessing dependency IDs, and preserve mc-router deletion idempotency while surfacing other HTTP failures.
- [x] 5.4 Preserve Linux filename compatibility while retaining directory confinement, and document deliberate root-operation and multipart validation policies.
- [x] 5.5 Rebuild the application and runner, validate the affected scenarios with reuse disabled and the complete local regression, and correct the Chinese coverage and evidence records.
- [x] 5.6 Preserve equals signs in Docker label values so real healthy containers are reported correctly; verify both Docker parsers and the deployed Minecraft lifecycle.
