## Why

Backend tests need to protect administrator and player outcomes rather than duplicate implementation decisions. Independent database/session overrides, permissive doubles and repeated fixture lifecycles currently weaken that assurance and make failures harder to interpret.

## What Changes

- Audit every backend test file against its business purpose with independent reviewers; record retained coverage, justified consolidation and repaired gaps.
- Standardize real, isolated SQLite resources and independent sessions across HTTP, services and background work, using production database configuration.
- Prefer real local files, subprocesses and installed third-party binaries; retain external API doubles and narrowly controlled fault/cancellation boundaries with explicit purposes.
- Replace implementation-shaped assertions with persisted outcomes, preserved data, authorization, recovery and resource cleanup assertions where appropriate.
- Remove redundant test scaffolding and shared mutable test managers; make setup failures and teardown safe.
- Document testing contracts and add focused regression protection for the common infrastructure.

## Capabilities

### New Capabilities

None. This change refactors test infrastructure and strengthens verification of existing behavior; `skip_specs: true` applies.

### Modified Capabilities

None. Existing business specifications remain the acceptance source.

## Impact

Scope: all backend tests, support fixtures and owning backend testing documentation. Existing API E2E and browser coverage remain qualification gates. No frontend, public API, production persistence schema, deployment configuration or Docker behavior changes are intended. No breaking changes. Product behavior fixes discovered during review must be explicitly documented and receive their required API E2E coverage.

Non-goals: reducing test counts or runtime as an end in itself; removing meaningful safety boundaries; replacing integration coverage with mocks; executing a full suite locally.
