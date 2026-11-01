# Implementation evidence

Baseline: `029c6fe57ef76b3958b1a97cbec3ae2665b6ec8a`.

## Migration inventory

| Existing read | Owner / consumers | Replacement |
| --- | --- | --- |
| Server status and overview | `routers/servers/misc.py`; sidebar, overview, detail, console, world; server/world/configuration API E2E | Shared monitoring status sample; static server metadata stays separate |
| Server maintenance | `routers/servers/operations.py`; operations/buttons, files/world, overview; recovery E2E | Batch projection from admission, active tasks and holders |
| Server CPU/memory/I/O/disk | `routers/servers/resources.py`; server resource cards, overview; system/server E2E | Shared per-generation samples |
| System info/CPU/disk | `routers/system.py`; overview; system/auth API E2E | Shared host samples; health remains independent |
| Authoritative internal status | `MCInstance`; configuration application, commands, lifecycle tasks, operation recovery, file population, snapshot file restore, world/prune, player sync, self-check, console/RCON | Direct Engine reads with existing operation admission |
| Cache invalidations | servers/files/world/backups operation resource mappings, application OperationObserver | One monitoring query key |
| Process termination | `operations/processes.py`, `utils/exec.py`; all owned binary operations | Same ownership path with positive evidence of absent groups |

## Measurement protocol

Use isolated owned deployments and the baseline application image/check-out, never production. Compare identical fixture server identities, archive contents and game workload. Record warmup separately, then fixed windows for no observers, one observer, ten observers and overview+sidebar. Measure the entire admin container CPU including children, API p50/p95, sample ages, Engine requests, subprocess launches, group scans, loop latency and final thread/FD/process cleanup. Compare 1/6/20 servers; identify simulated Engine scaling separately from real containers. Exclude backup prune from the monitoring comparison and retain a separate concurrent-operation scenario. Store command, image IDs, fixture ownership, measurement duration and cleanup result with each result.

The reproducible driver is [benchmark.py](benchmark.py). Results and limitations
are recorded in [performance.md](performance.md); the historical report is not
used as a substitute for this comparison.

## Targeted verification

All local test commands selected explicit files, nodes or case IDs. Full-suite
execution is reserved for qualification. The following records describe selected
checks, not a sum of distinct tests across overlapping runs.

- `tests/test_docker_reader.py`: 13 passed; structured health, explicit projects,
  additional services, foreign/one-off exclusion, ambiguous Java and cancelled
  SDK calls retain ownership until completion.
- `tests/test_instance.py::test_server_status_lifecycle_with_docker`: passed
  (46.88 s); real start/healthy/restart/stop/down and owned cleanup.
- `tests/test_runtime_monitoring.py`: interval math, stale/partial data,
  generation replacement, maintenance precedence, slow Docker/directory
  isolation and authentication passed. The added malformed YAML test passed.
  Six scaling cases use real SQLite/configuration and a controlled Engine;
  details and loop-delay observations are in the performance report.
- `tests/test_monitoring.py::test_running_container_metrics_observe_real_activity`
  and `tests/configuration/test_owned_docker_rebuild.py`: real Java/cgroup/network,
  stopped metrics and configuration rebuild passed. The snapshot file restore
  guard rejects a live server even when monitoring says CREATED.
- `tests/operations/test_process_descendants.py`: 18 passed; absent group,
  uncertain namespace, permission/unknown errors, previous boot, real zombie,
  surviving child, late fork, ignored TERM, inherited pipes and cancellation.
  Runtime isolation passed alongside it, including independent monitor owners.
- Runtime partial-startup stages and cancelled shutdown passed. Thirteen selected
  snapshot/recovery/cleanup checks passed (83.34 s), including actual Restic
  cancellation, rollback references, unknown-writer deletion blocking, mcmap
  consumer cancellation and image SIGTERM cleanup.
- Selected lifecycle, registry sync, creation identity and archive-population
  tests passed. Four population tests initially exposed obsolete Compose test
  substitutes; replacing the external Engine observation boundary retained the
  real SQLite/archive/file assertions. All seven population cases then passed.
- Frontend overview/console/HTTP initially passed 18 selected tests; related
  world/sidebar/buttons passed 33. The final overview/monitoring selection passed
  eight cases, including healthy-only player display, one periodic source,
  hidden/offline pauses, stale HTTP failures and late-session isolation.

### Deployed API and browser runs

Run evidence lives under `/root/.local/share/mc-admin-e2e/` on the local WSL host.
Every listed manifest was inspected and all environment `cleaned` flags are true.

| Run | Explicit selection | Result |
| --- | --- | --- |
| `e2e-85027c176b2a` | `system.metrics-static-validation`, `minecraft.shared-monitoring`, `minecraft.stopped-and-invalid-requests` | 3 passed, normal mode |
| `e2e-15f225b98eb8` | Above three plus `world.safety-snapshot-disconnect`, `world.disconnect-restore-and-maintenance` | 5 passed, `--no-reuse` |
| `e2e-468c63f075ec` | The two world cases above | 2 passed, normal mode |
| `browser-5547662e512e` | `browser/monitoring.spec.ts`, shared observation/navigation/failure/real restart | 1 passed (25.4 s) |
| `browser-8a5039f017ef` | `browser/journeys.spec.ts`, lifecycle acceptance and disconnected reversible world restoration | 2 passed (17.8 s, 52.4 s) |

The Minecraft fixture image is the locally available
`itzg/minecraft-server:java25-issue150-offline` (real Vanilla 1.21.11), explicitly
selected for isolated local checks. Production was neither accessed nor changed.

### Contract and coverage replacement

The removed Compose text-parser tests are replaced by structured Engine identity,
label and health tests plus the real lifecycle case. Per-request one-second CPU
tests are replaced by independent interval/reset examples and a real busy
process counter test. The deleted overview endpoint's aggregation test is
replaced by shared monitoring failure/registry tests and frontend healthy-only
player presentation; static registry drift coverage remains in its owner.
The reviewed API fixture follows the new monitoring contract, with route
authorization still checked independently.

### Static and delivery checks

Backend Pyright and Ruff passed. Frontend lint/import boundaries, type checking,
OpenAPI contract freshness and production bundle passed. A separate browser
TypeScript project now resolves the same application aliases for imported wire
contracts. Affected Go packages passed vet and the runner build. Main OpenSpec
specifications and the change passed strict validation. Qualification and final
commit evidence are recorded after the latest pushed SHA is verified.
