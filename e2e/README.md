# MC Admin API E2E

Standalone Go executable for testing an actual MC Admin deployment through HTTP, SSE and WebSocket APIs. Each environment runs the repository's application image with a private SQLite database, configuration, credentials and files. Scenarios that need Minecraft or Restic use the real dependencies. Application Python modules are never imported by the runner.

See [architecture and extension contracts](docs/architecture.md), the [backend feature coverage inventory](docs/coverage.md), and the [qualification results](docs/verification.md). The catalog contains smoke and functional regression scenarios across every backend feature family, with explicitly selected real external provider qualification.

The [defect review](docs/defect-review.md) distinguishes confirmed defects, deliberate operation policies, fixture mistakes and remaining qualification limits.

## Build and run

From the repository root:

```bash
docker build -t mc-admin:e2e .
cd e2e
make build
./bin/mc-admin-e2e run --backend-image mc-admin:e2e
```

Building the runner requires the Go version in `go.mod`; `make` is optional:

```bash
CGO_ENABLED=0 go build -trimpath -o bin/mc-admin-e2e ./cmd/mc-admin-e2e
```

The resulting executable can run from any directory without the repository, Go, Python, Node.js, Java or a separately installed database. Its runtime inputs are:

- Linux, the `docker` CLI, and access to a local Docker Engine Unix socket (default `/var/run/docker.sock`). The daemon must see the same absolute host filesystem paths as the runner. Remote Docker and Docker Desktop path translation are not supported.
- An application image built from the revision being tested. The root Dockerfile includes Compose, `fd`, Restic, `7z` and `mcmap`; the runner does not silently substitute a released application image.
- A writable directory for reports and private runtime files, and Linux cgroup mounts used by the deployed application's metrics.
- Sufficient memory for the configured concurrency. Defaults are two backend environments and one live Minecraft environment per runner; the smoke Minecraft configuration requests 1 GiB of heap. Concurrent runners each have their own budget.
- Network access for uncached images and the pinned Minecraft server download. Minecraft's image digest and game version are defined in `internal/fixtures/factory.go` and can be overridden explicitly. The generated test Compose accepts the Minecraft EULA and starts a private flat offline test world.

The runner provisions users, configuration and test data itself. Do not point it at an existing backend or production data; there is no attach mode.

## Selection, parallelism and reproduction

```bash
./bin/mc-admin-e2e list
./bin/mc-admin-e2e list --tag regression
./bin/mc-admin-e2e plan --shard 1/3 --seed 42
./bin/mc-admin-e2e run --backend-image mc-admin:e2e --suite minecraft
./bin/mc-admin-e2e run --backend-image mc-admin:e2e --case '^snapshots\.'
./bin/mc-admin-e2e run --backend-image mc-admin:e2e --tag regression --no-reuse --seed 42
./bin/mc-admin-e2e run --backend-image mc-admin:e2e --tag mojang
```

`--tag smoke` is the local default; `--tag regression` includes smoke and all ordinary regression cases. `--tag ''` selects all cases including external providers and therefore requires their configuration. Suite, tag and case regex filters intersect. A selection matching no scenarios is an error. An empty individual shard is valid when the overall selection is nonempty. Use `--tag regression --suite world` for a regression-only suite; the default smoke tag otherwise narrows selection.

External Mojang scenarios use `--tag mojang`. DNSPod/Huawei scenarios use `--tag dns` and require `--external-config /private/path/external.json`; select one with `--case '^dns\.dnspod-'` or `--case '^dns\.huawei-'`. See [DNS qualification](suites/dns/README.md) for the private configuration schema, owned test-domain scope and cloud cleanup contract. Missing configuration or unavailable dependencies fail explicitly.

For concurrent CI processes, use the same executable, selection, shard count and seed, and a different shard index and run ID for each process:

```bash
./bin/mc-admin-e2e run --backend-image mc-admin:e2e --tag regression --shard 1/2 --run-id e2e-local-one
./bin/mc-admin-e2e run --backend-image mc-admin:e2e --tag regression --shard 2/2 --run-id e2e-local-two
```

Run these commands in separate terminals or jobs. On a shared Docker host, runners under the same OS user must share `--port-directory` (default `/tmp/mc-admin-e2e-ports`). Port locks coordinate cooperating runners; they do not reserve ports against unrelated host processes. A setup-only retry handles a detected port conflict. Tests never retry a failed business operation automatically.

`--workers` bounds live environments, while `--mc-slots` separately bounds Minecraft environments. Both limits are per runner. Recipe affinity keeps compatible cases on one shard for exclusive sequential reuse. `--seed` changes execution order without changing shard membership; `--no-reuse` creates a new environment for every selected case without changing selection or shard assignment.

Additional controls: `--output`, `--docker-socket`, `--setup-timeout`, `--cleanup-timeout`, `--timeout`, `--minecraft-image` and `--minecraft-version`. Use `run -h` for defaults. Exit codes are 0 for success, 1 for test/infrastructure/reporting failure, and 2 for invalid invocation or preparation of the local run directory.

## Reports and cleanup

Each run prints its new directory, normally `.runs/e2e-<random>/`:

```text
plan.json                  selected catalog, shard assignment, seed and order
results.json               image identity, cases, environments, timings and failure phases
junit.xml                  CI test report, including infrastructure failures
manifest.json              durable ownership records and cleanup status
cases/<case-id>.jsonl       redacted steps and scenario API evidence
environments/<id>/         deployed OpenAPI, provider/API trace, recipe and bounded container logs/status
runtime/<id>/              temporary deployment files; removed by cleanup
active.lock                exclusive execution/recovery lock
```

HTTP bodies and errors are redacted; large/binary bodies are represented by size and digest. Container inspect evidence uses a restricted structure that excludes environment variables. Add newly introduced secret values to the redactor before issuing requests. CI uploads the report/evidence paths explicitly and never uploads `runtime/`, which contains real test credentials and mutable data.

Audit one run or the union of all shards from the same executable, immutable application image and selection:

```bash
./bin/mc-admin-e2e coverage --require-complete --output coverage \
  .runs/e2e-local-one .runs/e2e-local-two
```

`coverage.json` and `coverage.md` distinguish successful operation observations, expected rejections, observations from failed cases and unobserved operations. Fixture traffic is excluded. `--require-complete` requires every selected case and shard to pass with trace evidence; it does not impose a 100% route threshold or claim that visiting an endpoint proves the full feature. Missing/duplicate cases and incompatible image/schema/catalog reports remain visible failures.

CI additionally uses `--require-observed` for the full regression selection: a deployed API/WS operation with no case observation fails the audit. This catches new routes omitted from the catalog; an observed rejection still does not establish the successful feature workflow. Filtered smoke/domain/external selections can produce valid partial operation reports without this flag.

Normal completion, assertion failure, SIGINT and SIGTERM all attempt cleanup with a deadline independent of the cancelled test. Cleanup failures fail the run and retain the manifest. After a killed process, host interruption, or recoverable Docker failure, run:

```bash
./bin/mc-admin-e2e cleanup --run-dir /absolute/path/to/.runs/e2e-example-run
```

Use the original canonical directory on the original Docker host. Cleanup refuses an active run and validates resource ownership; it can be repeated. It removes only recorded/labeled containers, recorded Compose networks and that environment's runtime tree. Images and port lock files remain reusable. Root-owned runtime files are reclaimed through a narrowly mounted helper using the same application image, so the runner itself need not run as root. Keep the manifest and runtime directory until cleanup succeeds.

## Development and CI

```bash
gofmt -w cmd internal suites
make check
make build
```

`make lint` checks Go formatting and runs `go vet`. `make test` runs race-enabled framework tests with implicit vet disabled; `make check` runs both targets. The scenarios are compiled into the executable and run with `mc-admin-e2e run`; framework tests verify infrastructure and domain fixture behavior.

[Static Checks](../.github/workflows/static-checks.yml) runs independently on every push: frontend lint and TypeScript checks, backend Ruff and Pyright, and Go formatting/vet. The Docker build bundles frontend assets without invoking the separate TypeScript check.

[The E2E workflow](../.github/workflows/e2e-tests.yml) runs framework unit tests and builds the application and executable once, then distributes them to three independent regression shards. Each shard runs cleanup and uploads diagnostics even when testing fails; a final job audits the complete case/shard union and publishes operation observations. Manual dispatch can disable reuse or select smoke, Mojang, DNSPod or Huawei qualification. DNS selections read the repository's `E2E_EXTERNAL_CONFIG` secret into a private temporary file. New scenarios participate through the catalog without directory-specific CI matrix edits.

New backend features and bug fixes that change observable behavior require an API E2E scenario or an extension to an existing scenario in the same change. Update the coverage inventory, choose explicit isolation, and verify both the normal run and `--no-reuse` for affected cases. Existing pytest tests continue to cover focused internals and broad boundary conditions.
