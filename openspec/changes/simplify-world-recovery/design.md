## Context

See proposal.md and the snapshot ownership topics in backend/docs/snapshots.md, snapshot-restoration.md, world-restore.md and frontend-react/docs/snapshot-recovery.md. World selections currently share file protection across planning, Restic staging, chunk merging and preview presentation.

## Goals / Non-Goals

Make the world policy explicit at scope preparation and retain it through shared execution so later source/config reads cannot reintroduce exclusions. Remove world-only skip expansion and partial-scope filtering. Keep ordinary file semantics, confinement, source coverage, absence, lifecycle ownership and real MCC execution. No production mutation or binary changes.

## Decisions

- An exclusion-free world policy travels with the existing path bindings through shared Restic services. It does not read current ignored paths, merge source/retained exclusions or revalidate exclusion configuration. File policy remains the default. This avoids duplicating the backup/staging/cleanup engines.
- World candidate matching uses selected MCA/root coverage and absence indexes; source cache identity depends on relevant coverage metadata, not exclusion strings. Remove RegionSidecars and its speculative skip enumeration. Keep request cancellation and bounded computation.
- Remove partial protected-chunk selection and copying protected live data into previews. World scopes either pass range validation or fail; execution processes the selection. Scope-specific UI has no skip notices. Shared file response fields may remain where file flows use them, with no world computation; world-only target feedback contains only validity/reason.
- Historical world records retain their scope, source and instance ownership but ignore recorded exclusion data. Missing data inside the source range is restored as absence. This policy is explicitly accepted by the user; no legacy world-protection branch is retained.
- Current specs/docs describe the final policy directly. Replace broad cross-scope protection statements with concise file/world boundaries. Preserve unrelated snapshot safety and file alias requirements. Historical change evidence is not rewritten as current documentation.

## Risks / Trade-offs

- Wrong propagation could reapply source exclusions or omit safety data → exercise real Restic creation, staged preview, recovery and repeated rollback under current and historical exclusions, including old recorded protection.
- Removing skip logic must not remove real MCC payloads or touch unselected chunks → retain independent byte/NBT assertions, missing sidecars and negative coordinates.
- Shared file flows could lose protection → keep targeted file exclusion, alias and preview tests unchanged.
- Existing world fixtures asserting exclusion preservation describe removed behavior → replace their assertions with full-selection behavior rather than weakening task/content checks.

## Migration Plan

No schema migration. Frontend and backend ship together; world histories follow current scope semantics, while ordinary file histories keep their protection. Validate locally with selected cases, then commit/push and run the required publish=false qualification. Update current specs and owning docs before final delivery. The existing user implementation instruction carries through planning into apply.
