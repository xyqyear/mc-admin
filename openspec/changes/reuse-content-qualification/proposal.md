## Why

Issue #184 reports three complete qualification runs for the same application: development, version notes, and release. Content-equivalent commits should reuse audited evidence and immutable artifacts without misrepresenting their original source or publishing stale version notes.

## What Changes

- Compute conservative verification and release content identities independent of commit IDs.
- Restore trusted complete qualification receipts and candidates across runs, with expiry and explicit forced validation.
- Separate release notes into validated same-origin static JSON; derive metadata-only images from tested OCI layers and smoke-test the resulting image.
- Route automatic, manual and tag validation through one coordinator, serialize equivalent qualification, and promote existing verified digests.
- Preserve full tests, exact-once audits, cloud cleanup and source provenance; update delivery instructions to recognize validated reuse.

## Capabilities

### New Capabilities
- `content-qualification`: Auditable content-based qualification, bounded metadata derivation and immutable publication.

### Modified Capabilities
- `ci-test-planning`: Centralized entry points may reuse complete evidence instead of independently executing unchanged inventories.
- `api-e2e-regression`: Distinguish fresh complete API execution from trusted evidence reuse.
- `dns-provider-qualification`: Preserve cloud evidence requirements when qualification is inherited.

## Impact

Workflows, Python release tooling, frontend version loading, browser version coverage, CI/release documentation and version-entry skill. No API or persisted-data migration. Version storage keys and notification behavior remain unchanged. No per-test result cache or selective business-test engine is introduced.
