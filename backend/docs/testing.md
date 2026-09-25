# Backend testing and compatibility baselines

Run commands from `backend/` with `uv`. Install the locked development environment with `uv sync --locked --all-groups`.

## Isolation and capabilities

`tests/conftest.py` configures an owned temporary application root before importing application modules. The pytest session explicitly owns the runtime used during collection; every test then binds a fresh `Runtime`. Each test owns its SQLite, log, server and archive directories as well as its manager state and caches. Static fixtures, test configuration files and archive upload scratch files remain in the session-owned root. Inherited JWT, audit, and Restic connection settings are removed. Explicit `create_app(runtime=...)` apps retain their own runtime. Fixture teardown awaits runtime closure; tests must still join independently constructed managers and resources outside the runtime. See `runtime.md` for application construction and lifecycle verification.

Replace external adapters through `tests.support.runtime.set_runtime_resource` or `patch_runtime_resource`, which restore the individual resource on the current test's runtime. Patching a removed module-level singleton cannot isolate an application. Multiple feature getters for one resource intentionally return the same object. Use `patch_settings` to change fields on the actual owned settings object while preserving its other valid configuration and restoring fields afterward. Database and adapter fixtures normally have function scope so their overrides bind to the runtime that executes the test.

```bash
# Run all tests that do not require Docker or external services.
uv run pytest tests

# Require installed local binaries instead of skipping their tests.
uv run pytest tests --require-capabilities

# Select tests without declared local binary dependencies.
uv run pytest tests -m 'not binary'

# Explicitly enable owned Docker integration tests.
uv run pytest tests --run-docker --require-capabilities

uv run pyright
uv run ruff check .
```

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

Docker fixtures generate a random owner identifier and container names. They label containers and Compose networks, inspect ownership before removal, and remove verified Docker IDs. A same-name resource belonging to someone else is rejected. Cleanup attempts the other registered resources if one removal fails. No fixture removes `mc-testserver1` or `/tmp/test_temp_dir`. These fixtures are still run serially; random names do not establish that fixed host ports or shared application state support parallel execution.

`tests/testing/test_isolation.py` verifies default paths, CLI/SDK guards, owner mismatch refusal, cleanup continuation, and a subprocess run of the ordinary instance tests with a fake Docker executable. Its fault-injection subprocesses replace the snapshot restriction with an always-allow function and disable audit matching. Both regression suites must return a failing exit status. Snapshot window cases assert both sides of each configured time boundary; audit cases assert decisions and emitted files instead of printing mismatches.

## CI collection

`.github/workflows/backend-tests.yml` collects the entire suite and derives its matrix from collected test identities. Groups are the first directory below `tests/`, with top-level files grouped as `root`. Each group reports its declared capabilities. CI installs Dockerfile-pinned fd, Restic, and mcmap binaries with checksum verification, then runs the group with required capabilities enabled.

The inventory and every selected group are uploaded as JSON artifacts. A final audit rejects missing, unexpected, or duplicate test identities. Test execution failures independently fail their matrix jobs. A collection manifest proves selection, not successful execution or meaningful business assertions. New groups enter the matrix without a manually maintained directory list. External service tests need an explicitly configured CI environment before their marker can be enabled.

```bash
uv run pytest tests --collect-only --run-docker -o addopts= -q \
  --collection-manifest /tmp/mc-admin-inventory.json
uv run python tests/support/collection.py matrix /tmp/mc-admin-inventory.json
uv run pytest tests --collect-only --run-docker --test-group contracts \
  -o addopts= -q --collection-manifest /tmp/mc-admin-contracts.json
# Supply all group manifests, not just the example group above.
uv run python tests/support/collection.py audit /tmp/mc-admin-inventory.json /path/to/groups/*.json
```

A local verification collected all 21 actual groups independently and checked their exact union: 1,770 test identities, with no omissions or duplicates. Counts describe that capture; they are not coverage or release targets.

## Executable module boundaries

`tests/architecture/test_import_boundaries.py` scans production Python imports. Feature modules cannot import HTTP routers, another feature's private symbols or private modules, retired compatibility modules, or the eager application metadata registry. Runtime resources use named, typed accessors; transparent proxies and import-time factory registration are rejected. The rule checks both full module imports and aliases such as `from app.servers import rebuild`. Fault snippets prove each prohibited dependency is detected. The architecture directory automatically enters the CI collection matrix.

```bash
uv run pytest tests/architecture
```

These checks enforce dependency direction. Runtime isolation, command ownership, persistence, cancellation, and API behavior still require the corresponding integration tests.

## API and protocol fixture

`tests/contracts/fixtures/api-contract.json` contains:

- All 153 HTTP operations and three WebSocket routes, including their declared dependencies, role restrictions, and cookie-CSRF applicability.
- Request/response schemas and recursively referenced models for 14 representative authentication, task, upload, Compose, operation, file, maintenance, and world-restore paths.
- Public event, task progress/result, and task status/type schemas.

`test_api_contract.py` compares the live declarations and schemas with this fixture. The initial capture was independently reproduced from an unmodified archive of commit `9cf6f77b258a7ccf4507c51cb686a45f8f74d823`; provenance is recorded alongside the fixture. A declaration comparison cannot prove every role combination or stream lifecycle works at runtime. Domain integration tests and Go API E2E remain responsible for those behaviors; see [administration-contracts.md](administration-contracts.md).

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

The collected inventory includes each test's capability declarations and the explicit Docker, external-service and marker-expression selection policy. CI derives its matrix from the selected identities, so externally qualified tests remain deliberately excluded unless opted in. Every shard must report the same complete inventory and capability metadata, the same selection policy, and only its declared group's identities. The audit rejects omissions, duplicates, extra identities, changed declarations and policy drift.

Backend groups currently run serially (`max-parallel: 1`); no pytest worker parallelism is enabled. Docker tests require both their marker and `--run-docker`, while ordinary tests retain the subprocess/SDK guard even in a Docker-enabled suite. A completed collection manifest is not evidence that execution passed: the CI audit also requires the test matrix result to be successful.

`tests/ci` contains executable collection and release-gate regression checks and is discovered like every other test group. The publication graph, immutable OCI archive, distinction between manifest/config digests and local validation commands are documented in [release qualification](../../docs/release.md). Current representative measurements and their limitations are recorded in [workload measurements](workload-measurements.md).
