# DNS Management (`app.dns`)

DNS records and the mc-router routing table follow ACTIVE database server records, including stopped servers. Each configured address supplies a wildcard A/AAAA/CNAME record, and each server/address combination supplies an SRV record and an mc-router route. Database `server_id` identifies the server; the compose project name does not replace it.

## Planning, observation and application

`planning.py` contains pure record/route generation, route differences and `DesiredConnectivity` / `ConnectivityObservation`. `SimpleDNSManager` reads the ACTIVE inventory and each server's compose game port, observes the two external systems independently, and applies known differences. `get_dns_manager()` obtains the actual manager owned by the current Runtime. Runtime construction injects its configuration reader and Docker manager; there is no shared DNS manager instance.

`observe(db)` is read-only with respect to remote records and routes. It returns separate nullable DNS/router differences, `unknown_servers`, safe `issues`, `empty_desired` and a `state`:

| State | Meaning |
| --- | --- |
| `ready` | Both observations succeeded and no differences remain. |
| `pending` | Known differences can be applied. |
| `degraded` | An observation, server configuration read or previous application failed. |
| `empty` | There are no configured addresses or no readable ACTIVE servers; existing connectivity is retained. |

A failed remote read is unknown, never an empty record set. The affected branch performs no writes; a separately observed healthy branch can still converge. If any ACTIVE server's compose is unreadable, both plans suppress deletions, preserving its existing connectivity without guessing which old routes belong to it. Known additions and updates continue. An unavailable database inventory prevents both branches from writing.

Empty desired state retains the existing deletion policy: no configured addresses or no readable ACTIVE servers means no remote deletion. Removing some addresses or servers is reconciled when at least one address and readable server remain and the inventory is completely known. The older `get_current_diff(db)` interface still reports an error for an empty target; the status API uses the richer observation instead.

`update(db)` observes afresh before applying. It does not apply a previously displayed UI diff. Targets are independent: one failed add/update/delete does not prevent unrelated targets from being attempted. DNS writes have a maximum concurrency of four; provider methods retain their existing payload contracts. After all issued writes settle, a partial failure returns a safe error and remains visible through status. Retrying reads the actual state again and applies only remaining differences. No-change updates make no remote writes. There is no cross-provider rollback or transaction with external administrative tools.

## Providers and mc-router

`DNSClient` defines listing/filtering and incremental application over DNSPod and Huawei adapters. Filtering retains only wildcard A/AAAA/CNAME and Minecraft SRV records under the configured managed subdomain. Unrelated DNS records are outside the plan. DNSPod replaces a changed record with delete then add, retaining its propagation delay; Huawei supports updating a record in place. A failed DNSPod replacement is visible as a pending addition on the next successful observation.

`MCRouterClient` accepts both legacy string-valued route maps and objects containing `backend`, exposing backend strings through MC Admin's API. Missing, empty or non-string backend values fail observation; they do not authorize deleting routes. DELETE 404 succeeds idempotently; other remote failures remain failures.

Route application POSTs only additions and changed backends, then DELETEs only obsolete routes. POST upserts an existing route, so changing one backend does not remove all routes or disturb unchanged routes. The dedicated router's existing complete-table ownership policy remains; an empty manager target is protected as described above. The low-level `override_routes({})` adapter operation still means clearing the table.

The upsert contract is qualified against the real owned image `itzg/mc-router@sha256:e06735ea74877a7de649bcaec4cb917bf952564d32cbe258670fb7753192a1e9` (1.46.5). Its [API handler](https://github.com/itzg/mc-router/blob/d99439c1ae3195aecb714a11b9f227a96a961f64/server/api_server.go) calls the [mapping replacement implementation](https://github.com/itzg/mc-router/blob/d99439c1ae3195aecb714a11b9f227a96a961f64/server/routes.go). The Docker contract test checks real upserts, idempotent deletion, zero mutations for an unchanged plan, and availability of an unchanged route around every changed route request. Provider failure tests use controlled adapters and never contact a real cloud account.

## API and lifecycle

The existing `/dns/enabled`, `/dns/status`, `/dns/records`, `/dns/routes` and `/dns/update` routes retain their authorization and success payloads. Status adds `state`, `dns_known`, `router_known`, `unknown_servers`, `issues` and `empty_desired`; an unknown side has a null diff. The frontend can display a partial failure and retry without treating unknown data as successful synchronization. Disabled DNS still returns 503 for status/records/routes/update, while enabled-state reads remain available.

Explicit API updates, application startup and server create/remove/sync orchestration trigger reconciliation. DNS failures are reported without reversing the completed local server operation. There is no `auto_update` dynamic configuration field or background retry loop.

Provider credentials, addresses, managed subdomain, TTL and router URL live in dynamic configuration. Before each action, enabled/provider/router settings determine whether clients need replacement; planning reads the current addresses/subdomain/TTL. Initialization, observation, update, direct reads and shutdown share one manager lock and captured configuration. Concurrent page queries cannot close a client while another query uses it. Issued write batches drain even when their caller is cancelled, before shutdown or the next action obtains the lock.

Each constructed client is immediately registered for cleanup. Provider initialization failure can leave the independent router available in degraded mode; a later action retries provider initialization. If cleanup itself fails, the unclosed client remains owned and shutdown retries it, while other clients are still closed. Disabling clears active clients and stops synchronization before enumerating servers or writing records. Re-enabling builds clients from the current configuration.

## Files

- `planning.py` — pure desired state, route differences and observation result.
- `manager.py` — application orchestration, per-Runtime accessor and client lifecycle.
- `dns.py`, `dnspod.py`, `huawei.py` — common provider operations and external adapters.
- `router.py` — MC Router HTTP adapter and incremental changes.
- `api_models.py` — public DNS response DTOs.
- `types.py`, `utils.py` — record types, keys and DNS differences.

Focused checks: `uv run pytest --no-cov -q tests/dns` and the owned external contract `uv run pytest --no-cov -q tests/dns/test_router_live.py --run-docker`.
