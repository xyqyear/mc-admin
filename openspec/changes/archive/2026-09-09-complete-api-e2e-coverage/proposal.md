## Why

The real API E2E framework has representative smoke coverage but many shipped feature families lack functional scenarios. The regression catalog needs to exercise every backend API family, identify real defects, and keep external dependencies and unexecuted coverage visible.

## What Changes

- Add modular regression scenarios for every backend feature family, including authentication, scheduling, files, archives, templates, server lifecycle, players/events, world/map/prune/restore, DNS and startup migrations.
- Add deterministic owned fixtures and streaming helpers where real operations require them; retain real application, Docker, database, Minecraft and dependency binaries.
- Track API operation coverage and distinguish local regression from real external provider qualification; missing required credentials fail selected external scenarios.
- Repair observable defects exposed by the regression cases with focused backend regression tests.
- Run local regression shards and update CI and documentation with actual validation evidence and coverage boundaries.

## Capabilities

### New Capabilities
- `api-e2e-regression`: Complete backend feature-family scenarios, API surface coverage accounting, explicit external dependencies and independently runnable regressions.

### Modified Capabilities

None. Defect fixes restore documented behavior rather than introducing a new application feature.

## Impact

Changes affect the independent `e2e/` project, its CI workflow and docs, and narrowly scoped backend fixes proven necessary by real regression failures. The frontend is served by the tested image but browser interaction remains outside the established API E2E scope. No mocks replace real backend or dependency operations. External DNS tests use only explicitly supplied disposable domains and credentials. No breaking API/configuration/data changes are intended.
