## Why

The independent code-humanizer audit found duplicated policy, unused internal APIs, speculative abstractions and tests that can pass despite incorrect business results. The maintainer approved the reviewed report for implementation, including substantial structural refactoring.

## What Changes

- Implement the 66 retained findings from the reviewed audit; preserve the two rejected consolidations and documented compatibility, resource ownership and recovery constraints.
- Replace implementation-only assertions with independent business oracles, gated concurrency observations, real boundary payload checks and owned integration coverage.
- Retire unused internal interfaces, consolidate equivalent helpers and simplify concrete runtime, feature hooks, map controllers and file trees without changing supported API or persistence contracts.
- Correct Cron zero/empty edits, atomic directory overwrite selection and visible player-profile stream failures.
- Remove sensitive exception/argument output from upload, console, profile, cron and backup-notification paths while retaining status codes, cancellation and partial-result policies.
- Characterize process monitoring and OCI verification costs before selecting performance changes.

Public routes, database schemas, Docker ownership rules, configuration formats and historical recovery data remain supported. Internal test-only APIs are retired; these are not supported external contracts. No new plugin system, generic workflow framework or persistence migration is planned.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `administration-compatibility`: explicit zero/empty Cron edits and directory overwrite selections preserve user intent; failures exclude sensitive adapter details.
- `operation-consistency`: player-profile streams expose recoverable failures while cached map data remains usable; upload and backup failures preserve existing bounded effects with safe output.

## Impact

Backend runtime, operations, files, world/map, configuration, players, self-check, DNS/cron and tests; frontend feature queries/commands, Cron/schema forms, file trees, player streams and map composition; standalone API E2E helpers/oracles and release verification scripts. Relevant current-state component docs and AGENTS.md stay synchronized. Validation uses targeted local tests and component static/build checks, followed by full non-publishing qualification of the latest pushed commit.
