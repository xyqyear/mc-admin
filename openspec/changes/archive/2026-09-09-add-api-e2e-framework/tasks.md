## 1. Architecture and feature inventory

- [x] 1.1 Document the backend feature inventory, smoke coverage boundaries, and extension/lifecycle contracts.
- [x] 1.2 Create the independent Go module and CLI with catalog validation, selection, planning and deterministic sharding.

## 2. Environment and execution infrastructure

- [x] 2.1 Implement composable providers, dependency validation, exclusive leases, conservative reuse and failure retirement with targeted lifecycle tests.
- [x] 2.2 Implement Docker deployment, ownership manifests, host port leases, bounded resources, signal cleanup and idempotent recovery cleanup.
- [x] 2.3 Implement session/CSRF API transport, deadline-based waits, SSE/task completion, redacted evidence and JSON/JUnit reporting.

## 3. Real smoke scenarios

- [x] 3.1 Cover authentication/authorization, startup discovery and dynamic configuration persistence through real APIs.
- [x] 3.2 Cover templates, server creation, files, archive upload and asynchronous archive tasks.
- [x] 3.3 Cover real Minecraft startup, RCON, restart/stop/removal and observational environment reuse.
- [x] 3.4 Cover real Restic snapshot, preview, streamed restore and restored content.

## 4. Integration and verification

- [x] 4.1 Add CI image build, independent smoke shards, mandatory cleanup and diagnostic artifact upload; update project CLAUDE instructions.
- [x] 4.2 Run Go formatting, vet and race-enabled framework tests, validate OpenSpec and inspect available IDE diagnostics.
- [x] 4.3 Build the standalone executable and run real smoke tests, no-reuse verification and concurrent runs; verify owned resources are reclaimed and record results.
