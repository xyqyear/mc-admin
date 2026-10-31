## Why

Map recovery has no business requirement to skip selected world files. General file-exclusion projection and speculative MCC accounting add substantial work and obscure the intended whole-selection recovery behavior.

## What Changes

- **BREAKING** World/map snapshots, candidate queries, previews, recovery, safety snapshots and rollback do not apply current, source or retained exclusion rules. Missing selected source data follows normal absence recovery, even when historical backup exclusions caused the absence.
- Remove world skip accounting and presentation, while retaining ordinary file/server/global backup and recovery exclusions.
- Replace candidate sidecar expansion with indexed selected-range coverage and request-local reuse.
- Simplify world execution, tests, current specifications and documentation around selected data rather than partial exclusion handling; explain the setting's scope in Chinese.
- Preserve source-range validation, genuine absence evidence, MCA/MCC handling, unselected chunks, instance/confinement checks, maintenance, safety capture, cancellation and cleanup.
- No production changes, release, binary upgrade, database schema change or chunk-prune policy change.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `snapshot-recovery`: world recovery processes its selected scope without file-exclusion skips; ordinary file recovery retains protection.

## Impact

Backend snapshot planning/query/Restic integration, world execution and previews; shared frontend snapshot contracts and map presentation; behavior tests and public API E2E inventory; current snapshot specifications and owning docs. Persisted histories remain readable and world records use the same exclusion-free semantics. User explicitly accepted historical omitted-data removal and authorized implementation after exploration. Related issue: #183.
