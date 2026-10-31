# Backend business-test governance evidence

## Scope and review

The baseline contains 257 `test_*.py` files. Static inventory reconciliation
found every baseline test filename in the three independent initial audits.
The resulting tree contains 256 such files: two redundant test modules were
merged into business scenarios and one shared-database regression module was
added. This is a file inventory, not a claim that every test ran locally.

| Review area | Initial inventory | Final decisions |
| --- | --- | --- |
| Persistence, players, scheduling, configuration, templates, servers, self-check | [Initial audit](audit-persistence.md) | [Implementation reconciliation](audit-persistence-final.md) |
| Files, archives, snapshots, worlds, maps, extraction, operations and tasks | [Initial audit](audit-resources.md) | [Implementation reconciliation](audit-resources-final.md) |
| Authentication, events, DNS, root tests, migrations, contracts and CI | [Initial audit](audit-boundaries.md) | [Implementation reconciliation](audit-boundaries-final.md) |

Independent cross-review covered the shared infrastructure and each other
agent's changes. Findings included blocking Docker SDK log reads, missing
database-setup-failure cleanup evidence, and a recurring-scheduler exact-count
race. Further review found task API fixtures silently using the in-memory
submission fallback and an ownership test that did not distinguish different
UIDs. Real journals and independent terminal reads, plus a focused ownership
adapter regression alongside the existing Docker scenario, close those gaps.
Each finding was corrected without changing production behavior or relaxing
business assertions.

## Main-agent implementation and coverage mapping

- Shared fixtures use the production file-backed SQLite Database and independent
  sessions. HTTP commits are observed by real background work and then by HTTP;
  rollback, failed transactions, cancellation and initialization failure have
  independent connection/reopen evidence.
- Ordinary Python socket access is restricted to local resources unless a test
  explicitly opts into external capability. Regression examples prove refused
  outbound DNS/connect/datagrams and a working real loopback connection. This
  guard does not claim to sandbox subprocess networking.
- Dynamic configuration verifies reload after updates/resets and preserves
  persisted values on invalid writes. Log-parser rules pass through the real
  configuration manager. Schema-version assertions check meaningful changes
  rather than a digest's character count.
- File APIs use actual managed directories and real fd. Ownership completes a
  real durable task, changes actual ownership and preserves unrelated paths and
  bytes. A write-permission failure checks original content remains unchanged;
  it does not claim an unimplemented backup exists.
- Snapshot planner success-step tuple assertions are replaced by real Restic
  restoration in `test_mixed_and_duplicate_selections_restore_only_allowed_bytes`.
  It checks preview is read-only, mixed/duplicate selections restore the chosen
  bytes and protected/unselected files survive. Existing `TestRestore` and
  `TestStage` in `test_service_integrated.py`, plus `test_empty_restore.py`, retain
  single/multiple/missing-source and ignored-path outcomes.
- PATH resolution uses temporary executables; audit middleware consumes a real
  HTTP body and writes redacted logs; SPA fallback distinguishes navigation from
  missing API/static assets. Docker monitoring consolidates getters into actual
  process identity, resource observations and traffic caused by RCON. The real
  Minecraft chat scenario waits for readiness/messages and always disconnects.
- Protocol-process scripts remain narrow fault inputs and now belong to the
  test runtime's temporary directory. Real mcmap configuration replaces the
  shared unrestricted configuration Mock.

## Verification boundary

Selected local behavior regressions passed, including database isolation and
cleanup, network capability isolation, dynamic configuration persistence,
filesystem API and ownership outcomes, mixed Restic restoration, audit/PATH/SPA
behavior, and the domain scenarios recorded in the final independent reports.
Only explicit files/nodes were selected; no complete backend collection or
suite was run locally. Full backend Ruff and Pyright passed. OpenSpec strict
validation and `git diff --check` passed before delivery.

The complete qualification must run against the pushed commit via manual
`Qualify and Publish Application` dispatch with `publish=false`. Local results
and static review do not establish complete qualification. The delivery report
records the exact SHA, Actions URL and final gate/audit outcome.

## Qualification findings

The first full run, [39288106004](https://github.com/xyqyear/mc-admin/actions/runs/39288106004),
tested `dcf807dd2550841ace9135be7d6d0348ea201a49`. Candidate/Go, static/frontend,
all API and browser shards and their audits passed. Seven backend shards passed;
the remaining shard exposed an outdated populate rejection assertion after the
fixture began using the real durable journal. Admission correctly rejects an
unregistered server before filesystem existence checks. Its regression now
requires the precise registration error, an unchanged archive, no server
directory/registration, no journal row and no submitted task. The failed run
does not qualify the change; the correction requires a new complete run.

The second full run, [39291131375](https://github.com/xyqyear/mc-admin/actions/runs/39291131375),
tested `6dd40f2d45e356f5d321ad082f3c774e1121f40d`. All backend shards and their
audit passed, as did candidate/Go, static/frontend and API qualification. A
browser lifecycle journey failed because its page-wide "查看任务" locator matched
both the pending-operation status region and an observation-failure toast.
Trace inspection and independent review identified the original assertion,
which premature cleanup had masked with a 423 response. The locator now targets
the actual status region. Cleanup preserves original failures and waits for the
accepted task's terminal state before restoring the server; no task state,
server state or business assertion is replaced or relaxed.

The corrected lifecycle journey passed alone against the second run's verified
candidate image, using the owned Go wrapper and a real Minecraft container.
Candidate identity, successful outcome and owned cleanup were verified by the
release evidence checker. Node 24 frontend lint/boundaries, typecheck and bundle
build passed. Complete acceptance still requires qualification of the new
commit containing this correction.
