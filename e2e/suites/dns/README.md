# DNS qualification

`dns.disabled-and-validation` is part of ordinary regression. It covers all five DNS routes with a disabled provider, authentication, and invalid configuration without cloud access.

`dns.owned-edge-reconciliation` is also ordinary regression and needs no cloud credentials. The deployed application uses its original DNSPod SDK over HTTPS against a protocol server owned by this case, with a real digest-pinned MC Router behind a recording HTTP edge. It verifies known versus unknown observations, isolation of target failures, fresh retry, zero writes without changes, individual route upserts, preservation for empty targets/disabled configuration, and safe degraded health findings without stopping unrelated checks or local server synchronization.

This fixture generates its own short-lived certificate, appends it only to the owned backend container's CA bundle, and maps the provider hostname only in that container's `/etc/hosts`. Its HTTPS/control/router-edge ports bind loopback in the backend's private network namespace. No host trust, host name mapping, host port, cloud account or application implementation is modified. The helper container is registered in the environment ownership journal before creation and removed with the deployment. A failed bind fails the fixture; it never stops an unknown process. The helper implements the documented DNSPod response envelope and record calls but does not qualify cloud authentication, propagation, quotas or asynchronous provider jobs; those require the external scenarios below.

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
      "domain": "e2e-test-mc.example.com",
      "managed_sub_domain": "",
      "prefix": "run",
      "ak": "Huawei access key",
      "sk": "Huawei secret key",
      "region": "cn-north-4",
      "ttl": 600
    }
  }
}
```

The domain must already exist in that provider's public DNS service. The supplied credentials must permit domain/record listing and creation, modification and deletion of test records. The prefix authorizes an isolated namespace: every environment uses `<prefix>-<12 hexadecimal environment ID>.<managed_sub_domain>`. The optional parent is omitted for legacy configurations. The runner refuses a generated scope containing pre-existing records. It never loads production configuration.

```bash
mc-admin-e2e run --backend-image mc-admin:e2e \
  --tag external --case '^dns\.dnspod-' \
  --external-config /private/path/external.json
```

Each scenario uses an API-created server and its Compose game-port mapping, a real digest-pinned mc-router container, and the actual provider. A running Minecraft process is unnecessary for this routing-control contract. The router's API shares the private backend network namespace and is bound to loopback. The scenario tests enabled state, non-mutating previews, A/AAAA/SRV creation, idempotency, configuration refresh, upstream router drift, value/port updates, CNAME conversion, address removal, and the enabled DNS self-check.

Backend reconciliation intentionally skips an empty address/server set. The scenario tests removal while retaining one desired address; final cloud cleanup uses independent vendor SDK calls rather than an application reset endpoint. The helper is shipped inside the executable and runs with the installed SDKs from the application image. It lists records with pagination and deletes only wildcard/SRV records and the exact owned protection TXT record under the generated scope. A TXT record in each scope must survive application reconciliation. Unexpected records remain untouched and cause cleanup to fail. Cleanup is registered before API writes and completes before local environment destruction. Credentials are written only to private runtime files and registered with the evidence redactor.

Cloud ownership is saved in `<run-directory>/cloud/<environment-id>.json` before mutation, outside disposable runtime data. Manifests contain no credentials and validate the exact domain, parent, prefix and environment ID. Normal cleanup stops the backend writer before deleting cloud records through a standalone helper container; it then verifies the scope is empty. A failed cleanup fails the case. For interrupted runs, reclaim the local writer first and then recover each recorded cloud scope:

```bash
mc-admin-e2e cleanup --run-dir /path/to/run
mc-admin-e2e cleanup-dns --manifest /path/to/run/cloud/ENVIRONMENT.json \
  --external-config /private/path/external.json --backend-image mc-admin:e2e
```

Recovery locks the manifest and refuses a scope while a matching environment container is running. It works without the original backend or runtime directory, preserves unexpected records and is idempotent. Retain/download the `cloud/` manifests with the run evidence. Complete runner/host loss before artifact upload may lose local evidence; never guess a scope from a broad prefix or infer cloud cleanup from Docker cleanup.

`dns.router-minecraft-traffic` runs in ordinary regression without cloud credentials. It uses a host-network backend and router, leased ports and a real Minecraft server with a unique MOTD. Backend/router APIs bind loopback. The router's game listener allows only loopback clients; mc-router does not expose a game bind-address option. A failed cloud branch still permits router convergence; the case verifies the correct hostname, rejects an unknown hostname and repairs a drifted route.

`dns.huawei-minecraft-connectivity` verifies cloud records through independent SDK reads and authoritative DNS over TCP, checks initial recursive SRV resolution, then uses actual SRV/A answers to connect to the router and verify the unique Minecraft MOTD. It checks startup repair, automatic create/remove/sync triggers, changed router/SRV port and preservation for stopped ACTIVE servers. Unique run names avoid previous-run caches; subsequent changes use authoritative answers because recursive caches may retain prior TTLs. The router destination is the runner's loopback address, so Internet inbound firewalls/NAT and external player reachability remain outside this contract.

`dns-tests.yml` runs Huawei qualification on main changes, daily, manually and as a required same-candidate release gate. The protected `dns-e2e` GitHub Environment stores `HUAWEICLOUD_AK`/`HUAWEICLOUD_SK`; credentials are injected only into cloud execution and unconditional recovery steps. Allow only main, release tags and explicitly authorized development branches in that Environment. The cloud IAM identity is restricted to the dedicated test zone. Missing credentials are failures, never skips. Ordinary PR regression receives no Huawei credentials. DNSPod remains an explicit manual selection using `E2E_EXTERNAL_CONFIG`.

The router image currently returns route objects containing `backend` and `scalingTarget`; MC Admin normalizes these to its public string-valued route map and also supports legacy strings. This format is documented by [mc-router's REST API](https://github.com/itzg/mc-router#rest-api).

Create a dedicated public test zone such as `e2e-test-mc.example.com`, with working public delegation to its Huawei nameservers. This fixed zone retains its SOA/NS records; each run creates and removes its own descendant records. Create a programmatic IAM user and attach the [identity policy template](huawei-policy.example.json), replacing the account and **test-zone** IDs. The policy grants zone/quota listing and record operations only in that dedicated zone; it does not grant zone creation/deletion or record access to the parent zone. See Huawei's [DNS authorization reference](https://support.huaweicloud.com/api-dns/Permission.html). Allow IAM authorization to propagate before qualification.

Configure the GitHub `dns-e2e` Environment before running the workflow:

| Setting | Kind | Example / purpose |
| --- | --- | --- |
| `HUAWEICLOUD_AK`, `HUAWEICLOUD_SK` | Secrets | Dedicated IAM access key and secret key |
| `HUAWEICLOUD_DNS_ZONE` | Variable, required | `e2e-test-mc.example.com` |
| `HUAWEICLOUD_DNS_PARENT` | Variable, optional | Empty for a dedicated test zone; otherwise an explicitly authorized relative parent |
| `HUAWEICLOUD_DNS_REGION` | Variable, optional | `cn-north-4` by default |

Keep actual account domains and credentials in GitHub configuration or a private local JSON file, never in source, examples or committed test evidence. Successful, failed and cancelled scenarios all execute independent cloud cleanup. The workflow repeats recovery in an `always()` step and fails if cleanup cannot be verified; use retained manifests for explicit recovery when infrastructure or provider outages prevent completion.
