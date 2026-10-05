# MC Admin API E2E

Independent Go module and Linux executable; scenarios exercise the real application image through HTTP, SSE and WebSocket with actual SQLite, Docker/Minecraft and Restic. See `README.md` for commands, `docs/architecture.md` for lifecycle/extension contracts, `docs/coverage.md` for feature families and gaps, and `docs/defect-review.md` for defect evidence and policy boundaries.

## Commands

```bash
make lint
go vet ./internal/engine
go test -race -vet=off -count=1 -run '^TestShardPartitionIsCompleteAndStable$' ./internal/engine
make build
./bin/mc-admin-e2e run --backend-image mc-admin:e2e --tag regression --case '^files\.directories-search-and-errors$'
./bin/mc-admin-e2e run --backend-image mc-admin:e2e --tag regression --case '^files\.directories-search-and-errors$' --no-reuse
./bin/mc-admin-e2e browser --backend-image mc-admin:e2e -- pnpm --dir ../frontend-react exec playwright test browser/journeys.spec.ts --grep 'lifecycle acceptance stays blocked until task status confirms completion$'
```

These local examples apply only when the named tests cover the change. Select explicit Go packages and test-name regexes, API case-ID regexes, and browser spec/title filters for directly related cases and shared affected paths. Never run entire project, component or browser test suites locally, including reconstructing them through directory batches or subagents. `--case` matches a regular expression; anchor each selected ID. `--tag` intersects with that selection, and its CLI default is `smoke`; use the appropriate explicit tag to include a related regression or external case.

Full-suite commands are CI entry points:

```bash
make test
make test TEST_FLAGS=-json
make check
./bin/mc-admin-e2e run --backend-image mc-admin:e2e --tag regression --no-reuse --seed 42
./bin/mc-admin-e2e coverage --require-complete --output coverage /path/to/run-one /path/to/run-two
./bin/mc-admin-e2e browser --backend-image mc-admin:e2e -- pnpm --dir ../frontend-react test:browser
```

Build the application image from the repository root with `docker build -t mc-admin:e2e .`. Go version and dependency checksums live in this module's `go.mod` and `go.sum`. The runtime binary needs no Go installation. `make lint` checks formatting and runs vet in the independent Static Checks push workflow. `make test` runs all framework packages with race detection, implicit vet disabled and uncached results; `TEST_FLAGS=-json` exposes per-test events and elapsed times. `make check` combines lint and the full framework suite for CI, not local validation. Candidate qualification runs `make test` and `make build`; real scenarios run through the executable. CI selects `regression`, including smoke. Explicit external selections fail if required configuration or dependencies are absent. Full validation requires all GitHub Actions gates for the latest commit SHA under `../AGENTS.md`.

## Module map

- `cmd/mc-admin-e2e/` — CLI, preflight, signals and recovery entrypoint.
- `cmd/mc-admin-e2e/browser.go` — owned provider wrapper for real browser/deployment commands, private fixture metadata, child-process draining and durable cleanup.
- `scripts/deployment_rehearsal.py` — released-image upgrade, complete persistent checkpoints, guarded old-code rejection, disaster recovery, retained legacy-history rollback/undo, ambiguous-identity rejection and explicit world rollback through actual APIs. Bootstrap actual historical releases with their matching runner; current API bootstrap is not backward compatible.
- `internal/engine/` — catalog, deterministic cost-balanced shard plans, resource-aware exclusive workers and JSON/JUnit lifecycle timings.
- `internal/environment/` — provider dependency graph, resources, verification and LIFO cleanup.
- `internal/platform/` — local Docker adapter, port/run locks and durable ownership journal.
- `internal/api/` — sessions/CSRF, HTTP, bounded waits, tasks, SSE and WebSocket.
- `internal/api/wait.go` — `StartTask` validates 202 acceptance; `RunTask`/`RunTaskResult` wait for confirmed completion and decode the business result. Lifecycle, creation, synchronization, deletion, manual self-check/DNS, map initialization and upload hashing/publication use these task contracts.
- `internal/evidence/` — structured evidence, secret redaction and bounded payloads.
- `internal/coverage/` — deployed OpenAPI/WS operation observations, shard union and missing-case audits.
- `internal/fixtures/` — API bootstrap, deployment, Minecraft/Restic providers and shared fixture data. The backend uses `ARCHIVE_PATH=archives` relative to `/data`, so archive journeys cover configuration path normalization.
- `suites/<domain>/` — normal Go case functions, registered through `suites/catalog.go`.
- `suites/costs.json` — embedded, versioned historical scheduling costs with source runs and measurement semantics; unknown cases use recipe/default costs and remain automatically discovered.
- `suites/servers/` — configuration versions, legacy mode conversions, stopped intent, real Docker startup failure and recovery, managed schedule generations, and stopped SQLite migration inputs.
- `suites/cron/` — configured versus registered state, invalid retained definitions, safe scheduling and durable execution outcomes. Repeated explicit-ID submissions retain one stored job with the requested name/cron updates.
- `suites/files/` — real fd filtering and file mutations through public APIs; upper and lower date filters each exclude results independently.
- `suites/dns/` — incremental reconciliation through the real SDK and pinned MC Router, owned TLS service-edge faults, unknown/empty observations and cross-service failure isolation. Test hosts/CA changes stay inside the owned backend container. The `connectivity-v1` recipe leases host ports for local backend/router access and actual Minecraft traffic; Huawei cases verify cloud records and public DNS resolution and persist non-secret cloud recovery manifests. See `suites/dns/README.md` for `cleanup-dns`.
- `suites/operations/` — startup handling of interrupted task/cron histories, scoped recovery permissions and cache degradation; local SQLite inputs are prepared only while the owned deployment is stopped.
- `suites/tasks/` — task acceptance, cross-session observation, retained outcomes after dismissal/restart, list filtering and cleanup.
- `suites/snapshots/` — task-based global/project/path creation, file recovery history and reversible rollback, source/current exclusion protection, task-owned paginated previews and stale-preview rejection, repository maintenance tasks and real lock recovery.
- `suites/world/` — real Restic scope/rollback including empty ranges and instance ownership, precise file conflicts, task-observation disconnection, explicit cancellation and process interruption with database-write recovery, mcmap preview freshness and artifact leases; deterministic public-format inputs supplement actual Minecraft worlds.

## Rules

- Add API E2E coverage for new observable backend behavior and update `docs/coverage.md` in the same change.
- Declare a stable case ID, recipe, timeout, tags and explicit isolation. Start with `engine.Fresh`; verified reuse needs a narrow documented invariant and compensation for every mutation.
- Cases must run independently, in shuffled order and with reuse disabled. Do not import backend internals or another suite, share mutable cross-run data, or add feature-specific branches to the scheduler.
- Historical database inputs use isolated, stopped deployments and standard SQLite/shipped Alembic maintenance commands. Assert behavior through public APIs and process outcomes; do not use database queries as substitutes for API assertions.
- Propagate context through all I/O and polling. Require terminal task/SSE results and assert resulting state/content. Never retry a failed business scenario into success or silently skip missing real dependencies.
- Reserve environment capacity before starting the deployment deadline; retain it through teardown. Give each diagnostic and cleanup phase its own budget. SSE bodies use their operation context without the ordinary HTTP client timeout.
- Failed or expired environment teardown leaves ownership unresolved: retain its capacity, cancel new allocations and drain active groups with independent cleanup contexts. Pending cases must still have failed results. Diagnostic failure alone does not retain capacity after successful teardown.
- Keep Fresh case and reusable recipe groups atomic when balancing worker/Minecraft costs. Seed changes execution priority only. All shards must share selection, cost fingerprint, worker/slot limits and seed; coverage rejects inconsistent plans.
- Read scheduler queue/resource wait separately from case execution and lifecycle phases. Queue times are attributed once to the first case in a group; final group teardown belongs to its last case. Historical baseline costs remove reservation delay approximately and are not pure assertion times.
- Permission scenarios verify rejected requests preserve real task/resource state as well as checking status codes. Credential-log scenarios require successful audited business operations and inspect both audit and ordinary application logs.
- Register cleanup when allocating a resource, including partial setup. Journal Docker objects before creating them; keep run/environment ownership labels. Never prune the daemon or delete by an unvalidated prefix.
- Register secret values with the redactor before use. Upload explicit report/evidence paths; never upload `runtime/`.
- Run `gofmt` on changed Go files, `go vet` on explicit affected packages and race-enabled framework tests selected by package and `-run` for infrastructure changes; preserve `-count=1` and run vet separately when tests use `-vet=off`. Run explicitly selected affected real cases normally and with `--no-reuse`. The shard-count CI matrix discovers the complete catalog for remote validation.
