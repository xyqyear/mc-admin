# MC Admin API E2E

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

For concurrent CI processes, use the same executable, selection, shard count, worker/Minecraft limits and seed, and a different shard index and run ID for each process:

```bash
./bin/mc-admin-e2e run --backend-image mc-admin:e2e --tag regression --shard 1/2 --run-id e2e-ci-one
./bin/mc-admin-e2e run --backend-image mc-admin:e2e --tag regression --shard 2/2 --run-id e2e-ci-two
```

These complete-regression examples run in separate CI jobs, not local terminals. On a shared Docker host, runners under the same OS user must share `--port-directory` (default `/tmp/mc-admin-e2e-ports`). Port locks coordinate cooperating runners; they do not reserve ports against unrelated host processes. A setup-only retry handles a detected port conflict. Tests never retry a failed business operation automatically.

`--workers` bounds live environments, while `--mc-slots` separately bounds Minecraft environments. Both limits are per runner and participate in cost-aware planning. Fresh cases and compatible reusable recipe groups remain atomic. `--no-reuse` keeps the selected cases but splits them into individual Fresh groups, so placement and shard count can change; CI uses a separate history profile for that policy. The dispatcher skips temporarily blocked groups so ordinary work can continue while another group occupies Minecraft capacity. `--seed` changes execution priority without changing shard membership.

Direct filtered `plan`/`run` uses the compiled positive fallback costs. CI's `ci-plan` collects the required current profile and freezes compatible audited history, source SHA, image ID, executable digest, costs, capacity, seed and all assignments in `api-planning/plan.json`, uploaded as the `api-plan` artifact. Every job executes that file through `run --execution-plan`; jobs never independently restore history. `ci-audit` independently reconstructs the requested profile from the executable's current catalog, so missing regression tags or historical selections cannot narrow the required non-DNSPod inventory.

Automatic CI planning globally allocates every atomic group selected by a profile into one matrix, targeting 300 seconds including fixture initialization, case lifecycle work and cleanup. It permits up to 16 total shards and eight concurrent jobs; each runner uses two workers and one Minecraft slot. Groups with different provider dependencies may share a shard. Provider dependencies select required private configuration and recovery steps. Every API shard uses the unrestricted `dns-e2e` configuration store; only provider steps receive their required credentials. Preflight/image preparation, checkout, dependency installation and OCI loading are outside this execution budget. Indivisible oversized groups, fixed cleanup overhead and bounded capacity can prevent the target; the target does not shorten scenario deadlines or fail an otherwise successful scenario. Reusable-group history retains a lifecycle floor when members are removed and adds positive estimates for new members, preserving setup/teardown costs that were attributed to another case. api-lifecycle-v2 costs and their compatibility fingerprint remain reusable when only placement changes.

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

Case `seconds` includes all execution lifecycle phases after dispatch, including final reusable-group teardown. `timings` separates reservation, setup, scenario execution, compensation, verification, diagnostics and teardown. Scheduler queue time and its overlapping Minecraft-capacity wait are recorded separately on the first case of each group; they are excluded from case execution seconds. Run-level `preparation_seconds` records preflight/image preparation outside the soft budget; `cleanup_seconds` and `recovery.json` record final journal cleanup and unconditional workflow recovery. `Scope.Step` durations cover only explicitly declared steps. See [timing semantics and historical calibration](docs/architecture.md#timing-evidence-and-calibration) before aggregating these overlapping measurements. CI framework checks emit Go test JSON with `make test TEST_FLAGS=-json` while preserving race detection; targeted local `go test` commands can add `-json` without broadening their package or `-run` selection.

HTTP bodies and errors are redacted; large/binary bodies are represented by size and digest. Container inspect evidence uses a restricted structure that excludes environment variables. Add newly introduced secret values to the redactor before issuing requests. CI uploads the report/evidence paths explicitly and never uploads `runtime/`, which contains real test credentials and mutable data.

Audit one run or the union of all shards from the same executable, immutable application image and selection:

```bash
./bin/mc-admin-e2e coverage --require-complete --output coverage \
  .runs/e2e-ci-one .runs/e2e-ci-two
```

`coverage.json` and `coverage.md` distinguish successful operation observations, expected rejections, observations from failed cases and unobserved operations. Fixture traffic is excluded. `--require-complete` requires every selected case and shard to pass with trace evidence; it does not impose a 100% route threshold or claim that visiting an endpoint proves the full feature. Missing/duplicate cases and incompatible image/schema/catalog, cost fingerprint, capacity configuration or seed remain visible failures.

CI additionally uses `--require-observed` for the full regression selection: a deployed API/WS operation with no case observation fails the audit. This catches new routes omitted from the catalog; an observed rejection still does not establish the successful feature workflow. Filtered smoke/domain/external selections can produce valid partial operation reports without this flag.

Formal CI uses `ci-audit` against the frozen run-level plan and an independently requested profile before publishing history. It requires exact current assignments and provider dependencies, passed results, matching candidate/executable identities, every owned environment cleaned and recorded cloud cleanup completed. Any missing, skipped or failed required case fails the audit. General `coverage` remains useful for reading selected-run operation reports; it does not replace this qualification audit.

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

CI runs the full framework suite:

```bash
make lint
make test
make test TEST_FLAGS=-json
make check
```

`make lint` checks Go formatting and runs `go vet`; this static check is also permitted locally. `make test` tests all packages with race detection, implicit vet disabled and uncached results; `make check` runs both targets. `make test` and `make check` are not local validation commands, even when extra test flags are supplied, because the Makefile always selects `./...`.

[Static Checks](../.github/workflows/static-checks.yml) runs independently on every push: frontend lint and TypeScript checks, backend Ruff and Pyright, and Go formatting/vet. The Docker build bundles frontend assets without invoking the separate TypeScript check.

[The candidate workflow](../.github/workflows/candidate.yml) runs framework race tests and builds one application OCI archive and executable. [The E2E workflow](../.github/workflows/e2e-tests.yml) verifies those inputs, freezes one complete current-profile plan and audited history snapshot, and derives one globally allocated job matrix. Each shard runs cleanup and uploads diagnostics even when testing fails. Every API shard uses the unrestricted `dns-e2e` configuration store, with required private configuration supplied to provider steps according to shard dependencies. Explicit DNSPod selection uses `E2E_EXTERNAL_CONFIG`. Browser qualification consumes the same artifact. Release promotion preserves its OCI manifest digest; see [release qualification](../docs/release.md).

The final API job audits expected cases, operation observations and owned local/cloud cleanup before writing `costs.json` and publishing `timing-history-api/history.json` for 90 days. The shared transport selects comparable successful audited history from the same branch, then main, freezes its run/attempt/SHA/branch/artifact source and compatibility fingerprint, and falls back to committed positive costs when unavailable or invalid. Compatibility includes dependency/Docker inputs, measurement version, fixture recipes, reuse policy and worker/Minecraft limits. New scenarios participate through the current catalog without directory-specific matrix edits or historical inventory updates.

New backend features and bug fixes that change observable behavior require an API E2E scenario or an extension to an existing scenario in the same change. Update the coverage inventory, choose explicit isolation, and verify both the normal run and `--no-reuse` for explicitly selected affected cases. Existing pytest tests continue to cover focused internals and broad boundary conditions; local runs select related nodes, while CI owns the complete inventory.
