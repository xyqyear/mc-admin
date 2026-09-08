## Why

The existing backend tests exercise many domains through in-process clients and dependency overrides. A separately distributed API E2E runner is needed to verify the deployed application, its startup migrations, real Minecraft containers, and real Restic operations while supporting isolated concurrent CI runs.

## What Changes

- Add an independent Go project under `e2e/` with a standalone CLI, composable environment providers, explicit reuse policies, deterministic sharding, bounded concurrency, and structured reports.
- Run the actual application image with private data directories and real Docker-managed Minecraft servers. Bootstrap business resources through public APIs.
- Add representative smoke scenarios for authentication, discovery, configuration persistence, templates, servers, files, archive transfers/tasks, Minecraft operations, and snapshot restoration.
- Document the full backend feature inventory, current smoke coverage, extension rules, and environment lifecycle contracts.
- Add CI that builds the application once and runs independent smoke shards, including cleanup after cancellation.

## Capabilities

### New Capabilities

- `api-e2e-testing`: Independently executable API smoke testing with isolated environments, explicit reuse, parallel execution, diagnostics, and owned-resource cleanup.

### Modified Capabilities

None.

## Impact

Adds `e2e/`, a GitHub Actions workflow, and project documentation. The test project's build requires Go; running the binary requires Linux and local Docker with the application's existing runtime prerequisites supplied by its image. No frontend changes, production API changes, or database schema migrations are intended. Existing pytest remains in place. Cloud DNS credentials, exhaustive Minecraft/mod-version matrices, and complete feature regression coverage are outside this initial implementation.
