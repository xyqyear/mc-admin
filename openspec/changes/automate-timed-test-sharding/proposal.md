## Why

Static historical weights and fixed shard counts do not follow the measured cost of the current tests. Backend, API and browser execution need automatic plans targeting five minutes, while real DNS qualification should use the API E2E execution and evidence flow.

## What Changes

- Restore the latest comparable, successfully audited timing history and publish new history after complete execution audits.
- Derive backend, API and browser shard counts and assignments from a 300-second execution budget, including fixture setup and cleanup.
- Keep oversized indivisible units valid, report the reason the target cannot be met, and bound shard creation and concurrency.
- Include Huawei scenarios in the API E2E qualification plan, protected execution and aggregate gate; remove the independent DNS workflow and gate.
- Audit exact-once current test coverage, immutable plan identity, successful results, candidate identity and owned cleanup before qualifying or learning costs.

Application APIs, schemas, persistence and deployment behavior do not change. Five minutes is a planning target, not a test timeout. This change does not introduce assertion retries, shared mutable cross-run fixtures, or local full-suite execution.

## Capabilities

### New Capabilities

- `ci-test-planning`: Historical execution timing, automatic bounded sharding and complete qualification evidence for backend, API and browser tests.

### Modified Capabilities

None. Existing application and external qualification contracts remain in force.

## Impact

CI workflows, Python test support and CI scripts, Go E2E planning and reports, browser selection and reports, release gate validation, related tests, agent instructions and CI/component design documents. Protected Huawei credentials and recovery remain scoped to cloud execution. No new application runtime dependency or database migration is required.
