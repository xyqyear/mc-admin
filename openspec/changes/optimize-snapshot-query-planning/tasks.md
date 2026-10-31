## 1. Query and source planning

- [x] 1.1 Add shared source/path indexes and verify ancestor, sibling, exclusion and identity behavior with independent and reference comparisons.
- [x] 1.2 Implement compact eligible selection with exact sidecar exceptions and verify candidate order, skips, missing paths against exhaustive planning, retaining file-scope link tests.
- [x] 1.3 Share compiled source checks with execution and historical listing; verify existing snapshot, preview, restoration and rollback scenarios without removing coverage.

## 2. Request lifetime and integration

- [x] 2.1 Bound query computation and handle disconnect cleanup; verify concurrent reads, cancelled lookup settlement and fresh subsequent queries.
- [x] 2.2 Forward frontend candidate-query cancellation; verify closing/changing/reopening selections without cancelling durable recovery.
- [x] 2.3 Add a public API responsiveness and candidate-equivalence scenario, run the selected case with and without reuse, and update coverage inventories.

## 3. Qualification

- [x] 3.1 Record the 385-snapshot/six-region benchmark and targeted regression results; pass backend/frontend static checks and frontend build.
- [x] 3.2 Update snapshot ownership documentation and validate coherent OpenSpec artifacts with no production or map changes.
- [ ] 3.3 Commit and push the branch, then pass complete publish=false qualification on the latest SHA and record its Actions link and audited outcome.
