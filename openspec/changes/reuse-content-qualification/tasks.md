## 1. Release data

- [x] 1.1 Extract pure version JSON and load validated same-origin data; verify notification, failure/retry, snooze and first-visit behavior with targeted frontend tests.
- [x] 1.2 Add real-image release notification smoke coverage, verify the requested version and owned cleanup.

## 2. Qualification evidence

- [x] 2.1 Implement Git content identities and trusted receipt retrieval; test documentation equivalence, invalidation, provenance, expiry, missing artifacts and force-full behavior.
- [x] 2.2 Implement deterministic data-only OCI derivation and target-source receipts; test unchanged layers/configuration, tampering rejection and promotion of exact final digest.

## 3. Workflow integration

- [x] 3.1 Centralize triggers, serialize content-equivalent requests, and integrate full/reuse/metadata routes; validate workflow graph, failure gates and actionlint.
- [x] 3.2 Update delivery instructions, owning documentation, version-entry skill and main specifications; validate OpenSpec and documentation consistency.

## 4. Delivery

- [x] 4.1 Pass related Python/frontend tests and required Ruff, Pyright, frontend lint/types/contracts/build checks.
- [x] 4.2 Commit and push with issue #184, run forced complete qualification on the latest SHA, then verify exact reuse and metadata-only paths without publishing; record Actions links and evidence.
