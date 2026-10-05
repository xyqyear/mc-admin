## Why

Huawei DNS scenarios exist but are absent from automatic release qualification and do not independently establish correct cloud record state or that Minecraft traffic reaches the intended server. Backend reconciliation also needs coverage for paginated inventories and provider-enforced record-type conflicts.

## What Changes

- Qualify Huawei DNS through deployed application tasks, independent cloud reads, authoritative/recursive DNS and real mc-router/Minecraft traffic.
- Confine every cloud run to a unique descendant of a GitHub-configured test zone, with durable ownership evidence and independent recovery.
- Exercise lifecycle synchronization, configuration changes, idempotency, partial failures and cleanup without concealing failed business operations.
- Correct incomplete Huawei inventory reads and conflicting address-type replacement, backed by deterministic regressions.
- Add a trusted cloud workflow using environment-scoped AK/SK, scheduled/manual/main-branch execution and the same candidate release gate.
- Preserve ordinary credential-free regression and existing provider configuration compatibility.

## Capabilities

### New Capabilities
- `dns-provider-qualification`: complete inventory, conflict-aware convergence and externally observable DNS/router qualification with bounded resource ownership.

### Modified Capabilities
None.

## Impact

Backend DNS adapters and reconciliation, backend tests, Go E2E fixtures/scenarios/recovery, GitHub Actions and release evidence change. Secrets belong to GitHub Environment configuration, never source control. No frontend, public API or database migration is planned. A dedicated Docker network layout is required for real routing. Inbound firewall/NAT validation and DNSPod cloud qualification are outside this change.
