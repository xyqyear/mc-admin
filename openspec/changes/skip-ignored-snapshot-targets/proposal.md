## Why

Mixed file selections currently reject the entire snapshot or restoration when one selected root is ignored. Ignored paths should be skipped while the remaining targets are processed, consistently across source selection, preview, execution and rollback.

## What Changes

- Filter protected roots through one shared selection policy; reject only an empty effective selection.
- Apply current, source and retained-chain protection before restoration admission and show source-specific skips.
- Keep explicit source coverage checks for every allowed file root and retain skipped-path protection during rollback.
- Preserve confinement, generation checks, preview freshness and queued rule-change rejection.
- Non-goals: changing exclusion syntax, world partial-coverage semantics, Restic options or historical identity compatibility.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `snapshot-recovery`: mixed ignored selections proceed with consistent protected source selection, preview, execution and rollback.

## Impact

Backend snapshot protection/planning and eligible-source DTOs; frontend file controls and source feedback; API E2E and related tests. Existing scope and protection persistence are reused without a schema migration. Docker dependencies and configuration syntax stay unchanged. Eligible-source responses gain additive skip metadata.
