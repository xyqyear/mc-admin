## 1. Business review

- [x] 1.1 Independently audit every backend test file and document business purpose, retention and consolidation decisions.

## 2. Shared resources

- [x] 2.1 Introduce coherent real SQLite fixtures with production configuration and independent sessions; cover commit visibility and cleanup.
- [x] 2.2 Migrate ordinary persistence fixtures and remove shared managers, split database overrides and unsafe cleanup.
- [x] 2.3 Consolidate runtime overrides and typed configuration fixtures while retaining explicit external/fault boundaries.

## 3. Business verification

- [x] 3.1 Strengthen authentication, task authorization, event and filesystem scenarios using real local resources.
- [x] 3.2 Govern players, cron, configuration, templates, servers and self-check assertions against business outcomes.
- [x] 3.3 Govern snapshot/world, files/archive, map/extraction and durable-operation scenarios; preserve recovery, cancellation and data-integrity contracts.
- [x] 3.4 Review external API, migration, contract and CI tests; consolidate only demonstrably redundant coverage and document retained fault doubles.

## 4. Verification and delivery

- [x] 4.1 Update owning testing documentation and agent reading rules, and reconcile the complete file audit against the final implementation.
- [x] 4.2 Independently review final changes and run selected local behavior regressions plus backend Ruff and Pyright.
- [ ] 4.3 Commit and push, dispatch full qualification with publish=false, and verify the latest SHA and every required gate/audit.
