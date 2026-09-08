# MC Admin API E2E

Independent Go module and Linux executable; scenarios exercise the real application image through HTTP, SSE and WebSocket with actual SQLite, Docker/Minecraft and Restic. See `README.md` for commands, `docs/architecture.md` for lifecycle/extension contracts, `docs/coverage.md` for feature families and gaps, and `docs/defect-review.md` for defect evidence and policy boundaries.

## Commands

```bash
make lint
make test
make check
make build
./bin/mc-admin-e2e run --backend-image mc-admin:e2e
./bin/mc-admin-e2e run --backend-image mc-admin:e2e --tag regression --no-reuse --seed 42
./bin/mc-admin-e2e coverage --require-complete --output coverage /path/to/run-one /path/to/run-two
```

Build the application image from the repository root with `docker build -t mc-admin:e2e .`. Go version and dependency checksums live in this module's `go.mod` and `go.sum`. The runtime binary needs no Go installation. `make lint` checks formatting and runs vet in the independent Static Checks push workflow. `make test` runs race-enabled framework tests with implicit vet disabled; `make check` runs both targets locally. The E2E workflow runs `make test` and `make build`; real scenarios run through the executable. Default local selection is `smoke`; CI selects `regression`, including smoke. Explicit external selections fail if required configuration or dependencies are absent.

## Module map

- `cmd/mc-admin-e2e/` — CLI, preflight, signals and recovery entrypoint.
- `internal/engine/` — catalog, deterministic shard plan, exclusive workers and JSON/JUnit reports.
- `internal/environment/` — provider dependency graph, resources, verification and LIFO cleanup.
- `internal/platform/` — local Docker adapter, port/run locks and durable ownership journal.
- `internal/api/` — sessions/CSRF, HTTP, bounded waits, tasks, SSE and WebSocket.
- `internal/evidence/` — structured evidence, secret redaction and bounded payloads.
- `internal/coverage/` — deployed OpenAPI/WS operation observations, shard union and missing-case audits.
- `internal/fixtures/` — API bootstrap, deployment, Minecraft/Restic providers and shared fixture data.
- `suites/<domain>/` — normal Go case functions, registered through `suites/catalog.go`.

## Rules

- Add API E2E coverage for new observable backend behavior and update `docs/coverage.md` in the same change.
- Declare a stable case ID, recipe, timeout, tags and explicit isolation. Start with `engine.Fresh`; verified reuse needs a narrow documented invariant and compensation for every mutation.
- Cases must run independently, in shuffled order and with reuse disabled. Do not import backend internals or another suite, share mutable cross-run data, or add feature-specific branches to the scheduler.
- Historical database inputs use isolated, stopped deployments and standard SQLite/shipped Alembic maintenance commands. Assert behavior through public APIs and process outcomes; do not use database queries as substitutes for API assertions.
- Propagate context through all I/O and polling. Require terminal task/SSE results and assert resulting state/content. Never retry a failed business scenario into success or silently skip missing real dependencies.
- Reserve environment capacity before starting the deployment deadline; retain it through teardown. Give each diagnostic and cleanup phase its own budget. SSE bodies use their operation context without the ordinary HTTP client timeout.
- Permission scenarios verify rejected requests preserve real task/resource state as well as checking status codes. Credential-log scenarios require successful audited business operations and inspect both audit and ordinary application logs.
- Register cleanup when allocating a resource, including partial setup. Journal Docker objects before creating them; keep run/environment ownership labels. Never prune the daemon or delete by an unvalidated prefix.
- Register secret values with the redactor before use. Upload explicit report/evidence paths; never upload `runtime/`.
- Run `gofmt`, `go vet` and race-enabled framework tests for infrastructure changes; run affected real cases normally and with `--no-reuse`. The shard-count CI matrix discovers cases through the catalog.
