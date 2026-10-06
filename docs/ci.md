# CI scheduling and verification

The release qualification graph builds one immutable candidate while static checks and backend tests run independently. API and browser shards consume the same candidate. See [release qualification](release.md) for source and image identity checks.

## Scheduling budget

Backend, API and browser planners target 300 seconds of execution per shard, including fixture initialization and cleanup. Checkout, dependency installation, OCI/Chromium preparation and runner queueing are reported separately. The target is not a deadline: test assertions, propagation waits and independent cleanup budgets retain their contracts. Plans create additional shards when predicted execution exceeds the target, within explicit shard/concurrency limits. Oversized indivisible units and fixed overhead are reported rather than truncated or retried.

Backend runners execute pytest sequentially without worker processes sharing Docker fixtures. Planning retains whole files and shared-fixture groups, assigns longest-cost units first and derives capabilities from selected tests. Actual setup/call/teardown costs are aggregated from current node identities; unseen tests receive positive fallback estimates. Exact node-ID and execution-phase audits remain mandatory before combined coverage and timing publication.

API planning globally allocates every atomic group selected by a profile into one immutable plan and one matrix. Fresh cases and reusable recipe groups remain intact; groups with different provider dependencies may share a shard. The matrix permits at most 16 shards and 16 concurrent jobs, with two workers and one Minecraft slot per runner. Provider requirements supply dependency metadata and credential/recovery bindings. PR regression, ordinary automatic CI and complete qualification select every current API case except DNSPod. The manual CI profiles are `regression`, `qualification` and `dnspod`; only DNSPod requires explicit selection. Local case/tag filters remain available. Capacity and ownership remain held through teardown; seed changes execution priority. See [API execution contracts](../e2e/docs/architecture.md).

Browser planning uses explicit stable case identities and verified isolation boundaries. Every shard gets an independent owned application/world and one Playwright worker. Each estimate includes repeated wrapper setup and cleanup plus case execution; the wrapper and Playwright reports are audited together. See [browser execution](../frontend-react/docs/browser-tests.md).

Each test family permits up to 16 simultaneous shard jobs. Backend planning permits up to 32 shards; API and browser planning each permit up to 16. Shard counts and simultaneous runner counts are separate budgets. A larger matrix can execute in waves; preparation, candidate construction and account-wide availability still affect overall elapsed time. Job creation-to-start intervals include dependencies and matrix constraints and do not directly measure account quota exhaustion.

Standalone ordinary push/PR runs use component-specific concurrency groups and cancel superseded executions. Cloud qualification, manual runs and reusable qualification children use run identities so a later branch push cannot cancel cloud recovery or their caller. Release promotion remains serialized and non-cancelling. Candidate artifacts and qualification receipts are never reused across unrelated runs.

## Historical feedback

`scripts/ci/timing_history.py` restores a read-only historical artifact once during family planning. It selects the latest compatible successfully audited sample across trusted branches in the same repository, ordered by artifact creation time. Forks, expired artifacts and the current run are excluded, and the recorded source must match the artifact. The envelope identifies its family, execution profile, measurement/configuration fingerprint and source run, attempt, commit and branch. Compatibility covers fixture/resource/measurement configuration and pinned inputs, not the source SHA, so costs can inform later commits. Expired, malformed, incompatible or absent history uses explicit positive fallback estimates.

Planning freezes the restored snapshot and its identity before generating the current immutable plan. Every shard executes that plan; independent shards never each choose a different latest history. History affects costs and placement only. The current collected catalog and execution policy independently determine completeness and required scenarios.

API history retains api-lifecycle-v2 individual costs, reusable-group membership/floors and fixed cleanup/recovery overhead. Global matrix placement preserves that measurement and compatibility fingerprint, so matching prior audited costs remain reusable. Historical assignments and candidate receipts are never reused.

Each family publishes `timing-history-<family>` only after its complete successful coverage, outcomes, candidate/cleanup audit. History artifacts retain `history.json` for 90 days; raw failed reports remain diagnostic and cannot replace successful costs. New and changed inventories remain fully selected, with unseen identities receiving fallback estimates. Read-only Actions permissions allow cross-run retrieval without repository writes or automatic weight commits.

## Evidence

| Artifact | Evidence |
| --- | --- |
| `backend-test-inventory` | Full inventory and deterministic shard plan |
| `backend-test-shard-N` | Selection manifest, precise setup/call/teardown timings, JUnit and raw coverage |
| `backend-test-reports` | Audited shard evidence and centrally combined coverage reports |
| `frontend-test-results` | Vitest JSON with individual test outcomes and durations |
| `go-test-results` | Race-enabled Go test JSON events, including per-test and package elapsed times |
| `api-results-N` | API plan, provider dependencies, lifecycle timings, outcomes, candidate identity and redacted diagnostics; cloud-dependent shards retain DNS/Minecraft observations and verified non-secret recovery manifests |
| `browser-results-*` | Assigned Playwright identities, durations, outcomes, wrapper timings and owned application evidence |
| `timing-history-backend`, `timing-history-api`, `timing-history-browser` | Successfully audited reusable costs with execution compatibility and source identity |

The backend audit verifies the original inventory, selection policy, plan identity, exact-once membership and successful phase outcomes. A collection manifest alone is never sufficient. Failed runs retain available evidence but cannot qualify an image. The Go JSON pipeline uses Bash `pipefail`; writing a report cannot turn failed tests into a successful candidate build.

Coverage instrumentation remains enabled in every backend shard. Only raw data is produced there; the audit job combines it and generates XML/HTML once. GitHub artifact uploads explicitly include hidden coverage files. Tool downloads use Dockerfile pins, bounded transport retries and SHA-256 verification; business assertions are not retried into success.

Committed backend log intervals and embedded API costs are cold-start scheduling estimates. Precise phase reports distinguish execution from queueing and automatically inform later compatible plans. Skipped, failed-to-start, cancelled or incomplete execution cannot contribute zero or reduced successful costs. Browser wrapper initialization and cleanup are measured separately so repeated fixture costs are not omitted from shard estimates.

## Validation

Follow the repository's [delivery and test requirements](../AGENTS.md#交付与测试要求). Local execution is limited to tests for changed behavior and affected call paths, selected by explicit files, node IDs, packages or case filters. Never run the full project or a component's full test suite locally, including through accumulated directory, shard or subagent runs. Required lint, type checks and build checks remain in place. Documentation-only changes need no local tests.

Use the existing `Qualify and Publish Application` workflow's manual dispatch on the implementation branch with `publish=false`. It executes candidate, static, backend, integrated API and browser gates without changing registry tags. Confirm the source SHA, complete successful gates, all three exact-once audits and owned cleanup before comparing elapsed times. For E2E engine changes, also run the API workflow with reuse disabled to check isolation.

Bind the dispatched run ID to the latest pushed commit, then have the primary agent start a single persistent wait command:

```bash
gh run watch <run-id> --exit-status --interval 60 --compact > <log-path> 2>&1
```

Wait silently for this command to exit. Do not read its log or progress, send progress updates or continue other work during the wait. Neither the primary agent nor any subagent may repeatedly poll the same run or job through `gh run view`, `gh run list`, `gh api` or other GitHub interfaces. If the execution tool yields before completion, continue waiting for the same process. The CLI refreshes internally every 60 seconds; a user message may interrupt the wait, and a command interruption or connection failure is not a workflow conclusion. After the command finishes, read its log and inspect the final result once:

```bash
gh run view <run-id> --json headSha,status,conclusion,jobs,url
```

Require the exact latest commit and successful candidate, static, all backend shards and their audit, all API shards and their audit, all browser shards and their audit, and final qualification. On failure, inspect failed steps with `gh run view <run-id> --log-failed`, fix the cause, run only related local checks, commit and push, then repeat full qualification for the new commit. Old successful runs or incomplete gates do not qualify it.

## Cloud configuration and recovery

Every API shard uses the unrestricted `dns-e2e` Environment as a configuration store. It has no branch restrictions or protection rules; shard provider dependencies select configuration and recovery steps, and Huawei steps receive `HUAWEICLOUD_AK` and `HUAWEICLOUD_SK` when needed. These bindings apply to PR, automatic, manual and release runs. Missing required credentials, cancelled or missing execution, and residual managed records fail the API aggregate gate. Explicit DNSPod selection receives `E2E_EXTERNAL_CONFIG`.

Environment variables `HUAWEICLOUD_DNS_ZONE`, optional `HUAWEICLOUD_DNS_PARENT` and `HUAWEICLOUD_DNS_REGION` configure an existing public zone without committing account domains. The common environment ID supplies each run's relative name, followed by the optional parent. EXIT and unconditional recovery stop owned writers and reclaim managed cloud records using the domain and scope recorded in non-secret manifests and currently supplied credentials after success, failure or cancellation. Local Docker cleanup does not replace cloud verification. Explicit manual selection can disable reuse. See [DNS qualification and recovery](../e2e/suites/dns/README.md).
