## Context

See proposal.md, docs/ci.md, backend/docs/testing.md, e2e/docs/architecture.md, frontend-react/docs/browser-tests.md and docs/release.md. Backend costs are committed per-file estimates; API costs are embedded estimates. Browser cases have JSON durations but one shared owned world. Huawei already uses ordinary Fresh E2E cases but has a separate protected workflow and release gate.

## Goals / Non-Goals

Preserve exact coverage, deterministic planning, resource ownership, independent runner isolation and protected cloud authorization. The budget is execution plus fixture initialization and cleanup, not installation or queueing. Application behavior, persistence, assertion retries and case deadlines are outside the change.

## Decisions

1. A shared Python history transport restores and wraps component cost payloads. Versioned envelopes identify component, execution profile, compatibility fingerprint, source run/attempt/commit/branch and costs. Restore selects the latest available audited family artifact on the branch, then trusted main; absent, expired or invalid records explicitly fall back. Fingerprints represent measurement/fixture/resource configuration, not the source commit, so history remains usable across commits. Each planner restores once and distributes the frozen snapshot and plan.
2. Plans target 300 seconds with bounded automatic shard counts and separate concurrency limits. Backend retains whole-file/shared-fixture boundaries and sequential pytest. API retains Fresh/reusable groups and predicts serial group/resource occupancy, including the longest-group lower bound. Browser uses explicit stable case identities, serial workers and a private owned world per shard, adding repeated world setup and cleanup to every estimate. Oversized units prefer their own shard when capacity allows; plans report indivisible work, fixed overhead or shard limits that prevent meeting the target. No deadline is reduced.
3. Component adapters normalize actual phases into reusable cost payloads only after exact coverage and success audits. Backend retains per-node phases and sums them to current files. API retains lifecycle phases and accounts for reuse setup/retirement once per group. Browser adds wrapper setup/command/cleanup measurements and audits its discovered full inventory against assigned and passed case identities. Raw failed evidence remains diagnostic but is never published as successful history.
4. API qualification uses one run-level expected catalog and immutable plan with ordinary and protected Huawei execution capabilities. Only cloud execution receives dns-e2e Environment credentials and private configuration. A trusted qualification request independently requires all current Huawei cases; a self-reported reduced catalog cannot satisfy it. The aggregate API audit validates ordinary API observations, all expected shard/case identities, candidate identity, local cleanup and exact cloud scope cleanup. Release depends on this aggregate API gate and no independent DNS gate. Explicit DNSPod/Mojang selections remain explicit and are not implicitly added.
5. Shared history is scheduling evidence only; candidate artifacts and qualification receipts continue to belong to the current run. Artifact restore is read-only, history publication is an audited artifact upload, and no automatic commits or repository writes are required. Missing history does not suppress tests.

## Risks / Trade-offs

- Larger matrices repeat fixture work and encounter account queueing: keep a maximum shard count and explicit concurrency budgets, report preparation separately.
- Indivisible files/cases or fixed overhead exceed five minutes: report oversized units and preserve the soft target.
- Cloud recovery is distinct from Docker recovery: preserve EXIT and unconditional recovery, exact scope ownership validation and non-secret manifests.
- Stale or incompatible costs produce poor placement: fingerprint execution context, retain positive fallback estimates and record the historical source.
- A partial matrix appears successful: audit complete current inventories, assignment identity, exact-once outcomes and cleanup before learning or qualification.

## Migration Plan

Implement on perf/automatic-timed-shards. Keep committed initial costs as the cold-start fallback. Update scoped AGENTS, CI/release/component documentation and release gate contracts. Run only affected planner/history/release/framework tests and required static checks locally; push and qualify the exact latest commit with publish=false. Wait with one persistent gh run watch command and inspect the final result once. Reverting this infrastructure change restores fixed sharding and the separate DNS gate; no application data migration is needed.
