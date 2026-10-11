# Backend CI test planning

This document owns pytest shard allocation, timing and exact execution evidence.
[Testing](testing.md) owns local selection and fixture contracts; [repository CI](../../docs/ci.md)
owns shared history transport, dispatch and full qualification. The commands here
run from `backend/` as CI runner steps; they do not authorize collecting or
executing the full suite locally.

## Plan and execution

`.github/workflows/backend-tests.yml` collects the entire suite and chooses up to 32 nonempty shards targeting 300 seconds of execution, including fixture initialization and cleanup. At most 16 independent runners execute concurrently; queueing and runner preparation are separate costs. The target is a planning estimate, not a timeout or qualification requirement. Each complete test file is an allocation unit. Files that share a fixture boundary can declare `pytestmark = pytest.mark.shard_group("boundary-name")`; all files carrying that label stay together, including their unmarked tests. Overlapping labels join transitively. Module fixtures therefore stay within their file, and session fixtures must own independent per-runner state unless their users declare a shared boundary. Common isolated session fixtures do not force unrelated tests into one shard.

Discovery restores the latest available comparable successful `timing-history-backend` artifact across trusted branches in the same repository, ordered by artifact creation time. The versioned envelope records the run, attempt, source SHA, branch, backend/default profile and compatibility fingerprint. The fingerprint covers dependency/tool pins, fixture configuration, Python/runner settings, coverage and capability policy, without binding to the current application SHA. Absent, expired, incompatible or malformed history falls back to `tests/ci/timing-weights.json`, whose initial estimates come from successful release run 36148282102. Restored phase costs retain per-node setup/call/teardown sums; new node IDs receive a positive 15-second default even inside an existing file. A retained file's prior measured total remains a conservative lower bound, because removing a node that previously paid for module/session fixture setup does not remove that fixture. Entirely deleted files have no scheduling effect. Cold-start unknown files receive a positive 15-second estimate. History affects costs and placement only; current collection and explicit capability policy determine selection.

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

## Related implementation

[Collection](../tests/support/collection.py), [timing](../tests/support/timing.py)
and the [backend workflow](../../.github/workflows/backend-tests.yml) implement
collection, planning and evidence. Read the
[coverage and capability audit](testing.md#release-qualification-and-capability-audit)
before changing the selection policy.
