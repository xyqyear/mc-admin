# Backend testing and compatibility baselines

Run commands from `backend/` with `uv`. Install the locked development environment with `uv sync --locked --all-groups`.

## Local targeted validation

Run only the files, nodes, or small directories directly related to the change. The examples below are alternatives for the affected behavior, not a checklist. Do not run a repository-wide or component-wide test suite locally, or accumulate one by splitting directories, looping shards, or delegating slices to other agents. Complete collection and execution belong to GitHub Actions on the latest committed SHA; the CI examples below are not local entrypoints.

```bash
# File-operation changes: select the relevant test file.
uv run pytest tests/files/test_file_operations.py --require-capabilities

# Execution-history changes: select one exact test node.
uv run pytest tests/cron/test_cron_api.py::TestCronJobAPI::test_get_cronjob_executions_with_limit --require-capabilities

# Narrow the related directory to execution-history cases.
uv run pytest tests/cron/ -k get_cronjob_executions --require-capabilities

# Archive logic that does not invoke a real binary.
uv run pytest tests/archive/test_archive_compression.py -m 'not binary'

# Explicitly enable a related owned Docker integration node.
uv run pytest tests/test_instance.py::test_server_status_lifecycle_with_docker --run-docker --require-capabilities

uv run pyright
uv run ruff check .
```

## Isolation and capabilities

`tests/conftest.py` configures an owned temporary application root before importing application modules. The pytest session explicitly owns the runtime used during collection; every test then binds a fresh `Runtime`. Each test owns its SQLite, log, server and archive directories as well as its manager state and caches. Static fixtures, test configuration files and archive upload scratch files remain in the session-owned root. Inherited JWT, audit, and Restic connection settings are removed. Explicit `create_app(runtime=...)` apps retain their own runtime. Fixture teardown awaits runtime closure; tests must still join independently constructed managers and resources outside the runtime. See `runtime.md` for application construction and lifecycle verification.

Replace external adapters through `tests.support.runtime.set_runtime_resource` or `patch_runtime_resource`, which restore the individual resource on the current test's runtime. Patching a removed module-level singleton cannot isolate an application. Multiple feature getters for one resource intentionally return the same object. Use `patch_settings` to change fields on the actual owned settings object while preserving its other valid configuration and restoring fields afterward. Database and adapter fixtures normally have function scope so their overrides bind to the runtime that executes the test.

Capabilities are declarations, not naming conventions:

| Marker | Meaning | Default behavior |
| --- | --- | --- |
| `@pytest.mark.binary("fd")` | Real fd file discovery | Skip if unavailable |
| `@pytest.mark.binary("restic")` | Real isolated Restic repository | Skip if unavailable |
| `@pytest.mark.binary("mcmap")` | Real mcmap subprocess | Skip if unavailable |
| `@pytest.mark.binary("7z")` | Real archive subprocess | Skip if unavailable |
| `@pytest.mark.docker` | Docker daemon and owned containers/networks | Deselect unless `--run-docker` |
| `@pytest.mark.external` | Explicit external service dependency | Deselect unless `--run-external` |

`--require-capabilities` fails before execution if a selected local binary is missing. `FD_BINARY_PATH`, `RESTIC_BINARY_PATH`, and `MCMAP_BINARY_PATH` select binary locations. Strict marker validation rejects unknown markers and malformed binary declarations. Pure tests that accidentally execute a known installed binary fail. Docker subprocesses and SDK clients are blocked in tests without the Docker marker and explicit opt-in. Adapter mocks can still replace those boundaries.

Docker fixtures generate a random owner identifier and container names. They ask Docker to allocate available host ports and inspect the owned container's actual port bindings. They label containers and Compose networks, inspect ownership before removal, and remove verified Docker IDs. A same-name resource belonging to someone else is rejected. Cleanup attempts the other registered resources if one removal fails. No fixture removes `mc-testserver1` or `/tmp/test_temp_dir`. Tests execute sequentially inside each runner; independent CI runners provide the parallelism, without pytest workers sharing a Docker host.

`tests/testing/test_isolation.py` verifies default paths, CLI/SDK guards, owner mismatch refusal, cleanup continuation, and a subprocess run of the ordinary instance tests with a fake Docker executable. Its fault-injection subprocesses replace the snapshot restriction with an always-allow function and disable audit matching. Both regression suites must return a failing exit status. Snapshot window cases assert both sides of each configured time boundary; audit cases assert decisions and emitted files instead of printing mismatches.

## CI full collection and shards

`.github/workflows/backend-tests.yml` collects the entire suite and chooses up to 32 nonempty shards targeting 300 seconds of execution, including fixture initialization and cleanup. At most eight independent runners execute concurrently; queueing and runner preparation are separate costs. The target is a planning estimate, not a timeout or qualification requirement. Each complete test file is an allocation unit. Files that share a fixture boundary can declare `pytestmark = pytest.mark.shard_group("boundary-name")`; all files carrying that label stay together, including their unmarked tests. Overlapping labels join transitively. Module fixtures therefore stay within their file, and session fixtures must own independent per-runner state unless their users declare a shared boundary. Common isolated session fixtures do not force unrelated tests into one shard.

Discovery restores the latest available comparable successful `timing-history-backend` artifact from the current branch, then trusted main. The versioned envelope records the run, attempt, source SHA, branch, backend/default profile and compatibility fingerprint. The fingerprint covers dependency/tool pins, fixture configuration, Python/runner settings, coverage and capability policy, without binding to the current application SHA. Absent, expired, incompatible or malformed history falls back to `tests/ci/timing-weights.json`, whose initial estimates come from successful release run 36148282102. Restored phase costs retain per-node setup/call/teardown sums; new node IDs receive a positive 15-second default even inside an existing file. A retained file's prior measured total remains a conservative lower bound, because removing a node that previously paid for module/session fixture setup does not remove that fixture. Entirely deleted files have no scheduling effect. Cold-start unknown files receive a positive 15-second estimate. History affects costs and placement only; current collection and explicit capability policy determine selection.

Every shard also pays a fixed pytest session estimate. Successful history uses the maximum nonnegative difference between session duration and summed node phases across all shards, retaining collection, plugin and session-finalization work without double-counting fixture phases. Cold starts use ten seconds. This estimate excludes CI installation and queueing. The planner reserves it before assigning groups; if the fixed cost alone reaches the target, it makes one bounded best-effort allocation and reports `fixed_overhead` rather than dividing by a nonpositive budget or creating shards indefinitely.

The planner sorts atomic groups by descending cost and uses stable file names and shard indexes to break ties. It reserves individual shards for oversized groups when capacity permits. For the remaining groups it starts from the total-cost lower bound and increases the shard count until longest-first allocation meets the target or reaches the shard limit. When capacity cannot keep every oversized group separate, complete groups share shards. The plan records the largest atomic cost including session overhead, oversized groups and `oversized_unit`/`shard_limit` reasons; it never splits a file, suppresses tests or loops indefinitely to satisfy the soft target.

The plan binds the complete inventory, selected node IDs, capability declarations, fixture labels and selection policy with a canonical SHA-256 digest, and records the frozen historical source and snapshot digest. Every shard consumes the same plan; there is no reassignment during execution. Each shard declares the union of its required tools; CI installs Dockerfile-pinned binaries with checksum verification and requires their presence. At execution, pytest recollects the inventory and applies the same Docker/external, marker and keyword policy before validating and selecting its planned assignment. `--test-group` remains available locally for first-level directories and the top-level `root` group, but cannot combine with a plan. It must stay within the directly relevant local scope and must not be used to accumulate a full suite.

Inventory, immutable plan, executed collection, JUnit and exact phase timings are separate artifacts. `--timing-report` records every setup/call/teardown outcome and duration, including setup, assertion and teardown failures. Session completion runs after runtime cleanup; a failure there leaves the report incomplete. JSON is atomically published at session finish, including normal failing or interrupted sessions. An uncatchable process termination can leave no report, which fails the audit. Reports contain node IDs and timing/outcome metadata, without captured output or traceback contents.

The final audit verifies plan identity, complete metadata, each shard's exact assignment, duplicate-free node-ID union and execution evidence bound to its collection manifest. Every selected node must have exactly one successful setup, call and teardown; failed, skipped, xfailed, incomplete or missing evidence fails qualification. JUnit and timing reports do not replace test assertions or the independent matrix success gate. The report adapter repeats the audit before exporting file and node costs; history is wrapped and uploaded only after execution, aggregate audit and coverage processing succeed. Successful reusable history remains available for 90 days; failed evidence is diagnostic and cannot replace it. External-service tests remain excluded until a CI environment explicitly opts in. Coverage stays enabled in each shard; raw coverage data is combined once for reports.

The following commands describe CI runner steps only. Discovery also restores the historical snapshot through `scripts/ci/timing_history.py`; Actions executes every generated matrix assignment and audits their union. A local shard run or local shard loop does not provide complete qualification.

```bash
# CI discovery runner.
uv run pytest tests --collect-only --run-docker -o addopts= -q \
  --collection-manifest /tmp/mc-admin-inventory.json
uv run --no-project python tests/support/collection.py plan /tmp/mc-admin-inventory.json \
  --weights tests/ci/timing-weights.json --history /tmp/mc-admin-history.json \
  --target-seconds 300 --max-shards 32 --output /tmp/mc-admin-plan.json
# Each CI matrix runner executes its assigned shard; shard 1 is shown.
uv run pytest tests --run-docker --require-capabilities \
  --test-plan /tmp/mc-admin-plan.json --test-shard 1 \
  --collection-manifest /tmp/manifests/shard-1.json \
  --timing-report /tmp/timings/timing-1.json --junitxml /tmp/junit/shard-1.xml
# CI audit runner receives every executed manifest and timing report.
uv run --no-project python tests/support/collection.py audit /tmp/mc-admin-inventory.json \
  /tmp/manifests/shard-*.json --plan /tmp/mc-admin-plan.json --timings /tmp/timings/timing-*.json
```

JUnit reports include per-case totals; the phase JSON supplies the separate setup/call/teardown measurements needed to review future weights. Fixture setup and teardown remain charged to the cases where pytest executes them, so whole-file or shared-boundary costs are aggregated before balancing and retained file totals protect shared setup attribution. Concurrent shard durations cannot be summed into a workflow wall-clock duration. The fixed session residual accounts for pytest work outside node phases; post-pytest coverage reporting and runner preparation remain separate costs.

## Executable module boundaries

`tests/architecture/test_import_boundaries.py` scans production Python imports. Feature modules cannot import HTTP routers, another feature's private symbols or private modules, retired compatibility modules, or the eager application metadata registry. Runtime resources use named, typed accessors; transparent proxies and import-time factory registration are rejected. The rule checks both full module imports and aliases such as `from app.servers import rebuild`. Fault snippets prove each prohibited dependency is detected. Architecture tests automatically enter the CI shard plan.

```bash
uv run pytest tests/architecture
```

These checks enforce dependency direction. Runtime isolation, command ownership, persistence, cancellation, and API behavior still require the corresponding integration tests.

`tests/operations/test_target_revalidation_cancellation.py` holds real SQLite server-query results before cursor consumption and cancels durable tasks at startup and resource-lease acquisition. It checks the cancelled journal result, absence of external work, lease release and an independent database writer. Asyncio and AnyIO cancellation, repeated cancellation during session close, close failures and server-identity conflicts retain their original semantics; test gates select the boundary without production sleeps or retries.

## API and protocol fixture

`tests/contracts/fixtures/api-contract.json` contains:

- All declared HTTP operations and WebSocket routes, including their dependencies, role restrictions, and cookie-CSRF applicability.
- Request/response schemas and recursively referenced models for representative authentication, task, upload, Compose, operation, file, maintenance, self-check, DNS, map and world-restore paths, including 202 acceptance for non-snapshot tasks.
- Public event, task progress/result, and task status/type schemas.

`test_api_contract.py` compares the live declarations and schemas directly with the reviewed fixture; provenance is recorded alongside it. A declaration comparison cannot prove every role combination or stream lifecycle works at runtime. Domain integration tests and Go API E2E remain responsible for those behaviors; see [administration-contracts.md](administration-contracts.md).

To review an intended contract change, generate a separate candidate and inspect its diff before replacing the fixture:

```bash
uv run python -m tests.support.api_contract --output /tmp/api-contract-candidate.json
```

## Released database fixture

`tests/contracts/fixtures/releases/v5.3.0.sql` is a synthetic database created by the model and startup migration code archived from release `v5.3.0`, commit `da30f4b033a386dc97ea72254e3ec0a4b0bdab1f`. Its companion JSON records the revision and SQL digest. It includes users, active/removed servers, a template snapshot, player history, an open session, a paused schedule, execution history, a restoration, and dynamic configuration. It contains no production records, usable password hashes, or credentials.

`test_release_upgrade.py` loads that SQL into a disposable database, runs current startup migrations twice, verifies all original row values and IDs, verifies subsequent ID allocation, and reads representative data through the API. This fixture covers that specific released schema. Duplicate-session repair and migration rollback have separate fixtures and tests under `tests/migrations/`.

Regeneration requires the pinned local Git release object and runs the released startup code in an isolated archive; it does not create an old schema by downgrading current metadata:

```bash
uv run python tests/support/release_fixture.py
uv run pytest tests/contracts/test_release_upgrade.py
```

## Workload observations

`tests/support/workload_baseline.py` creates only owned temporary resources and measures three samples of four workloads. The current application runs inside an explicitly owned runtime, which closes before its temporary directory is removed. The `--app-ref` adapter also supports the original released global-resource entry point inside a separate process and temporary source archive. Both paths exercise in-process HTTP and adapters without starting application lifespan or background producers.

| Workload | Behavior asserted |
| --- | --- |
| Upload, SHA256, and publish | 4 MiB in four chunks, ten HTTP requests, stale in-progress offset returns 409, a completed retry returns 200, HEAD offset, SSE completion/hash, publication only after verification, exact final bytes |
| File search | 256 files in 16 directories, one MiB total, exact result count and byte count through real fd |
| Restic backup and restore | Repository initialization, four-MiB backup, streamed restore, exact restored bytes and hash |
| mcmap chunk adapter | Real removal command against a synthetic empty 8 KiB region, typed events and preserved region content |

```bash
# Reproduce the pre-change application in a temporary Git archive.
uv run python -m tests.support.workload_baseline \
  --app-ref 9cf6f77b258a7ccf4507c51cb686a45f8f74d823 \
  --output /tmp/workload-before.json
# Measure the current application with the same workload.
uv run python -m tests.support.workload_baseline --output /tmp/workload-after.json
```

`workload-head.json` and `workload-current.json` record the initial observations, binary versions, individual durations, medians, behavior counters, and process-wide peak RSS. Their behavior counters match exactly. The local tools were fd 10.3.0, Restic 0.18.0, and mcmap 0.8.4; CI uses the Dockerfile pins (fd 10.4.2, Restic 0.18.1, mcmap 0.8.4). These local runs therefore do not replace the pinned candidate-image checks.

Timings use an in-process ASGI client on a shared development host, with warm imports and possible competing tests. They are reproducible workload definitions and observations, not controlled performance estimates or CI thresholds. RSS is for the whole Python process, and the mcmap case checks an empty-region protocol rather than map rendering throughput. Rendering, browser polling/request counts and candidate-image latency have separate deployed observations in [workload measurements](workload-measurements.md) and [browser verification](../../frontend-react/docs/browser-tests.md); the native baseline alone cannot establish them.

## Release qualification and capability audit

The collected inventory includes each test's capability and fixture-boundary declarations plus the explicit Docker, external-service, marker-expression and keyword selection policy. CI derives its matrix from the selected identities, so externally qualified tests remain deliberately excluded unless opted in. Every shard reports the same complete inventory and metadata, the same selection policy, and only its planned identities. The audit rejects omissions, duplicates, extra identities, changed declarations and policy drift.

Four independent backend runners execute their tests sequentially; no pytest worker parallelism is enabled. Docker tests require both their marker and `--run-docker`, while ordinary tests retain the subprocess/SDK guard even in a Docker-enabled suite. A completed collection manifest is not evidence that execution passed: the audit checks phase outcomes and the workflow independently requires the test matrix result to be successful.

`tests/ci` contains executable collection and release-gate regression checks and is discovered like every other test group. The publication graph, immutable OCI archive, distinction between manifest/config digests and local validation commands are documented in [release qualification](../../docs/release.md). Current representative measurements and their limitations are recorded in [workload measurements](workload-measurements.md).

## Unified world recovery regression ownership

`tests/snapshots/test_world_commands.py` and `test_world_recovery.py` exercise the common task entrypoints with real Restic and mcmap: four selection scopes, multiple roots/dimensions, unselected data, source absence, repeated rollback, protected sidecars, negative-coordinate external MCC chunks and precise cache cleanup. `test_world_history.py` covers legacy scope decoding, corrupt absence evidence, generation changes and safety failures/cancellation without live markers. `test_world_endpoints.py` verifies 202 acceptance, maintenance/stopped conflicts and shared history. `tests/world/` retains layout, selection confinement, preview, identity and cache adapter coverage. `tests/snapshots/test_previews.py` and related preview tests cover task preparation, binding freshness, pagination, TTL, protected map copies and cleanup before terminal cancellation. `test_observation_endpoints.py` verifies database-only active discovery, filtered history and lightweight protection feedback. `test_deletion_guards.py` exercises accepted/queued/global references before and during deletion admission. Common task tests replace obsolete restore/preview SSE orchestration tests.
