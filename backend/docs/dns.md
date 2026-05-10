# DNS Management (`app.dns`)

Keeps DNS records and the mc-router routing table in sync with the live set of managed servers. Every running server gets a wildcard DNS entry plus an SRV record (so `server.example.com` resolves to the router, which forwards to the right container) and a route in mc-router.

## Why two providers

The project is used by Chinese homelabbers (DNSPod) and Huawei Cloud customers (Huawei DNS). Both APIs do the same job — list/add/update records — but with incompatible request shapes. The `DNSClient` abstract base unifies them:

```python
class DNSClient(ABC):
    async def list_records(self) -> RecordListT: ...
    async def list_relevant_records(self) -> RecordListT: ...   # filters by managed sub-domain
    async def update_records(self, add, update, remove) -> None: ...
```

`DNSPodClient` and `HuaweiDNSClient` implement this; `SimpleDNSManager` picks one based on `dynamic_config.dns.provider`.

## How `update()` works

`SimpleDNSManager.update(db)` is the reconciliation entry point:

1. Enumerate `ACTIVE` rows from the DB via `get_active_servers(db)`, then read each row's compose in parallel to extract the game port. Per-row compose-read failures are isolated in try/except and logged-then-skipped, so one drifted row can't poison the whole tick. Records are keyed by `row.server_id` (the canonical DB identifier), not the compose project name.
2. Build the desired record set for the managed sub-domain (one wildcard A/AAAA/CNAME and one SRV per server).
3. Pull current records via `client.list_relevant_records()`.
4. `diff_dns_records()` produces add / update / remove lists.
5. `client.update_records(...)` applies them.
6. Push the same intent to mc-router via `MCRouterClient.update_routes()` so traffic actually reaches the container.

`get_current_diff(db)` runs steps 1–4 without applying — used by the frontend to render "pending changes" before the user clicks Update.

`manager.py` defers the import of `app.servers.crud.get_active_servers` to call-time because `app.servers.lifecycle` imports `app.dns`; a top-level import would close the cycle.

## mc-router

`MCRouterClient` POSTs route mappings (`server_address → localhost:port`) to mc-router's HTTP control endpoint. The router then forwards Minecraft traffic by SRV/hostname. Without this, DNS would resolve to the right machine but no port forwarding would happen.

## Triggering

DNS sync is **manual by default** — the admin clicks Update in the UI. There's also a hook in server lifecycle ops (start/stop/create/remove) that triggers `SimpleDNSManager.update()` if `dynamic_config.dns.auto_update` is true.

## Re-initialization on config change

Provider credentials (DNSPod id+key, Huawei ak+sk+region) and managed sub-domain are stored in `dynamic_config.dns`. The manager compares a hash of the relevant config on each call; if it changed, it rebuilds the provider client before continuing.

## Files

- `dns.py` — abstract `DNSClient`
- `dnspod.py` — DNSPod implementation
- `huawei.py` — Huawei Cloud implementation
- `manager.py` — `SimpleDNSManager` + `simple_dns_manager` singleton
- `router.py` — `MCRouterClient`
- `types.py` — record/diff types
- `utils.py` — `diff_dns_records`, `RecordKey`, `RecordDiff`
