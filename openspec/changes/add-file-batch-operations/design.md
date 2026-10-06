## Context

See proposal.md for motivation. Existing ownership is described in backend/docs/files.md, backend/docs/background-tasks.md, docs/snapshot-recovery.md and frontend-react/docs/file-management.md, data-architecture.md, player-management.md and task-center.md. PathsScope and /snapshots/eligible already support multiple targets. The file table already retains full-path selection across pages; deep search currently only navigates. Downloads currently buffer a Blob and trigger a single native download.

## Goals / Non-Goals

**Goals:** Compose concrete feature-owned commands and one file recovery owner; preserve existing single-target contracts; bound download transfer and enumeration resources; keep destructive results truthful.

**Non-Goals:** Automatic player data discovery or rollback, byte-range resume across browser restarts, transactional filesystem batch rollback, browser plugins, and automatic publishing/merging.

## Decisions

- The overview card owns a selected UUID and renders PlayerDetailDialog outside conditional list content. A UUID key resets detail-local state when explicitly switching players. No backend player interface changes.
- The ordinary table and deep-search tree share concrete FileBatchActions and captured path scopes. Real matches are identified by the result map, not tree leaf status. Search paths are converted using the returned search_path; display grouping cannot become recursive selection. Selection changes with location/executed-query identity and retains sorting/pagination.
- FileSnapshotRecovery accepts path arrays and uses useEligibleSnapshots(scope), retaining one preview/recovery/history owner. Eligible file sources and actual restoration share full-root protection rules.
- FileApplication accepts a deletion batch with full preflight and one durable task/lease. Per-target results survive journal detail retention; completed targets remain changed if later work fails or cancellation occurs. Existing single-delete interfaces remain supported.
- Archive compression accepts additive paths[] with data-relative archive members, disjoint roots, literal arguments and atomic owned-stage publication. Existing path and whole-project forms retain their semantics. Packing is a persistent archive action independent from direct download.
- Direct export uses showDirectoryPicker readwrite from the initial user gesture, streams existing authenticated file responses into writable local handles, and creates a unique export child directory. A bounded transfer queue reports bytes, counts, failures and filename mappings through the browser task center. Capability detection checks the API and secure context; no browser version appears in UI. Large recursive directories use a bounded download-manifest API, without materializing content as Blobs or generating server archives. Original layout captures search/browse root; flat naming and platform restrictions receive deterministic collision-safe mappings. Completed local files persist on cancellation; browser refresh/closure stops the browser-owned batch.
- Snapshot notes use a new table keyed by real Restic repository config ID and full snapshot ID. Editing Restic tags would change snapshot identity and invalidate references, so notes never mutate repository snapshot metadata. A creation outcome carries the created snapshot even if note persistence fails. Lists, eligible sources and details project the same note. Creation dialogs for all manual scopes collect notes.
- Existing application operation registries own backend terminal invalidation. Browser export does not invalidate server files. Feature public-entry import boundaries remain intact; no universal workflow framework is introduced.

## Risks / Trade-offs

- Limited browser support and insecure LAN HTTP → visible disabled control with accurate capability or HTTPS/localhost tooltip; independent packing remains available.
- Many small files and changing server files → bounded enumeration/transfer, frozen requested roots and truthful per-file failures; direct export is not a point-in-time snapshot.
- Local name restrictions and case collisions → unique export root, collision-safe mappings and visible warnings, never silent overwrite.
- Partial deletion or cancellation → retained per-target outcomes, failed selection for retry and no false atomicity guarantee.
- Notes live with application metadata → database migration/default-empty historical notes and repository identity isolation; application database backups retain notes.

## Migration Plan

Deploy frontend and backend together. Startup applies an additive notes-table migration; historical snapshots require no backfill. Existing single-path requests remain readable, while new clients use batch requests. A downgrade must follow the repository's existing schema/recovery boundaries and preserve a database checkpoint; this change does not weaken existing restoration-history downgrade guards. Update component AGENTS and current-state files/player/task/snapshot design docs; no CLAUDE.md exists in scope. Verify targeted behavior and static checks, commit/push on the development branch, then qualify the latest SHA with publish=false. Do not archive or publish without separate instruction.
