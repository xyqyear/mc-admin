## Context

See `backend/docs/dns.md`, `e2e/docs/architecture.md`, `e2e/suites/dns/README.md` and the proposal. Existing Huawei qualification runs the deployed SDK and an independent inspector, but only reads control-plane data. The application generates `localhost:<published game port>` routes. Current bridge-network router fixtures cannot reach host-loopback game ports. Cloud cleanup currently depends on the live backend container.

## Goals / Non-Goals

**Goals:** reuse the existing scenario engine and candidate artifacts; prove actual cloud record state and Minecraft routing behavior; keep cloud ownership recoverable even after local containers disappear; retain cancellation, independent-branch and empty-target semantics.

**Non-Goals:** no production reset endpoint, database migration, frontend changes, provider-wide cleanup, DNSPod live credentials, public Internet ingress qualification.

## Decisions

1. Paginate Huawei zone/record listing and test later-page matches and read failures. For incompatible type changes, capture the observed removed records in the internal diff and pair only conflicting names; unrelated additions still run independently. Never delete all records before applying a plan.
2. Add an optional authorized `managed_sub_domain` to external configuration. Generate `<prefix>-<environment-id>.<managed_sub_domain>`; preserve the previous label-only format when absent. CI loads the dedicated test zone and optional parent from GitHub Environment variables; account domains never appear in source or examples. Recovery validates full scope, environment ID and zone boundaries.
3. Share strict known/ready status assertions across cloud and controlled cases. Use independent vendor SDK reads, authoritative DNS over TCP, a first recursive SRV observation and a Minecraft status handshake. Validate record names, values, types and TTLs, then connect to the DNS-derived router address and port using the game hostname. Never retry a failed scenario into success.
4. Introduce a host-network backend recipe on the supported local Linux Docker host, with leased loopback HTTP, router API/listener and game ports. This keeps generated localhost routes meaningful without changing product behavior. The ordinary router traffic case needs no cloud credential; cloud cases add independent provider record verification and real DNS resolution. Host networking is limited to explicitly selected owned recipes and every port remains leased through teardown.
5. Persist a non-secret cloud ownership manifest before the first cloud write. A standalone recovery command executes the embedded vendor helper in an ephemeral application-image container, supplied current credentials through a private runtime file. Scope checks, cleanup and verification do not require a functioning application. Recovery is idempotent and reports residual records. Scheduled stale-scope recovery only uses explicit ownership manifests, never a guessed DNS prefix.
6. Add an environment-protected Huawei workflow with narrowly injected `HUAWEICLOUD_AK`/`HUAWEICLOUD_SK`. Run one serial cloud worker and retain reports, redacted diagnostics and manifests. Main-branch, scheduled and manual runs qualify a candidate; release invokes the same reusable workflow with its existing candidate and adds the cloud gate to qualification validation.

## Risks / Trade-offs

- Cloud API success before visibility → verify provider reads, retain task failures, and verify cleanup after deletion.
- Runner loss → upload durable ownership evidence before mutations where practical and retain the artifact for explicit recovery; cloud cleanup success cannot be inferred from Docker cleanup.
- SDK or audit credential exposure → register secrets before use, avoid raw exception output and never upload runtime credentials or databases.
- Shared host ports → leases, explicit loopback bindings and immediate failure on collision; do not stop unrelated processes.

## Migration Plan

No data migration. Existing external JSON remains accepted. Install the dedicated GitHub Environment and limited cloud credentials before enabling release requirements. Validate locally, push the implementation branch, and run complete non-publishing qualification for its exact SHA. Reverting the change restores prior test selection; recorded cloud scopes must still be reclaimed. Update root/backend/E2E CLAUDE files and DNS, CI, release, architecture and coverage documentation to describe final behavior.
