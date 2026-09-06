# DNS qualification

`dns.disabled-and-validation` is part of ordinary regression. It covers all five DNS routes with a disabled provider, authentication, and invalid configuration without cloud access.

The DNSPod and Huawei scenarios have `external,dns` tags. They require an explicitly supplied test-domain configuration; missing configuration fails the scenario and never becomes a skip. Only the selected provider's object is required:

```json
{
  "dns": {
    "dnspod": {
      "domain": "test.example.com",
      "prefix": "e2e",
      "id": "Tencent Cloud SecretId",
      "key": "Tencent Cloud SecretKey",
      "ttl": 600
    },
    "huawei": {
      "domain": "test.example.com",
      "prefix": "e2e",
      "ak": "Huawei access key",
      "sk": "Huawei secret key",
      "region": "cn-south-1",
      "ttl": 600
    }
  }
}
```

The domain must already exist in that provider's public DNS service. The supplied credentials must permit domain/record listing and creation, modification and deletion of test records. The prefix authorizes an isolated namespace: every environment uses `<prefix>-<12 hexadecimal environment ID>`. The runner refuses a generated scope containing pre-existing records. It never loads production configuration.

```bash
mc-admin-e2e run --backend-image mc-admin:e2e \
  --tag external --case '^dns\.dnspod-' \
  --external-config /private/path/external.json
```

Each scenario uses an API-created server and its Compose game-port mapping, a real digest-pinned mc-router container, and the actual provider. A running Minecraft process is unnecessary for this routing-control contract. The router's API shares the private backend network namespace and is bound to loopback. The scenario tests enabled state, non-mutating previews, A/AAAA/SRV creation, idempotency, configuration refresh, upstream router drift, value/port updates, CNAME conversion, address removal, and the enabled DNS self-check.

Backend reconciliation intentionally skips an empty address/server set. The scenario tests removal while retaining one desired address; final cloud cleanup uses independent vendor SDK calls rather than an application reset endpoint. The helper is shipped inside the executable and runs with the installed SDKs from the application image. It lists records with pagination and deletes only wildcard/SRV records under the exact generated scope. Cleanup is registered before API writes and completes before local environment destruction. Credentials are written only to private runtime files and registered with the evidence redactor.

The local Docker recovery journal cannot clean a cloud account after SIGKILL or host loss. The `external_dns_scope` evidence event records the provider, domain and generated scope. If normal cloud cleanup fails or the process is killed, use the supplied test account to delete only wildcard/SRV records beneath that scope before considering qualification cleanup complete. Do not infer cloud cleanup success from local Docker cleanup success. These external scenarios have not been qualified until run against supplied test credentials.

The router image currently returns route objects containing `backend` and `scalingTarget`; MC Admin normalizes these to its public string-valued route map and also supports legacy strings. This format is documented by [mc-router's REST API](https://github.com/itzg/mc-router#rest-api).
