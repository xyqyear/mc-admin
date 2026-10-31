## Context

The ownership contracts are documented in `backend/docs/snapshots.md`, `snapshot-restoration.md`, `world-restore.md` and `frontend-react/docs/snapshot-recovery.md`. Candidate discovery currently calls the mutation planner and retains speculative MCC mappings even after switching its coverage targets to MCA files. Source protection and coverage also reconstruct the same paths repeatedly.

## Goals / Non-Goals

Preserve candidate ordering, skip lists/counts, historical exclusion semantics, absence evidence and link identity checks. Make work proportional to selected regions and relevant metadata instead of all possible sidecars times all snapshots. Preserve execution leases, safety capture, revalidation and durable cancellation. No production operations, map changes, database migration, API redesign, dependency upgrade or global metadata cache.

## Decisions

### Query preparation has its own compact selection

Resolve the selected server and MCA targets without mutation preparation. Represent possible MCC paths by directory and region coordinates. Relevant current/source exclusions and recorded identities supply exceptions. World contents are regular files under the user-confirmed deployment constraint; MCC files remain supported external chunk data, not filesystem links. Broad source exclusions can materialize affected sidecars when required to preserve exact skip evidence; ordinary sources do not enumerate absent files. Derive sidecar bindings from the confined directory without scanning for filesystem links; reuse observations only during this query. Execution continues to prepare and revalidate complete targets.

Simply setting `include_mcc=False` would lose ignored MCC evidence. Replacing speculation with only live files would miss historical source identities. Keep the compact region membership predicate and explicitly account for both live and recorded exceptions.

### Shared immutable source and path indexes

Compile source roots, exclusions and logical identity metadata once. Ancestor membership and sorted descendant lookup replace repeated full scans; protection uses the same path index. Candidate, historical path-list and execution coverage checks share this machinery while preserving their distinct policies. Source absence stays lazy so historical listing does not gain unrelated validation failures. No cross-request filesystem binding cache is introduced.

Within one candidate request, identical `(paths, excludes, tags)` reuse their eligibility and skip decision. Snapshot IDs, timestamps and notes remain independent response metadata. Distinct policies are still evaluated separately; neither decisions nor filesystem observations survive the request.

### Cancellation and responsiveness

Yield between bounded source batches and during unusually large protection projections. Query-only disconnect handling cancels the owned lookup and joins its subprocess cleanup. The frontend consumes the query signal. Closing recovery observation retains the existing durable-task behavior. Moving all old work into a thread or adding a timeout alone would leave the excessive computation intact.

### Verification

Retain snapshot behavior tests. Add an exhaustive reference implementation in test-only support for differential candidate/protection checks, alongside independently specified expected outcomes. Cover current and historical excludes, absent parents, old/new metadata, changed aliases, individual external sidecars, negative coordinates, missing entity/POI directories, exact skips and order. Use real files, SQLite, Restic and mcmap for recovery regressions. Measure the 385-source/six-region case separately from repository I/O; require bounded event-loop delay and test cancellation. Add a deployed public-API scenario and frontend abort/reopen tests.

## Risks / Trade-offs

- Sparse exceptions could omit a historically selected sidecar → differential and independent exclusion tests, including source-only and missing paths. File-scope alias checks remain covered separately.
- Index prefix mistakes could match sibling names → compare path components, not raw string prefixes; retain root/ancestor/descendant examples.
- Read-query cancellation could affect durable restores → isolate it to eligible lookup and retain existing restoration lifecycle tests.
- Large genuinely excluded ranges still require output accounting → bounded checkpoints and exact evidence, without arbitrary truncation of the count.
- Timing varies across CI → combine generous latency limits with structural scaling and deterministic concurrency assertions; report actual local benchmark values.

## Migration Plan

No persisted/wire migration. Update owning snapshot and frontend documentation and E2E inventory; no AGENTS instruction changes or CLAUDE files are needed. Validate selected affected paths locally, commit/push the isolated branch, then qualify the latest SHA with publish=false. No deployment to production is included. The user explicitly authorized implementation after the prior exploration, so planning artifacts are followed directly by apply.
