## 1. Provider correctness

- [x] 1.1 Read all Huawei zone and record pages; add later-page and read-failure regressions.
- [x] 1.2 Apply incompatible type replacements in safe dependency order; cover replacement failures and unrelated-target progress.
- [x] 1.3 Require explicit ready and known observations in external qualification, with regression tests.

## 2. Owned cloud resources

- [x] 2.1 Support a fixed authorized parent namespace with independent descendant scopes, input validation and collision refusal.
- [x] 2.2 Persist non-secret cloud ownership and add independent, idempotent recovery with boundary and failure tests.
- [ ] 2.3 Extend provider scenarios with protected records, lifecycle triggers, configuration changes and cleanup assertions.

## 3. DNS and Minecraft traffic

- [x] 3.1 Add an owned host-network recipe with leased ports and real Minecraft/router traffic regression.
- [x] 3.2 Verify independent provider records, authoritative address/SRV/CNAME answers and initial recursive observation.
- [ ] 3.3 Exercise Huawei DNS-derived Minecraft routing, drift repair, port changes and wrong-host rejection.

## 4. CI and credentials

- [x] 4.1 Add trusted scheduled/manual/main-branch Huawei workflow and narrowly scoped Environment secrets.
- [x] 4.2 Include same-candidate Huawei results in release qualification and update gate regressions.
- [x] 4.3 Obtain dedicated Huawei credentials through the authorized browser and configure GitHub Secrets without exposing values.

## 5. Verification and documentation

- [x] 5.1 Update CLAUDE, DNS, E2E architecture/coverage, CI and release documentation.
- [ ] 5.2 Run targeted backend tests, Pyright/Ruff, Go formatting/vet/race tests and affected real E2E cases normally and without reuse.
- [ ] 5.3 Commit and push the implementation; complete full non-publishing qualification for the latest SHA and record cloud cleanup evidence.
