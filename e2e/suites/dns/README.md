# DNS qualification

`dns.disabled-and-validation` is part of ordinary regression. It covers all five DNS routes with a disabled provider, authentication, and invalid configuration without cloud access.

`dns.owned-edge-reconciliation` is also ordinary regression and needs no cloud credentials. The deployed application uses its original DNSPod SDK over HTTPS against a protocol server owned by this case, with a real digest-pinned MC Router behind a recording HTTP edge. It verifies known versus unknown observations, isolation of target failures, fresh retry, zero writes without changes, individual route upserts, preservation for empty targets/disabled configuration, and safe degraded health findings without stopping unrelated checks or local server synchronization.

This fixture generates its own short-lived certificate, appends it only to the owned backend container's CA bundle, and maps the provider hostname only in that container's `/etc/hosts`. Its HTTPS/control/router-edge ports bind loopback in the backend's private network namespace. No host trust, host name mapping, host port, cloud account or application implementation is modified. The helper container is registered in the environment ownership journal before creation and removed with the deployment. A failed bind fails the fixture; it never stops an unknown process. The helper implements the documented DNSPod response envelope and record calls but does not qualify cloud authentication, propagation, quotas or asynchronous provider jobs; those require the external scenarios below.

The DNSPod and Huawei scenarios have `external,dns` tags and belong to the unified API catalog. Ordinary regression excludes these cloud scenarios. Complete `qualification` independently requires every current Huawei case; DNSPod remains an explicit manual profile. They require a public-zone configuration and credentials; missing configuration fails the scenario and never becomes a skip. Only the selected provider's object is required:

```json
{
  "dns": {
    "dnspod": {
      "domain": "test.example.com",
      "managed_sub_domain": "",
      "id": "Tencent Cloud SecretId",
      "key": "Tencent Cloud SecretKey",
      "ttl": 600
    },
    "huawei": {
      "domain": "test.example.com",
      "managed_sub_domain": "",
      "ak": "Huawei access key",
      "sk": "Huawei secret key",
      "region": "cn-north-4",
      "ttl": 600
    }
  }
}
```

The domain must already exist in that provider's public DNS service. The supplied credentials must permit domain/record listing and creation, modification and deletion of test records. Record names use the common environment ID followed by the optional relative `managed_sub_domain`: `<environment-id>[.<managed_sub_domain>]`. Each environment has its own name so concurrent reconciliation does not overwrite another environment's targets. The optional parent defaults to empty.

```bash
mc-admin-e2e run --backend-image mc-admin:e2e \
  --tag external --case '^dns\.dnspod-reconciliation$' \
  --external-config /private/path/external.json
```

This local example selects the reconciliation case only when it is related to the change. Keep explicit anchored case IDs for local validation; complete provider qualification belongs to CI.

Each scenario uses an API-created server and its Compose game-port mapping, a real digest-pinned mc-router container, and the actual provider. A running Minecraft process is unnecessary for this routing-control contract. The router's API shares the private backend network namespace and is bound to loopback. The scenario tests enabled state, non-mutating previews, A/AAAA/SRV creation, idempotency, configuration refresh, upstream router drift, value/port updates, CNAME conversion, address removal, and the enabled DNS self-check.

Backend reconciliation intentionally skips an empty address/server set. The scenario tests removal while retaining one desired address; final cloud cleanup uses independent vendor SDK calls rather than an application reset endpoint. The helper is shipped inside the executable and runs with the installed SDKs from the application image. It lists records with pagination and deletes only wildcard/SRV records and the exact protection TXT fixture under the recorded scope. A TXT record in each scope must survive application reconciliation. Unrelated records remain untouched; remaining managed records cause cleanup to fail. Cleanup is registered before API writes and completes before local environment destruction. Credentials are written only to private runtime files and registered with the evidence redactor.

Cloud resource details are saved in `<run-directory>/cloud/<environment-id>.json` before mutation, outside disposable runtime data. Manifests contain no credentials and record the provider, domain and relative scope. Cleanup uses the recorded domain and scope with currently supplied provider credentials, even if the configured default domain changes. Normal cleanup stops the backend writer before deleting cloud records through a standalone helper container; it then verifies that managed records and the TXT fixture are absent. A failed cleanup fails the case. For interrupted runs, reclaim the local writer first and then recover each recorded cloud scope:

```bash
mc-admin-e2e cleanup --run-dir /path/to/run
mc-admin-e2e cleanup-dns --manifest /path/to/run/cloud/ENVIRONMENT.json \
  --external-config /private/path/external.json --backend-image mc-admin:e2e
```

Recovery locks the manifest and refuses a scope while a matching environment container is running. It works without the original backend or runtime directory, preserves unrelated records and is idempotent. Retain/download the `cloud/` manifests with the run evidence. Complete runner/host loss before artifact upload may lose local evidence; use recorded scopes for recovery and verify cloud cleanup independently of Docker cleanup.

`dns.router-minecraft-traffic` runs in ordinary regression without cloud credentials. It uses a host-network backend and router, leased ports and a real Minecraft server with a unique MOTD. Backend/router APIs bind loopback. The router's game listener allows only loopback clients; mc-router does not expose a game bind-address option. A failed cloud branch still permits router convergence; the case verifies the correct hostname, rejects an unknown hostname and repairs a drifted route.

`dns.huawei-minecraft-connectivity` verifies cloud records through independent SDK reads and authoritative DNS over TCP, checks initial recursive SRV resolution, then uses actual SRV/A answers to connect to the router and verify the unique Minecraft MOTD. It checks startup repair, automatic create/remove/sync triggers, changed router/SRV port and preservation for stopped ACTIVE servers. Unique run names avoid previous-run caches; subsequent changes use authoritative answers because recursive caches may retain prior TTLs. The router destination is the runner's loopback address, so Internet inbound firewalls/NAT and external player reachability remain outside this contract.

The unified `e2e-tests.yml` API workflow runs complete `qualification` on main changes, daily, explicit manual selection and release's same-candidate `qualification: true` gate. One immutable current-catalog plan globally allocates all 85 required ordinary/Huawei cases into one matrix, with at most 16 total shards and eight concurrent jobs. Ordinary and Huawei atomic groups may share a shard; each runner retains two workers and one Minecraft slot, and cases use the common explicitly declared environment lifecycle. The 300-second soft execution target includes fixture initialization and cleanup, while preflight/image preparation and CI installation are measured or handled separately. Oversized lifecycle groups retain their full deadlines.

The `dns-e2e` GitHub Environment stores `HUAWEICLOUD_AK`/`HUAWEICLOUD_SK` and provider variables. Every API shard uses it as an unrestricted configuration store with no branch restrictions or protection rules. Provider dependencies derived from each shard's assigned cases select its required private configuration and unconditional recovery, and only provider steps receive the credentials they need. Missing credentials are failures, never skips. Ordinary PR regression selects 83 cases without cloud dependencies or credentials. DNSPod remains an explicit manual selection using `E2E_EXTERNAL_CONFIG`.

The final API audit independently requires every current Huawei case, exact-once successful results, matching source/image/executable/plan identities and completed cleanup in recorded cloud manifests. Missing, failed or skipped cases and uncleared managed records fail qualification even if Docker cleanup succeeded. Compatible audited history is restored once from the same branch, then main, and frozen into the plan; it affects costs and placement only. History publication follows complete API coverage and verified local/cloud cleanup, retaining measurement and source identities for subsequent runs. Historical verification records retain their original workflow and shard evidence.

The router image currently returns route objects containing `backend` and `scalingTarget`; MC Admin normalizes these to its public string-valued route map and also supports legacy strings. This format is documented by [mc-router's REST API](https://github.com/itzg/mc-router#rest-api).

Use an existing public zone such as `test.example.com` with working public delegation to its Huawei nameservers. Its SOA/NS records remain in place while each environment creates and removes its own descendant records. Supply credentials with the zone/record listing and record mutation permissions needed by the real scenarios.

Configure the GitHub `dns-e2e` Environment before running the workflow:

| Setting | Kind | Example / purpose |
| --- | --- | --- |
| `HUAWEICLOUD_AK`, `HUAWEICLOUD_SK` | Secrets | Provider access key and secret key |
| `HUAWEICLOUD_DNS_ZONE` | Variable, required | `test.example.com` |
| `HUAWEICLOUD_DNS_PARENT` | Variable, optional | Relative parent appended after the common environment ID; empty by default |
| `HUAWEICLOUD_DNS_REGION` | Variable, optional | `cn-north-4` by default |

Keep actual account domains and credentials in GitHub configuration or a private local JSON file, never in source, examples or committed test evidence. Successful, failed and cancelled scenarios all execute independent cloud cleanup. The workflow repeats recovery in an `always()` step and fails if cleanup cannot be verified; use retained manifests for explicit recovery when infrastructure or provider outages prevent completion.

[Qualification evidence](../../../docs/evidence/huawei-dns-qualification.json) records the tested revision, real cloud and Minecraft observations, interrupted-run cleanup and independent cloud closeout without account domains or credentials.
