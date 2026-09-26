## Why

The successful beta qualification took 56 minutes because 25 backend groups ran serially and three API shards had substantially different workloads. Balance execution by measured cost while retaining every scenario, isolation boundary, capability check and release gate.

## What Changes

- Plan four deterministic backend shards from the complete collected inventory and historical file costs; record precise setup/call/teardown durations and retain exact-once audits.
- Balance API groups by worker and Minecraft costs, dispatch resource-ready groups, and expose timing phases without changing scenario assertions or reuse contracts.
- Allocate Docker fixture host ports dynamically, harden pinned downloads, and avoid obsolete branch runs occupying capacity.
- Execute the complete qualification workflow on an implementation branch with publication disabled, then compare actual timings with the successful baseline.

Non-goals: changing product behavior, persistence, HTTP contracts, weakening coverage, publishing a release, or introducing concurrent pytest workers within a shared Docker host. Cross-run reuse of qualification evidence requires a separate provenance design and is not used in this change.

## Capabilities

No product or E2E behavioral requirements change. This is test infrastructure and scheduling work; `skip_specs: true` preserves the existing deterministic coverage, isolation, cleanup and release requirements.

## Impact

Backend test infrastructure and fixtures, the standalone Go E2E engine and reports, GitHub workflows, test timing metadata and current-state documentation. Frontend test reporting may gain machine-readable output. Production APIs, configuration, database schema and the published image behavior remain compatible; there are no breaking changes or migrations.
