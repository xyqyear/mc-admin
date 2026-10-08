## Context

See backend/docs/snapshots.md, frontend-react/docs/file-operations.md and docs/snapshot-recovery.md. Resolved scopes already preserve original logical roots and execution mappings; protection already stores current, source and retained-chain exclusions.

## Goals / Non-Goals

Use one protection-owned target selection boundary across snapshot service and application planning. Preserve original identity evidence without using protected roots as write targets. No schema migration, exclusion syntax change or new world coverage policy.

## Decisions

- Protection selects allowed roots and rejects an empty selection. Strict per-target rejection is replaced at this shared boundary, avoiding per-entry exceptions.
- Prepared snapshots retain original resolved identity while exposing effective paths. Resource and maintenance preparation uses those effective paths; source protection is incorporated before restore admission. World-specific chunk coverage remains in its existing adapter.
- Eligible sources reuse source preparation and return additive per-source skip metadata. Ordinary missing coverage remains an error. Frontend renders authoritative source skips, rather than interpreting repository absolute paths or tags locally.
- Existing protection and scope JSON retain skipped roots across rollback. Low-level restore protection and queued revalidation remain authoritative; original path confinement is never relaxed.

## Risks / Trade-offs

- A source can narrow targets beyond current rules → disclose its skipped paths in source selection, previews and task outcomes.
- Narrowed write targets could retain unnecessary world stop guards → derive maintenance from effective targets after source protection, while retaining conservative accepted resource ownership.
- Changed rules or server identity during queueing → reject on existing frozen-rule and resolved-identity checks.

## Migration Plan

Deploy frontend and backend together. Eligible source metadata is additive; existing scope/protection persistence needs no migration. Update current docs, AGENTS descriptions and main snapshot-recovery spec with the resulting contract.
