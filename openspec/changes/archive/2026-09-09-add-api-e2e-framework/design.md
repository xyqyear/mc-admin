## Context

See proposal.md for motivation. Relevant contracts are documented in `backend/docs/auth.md`, `servers.md`, `minecraft.md`, `templates.md`, `dynamic-config.md`, `archive-upload.md`, `background-tasks.md`, and `snapshots.md`. The application includes in-memory caches, schedulers and tasks as well as SQLite state. Compose requires `mc-{server_id}` containers and known game/RCON published ports. Bind paths must match the Docker host. Temporary upload and restore directories are process-global paths.

## Goals / Non-Goals

**Goals:** Keep scenario code independent from application imports; make resource ownership explicit; make reuse optional and conservative; run representative real smoke flows; keep the scheduling kernel independent of feature modules.

**Non-Goals:** General-purpose distributed test orchestration, arbitrary environment mutation solving, cloud-account provisioning, production-attached destructive tests, or duplicating all existing pytest cases.

## Decisions

### Standalone Go command with small explicit contracts

Use a separate Go module with a command, API transport, execution engine, environment lifecycle, infrastructure adapters, and domain suites. Scenarios are registered ordinary functions returning errors; framework internals use Go's standard testing package. This avoids depending on generated internals of Go test binaries while providing a stable CLI and JSON/JUnit output. The application image remains an independent input artifact. Fixtures are embedded or generated and never depend on the launch directory.

### Composable recipes and bounded exclusive reuse

A recipe contains named providers with explicit dependency edges. Validate missing dependencies, cycles, and conflicting declarations before provisioning. Providers register compensating cleanup as resources are allocated, including partial setup. A worker owns at most one live environment while executing a recipe-affinity group. Fresh cases always destroy their environments. Observe and clean reuse require post-case provider verification; clean cases additionally register resource-specific compensation. Failure retires the environment. No-reuse forces fresh allocation for every case. Domain tests never depend on preceding tests.

### Production image and local Docker isolation

Launch an actual application container with private data, credentials, tmp, SQLite, logs, archive and Restic paths. Mount its server workspace into the identical host path, alongside the existing Docker/cgroup mounts. Track unique short server names, compose projects, container labels, and runtime directories in an on-disk ownership manifest. Avoid inherited application/Compose configuration. Backend ports use Docker allocation; explicit game/RCON ports use host-shared file leases, occupancy checks and bounded setup retries. The first supported target is Linux with a local Docker socket. No backend-only reset API is introduced.

### API-first fixtures and observable checks

Bootstrap users through the master credential and use real session/CSRF clients for scenarios. Create templates, servers, files and archives using APIs. Initialize the private Restic repository with the application's shipped binary. Poll real readiness and task completion with context deadlines; consume SSE terminal events and verify final content. Business assertions are never automatically retried. Global state and destructive scenarios are fresh. Only providers with explicit health/invariant verification admit reuse.

### Deterministic scheduling and recovery

Sort the catalog, select by ID/suite/tag, group by recipe for affinity, and assign stable groups to shards. Record the plan, seed, image identities, environment IDs and reuse decisions. Limit workers and live Minecraft environments separately. Report setup/assertion/cleanup/verification failures separately. Handle signals with fresh cleanup deadlines. An explicit cleanup command acquires a run lock, validates its manifest and Docker ownership, and retries reclamation after crashes. CI uses always-running cleanup and artifact upload steps.

### Coverage and maintenance

Record all router feature families and their environment needs in `e2e/docs/coverage.md`; distinguish exercised smoke paths from future regression work. Add root and E2E CLAUDE instructions requiring API E2E coverage for new backend behavior and describing how to register suites/providers. Do not imply core smoke exhaustively covers every feature.

## Risks / Trade-offs

- Real Minecraft startup and image downloads are expensive → pin the game version, record resolved image IDs, use Docker layer caching and bounded concurrency, and reuse only explicitly observational running-server cases.
- Shared Docker hosts retain host-wide contention → coordinate owned port leases, avoid exact host metrics, and reserve daemon-disrupting tests for dedicated hosts.
- Resource teardown may fail → keep ownership manifests and evidence, fail the run, and support idempotent retry; never use global pruning.
- Go is a new development toolchain → the runtime executable needs no Go installation and uses a small dependency surface.
- Verification cannot prove arbitrary state restoration → fresh is the default; reusable cases must specify and implement narrow cleanup contracts.

## Migration Plan

Add the independent runner and representative scenarios, verify internal lifecycle tests and real smoke execution, then wire CI using the same CLI. Existing backend tests and production schemas remain unchanged. Reverting the E2E module and workflow removes the tooling; retained run resources can be reclaimed first with the cleanup command.
