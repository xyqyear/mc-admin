# MC Admin API E2E

[Documentation index](docs/README.md) · [Contributor rules](AGENTS.md)

Standalone Go executable for testing an actual MC Admin deployment through HTTP, SSE and WebSocket APIs. Each environment runs the repository's application image with a private SQLite database, configuration, credentials and files. Scenarios that need Minecraft or Restic use the real dependencies. Application Python modules are never imported by the runner.

See [architecture and extension contracts](docs/architecture.md), the [backend feature coverage inventory](docs/coverage.md), and the [release qualification requirements](../docs/release.md). One catalog contains smoke, regression and real external-provider scenarios. PR regression, ordinary automatic CI and complete qualification run every current API case except DNSPod; only DNSPod requires explicit selection.

Local validation selects only cases directly related to a change and cases affected through shared dependencies. Complete project, component and browser test suites must run in GitHub Actions, never locally or through directory batches or subagents that reconstruct a full run. Full validation requires the complete qualification for the latest commit SHA; see [repository rules](../AGENTS.md) and [E2E rules](AGENTS.md). Existing static-diagnostic and build requirements still apply.

## Build and run

From the repository root:

```bash
docker build -t mc-admin:e2e .
cd e2e
make build
./bin/mc-admin-e2e run --backend-image mc-admin:e2e \
  --tag regression --case '^files\.directories-search-and-errors$'
```

The selected case is an example for related file-search changes. Replace it with explicit related case IDs for other changes, including cases affected through shared dependencies.

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

## Owned browser and deployment fixtures

```bash
./bin/mc-admin-e2e browser --backend-image mc-admin:e2e \
  --output .runs --run-id browser-local-example -- \
  pnpm --dir ../frontend-react exec playwright test browser/journeys.spec.ts \
  --grep 'lifecycle acceptance stays blocked until task status confirms completion$'
```

This example selects one lifecycle journey. Local browser validation must specify a related spec file and title filter; unfiltered `test:browser` is reserved for CI's complete browser gate.

`browser` provisions the same providers as API cases, invokes one command, then drains its owned process group and cleans the environment on success, failure or cancellation. It keeps the capacity reservation until cleanup ends. The default recipe is `world`; `--recipe base|server|backup|world` selects a smaller fixture for scripts. Each invocation creates a fresh application. Multiple browser cases inside that invocation share application state and must restore their own changes; the wrapper does not reset data between cases.

The command receives `MC_ADMIN_BROWSER_FIXTURE`, pointing to a mode-0600 JSON file with `base_url`, `api_url`, `server_id`, `server_path`, `username`, `password`, `master_token`, `backend_container`, `run_id`, `environment_id`, `image_id` and `manifest_path`. `server_path` is the host project directory; Minecraft data lives in its `data` child. Credentials and this file stay under private `runtime/` and must not be uploaded. A sanitized `fixture-result.json` records the image, recipe, result and separate setup/command/cleanup seconds. An interrupted wrapper can be recovered with the ordinary `cleanup --run-dir` command.

See [disposable deployment and rollback rehearsal](docs/deployment-rehearsal.md) for the released-version data exercise. Browser and deployment scripts use real public APIs and owned filesystem inputs; they do not import application internals or install fault hooks.

## Selection, parallelism and reproduction

```bash
./bin/mc-admin-e2e list
./bin/mc-admin-e2e list --tag regression
./bin/mc-admin-e2e plan --tag regression --case '^files\.directories-search-and-errors$' --seed 42
./bin/mc-admin-e2e run --backend-image mc-admin:e2e --tag regression --case '^files\.directories-search-and-errors$'
./bin/mc-admin-e2e run --backend-image mc-admin:e2e --tag regression --case '^files\.directories-search-and-errors$' --no-reuse --seed 42
```

The CLI defaults to `--tag smoke`; that implementation default is not a local validation recommendation. `--tag regression` includes every current case except DNSPod. `--tag ''` selects all tags, including DNSPod, before applying the other filters; selected external cases require their configuration. Suite, tag and case regex filters intersect. Local runs require `--case` anchored to explicit related IDs, such as `^(case-one|case-two)$`, plus an appropriate explicit tag. A broad suite, tag or case-prefix filter is not sufficient for local validation. A selection matching no scenarios is an error. An empty individual shard is valid when the overall selection is nonempty. The default smoke tag otherwise narrows selection.

Local filters such as `--tag mojang` and `--tag dns` remain available with explicit related case IDs. Real DNS provider cases require `--external-config /private/path/external.json`. CI offers only `regression`, `qualification` and `dnspod` profiles; the first two select the same complete non-DNSPod inventory. See [DNS qualification](suites/dns/README.md) for the private configuration schema, owned test-domain scope and cloud cleanup contract. Missing configuration or unavailable dependencies fail explicitly.

`--workers` limits live environments and `--mc-slots` separately limits Minecraft
environments. `--no-reuse` executes selected cases in separate fresh environments;
`--seed` changes execution priority without changing shard membership. Concurrent
runners on one host must share `--port-directory` (default
`/tmp/mc-admin-e2e-ports`); port locks coordinate cooperating runners only.

See [execution and scheduling](docs/scheduling.md) for atomic groups, capacity,
shards, immutable CI plans and timing history. Local validation still selects
explicit related cases; CI owns complete regression and qualification runs.

Additional controls: `--output`, `--docker-socket`, `--setup-timeout`, `--cleanup-timeout`, `--timeout`, `--minecraft-image` and `--minecraft-version`. Use `run -h` for defaults. Exit codes are 0 for success, 1 for test/infrastructure/reporting failure, and 2 for invalid invocation or preparation of the local run directory.

Capacity waits use the overall run deadline; `--setup-timeout` starts after reservation. Each compensation, verification, diagnostic and teardown phase has its own `--cleanup-timeout` budget. Long SSE bodies use their operation deadline rather than the ordinary request timeout.

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

The report separates reservation, setup, scenario, cleanup and queue timings.
Read [timing semantics](docs/scheduling.md#timing-evidence-and-calibration) before
aggregating them: several measurements overlap, and runner preparation is outside
the execution budget. Go framework JSON evidence is produced by CI's
`make test TEST_FLAGS=-json`; targeted local tests may add `-json` without
broadening their package or test-name selection.

HTTP bodies and errors are redacted; large/binary bodies are represented by size and digest. Container inspect evidence uses a restricted structure that excludes environment variables. Add newly introduced secret values to the redactor before issuing requests. CI uploads the report/evidence paths explicitly and never uploads `runtime/`, which contains real test credentials and mutable data.

Audit one run or the union of all shards from the same executable, immutable application image and selection:

```bash
./bin/mc-admin-e2e coverage --require-complete --output coverage \
  .runs/e2e-ci-one .runs/e2e-ci-two
```

`coverage.json` and `coverage.md` distinguish successful operation observations, expected rejections, observations from failed cases and unobserved operations. Fixture traffic is excluded. `--require-complete` requires every selected case and shard to pass with trace evidence; it does not impose a 100% route threshold or claim that visiting an endpoint proves the full feature. Missing/duplicate cases and incompatible image/schema/catalog, cost fingerprint, capacity configuration or seed remain visible failures.

CI additionally uses `--require-observed` for the full regression selection: a deployed API/WS operation with no case observation fails the audit. This catches new routes omitted from the catalog; an observed rejection still does not establish the successful feature workflow. Filtered smoke/domain/external selections can produce valid partial operation reports without this flag.

Formal qualification additionally audits the frozen plan, current catalog,
candidate identity and owned local/cloud cleanup before publishing timings;
see [CI scheduling and evidence](docs/scheduling.md). A selected-run coverage
report does not replace this audit.

Normal completion, assertion failure, SIGINT and SIGTERM all attempt cleanup with a deadline independent of the cancelled test. Cleanup failures fail the run and retain the manifest. After a killed process, host interruption, or recoverable Docker failure, run:

```bash
./bin/mc-admin-e2e cleanup --run-dir /absolute/path/to/.runs/e2e-example-run
```

Use the original canonical directory on the original Docker host. Cleanup refuses an active run and validates resource ownership; it can be repeated. It removes only recorded/labeled containers, recorded Compose networks and that environment's runtime tree. Images and port lock files remain reusable. Root-owned runtime files are reclaimed through a narrowly mounted helper using the same application image, so the runner itself need not run as root. Keep the manifest and runtime directory until cleanup succeeds.

## Development and CI

```bash
gofmt -w internal/engine/engine_test.go
go vet ./internal/engine
go test -race -vet=off -count=1 -run '^TestShardPartitionIsCompleteAndStable$' ./internal/engine
make build
```

The named file, package and test are examples for related engine changes. Format changed Go files and run vet on explicitly affected packages. Select related framework test names with `-run`, retaining `-race` and `-count=1`; `-vet=off` requires the separate vet check. The scenarios are compiled into the executable and run with `mc-admin-e2e run`; framework tests verify infrastructure and domain fixture behavior.

`make lint` checks Go formatting and runs vet, and is permitted locally.
`make test` runs all packages with race detection; `make check` also runs lint.
Both test targets belong to CI even when extra flags are supplied, because the
Makefile selects `./...`.

[Repository CI](../docs/ci.md) owns the candidate, static, backend, API and browser
gates. [E2E scheduling](docs/scheduling.md) explains the current-profile plan,
private provider configuration, cleanup audits and compatible timing history.
[Release qualification](../docs/release.md) defines artifact identity and promotion.
Latest-commit delivery requirements are in the [root instructions](../AGENTS.md#交付与测试要求).

New backend features and bug fixes that change observable behavior require an API E2E scenario or an extension to an existing scenario in the same change. Update the [coverage index](docs/coverage.md) and affected domain page, choose explicit isolation, and verify both the normal run and `--no-reuse` for explicitly selected affected cases. Existing pytest tests continue to cover focused internals and broad boundary conditions; local runs select related nodes, while CI owns the complete inventory.
