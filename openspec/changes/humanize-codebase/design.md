## Context

See proposal.md for motivation. The reviewed audit is the implementation scope; each retained finding has explicit preservation constraints. Existing ownership and lifecycle design lives in `backend/docs/runtime.md`, `operations.md`, `files.md`, `world-restore.md`, `cron.md` and `dns.md`. Frontend boundaries and observer lifetimes live in `frontend-react/docs/data-architecture.md`, `cron-management.md`, `file-management.md` and map documents; E2E isolation lives in `e2e/docs/architecture.md`.

## Goals / Non-Goals

Make concrete dependencies and policies readable and independently verifiable. Preserve supported wire formats, error status/timing, generation checks, finite cancellation, durable recovery and real ownership boundaries. Do not consolidate implementations whose error or permission policies differ, delete valid SDK/HTTP mocks, or replace concrete duplication with a generic framework.

## Decisions

- Establish trustworthy business oracles before removing duplicate tests or changing structure. Concurrency uses explicit entry/release gates and fresh committed reads; expected data is literal or independently captured, never computed through the production algorithm.
- Separate approved behavior fixes from cleanup commits. Cron input, directory selection, stream termination and safe error output get explicit regression coverage and specification updates. Safe output is based on message ownership, not merely an exception class.
- Use typed concrete lazy runtime fields and direct named feature hooks. Keep optional resources distinct from uninitialized ones and close the current replacement instance; avoid registries, descriptors and invented extension points.
- Retain distinct live/preview world workflows and strict/best-effort ownership behavior. Share only equivalent small operations and actual multi-implementation render interfaces.
- Execute dependencies explicitly: frontend dead exports before hook migration; Cron/selection fixes before their refactors; safe decorator output before retiring unused synchronous/custom fallback capabilities; process-monitoring characterization before runtime resource changes.
- Measure process constructor and OCI memory costs using owned inputs. A finding can finish with a justified removal of an ineffective cache or a bounded reader; measurements determine the choice rather than an assumed performance benefit.
- Keep all subagent changes on one independent branch with disjoint file ownership. Separate reviewers inspect implementation diffs and test oracles, fixes repeat until no material revision remains.

## Risks / Trade-offs

- Broad refactoring can obscure behavior changes → atomic logical commits, explicit finding IDs, targeted characterization and independent review.
- Runtime cleanup can release artifacts too early → retain shutdown ordering, current-instance ownership and unknown-writer evidence; exercise failure and cancellation gates.
- Tree and map consolidation can lose caller-specific ordering or lifecycle → keep policy with each caller and share only path/coordinate primitives.
- Local test limits leave unexecuted paths → run required static checks and qualify all backend/API/browser inventories remotely for the latest commit.

## Migration Plan

No schema or data migration is required. Backend and frontend ship together. Existing retained history is neither rewritten nor purged. Push the implementation branch, qualify the exact latest SHA with `publish=false`, and report its complete gate results. Reverting a logical cleanup commit restores its internal implementation without changing supported stored data.
