# MC Admin API E2E

An independent Go executable tests the actual application image through public
HTTP, SSE and WebSocket APIs. Inherit [repository rules](../AGENTS.md).
Use [build/run instructions](README.md), [the documentation index](docs/README.md)
and [the coverage inventory](docs/coverage.md).

## Commands and validation

Run from `e2e/`. These are examples for directly related cases, not a checklist:

From a Windows checkout, use `scripts/dev/e2e.ps1` from the repository root.
The executable and owned environments stay in WSL; see
[development](../docs/development.md) for build, case filters and Linux paths.

```bash
make lint
go vet ./internal/engine
go test -race -vet=off -count=1 -run '^TestShardPartitionIsCompleteAndStable$' ./internal/engine
make build
./bin/mc-admin-e2e run --backend-image mc-admin:e2e --tag regression --case '^files\.directories-search-and-errors$'
./bin/mc-admin-e2e run --backend-image mc-admin:e2e --tag regression --case '^files\.directories-search-and-errors$' --no-reuse
```

- Select explicit affected Go packages/test regexes, API case-ID regexes and browser spec/title filters. Anchor each API case ID. `--tag` intersects with case selection and defaults to `smoke`, so specify the appropriate tag.
- Format changed Go files with `gofmt`; run vet on affected packages and race-enabled, uncached framework tests for infrastructure changes. `-vet=off` requires the separate vet check.
- Run selected affected real cases normally and with `--no-reuse`; shuffle a relevant reusable group when its reuse contract changes.
- `make test`, `make check`, broad regression runs and unfiltered browser commands are full-suite CI entry points. Never reconstruct full local execution through directory batches, shards or agents.
- Full validation requires the latest SHA's complete qualification under the root rules; [CI](../docs/ci.md) owns dispatch and waiting instructions.

## Case and fixture rules

- Add coverage for observable backend behavior and update [coverage.md](docs/coverage.md) plus the affected domain page in the same change.
- Declare stable case ID, recipe, timeout, tags and explicit isolation. Start with `engine.Fresh`; reuse requires a documented verification invariant and compensation for every mutation.
- Cases run independently, in shuffled order and without reuse. Do not import backend internals or another suite, share mutable cross-run data, or add domain-specific branches to the scheduler.
- Historical SQLite inputs use isolated stopped deployments and standard SQLite/shipped Alembic maintenance. Assert results through public APIs and process outcomes; database queries cannot substitute for business assertions.
- `StartTask` validates acceptance. Use `RunTask`/`RunTaskResult` or equivalent terminal observation before asserting completion. Propagate context through all I/O and polling; retain terminal SSE events and independent state/content assertions.
- Never retry a failed business scenario into success or silently skip missing real dependencies. Permission tests verify unchanged state as well as status codes; credential-log tests inspect audit and application logs after successful business actions.

## Ownership and cleanup

- Reserve environment capacity before the deployment deadline and retain it through teardown. Diagnostic and cleanup phases have independent budgets. Long SSE reads use their operation context.
- Register cleanup at allocation, including partial setup; attempt remaining cleanup after individual failures. Journal Docker identities before creation and validate labels/IDs before removal. Never prune the daemon or delete by an unvalidated prefix.
- Unconfirmed teardown retains ownership and capacity, cancels new allocation and drains active groups. Pending cases still receive failed results. Diagnostic failure alone does not retain capacity after successful teardown.
- Register secrets with the redactor before use. Upload explicit redacted evidence paths, never `runtime/` or browser fixture credentials.
- Keep Fresh cases and verified reusable groups atomic in planning. Cost history affects placement only; it cannot remove current cases or shorten business/cleanup deadlines.

## Read for the task

| Change | Read before implementation |
| --- | --- |
| Add a case, recipe or provider | [Architecture and extension](docs/architecture.md), relevant [coverage domain](docs/coverage.md) |
| Scheduler, shards, timing or coverage audit | [Scheduling](docs/scheduling.md), [coverage reporting](docs/coverage.md#从真实运行结果生成接口覆盖记录), [CI](../docs/ci.md) |
| DNS/provider scenarios or cleanup | [DNS suite guide](suites/dns/README.md) |
| World inputs and subprocess interruption | [World suite guide](suites/world/README.md) |
| Browser journeys | [Browser verification](../frontend-react/docs/browser-tests.md) |
| Upgrade/checkpoint recovery | [Deployment rehearsal](docs/deployment-rehearsal.md), [release](../docs/release.md) |

Implementation and coverage details belong in their topic docs. Update these
instructions only for commands, constraints or reading routes; follow
[documentation ownership](../docs/documentation.md).
