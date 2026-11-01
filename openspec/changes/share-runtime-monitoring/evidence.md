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
specifications and the change passed strict validation. Complete qualification
evidence is recorded below; subsequent documentation-only commits use the
coordinator's checked content-equivalent qualification.

## Qualification follow-up

The first manual qualification of `bf7b722851c3a6c3ccc6c358a928e531e7324ddc`,
[run 41314770929](https://github.com/xyqyear/mc-admin/actions/runs/41314770929),
passed candidate/Go, static/frontend, all 14 backend shards and their audit,
and all three browser shards and their audit. API shard 5 failed three cases;
the qualification was not accepted.

`minecraft.scheduled-restart` and `minecraft.console-safe-adapter-errors` could
read a previous HEALTHY sample after task settlement, then hit the command's
correct live-state rejection. The shared fixture now requires a ready sample
captured after the wait begins; it does not weaken the RCON/game-state assertions
or force sampling through HTTP. A protocol test supplies old HEALTHY, fresh
STARTING and fresh HEALTHY in sequence and verifies the wait only accepts the
last observation.

`players.live-profile-and-skin` failed because the runner timed out fetching the
Mojang profile, confirmed by `skin_fetcher:fetch_player_profile` diagnostics.
Its external reachability and persistence assertions remain unchanged.

The readiness correction passed the race-enabled fixture protocol test, affected
Go vet/build, both real cases normally (`e2e-f4e78d392697`) and with `--no-reuse`
(`e2e-6d5699dd1ecd`), and the shared monitoring browser journey
(`browser-29d6115de355`, 32.0 s). All owned environments were cleaned. The browser
fixture applies the same freshness requirement, and frontend lint/types passed.
The local external Mojang probe (`e2e-85f9f374a1ec`) also timed out; direct host
access returned HTTP 502 after 12.77 s, while the configured host proxy returned
200. This distinguishes local direct-network failure from the monitoring change;
it does not establish the GitHub runner's upstream network cause.

The push-triggered qualification of `25bb6bd1393ce72aff3108cbc17a86968146bfd5`,
[run 41318043542](https://github.com/xyqyear/mc-admin/actions/runs/41318043542),
passed all backend and API shards/audits, including Mojang, plus static and
candidate/Go checks. One browser shard exposed a startup mutation bug: after
down, a cached CREATED sample made the UI submit Compose start for an absent
container. The resulting daemon failure correctly retained recovery blocking,
causing subsequent journeys on that environment to fail as well.

A real Docker regression reproduced `service "mc" has no container to start`
before the fix. The UI now submits startup intent, and the backend decides
creation versus starting inside its existing operation lease using live state.
The real regression passed (46.62 s), proving creation against stale CREATED,
preservation of the existing container ID and game mode against stale EXISTS,
successful RCON, durable success records and no recovery block. Nine selected
daemon history/cancellation checks also passed; uncertain mutation ownership
still blocks conflicting restores. The browser lifecycle journey supplies a
deliberately old CREATED observation and passed (20.0 s,
`browser-62dee5f6d31c`). The public shared-monitoring case covers down followed
directly by startup intent and verifies the running game through RCON.
It passed normally (`e2e-07592bcf9750`, 49.0 s) and with `--no-reuse`
(`e2e-ff7d2d0b2e4c`, 48.4 s); cleanup manifests were verified. Backend Ruff/Pyright,
frontend lint/types/contracts/bundle, the eight selected overview/button tests,
and affected Go vet/build passed after the correction.

[Push run 41320558059](https://github.com/xyqyear/mc-admin/actions/runs/41320558059)
for `83ac6bb6decba3262b5f5be2c80837cab400a1b3` passed every API/browser shard and
audit, candidate/Go, static/frontend and 13 of 14 backend shards. The remaining
failure was the world-maintenance fixture's missing `created()` method after
startup gained its live-state read. Adding that method preserves the same fake
external state and all original maintenance assertions. All five targeted
maintenance tests and backend Ruff/Pyright passed; no application code changed.

## Successful complete qualification

- Source: `3b9a15c24bdac67406b827a5a0b0738d3f1179fe`, branch
  `refactor/shared-runtime-monitoring`.
- [Push run 41321868833](https://github.com/xyqyear/mc-admin/actions/runs/41321868833)
  completed successfully; no duplicate manual run was dispatched.
- All 14 backend shards, six API shards, three browser shards, their complete
  coverage/cleanup audits, candidate/Go and static/frontend gates passed.
  Publication was skipped, as intended for a development branch.
- Receipt mode: `full`; executed gates: `api`, `backend`, `browser`, `candidate`,
  `static`; every gate is `success`.
- Verification identity:
  `542584146fb54e9d8d4de98d5f9849e310bf339f7b21a06805fd6009295b5d58`.
- Original verification time: `2026-11-01T15:47:11.297406+00:00`.
- Qualified OCI manifest:
  `sha256:5214b7c9dfc4f24c849b435ac49eead0a53f9fbdecfc7361678c59bd3ff54b15`.
- Local receipt:
  `/root/.local/share/mc-admin-ci/41321868833/qualification/qualification.json`.

Performance conditions, raw measurements and fixed idle cost remain in
[performance.md](performance.md). Production was not deployed or modified.
