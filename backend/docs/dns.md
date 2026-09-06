# DNS Management (`app.dns`)

Keeps DNS records and the mc-router routing table in sync with active database server records, including stopped servers. Each configured address supplies a wildcard A/AAAA/CNAME record, and each server/address combination supplies an SRV record and an mc-router route.

## Why two providers

The project is used by Chinese homelabbers (DNSPod) and Huawei Cloud customers (Huawei DNS). Both APIs do the same job — list/add/update records — but with incompatible request shapes. The `DNSClient` abstract base unifies them:

```python
class DNSClient:
    async def list_records(self) -> RecordListT: ...
    async def list_relevant_records(self, managed_sub_domain: str) -> RecordListT: ...
    async def update_records(self, target_records, managed_sub_domain=None) -> None: ...
```

`DNSPodClient` and `HuaweiDNSClient` implement this; `SimpleDNSManager` picks one based on `config.dns.dns.type`.

## How `update()` works

`SimpleDNSManager.update(db)` is the reconciliation entry point:

1. Enumerate `ACTIVE` rows from the DB via `get_active_servers(db)`, then read each row's compose in parallel to extract the game port. Per-row compose-read failures are isolated in try/except and logged-then-skipped, so one drifted row can't poison the whole tick. Records are keyed by `row.server_id` (the canonical DB identifier), not the compose project name.
2. Build the desired record set for the managed sub-domain (one wildcard A/AAAA/CNAME and one SRV per server).
3. Pull current records via `client.list_relevant_records()`.
4. `diff_dns_records()` produces add / update / remove lists.
5. `client.update_records(...)` applies them.
6. Push the same intent to mc-router via `MCRouterClient.override_routes()` so traffic actually reaches the container.

`get_current_diff(db)` runs steps 1–4 without applying — used by the frontend to render "pending changes" before the user clicks Update.

When no configured addresses or readable active servers remain, update skips reconciliation and diff calculation fails. Empty desired state does not delete existing cloud records. Removal of some addresses/servers is reconciled while at least one address and server remain.

`manager.py` defers the import of `app.servers.crud.get_active_servers` to call-time because `app.servers.lifecycle` imports `app.dns`; a top-level import would close the cycle.

## mc-router

`MCRouterClient` POSTs route mappings (`server_address → localhost:port`) to mc-router's HTTP control endpoint. It accepts both legacy string-valued route maps and current objects containing `backend` and `scalingTarget`, exposing the backend address through MC Admin's string-valued API. Deleting a route that already returns HTTP 404 succeeds idempotently; other HTTP failures and missing, empty or non-string backend values fail reconciliation. This validation does not check address syntax. Replacement removes existing routes before adding the desired routes, without transactional rollback or multi-writer isolation. The router then forwards Minecraft traffic by SRV/hostname.

## Triggering

The DNS API supports explicit reconciliation. Application startup and server creation/removal/synchronization orchestration also attempt updates; lifecycle update failures are logged without reversing the completed server operation. There is no `auto_update` dynamic configuration field.

## Re-initialization on config change

Provider credentials (DNSPod id+key, Huawei ak+sk+region), managed sub-domain, addresses, TTL and router URL are stored in `config.dns`. Before updates and diff calculation, a hash of enabled state, provider configuration and router URL determines whether to rebuild clients. Managed sub-domain, addresses and TTL are read when calculating the desired state.

## Files

- `dns.py` — abstract `DNSClient`
- `dnspod.py` — DNSPod implementation
- `huawei.py` — Huawei Cloud implementation
- `manager.py` — `SimpleDNSManager` + `simple_dns_manager` singleton
- `router.py` — `MCRouterClient`
- `types.py` — record/diff types
- `utils.py` — `diff_dns_records`, `RecordKey`, `RecordDiff`
