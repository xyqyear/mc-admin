## Why

Region snapshot selection expands every possible external chunk file before checking every snapshot. A production selection of six regions produced 18,450 mappings across 385 snapshots, starving the API event loop for minutes. Candidate selection must remain responsive without changing backup, protection, restoration or rollback results.

## What Changes

- Separate candidate-query preparation from execution planning, representing possible region sidecars compactly and resolving only relevant exceptions.
- Compile snapshot coverage and exclusions once and share indexed path matching across candidate queries and execution checks.
- Bound query work between cancellation checkpoints and cancel obsolete frontend candidate requests.
- Preserve candidate order, skip evidence, logical/physical path distinctions, source absence and execution revalidation.
- Add independent semantic, equivalence, responsiveness, cancellation and deployed API coverage; retain existing snapshot tests.
- Exclude production changes, map rendering compatibility, database migrations and restoration protocol changes.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `snapshot-recovery`: responsive, cancellable candidate discovery with unchanged protection and recovery behavior.

## Impact

Backend snapshot query, source indexing and world-selection helpers; frontend candidate query transport; backend/frontend tests and API E2E coverage. HTTP payloads, persisted data, dependency versions and Docker deployment behavior remain unchanged.
