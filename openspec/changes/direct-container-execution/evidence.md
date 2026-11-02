# Verification evidence

## Scope

Query/RCON/message execution uses Docker API with gnutimeout-first, timeout fallback
in the same exec. No version discovery/cache, automatic command retry, package
installation or custom remote process manager. Compose lifecycle, snapshot/world
recovery, pidfd and journal implementations are unchanged. No production deployment.

## Local verification (2026-11-02)

- Real owned containers: root/non-root argv and Chinese text; stdout/stderr separation;
  nonzero exit; preferred tool, fallback and missing tools; no retry on command failure;
  ordinary pipeline and TERM-ignoring process-group termination; instance mismatch;
  cancellation and resource drain; slow command does not block DockerReader.
- Fault boundaries: truncated/silent Docker output, finite deadline, queued cancellation,
  invalid timeout rejection. SDK client and output connection close on completion/failure.
- Player/API: saved Query limit, valid empty list, same-instance fallback, failure/cancellation,
  persisted online session preserved on unknown observation; RCON output, safe errors,
  authentication, 404/409/502/504, message ordering and no repeated completed lines,
  empty message target validation.
- `test_running_container_metrics_observe_real_activity` passed against real Minecraft,
  including refusal of snapshot file restore while running despite stale stopped cache.
- Architecture boundary tests and Runtime unvisited-resource shutdown test passed.
- Ruff, Pyright, Go vet (`./suites/minecraft`), E2E build, application image build and
  OpenSpec strict validation passed. Only selected local tests were executed.
- Deployed `minecraft.command-timeout` passed normally and with `--no-reuse`; actual
  API 504 followed by process-exit and single-execution evidence, monitoring availability,
  safe 502/logging and subsequent real Minecraft RCON. Owned binary restored on cleanup.
- `minecraft.stopped-and-invalid-requests` passed normally and with `--no-reuse`.
  Reports: `e2e-2104ee9bde61`, `e2e-49847ee086df`, `e2e-fdddd3a27c52`, and final-image repeat `e2e-b86eecb393ca` under the
  local WSL E2E output directory. Every case environment was reclaimed.

## Full-path performance

Explicit runner: `backend.ps1 run python -m tests.support.command_benchmark`.
One owned Minecraft server, existing pinned fixture image, default Query 0.25s,
100 samples per path, alternating old/new order. Full MCInstance call versus
prior Compose implementation; state/property reads included as appropriate.
No production data or service was accessed. Local machine shared with other
verification workloads; these numbers are comparative observations, not an SLA.

| Path | First call ms | p50 ms | p95 ms | Failures / 100 | Caller CPU seconds / 100 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Query / Compose | 115.80 | 114.55 | 133.86 | 1 | 5.799 |
| Query / Docker API | 58.25 | 60.43 | 85.45 | 1 | 0.704 |
| RCON / Compose | 101.14 | 117.05 | 136.54 | 0 | 5.997 |
| RCON / Docker API | 32.25 | 55.99 | 82.65 | 0 | 0.630 |

All samples, including failures, are retained in percentiles. Query p50 improved
47%, RCON 52%; caller CPU (Python and reaped CLI children, excluding daemon/game)
fell about 88%/89%. First call means first measured call after server readiness;
no claim of cold Docker image/startup or system cache. Both Query implementations
had one timeout; saved timeout was not relaxed and business fallback remains.

## Boundaries and rollback

Native timeout governs the normal command process group; no promise covers escaped
or background descendants after their parent has exited. API cancellation does
not undo Minecraft side effects. Already-started commands retain their own deadline;
normal app close drains local SDK work. Exit 137 is treated as timeout/termination,
not asserted to prove timeout was the sole cause. A non-GNU timeout is allowed.

No data/config migration. Reverting this change or restoring the previous application
image restores Compose exec. Production release and deployment require a separate request.

## Qualification

Full qualification passed for implementation SHA
`1a8b02d2b7cb1c4bc61ebc62ed09b0c746c7248a`:
https://github.com/xyqyear/mc-admin/actions/runs/41390967623

Candidate/Go, static/frontend, all 15 backend shards, all 6 API shards and all 3
browser shards passed, including complete selection, coverage and resource/cloud
cleanup audits. No release promotion ran. Receipt validated against committed
source with `scripts.release.reuse.validate_receipt`; full execution gates are
candidate/static/backend/api/browser, all success. Verified at
`2026-11-02T05:05:34.088057+00:00`.

Verification identity:
`3e214f96ae65ad7833b25ec1277e028c4750cfff310e9d4546cdb1b865d50a33`.
OCI manifest:
`sha256:9cba5e2af703baf29da61581fa5cdb7744acbaf4abf65de6fcda976ad907752a`.

This evidence-only follow-up changes no verification inputs. Its push still
requires a successful latest-SHA receipt binding any equivalent reuse; the
implementation run alone does not qualify a later commit.
