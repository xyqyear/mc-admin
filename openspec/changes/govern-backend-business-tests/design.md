## Context

See proposal.md for intent. The existing isolation foundation in `backend/docs/testing.md` binds one Runtime per test. `backend/docs/runtime.md` explains captured service dependencies and shutdown ordering; replacing only an HTTP dependency or a cached session factory does not replace every database consumer. `backend/docs/test-planning.md` requires full-file CI allocation and complete exact-once audits.

## Goals / Non-Goals

Goals: meaningful business regressions, coherent real resources, independent persistence observations, safe ownership and a reviewable audit of every test file. Pure algorithms, protocol adapters, architectural contracts and deliberate fault injection remain valuable tests with different boundaries.

Non-goals: changing application contracts, imposing one giant startup fixture on every pure test, using rollback-only shared transactions to conceal commit boundaries, or blanket deletion of low-level tests.

## Decisions

1. Provide function-scoped database/session fixtures backed by the isolated Runtime's production Database. Initialize current metadata explicitly when requested; migration/upgrade tests retain real migration execution and historical fixtures. File-backed databases preserve independent connections and durable commits. Specialized restart, cancellation and migration fixtures may own additional databases with explicit cleanup.
2. Reuse the same database in HTTP dependencies, services and background work. Replace service-specific database patching with coherent construction. Session factories create new sessions; assertions read committed state independently. Do not reuse a single session across concurrent operations.
3. Review every backend test file independently against existing business specs and documentation. The audit records its purpose, decision, concrete changes or retention justification. Consolidation must identify where the surviving coverage protects the same behavior.
4. Real temporary files and available binaries are the default for successful workflows. External HTTP/cloud APIs use controlled adapters; deliberate faults and scheduler/process barriers may use narrow doubles. Keep genuine Docker coverage with existing ownership and opt-in contracts. Do not convert every domain test into a costly Docker startup.
5. Prefer public observable outcomes: HTTP status/body, fresh database reads, data bytes, preserved unrelated state, event replay and cleanup after a real terminal state. Call assertions are retained only when invocation/absence is itself the external effect or safety boundary. Strengthen permissive adapter doubles where retained.
6. Each acquired resource must be protected during setup and teardown. Fixture dependency order drains managers before database close; patches restore even when initialization fails. Remove shared mutable manager instances and redundant nested overrides.
7. Maintain the owning testing topic and reading routes. Add focused infrastructure regression tests and bounded prevention checks only where they enforce these contracts, rather than test source formatting. No CLAUDE.md exists in this checkout.

## Risks / Trade-offs

- Real SQL reveals reliance on session identity/autoflush → correct setup and assert using new sessions, preserving production configuration.
- Broad cleanup accidentally removes failure boundaries → independent file-level review, explicit consolidation mapping and complete CI qualification.
- Real binaries increase execution cost → retain capability markers and existing immutable shard planner; avoid redundant workflows while retaining distinct data-integrity assertions.
- Fault doubles resemble business duplication → keep only controls necessary to reach otherwise nondeterministic failures, with outcomes asserted through real persistence/files.
- Initialization fails midway → register cleanup when acquiring resources and test a failing setup path.

## Migration Plan

Introduce shared infrastructure, migrate domain fixtures and business scenarios, independently review the result, run targeted local checks plus Ruff/Pyright, then commit/push and run full manual qualification with `publish=false`. Revert test-only commits if necessary; no production data migration or rollback is required. Existing published-schema and migration regression tests remain intact.
