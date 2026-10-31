## Context

See docs/release.md and docs/ci.md for the immutable OCI candidate, five required gates, exact-once audits and promotion boundary. frontend-react/docs/version-updates.md describes local version notification state. Existing independent push/PR workflows duplicate manual qualification; release notes are executable TypeScript bundled into application code.

## Goals / Non-Goals

Reuse one complete qualification for identical effective inputs, retain independently attributable source/run/image evidence, and allow bounded release-data changes. Do not introduce per-test dependency inference, registry candidate writes, external version services or database changes.

## Decisions

- Hash sorted Git tree entries (path, mode, object ID), excluding only known documentation paths and the single release-data file. All unknown files, tests, dependency locks, fixtures and workflow policy participate. Hash release bytes separately into the release identity. Keep the existing full clean-source snapshot check.
- Store versioned receipts as immutable Actions artifacts indexed by verification identity. Restore only same-repository non-PR successful runs of the coordinator; validate run/attempt/source, recompute identities at the original commit, verify artifact hashes, original qualification age and all gates. Preserve original evidence rather than refreshing its timestamp through reuse. Missing/expired artifacts cause full validation; corrupted evidence fails closed.
- Reuse the actual OCI archive. For documentation-equivalent sources, rebind target source metadata while preserving build provenance. For release-data changes, append one deterministic OCI layer containing only app/static/static/release.json; preserve runtime configuration and every original layer. No package installation or application recompilation is allowed. Verify the derivation before loading and smoke-test the final image. Keep both base and final digest in the receipt.
- Load release data using the existing QueryClient with no HTTP cache reuse. Validate its schema before updating notification state; failed loading cannot acknowledge a version. Preserve SemVer ordering, first-visit silence, snooze and close behavior. The file is local to each application image, not a remote update service.
- Centralize push/PR/tag/manual qualification in docker-image.yml. A reusable qualification workflow performs lookup again under a content-keyed concurrency lock with queued requests; promotion runs separately. Existing backend/static/browser workflows remain execution primitives; API scheduled/manual diagnostic runs remain independently available. A force_full input bypasses reuse.
- Publish a current-target receipt only after either all original gates pass, verified exact reuse succeeds, or bounded metadata derivation and its checks pass. Do not reinterpret skipped jobs as successful test execution. Candidate and receipt retention is 30 days, bounded by the original full qualification timestamp.

Workflow syntax validation pins the maintained actionlint fork at v1.17.0 because upstream v1.7.12 rejects GitHub's supported queue property. Node setup uses the Node 24 action runtime. All syntax checks remain enabled.

## Risks / Trade-offs

- Incorrect exclusion → explicit documentation allowlist, default inclusion, policy included in its own identity, and fixture/rename/mode tests.
- Mutable runner/provider environment → receipts are historical evidence, force_full bypasses them, scheduled provider tests remain live; source identity does not claim environmental immutability.
- Metadata-only images have a new digest → structural layer/config verification plus real-image version smoke evidence; publication still copies the final tested digest.
- Untrusted artifacts → approved coordinator/event/repository checks and independent source identity calculation; fork/PR results cannot authorize release.
- Artifact retention/cost → one bounded candidate and receipt per accepted run; original age cannot be extended by copying.

## Migration Plan

The first implementation SHA must pass forced complete qualification; legacy receipts are ineligible. No persisted user state migration is needed. Rollback restores the prior workflows and bundled version source together. Update root AGENTS.md, docs/ci.md, docs/release.md, version/browser docs and the version-entry skill. Keep the main specifications synchronized before delivery.
